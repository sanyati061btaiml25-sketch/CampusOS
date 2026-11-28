"""
campusos/gateway.py – HTTP fetch gateway with circuit breaker.

Rules
-----
* Only hosts listed in sources.fetch_hosts may be called.
* The circuit breaker lives in the sources table and is written via the
  connection supplied to __init__.
* In replay mode, raw payloads are read from data/raw/run_<id>/<source>.json
  and the network is never touched.
* In mock mode, deterministic in-process payloads are returned.
* Gateway writes raw payloads to data/raw/run_<id>/<source>.json and
  returns the path in FetchResult.raw_ref for snapshots.raw_ref.
* Kill switch (DB + file) is checked before every live/replay request.
* Every request increments a shared Budget object; the caller stops the
  loop when a cap is hit.

Circuit-breaker states
----------------------
closed    → normal; failures increment breaker_failures.
open      → all fetches rejected until breaker_until; then half_open.
half_open → one probe allowed; success → closed, failure → open again.
"""

import datetime as dt
import hashlib
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db import _REPO_ROOT, now_iso, resolve_path

log = logging.getLogger(__name__)

_UA = "CampusOS/0.1 (+https://github.com/nisabmohd/CampusOS; research bot)"
_FETCH_TIMEOUT = 20   # per-request timeout in seconds (overrides source.timeout_s for safety)


# ---------------------------------------------------------------------------
# Budget tracker (shared across all gateway.fetch() calls in one run)
# ---------------------------------------------------------------------------

@dataclass
class Budget:
    max_requests: int   = 200
    max_seconds:  float = 300.0
    used_requests: int  = 0
    run_start: float    = field(default_factory=time.monotonic)

    def request_ok(self) -> bool:
        return self.used_requests < self.max_requests

    def time_ok(self) -> bool:
        return (time.monotonic() - self.run_start) < self.max_seconds

    def tick(self) -> None:
        self.used_requests += 1

    @property
    def stop_reason(self) -> str | None:
        if not self.request_ok():
            return "budget_requests"
        if not self.time_ok():
            return "budget_time"
        return None


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    status: str           # ok|unchanged|error|timeout|circuit_open|rate_limited|blocked|budget_exceeded|kill_switch
    http_status: int | None = None
    duration_ms: int | None = None
    content_hash: str | None = None
    item_count: int | None = None
    data: Any = None
    raw_ref: str | None = None     # path written to data/raw/
    error_detail: str | None = None


# ---------------------------------------------------------------------------
# Kill-switch helpers (gateway is the single choke point)
# ---------------------------------------------------------------------------

def _kill_switch_active(conn, kill_file: str | None = None) -> bool:
    """Return True if the DB kill_switch is set or the kill file exists."""
    import os
    kf = kill_file or os.environ.get("KILL_FILE", "data/KILL")
    p = resolve_path(kf)
    if p.exists():
        return True
    try:
        row = conn.execute("SELECT value FROM settings WHERE key='kill_switch'").fetchone()
        return bool(row and row[0].lower() == "true")
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

class Gateway:
    """Fetch jobs from a source URL.

    Parameters
    ----------
    conn:
        Open campusos.db connection.  Used for breaker state and kill-switch.
    mode:
        'live' | 'mock' | 'replay'.
    budget:
        Shared Budget instance; if omitted a default one is created.
    run_id:
        Current run id, used to build data/raw/run_<id>/<source>.json paths.
    raw_root:
        Root directory for raw payload storage (default: data/raw).
    """

    def __init__(
        self,
        conn,
        mode: str = "live",
        budget: Budget | None = None,
        run_id: int | None = None,
        raw_root: str | Path | None = None,
        replay_run: int | None = None,
        replay_run_id: int | None = None,
    ):
        self._conn = conn
        self._mode = mode
        self._budget = budget or Budget()
        self._run_id = run_id
        self._raw_root = resolve_path(raw_root or "data/raw")
        self._replay_run = replay_run if replay_run is not None else replay_run_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self, source: dict) -> FetchResult:
        """Fetch *source* and return a FetchResult.

        Checks the kill switch and budget before every live/replay call.
        """
        # Pre-fetch kill + budget checks (not for mock — it never stalls)
        if self._mode != "mock":
            if _kill_switch_active(self._conn):
                return FetchResult(status="kill_switch",
                                   error_detail="kill switch set before fetch")
            reason = self._budget.stop_reason
            if reason:
                return FetchResult(status="budget_exceeded",
                                   error_detail=reason)

        # Circuit breaker check
        breaker_result = self._check_breaker(source)
        if breaker_result is not None:
            return breaker_result

        if self._mode == "mock":
            res = self._mock_fetch(source)
            self._record_success(source)
            return res

        if self._mode == "replay":
            res = self._replay_fetch(source)
            if res.status == "ok":
                self._record_success(source)
            return res

        # --- live ---
        url = self._build_url(source)
        allowed_hosts = json.loads(source["fetch_hosts"])
        parsed_host = urllib.parse.urlparse(url).hostname
        if parsed_host not in allowed_hosts:
            return FetchResult(
                status="blocked",
                error_detail=f"host '{parsed_host}' not in fetch_hosts {allowed_hosts}",
            )

        retry_max = int(source["retry_max"])
        delay = float(source["robots_delay_s"])
        timeout = min(int(source["timeout_s"]), _FETCH_TIMEOUT)

        last_result: FetchResult | None = None
        for attempt in range(retry_max + 1):
            if attempt > 0:
                time.sleep(delay)

            # Re-check kill switch between retries
            if _kill_switch_active(self._conn):
                return FetchResult(status="kill_switch",
                                   error_detail="kill switch set during retry")

            self._budget.tick()
            last_result = self._do_fetch(url, timeout)

            if last_result.status in ("ok", "unchanged"):
                self._record_success(source)
                self._save_raw(source, last_result)
                return last_result
            if last_result.status in ("blocked", "circuit_open", "kill_switch"):
                return last_result
            # Don't retry 4xx (except 429 which is already rate_limited)
            if last_result.http_status and 400 <= last_result.http_status < 500:
                break
            # transient error – retry

        assert last_result is not None
        self._record_failure(source)
        return last_result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_url(source: dict) -> str:
        base = source["base_url"]
        params = json.loads(source["fetch_params"] or "{}")
        if params:
            base = base + ("&" if "?" in base else "?") + urllib.parse.urlencode(params)
        return base

    def _do_fetch(self, url: str, timeout: int) -> FetchResult:
        t0 = time.monotonic()
        req = urllib.request.Request(
            url,
            headers={"User-Agent": _UA, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                duration_ms = int((time.monotonic() - t0) * 1000)
                raw = resp.read()
                http_status = resp.status
        except urllib.error.HTTPError as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            if exc.code == 429:
                return FetchResult(status="rate_limited", http_status=exc.code,
                                   duration_ms=duration_ms, error_detail=str(exc))
            return FetchResult(status="error", http_status=exc.code,
                               duration_ms=duration_ms, error_detail=str(exc))
        except TimeoutError:
            return FetchResult(status="timeout",
                               duration_ms=int((time.monotonic() - t0) * 1000),
                               error_detail="request timed out")
        except OSError as exc:
            return FetchResult(status="error",
                               duration_ms=int((time.monotonic() - t0) * 1000),
                               error_detail=str(exc))

        content_hash = hashlib.sha256(raw).hexdigest()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return FetchResult(status="error", http_status=http_status,
                               duration_ms=duration_ms, error_detail=f"JSON parse: {exc}")

        items = self._count_items(payload)
        return FetchResult(
            status="ok",
            http_status=http_status,
            duration_ms=duration_ms,
            content_hash=content_hash,
            item_count=len(items),
            data=payload,
        )

    @staticmethod
    def _count_items(payload: Any) -> list:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return next((v for v in payload.values() if isinstance(v, list)), [])
        return []

    def _save_raw(self, source: dict, result: FetchResult) -> None:
        """Write raw payload to data/raw/run_<id>/<source_name>.json."""
        if result.data is None or self._run_id is None:
            return
        try:
            dest = self._raw_root / f"run_{self._run_id}"
            dest.mkdir(parents=True, exist_ok=True)
            path = dest / f"{source['name']}.json"
            path.write_text(json.dumps(result.data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            result.raw_ref = str(path)
        except OSError as exc:
            log.warning("could not save raw payload: %s", exc)

    def _replay_fetch(self, source: dict) -> FetchResult:
        """Read cached raw file from data/raw/run_<replay_run>/<source>.json. Never touches the network."""
        if self._replay_run is None:
            return FetchResult(status="error",
                               error_detail="replay mode requires replay_run id")
        path = self._raw_root / f"run_{self._replay_run}" / f"{source['name']}.json"
        if not path.exists():
            return FetchResult(status="error",
                               error_detail=f"replay file not found: {path}")
        raw = path.read_bytes()
        content_hash = hashlib.sha256(raw).hexdigest()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return FetchResult(status="error", error_detail=f"replay JSON parse: {exc}")
        items = self._count_items(payload)
        return FetchResult(
            status="ok",
            http_status=200,
            duration_ms=0,
            content_hash=content_hash,
            item_count=len(items),
            data=payload,
            raw_ref=str(path),
        )

    def _mock_fetch(self, source: dict) -> FetchResult:
        """Return a deterministic offline payload (no I/O, no network)."""
        platform = source.get("platform", "greenhouse")
        slug = source.get("slug") or source.get("name", "mock")
        if platform == "greenhouse":
            payload: Any = {
                "jobs": [{
                    "id": 9001,
                    "title": "Software Engineer Intern",
                    "absolute_url": f"https://boards.greenhouse.io/{slug}/jobs/9001",
                    "location": {"name": "Remote"},
                }]
            }
            count = 1
        elif platform == "lever":
            payload = [{
                "id": "mock-1",
                "text": "Data Analyst Intern",
                "hostedUrl": f"https://jobs.lever.co/{slug}/mock-1",
                "categories": {"location": "Bengaluru, India"},
            }]
            count = 1
        elif platform == "himalayas":
            payload = {
                "jobs": [{
                    "id": "him-1",
                    "title": "Product Intern",
                    "applyUrl": "https://himalayas.app/jobs/him-1/apply",
                    "companyName": "Acme Corp",
                    "location": "Remote",
                }]
            }
            count = 1
        else:
            payload = {"jobs": []}
            count = 0
        raw = json.dumps(payload, sort_keys=True).encode()
        return FetchResult(
            status="ok",
            http_status=200,
            duration_ms=1,
            content_hash=hashlib.sha256(raw).hexdigest(),
            item_count=count,
            data=payload,
        )

    # ------------------------------------------------------------------
    # Circuit-breaker state management
    # ------------------------------------------------------------------

    def _check_breaker(self, source: dict) -> FetchResult | None:
        state = source["breaker_state"]
        if state == "closed":
            return None
        if state == "open":
            until = source["breaker_until"]
            if until:
                until_dt = dt.datetime.fromisoformat(until.rstrip("Z")).replace(
                    tzinfo=dt.timezone.utc
                )
                if dt.datetime.now(dt.timezone.utc) < until_dt:
                    return FetchResult(status="circuit_open",
                                       error_detail=f"circuit open until {until}")
                self._set_breaker_state(source["id"], "half_open")
                return None
            return FetchResult(status="circuit_open",
                               error_detail="circuit open (no until set)")
        return None  # half_open → allow probe

    def _record_success(self, source: dict) -> None:
        ts = now_iso()
        with self._conn:
            self._conn.execute(
                """UPDATE sources
                   SET breaker_state='closed', breaker_failures=0,
                       breaker_until=NULL, last_ok_at=?, updated_at=?
                   WHERE id=?""",
                (ts, ts, source["id"]),
            )

    def _record_failure(self, source: dict) -> None:
        failures = int(source["breaker_failures"]) + 1
        threshold = int(source["breaker_threshold"])
        ts = now_iso()
        with self._conn:
            if failures >= threshold:
                until = (dt.datetime.now(dt.timezone.utc) +
                         dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                self._conn.execute(
                    """UPDATE sources
                       SET breaker_state='open', breaker_failures=?,
                           breaker_until=?, updated_at=?
                       WHERE id=?""",
                    (failures, until, ts, source["id"]),
                )
            else:
                self._conn.execute(
                    "UPDATE sources SET breaker_failures=?, updated_at=? WHERE id=?",
                    (failures, ts, source["id"]),
                )

    def _set_breaker_state(self, source_id: int, state: str) -> None:
        ts = now_iso()
        with self._conn:
            self._conn.execute(
                "UPDATE sources SET breaker_state=?, updated_at=? WHERE id=?",
                (state, ts, source_id),
            )

    # ------------------------------------------------------------------
    # Apply-link domain check (P1 – working)
    # ------------------------------------------------------------------

    @staticmethod
    def check_apply_domain(apply_url: str, domain_allowlist: list[str]) -> bool:
        """Return True if apply_url's registrable domain is in domain_allowlist.

        Matching is suffix-based: 'greenhouse.io' matches 'x.greenhouse.io'.
        """
        host = urllib.parse.urlparse(apply_url).hostname or ""
        return any(host == d or host.endswith("." + d) for d in domain_allowlist)
