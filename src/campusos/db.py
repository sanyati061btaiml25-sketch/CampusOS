"""
CampusOS database layer.

Usage rules
-----------
1. **One connection per process or thread.**  Open a connection with
   ``connect()`` at startup (or at the top of a request) and keep it for
   the lifetime of that process/thread.  Do NOT share a single connection
   across threads – SQLite connections are not thread-safe in the default
   ``check_same_thread=True`` mode.

2. **Keep transactions short.**  Wrap every group of writes in a ``with
   conn:`` block.  The context manager commits on success and rolls back on
   any exception, so partial writes never reach the database::

       with conn:
           conn.execute("UPDATE settings SET value=? WHERE key=?", (val, key))

3. **Write ownership.**
   - The *daemon* is the sole writer of run data: ``runs``, ``snapshots``,
     ``opportunities``, ``opportunity_changes``, ``evidence``, ``matches``,
     ``coverage``, ``coverage_profile``, ``events``, ``actions``.
   - The *API / dashboard* writes only:
       - ``settings`` row ``kill_switch``  (stop flag)
       - ``settings`` row ``run_requested`` (manual trigger)
       - ``review_queue`` resolution columns  (review decisions)
       - ``profile`` and ``search_intent``  (profile edits)
   Mixing writers outside these boundaries risks WAL conflicts and
   inconsistent state.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo-root DB path: resolved relative to this module file so it works from
# any working directory.  Structure: src/campusos/db.py → parents[2] = repo root.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parents[1]          # src/campusos → src → repo root
_DEFAULT_DB = _REPO_ROOT / "data" / "campusos.db"
_DEFAULT_SCHEMA = _HERE / "schema.sql"


def resolve_path(p: str | Path) -> Path:
    """Resolve a filesystem path relative to the repository root if not absolute."""
    path = Path(p)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    return path


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (ms precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection with PRAGMAs applied.

    Parameters
    ----------
    path:
        Filesystem path to the database file.  Defaults to the
        ``CAMPUSOS_DB`` environment variable, falling back to
        ``<repo_root>/data/campusos.db``. Relative paths are always
        resolved against ``_REPO_ROOT``.

    Notes
    -----
    * ``row_factory = sqlite3.Row`` – rows are accessible by column name.
    * ``PRAGMA foreign_keys = ON`` – enforced on every connection.
    * ``PRAGMA busy_timeout = 5000`` – wait up to 5 s before raising
      ``OperationalError: database is locked``.
    * ``PRAGMA synchronous = NORMAL`` – safe with WAL mode; faster than
      FULL while still crash-safe.
    """
    raw = path or os.environ.get("CAMPUSOS_DB") or "data/campusos.db"
    p = resolve_path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(
    conn: sqlite3.Connection,
    schema: str | Path | None = None,
) -> None:
    """Create all tables and seed rows (idempotent).

    Uses ``IF NOT EXISTS`` for every ``CREATE`` statement and ``INSERT OR
    IGNORE`` for every seed row, so calling this function more than once on
    the same database is safe and produces no errors.

    Parameters
    ----------
    conn:
        An open connection returned by :func:`connect`.
    schema:
        Path to the SQL schema file.  Defaults to
        ``src/campusos/schema.sql`` relative to this module.
    """
    schema_path = Path(schema) if schema else _DEFAULT_SCHEMA
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()


def main() -> None:
    """Entry point for ``python -m campusos.db`` / ``campusos-db``.

    Initialises the database and prints the path so it can be scripted::

        python -m campusos.db
        # Database ready: /path/to/data/campusos.db
    """
    import sys

    db_path = os.environ.get("CAMPUSOS_DB", str(_DEFAULT_DB))
    conn = connect(db_path)
    init_db(conn)
    conn.close()
    print(f"Database ready: {db_path}", file=sys.stdout)


if __name__ == "__main__":
    main()
