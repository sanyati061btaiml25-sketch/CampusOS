"""
tests/test_pipeline.py – tests for gateway, runner (state machine), daemon, and api.

Run:  python -m pytest tests/test_pipeline.py -v
"""

import io
import json
import sqlite3
import threading
import urllib.error
import urllib.request as _urllib_request
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest

from campusos.api import _Handler
from campusos.daemon import run_daemon
from campusos.db import connect, init_db, now_iso
from campusos.gateway import Gateway, _kill_switch_active
from campusos.runner import execute_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_urlopen_factory(payload: dict | list, status: int = 200):
    """Return a context-manager mock for urllib.request.urlopen."""
    raw = json.dumps(payload).encode("utf-8")

    class _Resp:
        def __init__(self):
            self.status = status
            self._buf = io.BytesIO(raw)

        def read(self):
            return self._buf.read()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return lambda req, timeout=30: _Resp()


@pytest.fixture()
def db_path(tmp_path):
    p = str(tmp_path / "pipeline.db")
    conn = connect(p)
    init_db(conn)
    conn.close()
    return p


# ---------------------------------------------------------------------------
# 1. Gateway tests
# ---------------------------------------------------------------------------

def test_gateway_blocks_unlisted_host(db_path):
    conn = connect(db_path)
    gw = Gateway(conn)
    source = dict(conn.execute(
        "SELECT * FROM sources WHERE name='greenhouse_coinbase'"
    ).fetchone())
    source["base_url"] = "https://evil.example.com/jobs"
    res = gw.fetch(source)
    conn.close()

    assert res.status == "blocked"
    assert "evil.example.com" in (res.error_detail or "")


def test_gateway_circuit_breaker_opens_after_threshold(db_path):
    conn = connect(db_path)
    gw = Gateway(conn)

    def _fail(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)

    with patch("urllib.request.urlopen", side_effect=_fail), patch("time.sleep"):
        for _ in range(3):
            source = dict(conn.execute(
                "SELECT * FROM sources WHERE name='greenhouse_coinbase'"
            ).fetchone())
            res = gw.fetch(source)
            assert res.status == "error"

    row = conn.execute(
        "SELECT breaker_state, breaker_failures, breaker_until FROM sources WHERE name='greenhouse_coinbase'"
    ).fetchone()
    assert row["breaker_state"] == "open"
    assert row["breaker_failures"] == 3
    assert row["breaker_until"] is not None

    # Next fetch is rejected immediately with circuit_open
    res_open = gw.fetch(dict(conn.execute(
        "SELECT * FROM sources WHERE name='greenhouse_coinbase'"
    ).fetchone()))
    conn.close()
    assert res_open.status == "circuit_open"


def test_gateway_greenhouse_coinbase_fetch(db_path):
    sample = {
        "jobs": [
            {
                "id": 12345,
                "title": "Software Engineer, Intern ",
                "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/12345",
                "location": {"name": "Remote - USA"},
            }
        ]
    }
    conn = connect(db_path)
    gw = Gateway(conn)
    source = dict(conn.execute(
        "SELECT * FROM sources WHERE name='greenhouse_coinbase'"
    ).fetchone())

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(sample)):
        res = gw.fetch(source)

    row = conn.execute(
        "SELECT breaker_state, last_ok_at FROM sources WHERE name='greenhouse_coinbase'"
    ).fetchone()
    conn.close()

    assert res.status == "ok"
    assert res.http_status == 200
    assert res.item_count == 1
    assert res.content_hash is not None
    assert row["breaker_state"] == "closed"
    assert row["last_ok_at"] is not None


# ---------------------------------------------------------------------------
# 2. State machine end-to-end (Greenhouse Coinbase + idempotent re-run)
# ---------------------------------------------------------------------------

def test_runner_greenhouse_coinbase_end_to_end(db_path):
    # Enable only greenhouse_coinbase so the test exercises it cleanly end-to-end
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    coinbase_payload = {
        "jobs": [
            {
                "id": 101,
                "title": "Backend Engineer Intern",
                "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/101",
                "location": {"name": "Remote"},
            },
            {
                "id": 102,
                "title": "Data Science Intern",
                "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/102",
                "location": {"name": "Singapore"},
            },
        ]
    }

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(coinbase_payload)):
        r1 = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert r1.state == "done"
    assert r1.sources_checked == 1
    assert r1.listings_found == 2
    assert r1.listings_new == 2
    assert r1.listings_changed == 0

    # Second run with identical payload → unchanged
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(coinbase_payload)):
        r2 = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert r2.state == "done"
    assert r2.listings_new == 0
    assert r2.listings_unchanged == 2

    # Third run with updated title → changed
    coinbase_payload["jobs"][0]["title"] = "Backend Engineer Intern (2027)"
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(coinbase_payload)):
        r3 = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert r3.state == "done"
    assert r3.listings_changed == 1
    assert r3.listings_unchanged == 1

    conn = connect(db_path)
    opp_count = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    snap_count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    cov_count = conn.execute("SELECT COUNT(*) FROM coverage").fetchone()[0]
    ev_count = conn.execute("SELECT COUNT(*) FROM events WHERE run_id=?", (r1.run_id,)).fetchone()[0]
    conn.close()

    assert opp_count == 2
    assert snap_count == 3
    assert cov_count == 3
    assert ev_count >= 4


def test_runner_respects_kill_switch(db_path):
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE settings SET value='true' WHERE key='kill_switch'")
    conn.close()

    res = execute_run(db_path=db_path, trigger="manual", mode="live")
    assert res.state == "stopped"
    assert res.stop_reason == "kill_switch"


# ---------------------------------------------------------------------------
# 3. Daemon (--once in mock mode)
# ---------------------------------------------------------------------------

def test_daemon_run_once_mock(db_path):
    run_daemon(db_path=db_path, mode="mock", run_once=True)

    conn = connect(db_path)
    ds = conn.execute("SELECT * FROM daemon_status WHERE id=1").fetchone()
    runs = conn.execute("SELECT * FROM runs").fetchall()
    conn.close()

    assert ds["pid"] is not None
    assert ds["started_at"] is not None
    assert ds["current_run_id"] is None
    assert len(runs) == 1
    assert runs[0]["state"] == "done"
    assert runs[0]["mode"] == "mock"


# ---------------------------------------------------------------------------
# 4. API read endpoints
# ---------------------------------------------------------------------------

def test_api_read_endpoints(db_path, monkeypatch):
    monkeypatch.setenv("CAMPUSOS_DB", db_path)
    run_daemon(db_path=db_path, mode="mock", run_once=True)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    import urllib.request

    def get(path):
        url = f"http://127.0.0.1:{port}{path}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())

    try:
        code, status_data = get("/status")
        assert code == 200
        assert status_data["last_run"]["state"] == "done"

        code, runs_data = get("/runs")
        assert code == 200
        assert runs_data["count"] == 1
        run_id = runs_data["runs"][0]["id"]

        code, run_detail = get(f"/runs/{run_id}")
        assert code == 200
        assert run_detail["run"]["id"] == run_id
        assert run_detail["coverage"] is not None

        code, sources_data = get("/sources")
        assert code == 200
        assert sources_data["count"] == 10

        code, opps_data = get("/opportunities")
        assert code == 200
        assert opps_data["total"] >= 1
        opp_id = opps_data["opportunities"][0]["id"]

        code, opp_detail = get(f"/opportunities/{opp_id}")
        assert code == 200
        assert opp_detail["opportunity"]["id"] == opp_id

        code, prof_data = get("/profiles")
        assert code == 200
        assert prof_data["count"] == 3

        code, rev_data = get("/review")
        assert code == 200
        assert rev_data["count"] == 0

        code, set_data = get("/settings")
        assert code == 200
        assert "kill_switch" in set_data["settings"]

        # 404 on unknown route
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            get("/does-not-exist")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 5. P0: Breaker recovery – open breaker with expired until → source is retried
# ---------------------------------------------------------------------------

def test_breaker_recovery(db_path):
    """An open breaker whose breaker_until is in the past should be retried."""
    conn = connect(db_path)
    # Force greenhouse_coinbase into an expired open breaker state
    past = "2000-01-01T00:00:00.000Z"
    with conn:
        conn.execute(
            """UPDATE sources
               SET breaker_state='open', breaker_until=?, breaker_failures=3
               WHERE name='greenhouse_coinbase'""",
            (past,),
        )
        # Disable all other sources so only greenhouse_coinbase runs
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    coinbase_payload = {"jobs": [{"id": 999, "title": "Test Intern",
                                  "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/999",
                                  "location": {"name": "Remote"}}]}
    with patch("urllib.request.urlopen",
               side_effect=_fake_urlopen_factory(coinbase_payload)):
        result = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert result.state == "done"
    assert result.sources_checked == 1
    assert result.listings_new == 1

    # Confirm breaker is now closed again
    conn2 = connect(db_path)
    row = conn2.execute(
        "SELECT breaker_state FROM sources WHERE name='greenhouse_coinbase'"
    ).fetchone()
    conn2.close()
    assert row["breaker_state"] == "closed"


# ---------------------------------------------------------------------------
# 6. P0: Replay mode – never touches the network
# ---------------------------------------------------------------------------

def test_replay_never_uses_network(db_path, tmp_path):
    """Replay mode must read from data/raw/ and never call urlopen."""
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    # Seed a raw payload file for run_id=1 (replay looks for run_<replay_run_id>)
    raw_root = tmp_path / "raw"
    payload = {"jobs": [{"id": 42, "title": "Replay Intern",
                          "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/42",
                          "location": {"name": "Remote"}}]}
    raw_dir = raw_root / "run_1"
    raw_dir.mkdir(parents=True)
    (raw_dir / "greenhouse_coinbase.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    # Patch urlopen to raise if called – replay must NEVER call it
    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("urlopen called in replay mode!")

    from campusos.gateway import Gateway as _GW

    original_init = _GW.__init__

    def _patched_init(self, conn, mode="live", budget=None, run_id=None,
                      raw_root=None):
        original_init(self, conn, mode=mode, budget=budget,
                      run_id=run_id, raw_root=str(raw_root or "") or None)
        self._raw_root = raw_root or self._raw_root

    # Use replay mode with our custom raw_root by patching execute_run's Gateway call
    with patch("urllib.request.urlopen", side_effect=_should_not_be_called):
        with patch("campusos.runner.Gateway") as MockGW:
            # Delegate to real Gateway but with our raw_root
            from campusos.gateway import Budget
            real_gw_instances = []

            def _make_gw(conn, mode="live", budget=None, run_id=None, **kwargs):
                gw = Gateway(conn, mode=mode, budget=budget,
                             run_id=run_id, raw_root=str(raw_root), **kwargs)
                real_gw_instances.append(gw)
                return gw

            MockGW.side_effect = _make_gw
            result = execute_run(db_path=db_path, trigger="manual", mode="replay")

    # Replay fetches the file; if urlopen was called it would have raised
    assert result.state in ("done", "stopped")  # stopped if file not found is ok


# ---------------------------------------------------------------------------
# 7. P0: Kill switch mid-run – run ends with state='stopped'
# ---------------------------------------------------------------------------

def test_kill_switch_mid_run(db_path):
    """
    If kill_switch becomes 'true' between sources, the run stops with state='stopped'
    and a kill_switch event is recorded.
    """
    conn = connect(db_path)
    with conn:
        # Keep two sources enabled so there's a gap between them
        conn.execute(
            "UPDATE sources SET enabled=0 WHERE name NOT IN "
            "('greenhouse_coinbase','greenhouse_stripe')"
        )
    conn.close()

    coinbase_payload = {"jobs": [{"id": 1, "title": "A",
                                   "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/1",
                                   "location": {"name": "Remote"}}]}

    call_count = [0]
    original_urlopen = _fake_urlopen_factory(coinbase_payload)

    def _urlopen_with_side_effect(req, timeout=30):
        call_count[0] += 1
        if call_count[0] == 1:
            # After first successful fetch, flip the kill switch in DB
            kconn = connect(db_path)
            with kconn:
                kconn.execute(
                    "UPDATE settings SET value='true' WHERE key='kill_switch'"
                )
            kconn.close()
        return original_urlopen(req, timeout)

    with patch("urllib.request.urlopen", side_effect=_urlopen_with_side_effect):
        result = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert result.state == "stopped"
    assert result.stop_reason == "kill_switch"

    conn2 = connect(db_path)
    kill_events = conn2.execute(
        "SELECT * FROM events WHERE run_id=? AND type='kill_switch'",
        (result.run_id,),
    ).fetchall()
    conn2.close()
    assert len(kill_events) >= 1


# ---------------------------------------------------------------------------
# 8. P0: Budget exceeded – run stops when max_requests=1 and 2 sources enabled
# ---------------------------------------------------------------------------

def test_budget_exceeded(db_path):
    """With max_requests_per_run=1 and 2 enabled sources, run stops at budget."""
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE settings SET value='1' WHERE key='max_requests_per_run'")
        conn.execute(
            "UPDATE sources SET enabled=0 WHERE name NOT IN "
            "('greenhouse_coinbase','greenhouse_stripe')"
        )
    conn.close()

    payload = {"jobs": [{"id": 1, "title": "T",
                          "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/1",
                          "location": {"name": "Remote"}}]}
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(payload)):
        result = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert result.state == "stopped"
    assert result.stop_reason == "budget_requests"


# ---------------------------------------------------------------------------
# 9. P0: Crashed run → state='failed'
# ---------------------------------------------------------------------------

def test_crashed_run_state_failed(db_path):
    """An unhandled exception inside execute_run sets state='failed'."""
    with patch("campusos.runner._extract_jobs_list",
               side_effect=RuntimeError("simulated crash")):
        # Need a successful fetch to reach parse stage; use mock mode
        result = execute_run(db_path=db_path, trigger="manual", mode="mock")

    assert result.state == "failed"
    assert result.stop_reason == "crash"

    conn = connect(db_path)
    db_state = conn.execute(
        "SELECT state FROM runs WHERE id=?", (result.run_id,)
    ).fetchone()["state"]
    conn.close()
    assert db_state == "failed"


# ---------------------------------------------------------------------------
# 10. P0: Stale running row marked failed on startup
# ---------------------------------------------------------------------------

def test_stale_run_marked_failed(db_path):
    """A 'running' row left from a previous crash is marked 'failed' on daemon boot, but NOT by execute_run."""
    conn = connect(db_path)
    with conn:
        conn.execute(
            "INSERT INTO runs (trigger, state, stage, mode) VALUES ('scheduler','running','fetch','live')"
        )
        stale_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    # execute_run does NOT mark concurrent running rows as failed
    result = execute_run(db_path=db_path, trigger="manual", mode="mock")
    assert result.state == "done"

    conn = connect(db_path)
    stale_state_during = conn.execute(
        "SELECT state FROM runs WHERE id=?", (stale_id,)
    ).fetchone()["state"]
    conn.close()
    assert stale_state_during == "running"

    # Daemon startup marks leftover running rows as failed
    run_daemon(db_path=db_path, mode="mock", run_once=True)

    conn2 = connect(db_path)
    stale_state = conn2.execute(
        "SELECT state FROM runs WHERE id=?", (stale_id,)
    ).fetchone()["state"]
    conn2.close()
    assert stale_state == "failed"


# ---------------------------------------------------------------------------
# 11. API: CORS headers present on every response
# ---------------------------------------------------------------------------

def test_api_cors_headers(db_path, monkeypatch):
    monkeypatch.setenv("CAMPUSOS_DB", db_path)
    run_daemon(db_path=db_path, mode="mock", run_once=True)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        url = f"http://127.0.0.1:{port}/api/status"
        with _urllib_request.urlopen(url, timeout=5) as resp:
            assert resp.getheader("Access-Control-Allow-Origin") == "*"
            assert resp.status == 200
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 12. API: /api prefix and bare prefix both work
# ---------------------------------------------------------------------------

def test_api_prefix(db_path, monkeypatch):
    monkeypatch.setenv("CAMPUSOS_DB", db_path)
    run_daemon(db_path=db_path, mode="mock", run_once=True)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        for path in ("/api/runs", "/runs"):
            url = f"http://127.0.0.1:{port}{path}"
            with _urllib_request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            assert resp.status == 200
            assert "runs" in data
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 13. API: POST /api/kill-switch sets the flag in DB
# ---------------------------------------------------------------------------

def test_api_post_kill_switch(db_path, monkeypatch):
    monkeypatch.setenv("CAMPUSOS_DB", db_path)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        body = json.dumps({"value": "true"}).encode()
        req = _urllib_request.Request(
            f"http://127.0.0.1:{port}/api/kill-switch",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with _urllib_request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200

        conn = connect(db_path)
        val = conn.execute(
            "SELECT value FROM settings WHERE key='kill_switch'"
        ).fetchone()["value"]
        conn.close()
        assert val == "true"
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 14. API: POST /api/runs/request sets run_requested='true'
# ---------------------------------------------------------------------------

def test_api_post_run_request(db_path, monkeypatch):
    monkeypatch.setenv("CAMPUSOS_DB", db_path)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        body = b"{}"
        req = _urllib_request.Request(
            f"http://127.0.0.1:{port}/api/runs/request",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with _urllib_request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200

        conn = connect(db_path)
        val = conn.execute(
            "SELECT value FROM settings WHERE key='run_requested'"
        ).fetchone()["value"]
        conn.close()
        assert val == "true"
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 15. API: POST /api/review/<id> resolves a review_queue row
# ---------------------------------------------------------------------------

def test_api_post_review_resolve(db_path, monkeypatch):
    monkeypatch.setenv("CAMPUSOS_DB", db_path)

    # Insert a dummy opportunity + review_queue row
    from campusos.db import now_iso
    conn = connect(db_path)
    with conn:
        src_id = conn.execute(
            "SELECT id FROM sources WHERE name='greenhouse_coinbase'"
        ).fetchone()["id"]
        opp_cur = conn.execute(
            """INSERT INTO opportunities
                   (source_id, external_id, canonical_key, snapshot_id,
                    title, company, apply_url, content_hash, first_seen_at, last_seen_at)
               VALUES (?,?,?,NULL,?,?,?,?,?,?)""",
            (src_id, "review-test-1", "greenhouse_coinbase:review-test-1",
             "Review Test Job", "ACME", "https://boards.greenhouse.io/coinbase/jobs/rt1",
             "hash_rt1", now_iso(), now_iso()),
        )
        opp_id = opp_cur.lastrowid
        rq_cur = conn.execute(
            """INSERT INTO review_queue
                   (opportunity_id, reason)
               VALUES (?, 'seniority_ambiguous')""",
            (opp_id,),
        )
        rq_id = rq_cur.lastrowid
    conn.close()

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        body = json.dumps({"resolution": "accepted"}).encode()
        req = _urllib_request.Request(
            f"http://127.0.0.1:{port}/api/review/{rq_id}",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with _urllib_request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200

        conn2 = connect(db_path)
        row = conn2.execute(
            "SELECT resolution, resolved_at FROM review_queue WHERE id=?", (rq_id,)
        ).fetchone()
        conn2.close()
        assert row["resolution"] == "accepted"
        assert row["resolved_at"] is not None
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# 16. Bug A1: Kill switch / budget inside fetch doesn't write invalid snapshot
# ---------------------------------------------------------------------------

def test_kill_switch_inside_fetch_calls(db_path):
    """When kill switch fires inside gateway.fetch, run stops cleanly with no snapshot and no crash."""
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    call_seq = [0]
    def _mock_ks(c, kf=None):
        call_seq[0] += 1
        # Runner calls _kill_switch_active first (calls 1 and 2 before loop / in loop).
        # When gateway calls it inside fetch (call 3), return True!
        if call_seq[0] >= 3:
            return True
        return False

    with patch("campusos.runner._kill_switch_active", side_effect=_mock_ks), \
         patch("campusos.gateway._kill_switch_active", side_effect=_mock_ks):
        res = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert res.state == "stopped"
    assert res.stop_reason == "kill_switch"

    conn = connect(db_path)
    events = conn.execute("SELECT * FROM events WHERE run_id=?", (res.run_id,)).fetchall()
    snaps = conn.execute("SELECT COUNT(*) FROM snapshots WHERE run_id=?", (res.run_id,)).fetchone()[0]
    conn.close()

    types = [e["type"] for e in events]
    assert "error" not in types
    assert "kill_switch" in types
    assert snaps == 0


def test_budget_exhaustion_inside_gateway(db_path):
    """When budget runs out inside gateway.fetch, run stops with budget_requests and no crash."""
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    from campusos.gateway import Budget
    with patch.object(Budget, "stop_reason", new_callable=lambda: property(lambda self: "budget_requests")):
        res = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert res.state == "stopped"
    assert res.stop_reason == "budget_requests"

    conn = connect(db_path)
    events = conn.execute("SELECT * FROM events WHERE run_id=?", (res.run_id,)).fetchall()
    snaps = conn.execute("SELECT COUNT(*) FROM snapshots WHERE run_id=?", (res.run_id,)).fetchone()[0]
    run_row = conn.execute("SELECT used_requests FROM runs WHERE id=?", (res.run_id,)).fetchone()
    conn.close()

    types = [e["type"] for e in events]
    assert "error" not in types
    assert "budget_exceeded" in types
    assert snaps == 0
    assert run_row["used_requests"] is not None


# ---------------------------------------------------------------------------
# 17. Bug A2: Relative paths resolve against _REPO_ROOT
# ---------------------------------------------------------------------------

def test_relative_paths_resolve_to_repo_root(tmp_path, monkeypatch):
    """connect('data/x.db') must resolve relative to _REPO_ROOT regardless of cwd."""
    monkeypatch.setattr("campusos.db._REPO_ROOT", tmp_path)
    monkeypatch.delenv("CAMPUSOS_DB", raising=False)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)

    conn = connect("data/x.db")
    init_db(conn)
    conn.close()

    expected_file = tmp_path / "data" / "x.db"
    assert expected_file.exists()


# ---------------------------------------------------------------------------
# 18. Bug A3: Mock defaults to mock.db and does not create campusos.db
# ---------------------------------------------------------------------------

def test_mock_defaults_to_mock_db(tmp_path, monkeypatch):
    """When mode is mock and no db is given, data/mock.db is created and campusos.db is NOT created."""
    monkeypatch.delenv("CAMPUSOS_DB", raising=False)
    fake_repo = tmp_path / "repo"
    monkeypatch.setattr("campusos.db._REPO_ROOT", fake_repo)
    monkeypatch.setattr("campusos.daemon._REPO_ROOT", fake_repo)
    monkeypatch.setattr("campusos.runner._REPO_ROOT", fake_repo)

    run_daemon(db_path=None, mode="mock", run_once=True)

    mock_db = fake_repo / "data" / "mock.db"
    live_db = fake_repo / "data" / "campusos.db"

    assert mock_db.exists()
    assert not live_db.exists()


# ---------------------------------------------------------------------------
# 19. Bug A4: Continuous heartbeat during runs
# ---------------------------------------------------------------------------

def test_heartbeat_background_thread_during_run(db_path, monkeypatch):
    """Background heartbeat thread keeps daemon_status.heartbeat_at fresh during execute_run."""
    import time
    from campusos import daemon

    monkeypatch.setattr(daemon, "_HEARTBEAT_INTERVAL", 0.05)
    heartbeats_observed = []

    def _slow_run(*args, **kwargs):
        conn = connect(db_path)
        for _ in range(4):
            time.sleep(0.1)
            row = conn.execute("SELECT heartbeat_at FROM daemon_status WHERE id=1").fetchone()
            if row and row["heartbeat_at"]:
                heartbeats_observed.append(row["heartbeat_at"])
        conn.close()
        from campusos.runner import RunResult
        return RunResult(run_id=1, state="done")

    with patch("campusos.daemon.execute_run", side_effect=_slow_run):
        run_daemon(db_path=db_path, mode="mock", run_once=True)

    unique_heartbeats = set(heartbeats_observed)
    assert len(unique_heartbeats) >= 2


# ---------------------------------------------------------------------------
# 20. Bug A5: Live saves raw files and replay reproduces counts without network
# ---------------------------------------------------------------------------

def test_live_saves_raw_and_replay_reproduces(db_path, tmp_path):
    """Live run saves raw payloads; replay run reads them and reproduces counts with zero network calls."""
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    raw_dir = tmp_path / "raw"
    coinbase_payload = {
        "jobs": [
            {
                "id": 5001,
                "title": "Engineer 5001",
                "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/5001",
                "location": {"name": "Remote"},
            }
        ]
    }

    from campusos.gateway import Gateway as _GW
    orig_init = _GW.__init__
    def _patched_init(self, conn, mode="live", budget=None, run_id=None,
                      raw_root=None, replay_run=None, replay_run_id=None):
        orig_init(self, conn, mode=mode, budget=budget, run_id=run_id,
                  raw_root=raw_dir, replay_run=replay_run, replay_run_id=replay_run_id)

    with patch.object(_GW, "__init__", _patched_init):
        # 1. Live run writes raw files
        with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(coinbase_payload)):
            live_res = execute_run(db_path=db_path, trigger="manual", mode="live")
        assert live_res.state == "done"
        assert live_res.listings_new == 1

        raw_file = raw_dir / f"run_{live_res.run_id}" / "greenhouse_coinbase.json"
        assert raw_file.exists()

        # 2. Replay run never touches network (urlopen raises AssertionError)
        def _no_network(*args, **kwargs):
            raise AssertionError("network accessed in replay mode")

        with patch("urllib.request.urlopen", side_effect=_no_network):
            replay_res = execute_run(
                db_path=db_path,
                trigger="manual",
                mode="replay",
                replay_run=live_res.run_id,
            )

        assert replay_res.state == "done"
        assert replay_res.listings_unchanged == 1

        conn2 = connect(db_path)
        row = conn2.execute("SELECT mode FROM runs WHERE id=?", (replay_res.run_id,)).fetchone()
        conn2.close()
        assert row["mode"] == "replay"


# ---------------------------------------------------------------------------
# 21. Bug A6: execute_run does not mark concurrent running rows failed
# ---------------------------------------------------------------------------

def test_execute_run_does_not_mark_running_as_failed(db_path):
    """execute_run must NOT mark concurrent 'running' rows as crashed."""
    conn = connect(db_path)
    with conn:
        conn.execute(
            "INSERT INTO runs (trigger, state, stage, mode) VALUES ('scheduler','running','fetch','live')"
        )
        running_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    result = execute_run(db_path=db_path, trigger="manual", mode="mock")
    assert result.state == "done"

    conn2 = connect(db_path)
    row = conn2.execute("SELECT state FROM runs WHERE id=?", (running_id,)).fetchone()
    conn2.close()
    assert row["state"] == "running"


# ---------------------------------------------------------------------------
# 22. Bug A7: Expired / removed listings detection in both directions
# ---------------------------------------------------------------------------

def test_opportunity_removed_and_reappeared(db_path):
    """Listings missing from a successful payload get expired; when reappearing, restored to pending."""
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    payload_two = {
        "jobs": [
            {"id": 101, "title": "Job A", "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/101"},
            {"id": 102, "title": "Job B", "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/102"},
        ]
    }
    payload_one = {
        "jobs": [
            {"id": 101, "title": "Job A", "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/101"},
        ]
    }

    # Run 1: two listings
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(payload_two)):
        r1 = execute_run(db_path=db_path, trigger="manual", mode="live")
    assert r1.listings_new == 2

    # Run 2: Job B disappeared -> marked expired, removed_at set, opportunity_changes recorded
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(payload_one)):
        r2 = execute_run(db_path=db_path, trigger="manual", mode="live")
    assert r2.state == "done"

    conn = connect(db_path)
    b_row = conn.execute("SELECT * FROM opportunities WHERE external_id='102'").fetchone()
    assert b_row["status"] == "expired"
    assert b_row["removed_at"] is not None

    chg1 = conn.execute(
        "SELECT * FROM opportunity_changes WHERE opportunity_id=? AND field='removed_at'",
        (b_row["id"],),
    ).fetchall()
    assert len(chg1) == 1
    assert chg1[0]["old_value"] is None
    assert chg1[0]["new_value"] is not None
    conn.close()

    # Run 3: Job B reappears -> removed_at cleared, status pending, opportunity_changes recorded
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(payload_two)):
        r3 = execute_run(db_path=db_path, trigger="manual", mode="live")
    assert r3.state == "done"

    conn = connect(db_path)
    b_row2 = conn.execute("SELECT * FROM opportunities WHERE external_id='102'").fetchone()
    assert b_row2["status"] == "pending"
    assert b_row2["removed_at"] is None

    chg2 = conn.execute(
        "SELECT * FROM opportunity_changes WHERE opportunity_id=? AND field='removed_at' ORDER BY id ASC",
        (b_row["id"],),
    ).fetchall()
    assert len(chg2) == 2
    assert chg2[1]["new_value"] is None
    conn.close()


# ---------------------------------------------------------------------------
# 23. Bug A7: Apply-domain allowlist check flags domain_mismatch
# ---------------------------------------------------------------------------

def test_apply_domain_mismatch_flags_needs_review(db_path):
    """Listing with apply URL outside domain_allowlist is kept with domain_mismatch flag and needs_review."""
    conn = connect(db_path)
    with conn:
        conn.execute("UPDATE sources SET enabled=0 WHERE name != 'greenhouse_coinbase'")
    conn.close()

    payload = {
        "jobs": [
            {
                "id": 9999,
                "title": "Unlisted Domain Job",
                "absolute_url": "https://evil-unlisted.com/apply/9999",
                "location": {"name": "Remote"},
            }
        ]
    }

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen_factory(payload)):
        r = execute_run(db_path=db_path, trigger="manual", mode="live")

    assert r.state == "done"
    conn = connect(db_path)
    opp = conn.execute("SELECT * FROM opportunities WHERE external_id='9999'").fetchone()
    conn.close()

    assert opp is not None
    assert opp["status"] == "needs_review"
    flags = json.loads(opp["flags"])
    assert "domain_mismatch" in flags

