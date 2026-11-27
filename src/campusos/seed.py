"""Idempotent seed script for CampusOS matching the frozen SQLite schema.

Populates realistic demo rows across ``runs``, ``snapshots``,
``opportunities``, ``evidence``, ``matches``, ``review_queue``, ``actions``,
``events``, ``coverage``, and ``coverage_profile`` so the dashboard has
complete data to display immediately.

Usage::

    python -m campusos.seed
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from campusos.db import connect, init_db


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def seed_demo_data(conn: sqlite3.Connection) -> dict[str, int]:
    """Insert deterministic, idempotent demo rows into an initialized DB.

    Returns a summary dict with the ``run_id`` and row counts inserted or
    already present.
    """
    init_db(conn)

    # Check if demo seed run already exists (idempotency guard).
    existing_run = conn.execute(
        "SELECT id FROM runs WHERE stop_reason = 'seed_demo' LIMIT 1"
    ).fetchone()
    if existing_run is not None:
        run_id = int(existing_run["id"])
        opp_count = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        match_count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {
            "run_id": run_id,
            "opportunities": int(opp_count),
            "matches": int(match_count),
            "events": int(event_count),
        }

    with conn:
        # 1. Seed run
        cur = conn.execute(
            """
            INSERT INTO runs (
                trigger, state, stage, mode, ended_at, stop_reason,
                budget_json, used_requests, used_tokens, used_usd
            )
            VALUES (
                'manual', 'done', 'report', 'mock',
                strftime('%Y-%m-%dT%H:%M:%fZ','now'), 'seed_demo',
                '{"max_requests":200,"max_tokens":50000,"max_usd":0.5}',
                8, 2450, 0.012
            )
            """
        )
        run_id = int(cur.lastrowid)

        # Look up seeded sources and profiles from schema.sql
        stripe_src = conn.execute(
            "SELECT id FROM sources WHERE name = 'greenhouse_stripe'"
        ).fetchone()
        groww_src = conn.execute(
            "SELECT id FROM sources WHERE name = 'greenhouse_groww'"
        ).fetchone()
        meesho_src = conn.execute(
            "SELECT id FROM sources WHERE name = 'lever_meesho'"
        ).fetchone()
        himalayas_src = conn.execute(
            "SELECT id FROM sources WHERE name = 'himalayas'"
        ).fetchone()

        stripe_id = int(stripe_src["id"])
        groww_id = int(groww_src["id"])
        meesho_id = int(meesho_src["id"])
        himalayas_id = int(himalayas_src["id"])

        prof_tech = conn.execute(
            "SELECT id, updated_at FROM profile WHERE label = 'profile_a_tech'"
        ).fetchone()
        prof_fin = conn.execute(
            "SELECT id, updated_at FROM profile WHERE label = 'profile_b_finance'"
        ).fetchone()

        tech_pid = int(prof_tech["id"])
        tech_ver = str(prof_tech["updated_at"])
        fin_pid = int(prof_fin["id"])
        fin_ver = str(prof_fin["updated_at"])

        # 2. Snapshots
        snap_ids: dict[int, int] = {}
        for sid, count in [(stripe_id, 2), (groww_id, 1), (meesho_id, 1), (himalayas_id, 1)]:
            s_cur = conn.execute(
                """
                INSERT INTO snapshots (source_id, run_id, content_hash, status, http_status, duration_ms, item_count)
                VALUES (?, ?, ?, 'ok', 200, 320, ?)
                """,
                (sid, run_id, _hash_text(f"snap-{sid}-{run_id}"), count),
            )
            snap_ids[sid] = int(s_cur.lastrowid)

        # 3. Opportunities (including verified matches + 1 trap/review case)
        opps_spec = [
            {
                "source_id": stripe_id,
                "external_id": "stripe-swe-intern-2027",
                "canonical_key": "greenhouse_stripe:stripe-swe-intern-2027",
                "group_key": "stripe:software engineer intern",
                "title": "Software Engineer Intern (Backend & Payments)",
                "company": "Stripe",
                "apply_url": "https://stripe.com/jobs/listing/swe-intern-2027",
                "location_raw": "Bengaluru, India (Hybrid)",
                "location_norm": '["Bengaluru"]',
                "countries_json": '["IN"]',
                "remote_ok": 0,
                "remote_scope": "none",
                "seniority": "intern",
                "employment_type": "internship",
                "min_education": "bachelor",
                "grad_year_min": 2027,
                "grad_year_max": 2028,
                "min_experience_yrs": 0.0,
                "skills_json": '["Python","SQL","Git","Distributed Systems"]',
                "work_auth_statement": "Open to students authorized to work in India",
                "deadline": "2026-12-05",
                "deadline_kind": "fixed",
                "deadline_evidence": "Applications close Dec 5, 2026 at 11:59 PM IST.",
                "status": "verified",
                "confidence": 0.96,
                "flags": "[]",
            },
            {
                "source_id": groww_id,
                "external_id": "groww-ml-intern-2027",
                "canonical_key": "greenhouse_groww:groww-ml-intern-2027",
                "group_key": "groww:machine learning intern",
                "title": "Machine Learning & Data Intern",
                "company": "Groww",
                "apply_url": "https://groww.in/careers/ml-intern-2027",
                "location_raw": "Bengaluru, India",
                "location_norm": '["Bengaluru"]',
                "countries_json": '["IN"]',
                "remote_ok": 0,
                "remote_scope": "none",
                "seniority": "intern",
                "employment_type": "internship",
                "min_education": "bachelor",
                "grad_year_min": 2027,
                "grad_year_max": 2028,
                "min_experience_yrs": 0.0,
                "skills_json": '["Python","SQL","basic ML"]',
                "work_auth_statement": "India work authorization required",
                "deadline": "2026-12-10",
                "deadline_kind": "fixed",
                "deadline_evidence": "Submit applications by 2026-12-10.",
                "status": "verified",
                "confidence": 0.92,
                "flags": "[]",
            },
            {
                "source_id": meesho_id,
                "external_id": "meesho-fin-ops-intern",
                "canonical_key": "lever_meesho:meesho-fin-ops-intern",
                "group_key": "meesho:finance operations intern",
                "title": "Finance & Business Operations Intern",
                "company": "Meesho",
                "apply_url": "https://meesho.com/careers/finance-ops-intern",
                "location_raw": "Bengaluru / Remote India",
                "location_norm": '["Bengaluru","Remote"]',
                "countries_json": '["IN"]',
                "remote_ok": 1,
                "remote_scope": "region_limited",
                "seniority": "intern",
                "employment_type": "internship",
                "min_education": "bachelor",
                "grad_year_min": 2027,
                "grad_year_max": 2027,
                "min_experience_yrs": 0.0,
                "skills_json": '["Excel","financial analysis"]',
                "work_auth_statement": "India",
                "deadline": "2026-12-12",
                "deadline_kind": "fixed",
                "deadline_evidence": "Rolling review until Dec 12, 2026.",
                "status": "verified",
                "confidence": 0.89,
                "flags": "[]",
            },
            {
                "source_id": himalayas_id,
                "external_id": "trap-fastcash-dev-intern",
                "canonical_key": "himalayas:trap-fastcash-dev-intern",
                "group_key": "fastcash:paid training software intern",
                "title": "Software Intern — Pay Rs 999 Training Deposit",
                "company": "FastCash Labs",
                "apply_url": "https://fastcash-apply.example.org/deposit-form",
                "location_raw": "Remote",
                "location_norm": '["Remote"]',
                "countries_json": '["IN"]',
                "remote_ok": 1,
                "remote_scope": "worldwide",
                "seniority": "intern",
                "employment_type": "internship",
                "min_education": "bachelor",
                "grad_year_min": None,
                "grad_year_max": None,
                "min_experience_yrs": 0.0,
                "skills_json": '["Python"]',
                "work_auth_statement": "unknown",
                "deadline": None,
                "deadline_kind": "unknown",
                "deadline_evidence": None,
                "status": "needs_review",
                "confidence": 0.25,
                "flags": '["possible_scam","domain_mismatch"]',
            },
        ]

        opp_ids: dict[str, int] = {}
        for spec in opps_spec:
            c_hash = _hash_text(f"{spec['canonical_key']}:{spec['title']}:{spec['apply_url']}")
            conn.execute(
                """
                INSERT OR IGNORE INTO opportunities (
                    source_id, external_id, canonical_key, group_key, snapshot_id,
                    title, company, apply_url, location_raw, location_norm,
                    countries_json, remote_ok, remote_scope, seniority, employment_type,
                    min_education, grad_year_min, grad_year_max, min_experience_yrs,
                    skills_json, work_auth_statement, deadline, deadline_kind,
                    deadline_evidence, status, confidence, flags, content_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spec["source_id"],
                    spec["external_id"],
                    spec["canonical_key"],
                    spec["group_key"],
                    snap_ids[spec["source_id"]],
                    spec["title"],
                    spec["company"],
                    spec["apply_url"],
                    spec["location_raw"],
                    spec["location_norm"],
                    spec["countries_json"],
                    spec["remote_ok"],
                    spec["remote_scope"],
                    spec["seniority"],
                    spec["employment_type"],
                    spec["min_education"],
                    spec["grad_year_min"],
                    spec["grad_year_max"],
                    spec["min_experience_yrs"],
                    spec["skills_json"],
                    spec["work_auth_statement"],
                    spec["deadline"],
                    spec["deadline_kind"],
                    spec["deadline_evidence"],
                    spec["status"],
                    spec["confidence"],
                    spec["flags"],
                    c_hash,
                ),
            )
            row = conn.execute(
                "SELECT id FROM opportunities WHERE canonical_key = ?",
                (spec["canonical_key"],),
            ).fetchone()
            opp_ids[spec["canonical_key"]] = int(row["id"])

        stripe_opp = opp_ids["greenhouse_stripe:stripe-swe-intern-2027"]
        groww_opp = opp_ids["greenhouse_groww:groww-ml-intern-2027"]
        meesho_opp = opp_ids["lever_meesho:meesho-fin-ops-intern"]
        trap_opp = opp_ids["himalayas:trap-fastcash-dev-intern"]

        # 4. Evidence rows
        evidence_rows = [
            (
                stripe_opp,
                "deadline_verbatim",
                "Applications close Dec 5, 2026 at 11:59 PM IST.",
                "https://stripe.com/jobs/listing/swe-intern-2027",
            ),
            (
                stripe_opp,
                "domain_check",
                "Apply host stripe.com matches greenhouse_stripe allowlist.",
                "https://stripe.com/jobs/listing/swe-intern-2027",
            ),
            (
                groww_opp,
                "domain_check",
                "Apply host groww.in matches greenhouse_groww allowlist.",
                "https://groww.in/careers/ml-intern-2027",
            ),
            (
                trap_opp,
                "scam_flag",
                "Detected upfront fee phrase ('Pay Rs 999 Training Deposit') and unverified apply domain.",
                "https://fastcash-apply.example.org/deposit-form",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO evidence (opportunity_id, kind, snippet, source_url)
            VALUES (?, ?, ?, ?)
            """,
            evidence_rows,
        )

        # 5. Matches (for profile_a_tech and profile_b_finance)
        matches_rows = [
            (
                stripe_opp,
                tech_pid,
                run_id,
                _hash_text("greenhouse_stripe:stripe-swe-intern-2027"),
                tech_ver,
                "pass",
                '["Enrolled bachelor CS 2028 matches 2027-2028 window","India work auth satisfied"]',
                0.94,
                '{"skills":0.95,"location":1.0,"seniority":1.0}',
                '["Matched Python, SQL, Git"]',
                "notify",
                "High-fit verified match above 0.4 threshold",
                1,
            ),
            (
                groww_opp,
                tech_pid,
                run_id,
                _hash_text("greenhouse_groww:groww-ml-intern-2027"),
                tech_ver,
                "pass",
                '["CS 2028 eligible","Skills Python, SQL, basic ML matched"]',
                0.91,
                '{"skills":0.92,"location":1.0,"seniority":1.0}',
                '["Matched Python, SQL, basic ML"]',
                "notify",
                "High-fit verified match above 0.4 threshold",
                2,
            ),
            (
                meesho_opp,
                fin_pid,
                run_id,
                _hash_text("lever_meesho:meesho-fin-ops-intern"),
                fin_ver,
                "pass",
                '["Commerce 2027 eligible","Excel and financial analysis matched"]',
                0.88,
                '{"skills":0.90,"location":1.0,"seniority":1.0}',
                '["Matched Excel, financial analysis"]',
                "notify",
                "High-fit finance match",
                1,
            ),
            (
                trap_opp,
                tech_pid,
                run_id,
                _hash_text("himalayas:trap-fastcash-dev-intern"),
                tech_ver,
                "unknown",
                '["Flagged as possible_scam and domain_mismatch"]',
                0.15,
                '{"skills":0.4,"location":0.5,"trust":0.0}',
                '["Quarantined pending manual review"]',
                "queue",
                "Held in review queue due to scam/domain flags",
                None,
            ),
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO matches (
                opportunity_id, profile_id, last_run_id, evaluated_hash,
                evaluated_profile_version, eligibility, eligibility_reasons,
                score, score_breakdown, score_reasons, decision, decision_reason,
                ranked_position
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            matches_rows,
        )

        # 6. Review queue (quarantined trap listing)
        conn.execute(
            """
            INSERT OR IGNORE INTO review_queue (opportunity_id, run_id, reason, detail)
            VALUES (?, ?, 'possible_scam', ?)
            """,
            (
                trap_opp,
                run_id,
                "Requests Rs 999 training deposit and links outside allowlisted domain.",
            ),
        )

        # 7. Actions (digest + .ics)
        conn.execute(
            """
            INSERT OR IGNORE INTO actions (run_id, type, target, payload_ref, status)
            VALUES (?, 'digest', 'sandbox://student-digest', 'data/digest_seed.md', 'sent')
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO actions (run_id, type, target, payload_ref, status, opportunity_id, profile_id)
            VALUES (?, 'ics', 'data/stripe_swe_intern.ics', 'ics:stripe-swe-intern-2027', 'sent', ?, ?)
            """,
            (run_id, stripe_opp, tech_pid),
        )

        # 8. Events (audit trail)
        events_rows = [
            (run_id, 1, "run_start", "trigger", None, "manual seed run", "started", None, None),
            (run_id, 2, "stage_end", "fetch", "http_fetch", "4 sources", "fetched 5 listings", None, None),
            (run_id, 3, "decision", "verify", None, "fastcash trap", "quarantined possible_scam", "queue", "possible_scam"),
            (run_id, 4, "action", "act", "send_digest", "3 verified matches", "digest delivered", "notify", None),
            (run_id, 5, "run_end", "report", None, "seed_demo", "completed", None, None),
        ]
        conn.executemany(
            """
            INSERT OR IGNORE INTO events (
                run_id, seq, type, stage, tool, input_summary, result_summary, decision, reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            events_rows,
        )

        # 9. Coverage & per-profile coverage
        conn.execute(
            """
            INSERT OR IGNORE INTO coverage (
                run_id, sources_checked, sources_skipped, sources_failed,
                listings_found, listings_unchanged, after_dedup,
                by_region_json, not_covered_note
            )
            VALUES (?, 4, 0, 0, 4, 0, 4, '{"IN":3,"REMOTE":1}', 'Seeded demo coverage')
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO coverage_profile (
                run_id, profile_id, after_seniority, after_eligibility, notify_count, review_count
            )
            VALUES (?, ?, 3, 2, 2, 1)
            """,
            (run_id, tech_pid),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO coverage_profile (
                run_id, profile_id, after_seniority, after_eligibility, notify_count, review_count
            )
            VALUES (?, ?, 1, 1, 1, 0)
            """,
            (run_id, fin_pid),
        )

    return {
        "run_id": run_id,
        "opportunities": 4,
        "matches": 4,
        "events": 5,
    }


def main() -> None:
    conn = connect()
    try:
        summary = seed_demo_data(conn)
        print(json.dumps({"status": "seeded", **summary}))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
