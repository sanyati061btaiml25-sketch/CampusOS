"""
campusos/runner.py – run state machine.

Stages
------
plan     → load settings, check kill switch + kill file, pick due sources.
fetch    → gateway.fetch() per source; write snapshot row.
parse    → normalise payload into opportunity dicts.
upsert   → content-hash dedup; new / changed / unchanged.
match    → [stub – in progress].
done     → finalise run row, write coverage, clear heartbeat.

Write ownership
---------------
The runner is the ONLY writer of run data.  One connection per run.
"""

import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db import _REPO_ROOT, connect, init_db, now_iso
from .gateway import Budget, FetchResult, Gateway, _kill_switch_active

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def _audit(conn: sqlite3.Connection, run_id: int, seq: int, **kwargs) -> None:
    """Append one row to events (never raises)."""
    try:
        with conn:
            conn.execute(
                """INSERT INTO events (run_id, seq, type, stage, tool,
                       input_summary, result_summary, decision, reason, error,
                       cost_usd, tokens, opportunity_id)
                   VALUES (:run_id,:seq,:type,:stage,:tool,
                       :input_summary,:result_summary,:decision,:reason,:error,
                       :cost_usd,:tokens,:opportunity_id)""",
                {
                    "run_id": run_id, "seq": seq,
                    "type": kwargs.get("type", "tool_call"),
                    "stage": kwargs.get("stage"),
                    "tool": kwargs.get("tool"),
                    "input_summary": str(kwargs.get("input_summary", ""))[:500],
                    "result_summary": str(kwargs.get("result_summary", ""))[:500],
                    "decision": kwargs.get("decision"),
                    "reason": kwargs.get("reason"),
                    "error": str(kwargs.get("error", ""))[:500] if kwargs.get("error") else None,
                    "cost_usd": kwargs.get("cost_usd", 0.0),
                    "tokens": kwargs.get("tokens", 0),
                    "opportunity_id": kwargs.get("opportunity_id"),
                },
            )
    except Exception as exc:
        log.warning("audit write failed: %s", exc)


# ---------------------------------------------------------------------------
# Platform parsers
# ---------------------------------------------------------------------------

def _norm_text(s: str | None, maxlen: int = 300) -> str:
    return (s or "").strip()[:maxlen]


def _content_hash(d: dict) -> str:
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _parse_greenhouse(jobs: list[dict], source_name: str) -> list[dict]:
    out = []
    for job in jobs:
        job_id = str(job.get("id", ""))
        title = _norm_text(job.get("title", ""), 300)
        company = _norm_text(
            job.get("company", {}).get("name", "")
            if isinstance(job.get("company"), dict)
            else source_name.replace("greenhouse_", "").title(),
            200,
        )
        apply_url = job.get("absolute_url") or job.get("apply_url") or ""
        if not apply_url.startswith(("http://", "https://")):
            continue
        location_raw = _norm_text(
            (job.get("location") or {}).get("name", "")
            if isinstance(job.get("location"), dict)
            else str(job.get("location", "")),
            1000,
        )
        content = {"title": title, "company": company,
                   "apply_url": apply_url, "location_raw": location_raw,
                   "external_id": job_id}
        out.append({
            "external_id": job_id,
            "canonical_key": f"{source_name}:{job_id}",
            "title": title, "company": company,
            "apply_url": apply_url, "location_raw": location_raw,
            "content_hash": _content_hash(content),
        })
    return out


def _parse_lever(postings: list[dict], source_name: str) -> list[dict]:
    out = []
    for p in postings:
        pid = str(p.get("id", ""))
        title = _norm_text(p.get("text", ""), 300)
        company = source_name.replace("lever_", "").title()
        apply_url = p.get("applyUrl") or p.get("hostedUrl") or ""
        if not apply_url.startswith(("http://", "https://")):
            continue
        loc_raw = _norm_text(
            (p.get("categories") or {}).get("location", "")
            if isinstance(p.get("categories"), dict)
            else "",
            1000,
        )
        content = {"title": title, "company": company,
                   "apply_url": apply_url, "location_raw": loc_raw, "external_id": pid}
        out.append({
            "external_id": pid, "canonical_key": f"{source_name}:{pid}",
            "title": title, "company": company,
            "apply_url": apply_url, "location_raw": loc_raw,
            "content_hash": _content_hash(content),
        })
    return out


def _parse_himalayas(jobs: list[dict] | dict, source_name: str) -> list[dict]:
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])
    out = []
    for job in jobs:
        # Real Himalayas payload uses: id/guid, title, applyUrl/applicationLink, companyName, location
        jid = str(job.get("id") or job.get("guid") or job.get("slug", ""))
        title = _norm_text(job.get("title", ""), 300)
        company = _norm_text(
            job.get("companyName")
            or (job.get("company") or {}).get("name", "")
            if isinstance(job.get("company"), dict)
            else str(job.get("company", "")),
            200,
        )
        apply_url = (job.get("applyUrl") or job.get("applicationLink")
                     or job.get("url") or "")
        if not apply_url.startswith(("http://", "https://")):
            continue
        loc_raw = _norm_text(str(job.get("location", "") or ""), 1000)
        content = {"title": title, "company": company,
                   "apply_url": apply_url, "location_raw": loc_raw, "external_id": jid}
        out.append({
            "external_id": jid, "canonical_key": f"{source_name}:{jid}",
            "title": title, "company": company,
            "apply_url": apply_url, "location_raw": loc_raw,
            "content_hash": _content_hash(content),
        })
    return out


_PARSERS = {
    "greenhouse": _parse_greenhouse,
    "lever":      _parse_lever,
    "himalayas":  _parse_himalayas,
}


def _extract_jobs_list(payload: Any, platform: str) -> list[dict]:
    if platform == "greenhouse":
        return payload.get("jobs", []) if isinstance(payload, dict) else (payload or [])
    if platform == "lever":
        return payload if isinstance(payload, list) else []
    if platform == "himalayas":
        return payload.get("jobs", []) if isinstance(payload, dict) else []
    return []


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def _upsert_opportunity(
    conn: sqlite3.Connection,
    source_id: int,
    snapshot_id: int,
    opp: dict,
    run_id: int | None = None,
) -> tuple[str, int | None]:
    existing = conn.execute(
        "SELECT id, content_hash, removed_at, status FROM opportunities WHERE canonical_key=?",
        (opp["canonical_key"],),
    ).fetchone()
    ts = now_iso()
    status = opp.get("status", "pending")
    flags_json = json.dumps(opp.get("flags", []))

    if existing is None:
        cur = conn.execute(
            """INSERT INTO opportunities
                   (source_id, external_id, canonical_key, snapshot_id,
                    title, company, apply_url, location_raw, content_hash,
                    first_seen_at, last_seen_at, status, flags)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (source_id, opp["external_id"], opp["canonical_key"], snapshot_id,
             opp["title"], opp["company"], opp["apply_url"],
             opp.get("location_raw", ""), opp["content_hash"], ts, ts,
             status, flags_json),
        )
        return "new", cur.lastrowid

    opp_id = existing["id"]
    reappeared = existing["removed_at"] is not None
    if reappeared:
        old_removed = existing["removed_at"]
        conn.execute(
            """UPDATE opportunities
               SET removed_at=NULL, status=?, last_seen_at=?
               WHERE id=?""",
            (status, ts, opp_id),
        )
        conn.execute(
            """INSERT INTO opportunity_changes
                   (opportunity_id, run_id, field, old_value, new_value, changed_at)
               VALUES (?, ?, 'removed_at', ?, NULL, ?)""",
            (opp_id, run_id, old_removed, ts),
        )

    if existing["content_hash"] == opp["content_hash"]:
        conn.execute("UPDATE opportunities SET last_seen_at=? WHERE id=?", (ts, opp_id))
        return "changed" if reappeared else "unchanged", opp_id

    # Changed — write opportunity_changes row
    conn.execute(
        """UPDATE opportunities
           SET snapshot_id=?, title=?, company=?, apply_url=?,
               location_raw=?, content_hash=?, last_seen_at=?, last_changed_at=?,
               status=?, flags=?
           WHERE id=?""",
        (snapshot_id, opp["title"], opp["company"], opp["apply_url"],
         opp.get("location_raw", ""), opp["content_hash"], ts, ts,
         status, flags_json, opp_id),
    )
    conn.execute(
        """INSERT INTO opportunity_changes
               (opportunity_id, run_id, field, old_value, new_value, changed_at)
           VALUES (?, ?, 'content_hash', ?, ?, ?)""",
        (opp_id, run_id, existing["content_hash"], opp["content_hash"], ts),
    )
    return "changed", opp_id


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    run_id: int
    state: str
    stop_reason: str | None = None
    sources_checked: int = 0
    sources_skipped: int = 0
    sources_failed:  int = 0
    listings_found:  int = 0
    listings_new:    int = 0
    listings_changed: int = 0
    listings_unchanged: int = 0
    errors: list[str] = field(default_factory=list)


def _mark_stale_runs_failed(conn: sqlite3.Connection) -> None:
    """Mark any leftover 'running' rows from a previous crash as 'failed'."""
    ts = now_iso()
    with conn:
        conn.execute(
            """UPDATE runs
               SET state='failed', ended_at=?, stop_reason='crash',
                   stage='done'
               WHERE state='running'""",
            (ts,),
        )


def execute_run(
    db_path: str | Path | None = None,
    trigger: str = "scheduler",
    mode: str = "live",
    replay_run: int | None = None,
    replay_run_id: int | None = None,
) -> RunResult:
    """
    Execute the full pipeline and return a RunResult.

    Always creates a run row (even when kill_switch is already set).
    Wraps the body in try/except/finally — an unhandled crash sets state='failed'.
    """
    effective_replay_run = replay_run if replay_run is not None else replay_run_id

    if db_path is None:
        if mode == "mock" and "CAMPUSOS_DB" not in os.environ:
            db_path = "data/mock.db"

    conn = connect(db_path)
    init_db(conn)

    # Read settings
    kill_before = _kill_switch_active(conn)
    budget = Budget(
        max_requests=int(_setting(conn, "max_requests_per_run", "200")),
        max_seconds=float(_setting(conn, "max_seconds_per_run", "300")),
    )
    force_all = _setting(conn, "force_all_sources_due", "false").lower() == "true"

    # Always create the run row
    with conn:
        cur = conn.execute(
            "INSERT INTO runs (trigger, state, stage, mode, budget_json) VALUES (?,?,?,?,?)",
            (trigger, "running", "plan", mode,
             json.dumps({"max_requests": budget.max_requests,
                         "max_seconds": budget.max_seconds})),
        )
        run_id = cur.lastrowid
        conn.execute(
            "UPDATE daemon_status SET current_run_id=? WHERE id=1", (run_id,)
        )

    result = RunResult(run_id=run_id, state="running")
    seq = 0

    try:
        # Killed before we started
        if kill_before:
            _audit(conn, run_id, seq := seq + 1, type="kill_switch", stage="plan",
                   result_summary="kill_switch set before run start")
            result.stop_reason = "kill_switch"
            result.state = "stopped"
            return result

        _audit(conn, run_id, seq := seq + 1, type="run_start", stage="plan",
               input_summary=f"trigger={trigger} mode={mode}")

        # Pick due sources — fixed query: half_open breakers whose until has passed are included
        if force_all:
            due_sources = conn.execute(
                """SELECT * FROM sources
                   WHERE enabled=1
                     AND (breaker_state != 'open'
                          OR (breaker_until IS NOT NULL
                              AND breaker_until <= strftime('%Y-%m-%dT%H:%M:%fZ','now')))"""
            ).fetchall()
        else:
            due_sources = conn.execute(
                """SELECT * FROM sources
                   WHERE enabled=1
                     AND (breaker_state != 'open'
                          OR (breaker_until IS NOT NULL
                              AND breaker_until <= strftime('%Y-%m-%dT%H:%M:%fZ','now')))
                     AND (last_ok_at IS NULL
                          OR (strftime('%s','now') - strftime('%s', last_ok_at)) >= interval_s)"""
            ).fetchall()

        log.info("[run %d] plan: %d sources due", run_id, len(due_sources))
        _audit(conn, run_id, seq := seq + 1, type="stage_end", stage="plan",
               result_summary=f"{len(due_sources)} sources due")

        with conn:
            conn.execute("UPDATE runs SET stage='fetch' WHERE id=?", (run_id,))

        # Build gateway with shared budget
        gw = Gateway(conn, mode=mode, budget=budget, run_id=run_id, replay_run=effective_replay_run)

        for source in due_sources:
            sname = source["name"]
            platform = source["platform"]

            # Update daemon heartbeat before fetching each source
            try:
                with conn:
                    conn.execute(
                        "UPDATE daemon_status SET heartbeat_at=? WHERE id=1",
                        (now_iso(),),
                    )
            except Exception as exc:
                log.warning("heartbeat update failed: %s", exc)

            # Pre-source kill/budget check
            if _kill_switch_active(conn):
                result.stop_reason = "kill_switch"
                _audit(conn, run_id, seq := seq + 1, type="kill_switch",
                       stage="fetch", result_summary=f"stopped before {sname}")
                break
            if budget.stop_reason:
                result.stop_reason = budget.stop_reason
                _audit(conn, run_id, seq := seq + 1, type="budget_exceeded",
                       stage="fetch", reason=budget.stop_reason)
                break

            log.info("[run %d] fetch %s", run_id, sname)
            _audit(conn, run_id, seq := seq + 1, stage="fetch", tool="http_fetch",
                   input_summary=f"{sname} {source['base_url']}")

            fetch_result: FetchResult = gw.fetch(dict(source))
            result.sources_checked += 1

            if fetch_result.status in ("kill_switch", "budget_exceeded"):
                if fetch_result.status == "kill_switch":
                    result.stop_reason = "kill_switch"
                else:
                    result.stop_reason = fetch_result.error_detail or "budget_requests"
                _audit(conn, run_id, seq := seq + 1, type=fetch_result.status,
                       stage="fetch", reason=result.stop_reason)
                break

            # Write snapshot (including raw_ref)
            with conn:
                snap_cur = conn.execute(
                    """INSERT INTO snapshots
                           (source_id, run_id, content_hash, status, http_status,
                            duration_ms, item_count, raw_ref, error_detail)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (source["id"], run_id, fetch_result.content_hash,
                     fetch_result.status, fetch_result.http_status,
                     fetch_result.duration_ms, fetch_result.item_count,
                     fetch_result.raw_ref, fetch_result.error_detail),
                )
                snap_id = snap_cur.lastrowid

            if fetch_result.status not in ("ok",):
                if fetch_result.status == "circuit_open":
                    result.sources_skipped += 1
                else:
                    result.sources_failed += 1
                    result.errors.append(
                        f"{sname}: {fetch_result.status} – {fetch_result.error_detail}")
                _audit(conn, run_id, seq := seq + 1, stage="fetch", tool="http_fetch",
                       result_summary=f"{sname} {fetch_result.status}",
                       error=fetch_result.error_detail)
                continue

            _audit(conn, run_id, seq := seq + 1, stage="fetch", tool="http_fetch",
                   result_summary=(
                       f"{sname} ok items={fetch_result.item_count} "
                       f"hash={fetch_result.content_hash[:8] if fetch_result.content_hash else '?'}"
                   ))

            # --- PARSE ---
            raw_list = _extract_jobs_list(fetch_result.data, platform)
            parser = _PARSERS.get(platform)
            if parser is None:
                log.warning("[run %d] no parser for platform '%s'", run_id, platform)
                continue
            parsed = parser(raw_list, sname)
            result.listings_found += len(parsed)
            _audit(conn, run_id, seq := seq + 1, stage="parse",
                   result_summary=f"{sname} parsed {len(parsed)}")

            # --- DOMAIN CHECK (A7) ---
            allowlist = json.loads(source["domain_allowlist"] or "[]")
            for opp in parsed:
                flags = []
                status = "pending"
                if not Gateway.check_apply_domain(opp["apply_url"], allowlist):
                    flags.append("domain_mismatch")
                    status = "needs_review"
                opp["flags"] = flags
                opp["status"] = status

            # --- UPSERT (one transaction per source) ---
            new_c = changed_c = unchanged_c = 0
            with conn:
                for opp in parsed:
                    outcome, _ = _upsert_opportunity(conn, source["id"], snap_id, opp, run_id=run_id)
                    if outcome == "new":
                        new_c += 1
                    elif outcome == "changed":
                        changed_c += 1
                    else:
                        unchanged_c += 1

                # Expired / removed listings detection (A7)
                if len(parsed) > 0:
                    ts = now_iso()
                    seen_keys = {opp["canonical_key"] for opp in parsed}
                    active_opps = conn.execute(
                        "SELECT id, canonical_key FROM opportunities WHERE source_id=? AND removed_at IS NULL",
                        (source["id"],),
                    ).fetchall()
                    for old_opp in active_opps:
                        if old_opp["canonical_key"] not in seen_keys:
                            conn.execute(
                                """UPDATE opportunities
                                   SET removed_at=?, status='expired', last_changed_at=?
                                   WHERE id=?""",
                                (ts, ts, old_opp["id"]),
                            )
                            conn.execute(
                                """INSERT INTO opportunity_changes
                                       (opportunity_id, run_id, field, old_value, new_value, changed_at)
                                   VALUES (?, ?, 'removed_at', NULL, ?, ?)""",
                                (old_opp["id"], run_id, ts, ts),
                            )

            result.listings_new += new_c
            result.listings_changed += changed_c
            result.listings_unchanged += unchanged_c
            _audit(conn, run_id, seq := seq + 1, stage="upsert",
                   result_summary=f"{sname} new={new_c} changed={changed_c} unchanged={unchanged_c}")
            log.info("[run %d] %s → new=%d changed=%d unchanged=%d",
                     run_id, sname, new_c, changed_c, unchanged_c)

        # --- MATCH (stub) ---
        with conn:
            conn.execute("UPDATE runs SET stage='match' WHERE id=?", (run_id,))
        _audit(conn, run_id, seq := seq + 1, stage="match",
               result_summary="match stage stub – not yet implemented")

        final_state = "stopped" if result.stop_reason else "done"
        result.state = final_state

    except Exception as exc:
        log.exception("[run %d] unhandled exception", run_id)
        result.state = "failed"
        result.stop_reason = "crash"
        _audit(conn, run_id, seq := seq + 1, type="error", stage="done",
               error=str(exc)[:500])

    finally:
        ts = now_iso()
        try:
            with conn:
                conn.execute(
                    """UPDATE runs
                       SET state=?, stage='done', ended_at=?, stop_reason=?,
                           used_requests=?
                       WHERE id=?""",
                    (result.state, ts, result.stop_reason,
                     budget.used_requests, run_id),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO coverage
                           (run_id, sources_checked, sources_skipped, sources_failed,
                            listings_found, listings_unchanged, after_dedup)
                       VALUES (?,?,?,?,?,?,?)""",
                    (run_id, result.sources_checked, result.sources_skipped,
                     result.sources_failed, result.listings_found,
                     result.listings_unchanged,
                     result.listings_new + result.listings_changed),
                )
                conn.execute(
                    "UPDATE daemon_status SET current_run_id=NULL WHERE id=1"
                )
                # Clear run_requested flag if this was a manual trigger
                if trigger == "manual":
                    conn.execute(
                        "UPDATE settings SET value='false' WHERE key='run_requested'"
                    )
        except Exception as fin_exc:
            log.error("[run %d] finalise failed: %s", run_id, fin_exc)

        _audit(conn, run_id, seq := seq + 1, type="run_end", stage="done",
               result_summary=(
                   f"state={result.state} sources={result.sources_checked} "
                   f"new={result.listings_new} changed={result.listings_changed}"
               ),
               reason=result.stop_reason)
        conn.close()

    log.info("[run %d] finished state=%s", run_id, result.state)
    return result
