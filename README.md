# CampusOS

> An autonomous agent that **finds and surfaces opportunities** — internships and jobs — without ever auto-applying.

CampusOS watches public job boards, deduplicates and content-hashes each listing, and builds a searchable local database. Eligibility matching, scoring, review routing, and digest delivery are in progress.

See [`docs/AGENT.md`](docs/AGENT.md) for the full architecture and [`docs/SAFETY.md`](docs/SAFETY.md) for safety constraints.

---

## Status

| Stage | State |
|---|---|
| Fetch, circuit breaker, host allowlist | ✅ Working (live + mock) |
| Parse (Greenhouse, Lever, Himalayas), upsert, change detection | ✅ Working |
| Extract, verify, dedupe, match, rank, decide | 🔧 In progress |
| Digest + .ics actions, review queue | 📋 Planned |
| Trap Pack, replay mode | 📋 Planned |

---

## Table of Contents

- [Run With No Keys](#run-with-no-keys)
- [Project Layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Running the Agent](#running-the-agent)
- [Read-Only API](#read-only-api)
- [Database](#database)
- [Running the Tests](#running-the-tests)
- [Architecture](#architecture)
- [Safety](#safety)
- [Contributing](#contributing)
- [License](#license)

---

## Run With No Keys

CampusOS works completely offline in mock mode — no API keys, no network:

```powershell
# Windows PowerShell
python -m venv .venv; .venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
python -m campusos.db                    # init DB
python -m campusos.daemon --mock --once  # one full run, all offline
python -m campusos.api                   # API on http://127.0.0.1:8000
```

Mock mode serves deterministic payloads for every source (Greenhouse, Lever, Himalayas)
so the fetch → parse → upsert → audit path runs end-to-end without credentials.

---

## Project Layout

```
campusos/
├── pyproject.toml               # build config, console scripts, pytest settings
├── .env.example                 # copy → .env, fill in values
├── .gitignore
├── LICENSE                      # MIT
├── README.md
│
├── .github/
│   └── workflows/ci.yml         # GitHub Actions: pytest on push + PR
│
├── src/
│   └── campusos/
│       ├── __init__.py
│       ├── env.py               # stdlib .env loader (no third-party deps)
│       ├── db.py                # connect(), init_db(), __main__
│       ├── schema.sql           # SQLite schema: WAL, FK, seed sources & profiles
│       ├── gateway.py           # HTTP fetch + circuit breaker + host allowlist
│       ├── runner.py            # run state machine: plan→fetch→parse→upsert→match→done
│       ├── daemon.py            # scheduler loop, heartbeat, SIGINT/SIGTERM/kill-file
│       └── api.py               # read-only HTTP API (stdlib, no framework)
│
├── tests/
│   ├── __init__.py
│   ├── test_db.py               # 7 DB contract tests
│   └── test_pipeline.py        # 7 gateway / runner / daemon / API tests
│
├── docs/
│   ├── AGENT.md                 # architecture: stages, state machine, decisions
│   ├── SAFETY.md                # safety constraints: no auto-apply, kill switch, budget caps
│   └── API_current.md           # current read-only API endpoint reference
│
├── traces/                      # LLM call logs (git-ignored)
└── data/                        # SQLite DB files (git-ignored)
```

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.10 |
| pip | any recent |

No external services are needed for local development or mock-mode runs.

---

## Quick Start

```powershell
# 1. Clone
git clone https://github.com/nisabmohd/CampusOS.git
cd CampusOS

# 2. Virtual environment
python -m venv .venv
.venv\Scripts\activate        # PowerShell
# source .venv/bin/activate   # bash/zsh

# 3. Editable install with dev dependencies
pip install -e ".[dev]"

# 4. Environment
copy .env.example .env
# CAMPUSOS_DB default (data/campusos.db) is fine for local dev.
# The daemon loads .env automatically on startup.

# 5. Initialise the database
python -m campusos.db
```

---

## Running the Agent

```powershell
# One offline run (no network, no keys needed)
campusos-daemon --mock --once

# One live run (fetches the 8 enabled sources)
campusos-daemon --once

# Continuous scheduler loop (runs every interval_s from settings)
campusos-daemon

# Override database path
campusos-daemon --db path/to/other.db --mock --once
```

The daemon:
- Loads `.env` at startup (shell exports take precedence).
- Writes `daemon_status` heartbeats every 5 s while sleeping.
- Stops cleanly on `SIGINT` / `SIGTERM`, when `kill_switch = true` in the DB, or when `KILL_FILE` exists on disk.

---

## Read-Only API

```powershell
campusos-api                   # listens on http://127.0.0.1:8000
campusos-api --port 9000 --host 0.0.0.0
```

| Endpoint | Returns |
|---|---|
| `GET /status` | Daemon heartbeat + last run summary |
| `GET /runs` | Recent runs (newest first) |
| `GET /runs/<id>` | Run detail + coverage + audit events |
| `GET /sources` | All sources with circuit-breaker state |
| `GET /opportunities` | Paginated listing feed (`?page=1&per=50&status=pending`) |
| `GET /opportunities/<id>` | Single opportunity + evidence + match rows |
| `GET /profiles` | Profiles + search intents |
| `GET /review` | Open review-queue items (`?resolved=true` for resolved) |
| `GET /settings` | Key-value runtime config |

Full field reference: [`docs/API_current.md`](docs/API_current.md).

**Write ownership:**

| Owner | May write |
|---|---|
| **Daemon** (`runner.py`) | `runs`, `snapshots`, `opportunities`, `opportunity_changes`, `evidence`, `matches`, `coverage`, `coverage_profile`, `events`, `actions` |
| **Operator (direct DB)** | `settings.kill_switch`, `review_queue` resolutions, `profile`, `search_intent` |
| **API** | Nothing — read-only |

---

## Database

Schema: [`src/campusos/schema.sql`](src/campusos/schema.sql), applied by `init_db()`.
Every `CREATE` uses `IF NOT EXISTS` and every seed `INSERT` uses `OR IGNORE` — safe to call on every daemon start.

| Table | Purpose |
|---|---|
| `sources` | One row per job-board / API endpoint (10 seeded, 8 enabled) |
| `runs` | One row per daemon run |
| `snapshots` | One row per fetch attempt |
| `opportunities` | Canonical, deduplicated listings |
| `profile` | User profiles (3 synthetic seeds) |
| `search_intent` | Per-profile search preferences |
| `matches` | One row per (opportunity × profile) — populated when match stage is complete |
| `review_queue` | Items that need a human decision — populated when review logic is complete |
| `actions` | Outbound digests and calendar invites — planned |
| `events` | Append-only audit trail |
| `settings` | Kill switch, budget caps, interval, mode |
| `daemon_status` | Single heartbeat row |

| Variable | Default | Description |
|---|---|---|
| `CAMPUSOS_DB` | `data/campusos.db` | Path to the SQLite database |
| `CAMPUSOS_MODE` | `live` | `live` / `mock` / `replay` |
| `KILL_FILE` | `data/KILL` | Touch this file to stop the daemon |
| `SANDBOX_INBOX` | `outbox/` | Directory for generated digest files (planned) |

---

## Running the Tests

```powershell
python -m pytest tests/ -v
```

**14 tests, all green, under 3 s:**

```
tests/test_db.py::test_init_db_idempotent              PASSED
tests/test_db.py::test_foreign_keys_enabled            PASSED
tests/test_db.py::test_wal_enabled                     PASSED
tests/test_db.py::test_three_seeded_profiles           PASSED
tests/test_db.py::test_search_intents_match_profiles   PASSED
tests/test_db.py::test_eight_enabled_sources           PASSED
tests/test_db.py::test_foreign_key_enforced            PASSED
tests/test_pipeline.py::test_gateway_blocks_unlisted_host              PASSED
tests/test_pipeline.py::test_gateway_circuit_breaker_opens_after_threshold PASSED
tests/test_pipeline.py::test_gateway_greenhouse_coinbase_fetch         PASSED
tests/test_pipeline.py::test_runner_greenhouse_coinbase_end_to_end     PASSED
tests/test_pipeline.py::test_runner_respects_kill_switch               PASSED
tests/test_pipeline.py::test_daemon_run_once_mock                      PASSED
tests/test_pipeline.py::test_api_read_endpoints                        PASSED
```

Each test spins up a fresh database in `tmp_path` — fully isolated.

---

## Architecture

See [`docs/AGENT.md`](docs/AGENT.md). The working pipeline today:

```
scheduler tick
    └─ runner.execute_run()
           ├─ plan    — load settings, check kill switch + kill file, pick due sources
           ├─ fetch   — gateway.fetch() per source (circuit breaker, host allowlist)  ✅
           ├─ parse   — Greenhouse / Lever / Himalayas normaliser                     ✅
           ├─ upsert  — content-hash dedup; new / changed / unchanged                 ✅
           ├─ match   — [stub – in progress]
           └─ done    — finalise run row, write coverage, clear heartbeat             ✅
```

---

## Safety

See [`docs/SAFETY.md`](docs/SAFETY.md). Key constraints:

- **Never auto-applies.** No browser, no form-submission, no portal credentials.
- **Kill switch (DB).** Set `kill_switch = true` in `settings` to stop after current run. ✅
- **Kill file.** Touch `$KILL_FILE` (default `data/KILL`) for the same effect. ✅
- **Budget caps.** Per-run limits on requests and wall-clock seconds (token/USD caps tracked in schema, enforcement tied to LLM stage — in progress).
- **Host allowlist.** Gateway blocks any host not in `sources.fetch_hosts` before making a network call. ✅
- **Apply-link domain allowlist.** Schema stores per-source `domain_allowlist`; verification logic is in progress.

---

## Contributing

1. Fork and create a feature branch.
2. Write code **and** tests — the suite must stay green.
3. Run `python -m pytest tests/ -v` locally before opening a PR.
4. Open a pull request — GitHub Actions runs the same test suite automatically.

---

## License

[MIT](LICENSE)
