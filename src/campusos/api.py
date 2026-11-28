"""
campusos/api.py – JSON HTTP API (stdlib only, no framework).

GET endpoints  (read-only)
--------------------------
GET  /api/status
GET  /api/runs[?limit=N]
GET  /api/runs/<id>
GET  /api/sources
GET  /api/opportunities[?page=N&per=N&status=S]
GET  /api/opportunities/<id>
GET  /api/profiles
GET  /api/review[?resolved=true]
GET  /api/settings
GET  /api/coverage[?run_id=N]
GET  /api/events?run_id=N[&after_seq=N]
GET  /api/actions[?run_id=N]

POST endpoints  (write)
------------------------
POST /api/kill-switch          {"value": "true"|"false"}
POST /api/runs/request         {}  → sets settings.run_requested='true'
POST /api/review/<id>          {"resolution": "accepted"|"rejected"|"ignored"}

Paths without /api prefix are also accepted (backward compat).
CORS headers are sent on every response.
Server uses ThreadingHTTPServer for concurrent requests.
"""

import argparse
import json
import logging
import os
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .db import connect, init_db, now_iso
from .env import load_env

log = logging.getLogger("campusos.api")

_HIDDEN_SETTINGS = {"sandbox_inbox"}   # never expose these over the API

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    return connect()


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _one(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


# ---------------------------------------------------------------------------
# Route registry
# ---------------------------------------------------------------------------

_GET_ROUTES:  list[tuple] = []
_POST_ROUTES: list[tuple] = []


def _get(pattern):
    def dec(fn):
        _GET_ROUTES.append((re.compile(pattern), fn))
        return fn
    return dec


def _post(pattern):
    def dec(fn):
        _POST_ROUTES.append((re.compile(pattern), fn))
        return fn
    return dec


# ---------------------------------------------------------------------------
# GET handlers
# ---------------------------------------------------------------------------

@_get(r"^/status$")
def h_status(conn, _m, _p):
    return {
        "daemon": _one(conn, "SELECT * FROM daemon_status WHERE id=1") or {},
        "last_run": _one(conn, "SELECT * FROM runs ORDER BY id DESC LIMIT 1") or {},
    }


@_get(r"^/runs$")
def h_runs(conn, _m, p):
    limit = min(int((p.get("limit") or ["20"])[0]), 100)
    rows = _rows(conn, "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
    return {"runs": rows, "count": len(rows)}


@_get(r"^/runs/(\d+)$")
def h_run_detail(conn, m, _p):
    run_id = int(m.group(1))
    run = _one(conn, "SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        return None
    return {
        "run": run,
        "coverage": _one(conn, "SELECT * FROM coverage WHERE run_id=?", (run_id,)),
        "coverage_profile": _rows(conn, "SELECT * FROM coverage_profile WHERE run_id=?", (run_id,)),
        "events": _rows(conn, "SELECT * FROM events WHERE run_id=? ORDER BY seq LIMIT 200", (run_id,)),
    }


@_get(r"^/sources$")
def h_sources(conn, _m, _p):
    rows = _rows(conn, "SELECT * FROM sources ORDER BY name")
    return {"sources": rows, "count": len(rows)}


@_get(r"^/opportunities$")
def h_opportunities(conn, _m, p):
    page   = max(1, int((p.get("page") or ["1"])[0]))
    per    = min(int((p.get("per")  or ["50"])[0]), 200)
    status = (p.get("status") or [None])[0]
    offset = (page - 1) * per
    if status:
        total = conn.execute("SELECT COUNT(*) FROM opportunities WHERE status=?", (status,)).fetchone()[0]
        rows  = _rows(conn, "SELECT * FROM opportunities WHERE status=? ORDER BY id DESC LIMIT ? OFFSET ?",
                      (status, per, offset))
    else:
        total = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
        rows  = _rows(conn, "SELECT * FROM opportunities ORDER BY id DESC LIMIT ? OFFSET ?", (per, offset))
    return {"opportunities": rows, "total": total, "page": page, "per": per}


@_get(r"^/opportunities/(\d+)$")
def h_opportunity_detail(conn, m, _p):
    opp_id = int(m.group(1))
    opp = _one(conn, "SELECT * FROM opportunities WHERE id=?", (opp_id,))
    if not opp:
        return None
    return {
        "opportunity": opp,
        "evidence": _rows(conn, "SELECT * FROM evidence WHERE opportunity_id=?", (opp_id,)),
        "changes":  _rows(conn, "SELECT * FROM opportunity_changes WHERE opportunity_id=? ORDER BY changed_at DESC LIMIT 50", (opp_id,)),
        "matches":  _rows(conn, "SELECT * FROM matches WHERE opportunity_id=?", (opp_id,)),
    }


@_get(r"^/profiles$")
def h_profiles(conn, _m, _p):
    profiles = _rows(conn, "SELECT * FROM profile ORDER BY label")
    intents  = {r["profile_id"]: r for r in _rows(conn, "SELECT * FROM search_intent")}
    for p in profiles:
        p["search_intent"] = intents.get(p["id"])
    return {"profiles": profiles, "count": len(profiles)}


@_get(r"^/review$")
def h_review(conn, _m, p):
    resolved = (p.get("resolved") or ["false"])[0].lower() == "true"
    if resolved:
        rows = _rows(conn, "SELECT * FROM review_queue WHERE resolved_at IS NOT NULL ORDER BY resolved_at DESC LIMIT 100")
    else:
        rows = _rows(conn, "SELECT * FROM review_queue WHERE resolved_at IS NULL ORDER BY created_at ASC")
    return {"items": rows, "count": len(rows)}


@_get(r"^/settings$")
def h_settings(conn, _m, _p):
    rows = _rows(conn, "SELECT * FROM settings ORDER BY key")
    return {"settings": {r["key"]: r["value"] for r in rows
                         if r["key"] not in _HIDDEN_SETTINGS}}


@_get(r"^/coverage$")
def h_coverage(conn, _m, p):
    run_id = (p.get("run_id") or [None])[0]
    if run_id:
        row = _one(conn, "SELECT * FROM coverage WHERE run_id=?", (int(run_id),))
        return {"coverage": row}
    rows = _rows(conn, "SELECT * FROM coverage ORDER BY run_id DESC LIMIT 20")
    return {"coverage": rows, "count": len(rows)}


@_get(r"^/events$")
def h_events(conn, _m, p):
    run_id    = (p.get("run_id") or [None])[0]
    after_seq = int((p.get("after_seq") or ["0"])[0])
    if not run_id:
        return {"error": "run_id required"}, 400
    rows = _rows(conn,
        "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 500",
        (int(run_id), after_seq))
    return {"events": rows, "count": len(rows)}


@_get(r"^/actions$")
def h_actions(conn, _m, p):
    run_id = (p.get("run_id") or [None])[0]
    if run_id:
        rows = _rows(conn, "SELECT * FROM actions WHERE run_id=? ORDER BY id", (int(run_id),))
    else:
        rows = _rows(conn, "SELECT * FROM actions ORDER BY id DESC LIMIT 50")
    return {"actions": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# POST handlers
# ---------------------------------------------------------------------------

@_post(r"^/kill-switch$")
def h_kill_switch(conn, _m, body):
    value = str(body.get("value", "true")).lower()
    if value not in ("true", "false"):
        return {"error": "value must be 'true' or 'false'"}, 400
    ts = now_iso()
    with conn:
        conn.execute(
            "UPDATE settings SET value=?, updated_at=? WHERE key='kill_switch'",
            (value, ts),
        )
    return {"kill_switch": value}


@_post(r"^/runs/request$")
def h_run_request(conn, _m, _body):
    ts = now_iso()
    with conn:
        conn.execute(
            "UPDATE settings SET value='true', updated_at=? WHERE key='run_requested'",
            (ts,),
        )
    return {"run_requested": "true"}


@_post(r"^/review/(\d+)$")
def h_review_resolve(conn, m, body):
    item_id    = int(m.group(1))
    resolution = body.get("resolution")
    if resolution not in ("accepted", "rejected", "ignored"):
        return {"error": "resolution must be accepted|rejected|ignored"}, 400
    ts = now_iso()
    with conn:
        conn.execute(
            "UPDATE review_queue SET resolved_at=?, resolution=? WHERE id=?",
            (ts, resolution, item_id),
        )
    return {"id": item_id, "resolution": resolution, "resolved_at": ts}


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

_CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _strip_api_prefix(path: str) -> str:
    """Accept /api/... and /... equally."""
    if path.startswith("/api"):
        path = path[4:]
    return path.rstrip("/") or "/"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.debug(fmt, *args)

    def _send_json(self, body, code=200):
        data = json.dumps(body, default=str).encode()
        self.send_response(code)
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):  # noqa: N802  – preflight
        self.send_response(204)
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path   = _strip_api_prefix(parsed.path)
        params = parse_qs(parsed.query)
        conn = _get_conn()
        try:
            for pat, handler in _GET_ROUTES:
                m = pat.match(path)
                if m:
                    result = handler(conn, m, params)
                    if result is None:
                        self._send_json({"error": "not found"}, 404)
                    elif isinstance(result, tuple):
                        self._send_json(result[0], result[1])
                    else:
                        self._send_json(result)
                    return
            self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            log.exception("GET %s", self.path)
            self._send_json({"error": str(exc)}, 500)
        finally:
            conn.close()

    def do_POST(self):  # noqa: N802
        from urllib.parse import urlparse
        path = _strip_api_prefix(urlparse(self.path).path)
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length)) if length else {}
        except json.JSONDecodeError:
            self._send_json({"error": "invalid JSON"}, 400)
            return
        conn = _get_conn()
        try:
            for pat, handler in _POST_ROUTES:
                m = pat.match(path)
                if m:
                    result = handler(conn, m, body)
                    if isinstance(result, tuple):
                        self._send_json(result[0], result[1])
                    else:
                        self._send_json(result)
                    return
            self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            log.exception("POST %s", self.path)
            self._send_json({"error": str(exc)}, 500)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    load_env()
    parser = argparse.ArgumentParser(description="CampusOS API")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    conn = _get_conn()
    init_db(conn)
    conn.close()

    log.info("API listening on http://%s:%d  (GET + POST, /api prefix optional)",
             args.host, args.port)
    ThreadingHTTPServer((args.host, args.port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
