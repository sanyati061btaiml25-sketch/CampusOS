"""Contract tests for the 36 labelled listing fixtures and gold.json."""

import datetime
import html
import json
import re
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "listings"
GOLD_PATH = FIXTURES_DIR / "gold.json"


def _visible_text(raw: str, suffix: str) -> str:
    if suffix.lower() != ".html":
        return raw
    stripped = re.sub(r"<[^>]+>", " ", raw)
    stripped = html.unescape(stripped)
    return re.sub(r"\s+", " ", stripped)


def test_gold_and_files_match_and_counts():
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    assert len(gold) == 36

    gold_files = [entry["file"] for entry in gold]
    assert len(gold_files) == len(set(gold_files)), "Duplicate filenames in gold.json"

    disk_files = sorted(
        p.name for p in FIXTURES_DIR.iterdir()
        if p.is_file() and p.name != "gold.json"
    )
    assert sorted(gold_files) == disk_files

    tech_count = sum(1 for e in gold if 1 <= int(e["file"][:2]) <= 12)
    fin_count = sum(1 for e in gold if 13 <= int(e["file"][:2]) <= 24)
    mid_count = sum(1 for e in gold if 25 <= int(e["file"][:2]) <= 36)
    assert (tech_count, fin_count, mid_count) == (12, 12, 12)


def test_gold_deadlines_and_verbatim_evidence():
    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    for entry in gold:
        dl = entry["deadline"]
        if dl is not None:
            datetime.date.fromisoformat(dl)
        ev = entry["deadline_evidence"]
        if ev is not None:
            raw = (FIXTURES_DIR / entry["file"]).read_text(encoding="utf-8")
            vis = _visible_text(raw, Path(entry["file"]).suffix)
            assert ev in vis, f"deadline_evidence not verbatim in {entry['file']}: {ev!r}"
