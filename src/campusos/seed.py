"""
campusos/seed.py – populate a demo database with mock data.

Safety
------
Refuses to run if the DB path ends with 'campusos.db' (the live DB).
Every row written is tagged mode='mock' so live queries can exclude it.

Usage
-----
    python -m campusos.seed                # writes to data/demo.db
    python -m campusos.seed --db path/to/demo.db

Entry point (after pip install -e .):
    campusos-seed
"""

import argparse
import json
import sys
from pathlib import Path

from .db import connect, init_db, now_iso


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_RUNS = [
    {
        "trigger": "scheduler",
        "state": "done",
        "stage": "done",
        "mode": "mock",
        "stop_reason": None,
        "used_requests": 3,
        "budget_json": json.dumps({"max_requests": 200, "max_seconds": 300}),
    },
]

_MOCK_OPPORTUNITIES = [
    {
        "external_id": "demo-gh-1001",
        "canonical_key": "greenhouse_coinbase:demo-gh-1001",
        "title": "Software Engineer Intern (Demo)",
        "company": "Coinbase",
        "apply_url": "https://boards.greenhouse.io/coinbase/jobs/demo-gh-1001",
        "location_raw": "Remote – USA",
        "content_hash": "demo_hash_1001",
        "mode": "mock",
    },
    {
        "external_id": "demo-gh-1002",
        "canonical_key": "greenhouse_coinbase:demo-gh-1002",
        "title": "Data Science Intern (Demo)",
        "company": "Coinbase",
        "apply_url": "https://boards.greenhouse.io/coinbase/jobs/demo-gh-1002",
        "location_raw": "San Francisco, CA",
        "content_hash": "demo_hash_1002",
        "mode": "mock",
    },
    {
        "external_id": "demo-lv-m1",
        "canonical_key": "lever_meesho:demo-lv-m1",
        "title": "Product Analyst Intern (Demo)",
        "company": "Meesho",
        "apply_url": "https://jobs.lever.co/meesho/demo-lv-m1",
        "location_raw": "Bengaluru, India",
        "content_hash": "demo_hash_lv_m1",
        "mode": "mock",
    },
    {
        "external_id": "demo-him-1",
        "canonical_key": "himalayas:demo-him-1",
        "title": "Backend Engineer (Remote, Demo)",
        "company": "Acme Corp",
        "apply_url": "https://himalayas.app/jobs/demo-him-1/apply",
        "location_raw": "Remote",
        "content_hash": "demo_hash_him_1",
        "mode": "mock",
    },
]


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------

def _seed(conn, verbose: bool = True) -> None:
    ts = now_iso()

    # Ensure schema is up-to-date
    init_db(conn)

    # Insert mock run
    with conn:
        cur = conn.execute(
            """INSERT INTO runs (trigger, state, stage, mode, stop_reason,
                                 used_requests, budget_json, ended_at)
               VALUES (:trigger, :state, :stage, :mode, :stop_reason,
                       :used_requests, :budget_json, :ended_at)""",
            {**_MOCK_RUNS[0], "ended_at": ts},
        )
        run_id = cur.lastrowid

    if verbose:
        print(f"  inserted run id={run_id}")

    # Look up source ids (these were seeded by init_db)
    source_map = {
        row["name"]: row["id"]
        for row in conn.execute("SELECT id, name FROM sources").fetchall()
    }

    for opp in _MOCK_OPPORTUNITIES:
        # Determine source from canonical_key prefix
        src_name_prefix = opp["canonical_key"].split(":")[0]
        source_id = source_map.get(src_name_prefix)

        # Write snapshot
        with conn:
            snap_cur = conn.execute(
                """INSERT INTO snapshots
                       (source_id, run_id, content_hash, status, http_status,
                        duration_ms, item_count)
                   VALUES (?, ?, ?, 'ok', 200, 1, 1)""",
                (source_id, run_id, opp["content_hash"]),
            )
            snap_id = snap_cur.lastrowid

        # Write opportunity (INSERT OR IGNORE so seed is idempotent)
        with conn:
            conn.execute(
                """INSERT OR IGNORE INTO opportunities
                       (source_id, external_id, canonical_key, snapshot_id,
                        title, company, apply_url, location_raw, content_hash,
                        first_seen_at, last_seen_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    source_id, opp["external_id"], opp["canonical_key"], snap_id,
                    opp["title"], opp["company"], opp["apply_url"],
                    opp["location_raw"], opp["content_hash"], ts, ts,
                ),
            )

        if verbose:
            print(f"  inserted opportunity: {opp['title']}")

    # Write a coverage row for the demo run
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO coverage
                   (run_id, sources_checked, sources_skipped, sources_failed,
                    listings_found, listings_unchanged, after_dedup)
               VALUES (?, 3, 0, 0, ?, 0, ?)""",
            (run_id, len(_MOCK_OPPORTUNITIES), len(_MOCK_OPPORTUNITIES)),
        )

    if verbose:
        print(f"  demo DB seeded: {len(_MOCK_OPPORTUNITIES)} opportunities, 1 run")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a demo database with mock CampusOS data"
    )
    parser.add_argument(
        "--db",
        default="data/demo.db",
        help="path to target SQLite database (default: data/demo.db)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)

    # Safety guard: refuse to seed the live DB
    if db_path.name == "campusos.db":
        print(
            f"ERROR: refusing to seed '{db_path}' — "
            "this looks like the live database.\n"
            "Use --db to specify a demo path, e.g. --db data/demo.db",
            file=sys.stderr,
        )
        sys.exit(1)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Seeding demo database: {db_path}")
    conn = connect(str(db_path))
    _seed(conn)
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
