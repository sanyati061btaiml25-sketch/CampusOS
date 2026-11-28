# CampusOS – Read-Only API Reference (API_current.md)

> This file documents the **current** read-only API (`src/campusos/api.py`).
> POST endpoints for kill-switch, manual run trigger, and review decisions are planned.

Base URL: `http://127.0.0.1:8000` (default)

Start: `campusos-api` or `python -m campusos.api`

All responses are `application/json; charset=utf-8`.
The API is **read-only** — it never writes to the database.

---

## Endpoints

### `GET /status`

Daemon heartbeat and last run summary.

```json
{
  "daemon": {
    "id": 1, "pid": 12345,
    "started_at": "2026-11-28T07:00:00.000Z",
    "heartbeat_at": "2026-11-28T07:05:00.000Z",
    "current_run_id": null,
    "next_run_at": "2026-11-28T07:06:00.000Z"
  },
  "last_run": { "id": 3, "state": "done", "started_at": "...", "ended_at": "..." }
}
```

### `GET /runs?limit=20`

List recent runs, newest first. `limit` ≤ 100.

### `GET /runs/<id>`

Single run + coverage + first 200 audit events.

```json
{
  "run": { "id": 3, "state": "done", "stage": "done", "trigger": "scheduler", "..." : "..." },
  "coverage": { "sources_checked": 8, "listings_found": 142, "after_dedup": 11, "...": "..." },
  "coverage_profile": [],
  "events": []
}
```

### `GET /sources`

All 10 sources with live circuit-breaker state.

### `GET /opportunities?page=1&per=50&status=pending`

Paginated listings. `status` values: `pending` | `verified` | `needs_review` | `expired`.

```json
{ "opportunities": [], "total": 142, "page": 1, "per": 50 }
```

### `GET /opportunities/<id>`

Single opportunity + evidence rows + change history + match rows.

### `GET /profiles`

All profiles with their embedded `search_intent`.

### `GET /review?resolved=false`

Open review-queue items. `?resolved=true` returns resolved items.

### `GET /settings`

All key-value settings as a flat object.

```json
{ "settings": { "kill_switch": "false", "interval_s": "60", "mode": "live" } }
```

---

## Error Responses

| HTTP | Meaning |
|---|---|
| `404` | Route or row not found |
| `500` | Unhandled server error (details in response body) |

---

## Planned Write Endpoints (not yet implemented)

| Endpoint | Action |
|---|---|
| `POST /control/stop` | Set `kill_switch = true` in settings |
| `POST /runs` | Trigger a manual run |
| `POST /review/<id>/resolve` | Resolve a review-queue item |
