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
   - The *dashboard* writes only:
       - ``settings`` row ``kill_switch``  (stop flag)
       - ``review_queue`` resolution columns  (review decisions)
       - ``profile`` and ``search_intent``  (profile edits)
   Mixing writers outside these boundaries risks WAL conflicts and
   inconsistent state.
"""

import os
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Path to the schema file, resolved relative to this module so it works
# regardless of the working directory the caller uses.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
_DEFAULT_SCHEMA = _HERE / "schema.sql"


def connect(path: str | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection with PRAGMAs applied.

    Parameters
    ----------
    path:
        Filesystem path to the database file.  Defaults to the
        ``CAMPUSOS_DB`` environment variable, falling back to
        ``data/campusos.db``.

    Notes
    -----
    * ``row_factory = sqlite3.Row`` – rows are accessible by column name.
    * ``PRAGMA foreign_keys = ON`` – enforced on every connection.
    * ``PRAGMA busy_timeout = 5000`` – wait up to 5 s before raising
      ``OperationalError: database is locked``.
    * ``PRAGMA synchronous = NORMAL`` – safe with WAL mode; faster than
      FULL while still crash-safe.
    """
    path = path or os.environ.get("CAMPUSOS_DB", "data/campusos.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
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
