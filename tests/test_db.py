"""
tests/test_db.py – contract tests for src/campusos/db.py

Run:  python -m pytest tests/test_db.py -v
"""

import sqlite3
import pytest

from campusos.db import connect, init_db


# ---------------------------------------------------------------------------
# Fixture: a fresh file-based DB in tmp_path (WAL requires a real file).
# ---------------------------------------------------------------------------

@pytest.fixture()
def db(tmp_path):
    """File-based database with the schema initialised (WAL needs a real file)."""
    conn = connect(str(tmp_path / "test.db"))
    init_db(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# 1. init_db is idempotent – counts must not double after a second call.
# ---------------------------------------------------------------------------

def test_init_db_idempotent(tmp_path):
    """init_db called twice must not duplicate any seed rows.

    IF NOT EXISTS (DDL) and INSERT OR IGNORE (seed rows) guarantee this.
    If a seed table lacks a unique constraint, the second call would insert
    duplicates and the counts would be wrong.
    """
    conn = connect(str(tmp_path / "idempotent.db"))
    init_db(conn)
    init_db(conn)
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("profile", "search_intent", "sources", "settings")
    }
    conn.close()
    assert counts["profile"]       == 3,  f"profile count: {counts['profile']}"
    assert counts["search_intent"] == 3,  f"search_intent count: {counts['search_intent']}"
    assert counts["sources"]       == 10, f"sources count: {counts['sources']}"
    assert counts["settings"]      >= 1,  f"settings count: {counts['settings']}"


# ---------------------------------------------------------------------------
# 2. PRAGMA foreign_keys is ON for every connection from connect().
# ---------------------------------------------------------------------------

def test_foreign_keys_enabled(tmp_path):
    """PRAGMA foreign_keys must return 1 on every connection from connect()."""
    conn = connect(str(tmp_path / "fk.db"))
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    conn.close()
    assert row is not None, "PRAGMA foreign_keys returned no rows"
    assert row[0] == 1, f"Expected foreign_keys=1, got {row[0]}"


# ---------------------------------------------------------------------------
# 3. WAL mode is active (set by schema PRAGMA, persisted in the DB file).
# ---------------------------------------------------------------------------

def test_wal_enabled(db):
    """journal_mode must be 'wal' – set by schema and stored in the file."""
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


# ---------------------------------------------------------------------------
# 4a. Exactly three seeded profiles exist.
# ---------------------------------------------------------------------------

def test_three_seeded_profiles(db):
    """The schema seeds exactly 3 synthetic profiles."""
    expected_labels = {"profile_a_tech", "profile_b_finance", "profile_c_analyst"}

    rows = db.execute("SELECT label FROM profile").fetchall()
    actual_labels = {r["label"] for r in rows}

    assert len(rows) == 3, f"Expected 3 profiles, found {len(rows)}: {actual_labels}"
    assert actual_labels == expected_labels, (
        f"Profile labels mismatch.\n  expected: {expected_labels}\n  got:      {actual_labels}"
    )


# ---------------------------------------------------------------------------
# 4b. Each profile has a matching search_intent row.
# ---------------------------------------------------------------------------

def test_search_intents_match_profiles(db):
    """Every seeded profile must have exactly one search_intent row."""
    rows = db.execute(
        """
        SELECT p.label
        FROM profile p
        LEFT JOIN search_intent si ON si.profile_id = p.id
        WHERE si.id IS NULL
        """
    ).fetchall()
    missing = [r["label"] for r in rows]
    assert missing == [], f"Profiles missing a search_intent: {missing}"


# ---------------------------------------------------------------------------
# 4c. Exactly 8 enabled sources exist.
# ---------------------------------------------------------------------------

def test_eight_enabled_sources(db):
    """The schema seeds exactly 8 sources with enabled = 1."""
    expected_names = {
        "greenhouse_coinbase",
        "greenhouse_stripe",
        "greenhouse_databricks",
        "greenhouse_pinterest",
        "greenhouse_airbnb",
        "greenhouse_groww",
        "lever_meesho",
        "himalayas",
    }

    rows = db.execute("SELECT name FROM sources WHERE enabled = 1").fetchall()
    actual_names = {r["name"] for r in rows}

    assert len(rows) == 8, (
        f"Expected 8 enabled sources, found {len(rows)}: {actual_names}"
    )
    assert actual_names == expected_names, (
        f"Enabled source names mismatch.\n  expected: {expected_names}\n  got:      {actual_names}"
    )


# ---------------------------------------------------------------------------
# 5. Foreign key enforcement actually fires (not just PRAGMA = 1).
#    Use an UPDATE so the row already satisfies all NOT NULL constraints –
#    the only possible failure is the FK violation itself.
# ---------------------------------------------------------------------------

def test_foreign_key_enforced(db):
    """A deliberate FK violation must raise IntegrityError matching 'FOREIGN KEY'."""
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        with db:
            db.execute("UPDATE search_intent SET profile_id = 99999 WHERE id = 1")
