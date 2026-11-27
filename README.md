# CampusOS

An intelligent campus operating system — connecting students, faculty, and administration through AI-powered workflows.

---

## Table of Contents

- [Project Layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Database](#database)
- [Running the Tests](#running-the-tests)
- [DB Layer Rules](#db-layer-rules)
- [Contributing](#contributing)
- [License](#license)

---

## Project Layout

```
campusos/
├── pyproject.toml               # build config, pytest settings
├── .env.example                 # copy → .env, fill in values
├── .gitignore
├── LICENSE                      # MIT
├── README.md
│
├── src/
│   └── campusos/
│       ├── __init__.py
│       ├── db.py                # connect() + init_db() + usage rules
│       └── schema.sql           # SQLite schema (WAL, FK, seed data)
│
├── tests/
│   ├── __init__.py
│   └── test_db.py               # 7 contract tests for the DB layer
│
├── traces/                      # LLM call logs — git-ignored
└── data/                        # SQLite files — git-ignored
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | ≥ 3.10 |
| pip | any recent |

No external services are needed for local development — the database is a single SQLite file.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-org/campusos.git
cd campusos

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install the package in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Set up your environment
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
# Edit .env — at minimum set CAMPUSOS_DB (default is fine for local dev)

# 5. Initialise the database
python - <<'EOF'
from campusos.db import connect, init_db
conn = connect()
init_db(conn)
conn.close()
print("Database ready.")
EOF
```

---

## Database

### Schema (`src/campusos/schema.sql`)

The schema is applied by `init_db()`. Every `CREATE` uses `IF NOT EXISTS`
and every seed `INSERT` uses `OR IGNORE`, so it is **safe to call on every
start-up** — the second call is always a no-op.

Key tables:

| Table | Purpose |
|-------|---------|
| `sources` | One row per job-board / API endpoint (10 seeded, 8 enabled) |
| `runs` | One row per daemon run |
| `snapshots` | One row per fetch attempt |
| `opportunities` | Canonical job listings |
| `profile` | User profiles (3 synthetic seeds) |
| `search_intent` | Search preferences per profile |
| `matches` | One row per (opportunity × profile) |
| `review_queue` | Items that need a human decision |
| `actions` | Outbound digests and calendar invites |
| `events` | Append-only audit trail |
| `settings` | Key-value runtime config (kill switch, budgets, …) |
| `daemon_status` | Heartbeat for the dashboard |

### WAL mode

`PRAGMA journal_mode = WAL` is set in the schema and **persisted in the
database file**. The per-connection PRAGMAs (`foreign_keys`,
`busy_timeout`, `synchronous`) are applied by `connect()` on every new
connection.

### Environment variable

| Variable | Default | Description |
|----------|---------|-------------|
| `CAMPUSOS_DB` | `data/campusos.db` | Path to the SQLite database file |
| `APP_SECRET_KEY` | — | Application secret (required in production) |
| `APP_ENV` | — | `development` / `staging` / `production` |

---

## Running the Tests

```bash
# From the repo root (virtual environment must be active)
python -m pytest tests/ -v
```

Expected output (all 7 should pass in < 1 s):

```
tests/test_db.py::test_init_db_idempotent            PASSED
tests/test_db.py::test_foreign_keys_enabled          PASSED
tests/test_db.py::test_wal_enabled                   PASSED
tests/test_db.py::test_three_seeded_profiles         PASSED
tests/test_db.py::test_search_intents_match_profiles PASSED
tests/test_db.py::test_eight_enabled_sources         PASSED
tests/test_db.py::test_foreign_key_enforced          PASSED
```

Each test uses a **fresh database in a temporary directory** (`tmp_path`),
so tests are fully isolated and leave nothing behind.

---

## DB Layer Rules

These rules are enforced by convention and documented in `src/campusos/db.py`.

1. **One connection per process or thread.**
   Call `connect()` once at startup and reuse it. Do not share a single
   connection across threads — SQLite connections are not thread-safe with
   the default `check_same_thread=True`.

2. **Keep transactions short.**
   Wrap every group of writes in a `with conn:` block. It commits on
   success and rolls back on any exception:

   ```python
   with conn:
       conn.execute("UPDATE settings SET value=? WHERE key=?", (val, key))
   ```

3. **Write ownership — who writes what.**

   | Writer | Tables it may write |
   |--------|-------------------|
   | **Daemon** | `runs`, `snapshots`, `opportunities`, `opportunity_changes`, `evidence`, `matches`, `coverage`, `coverage_profile`, `events`, `actions` |
   | **Dashboard** | `settings.kill_switch` (stop flag), `review_queue` resolutions, `profile`, `search_intent` |

   Mixing writers outside these boundaries risks WAL conflicts and
   inconsistent state.

---

## Contributing

1. Fork and create a feature branch.
2. Write code **and** tests — the test suite must stay green.
3. Run `python -m pytest tests/ -v` locally before opening a PR.
4. Open a pull request; CI must pass.

---

## License

[MIT](LICENSE)
