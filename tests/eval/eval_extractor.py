"""Evaluation script comparing extractor outputs against fixtures/listings/gold.json.

Always exits 0 (report-only). Prints per-field accuracy (correct / wrong / unknown)
and writes tests/eval/results.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "listings"
GOLD_PATH = FIXTURES_DIR / "gold.json"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"

EVAL_FIELDS = [
    "seniority",
    "employment_type",
    "min_education",
    "deadline",
    "deadline_kind",
    "conflict",
]


def _load_extractor(name: str):
    """Import read_any and the named extractor from campusos if available."""
    try:
        from campusos import extractors  # type: ignore
        from campusos.readers import read_any  # type: ignore
    except ImportError:
        return None, None
    fn = getattr(extractors, name, None)
    return read_any, fn


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate CampusOS extractor on gold fixtures.")
    parser.add_argument("--extractor", default="rules", help="Extractor name in campusos.extractors")
    args = parser.parse_args()

    gold = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    read_any, extractor_fn = _load_extractor(args.extractor)

    if read_any is None or extractor_fn is None:
        # TODO: Member 1 has not merged campusos.readers / campusos.extractors yet.
        summary = {
            "extractor": args.extractor,
            "status": "pending_extractor_merge",
            "total_listings": len(gold),
            "fields": {f: {"correct": 0, "wrong": 0, "unknown": len(gold)} for f in EVAL_FIELDS},
        }
        RESULTS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"[TODO] campusos.extractors.{args.extractor} not yet merged; wrote baseline report to {RESULTS_PATH}")
        return 0

    counts = {f: {"correct": 0, "wrong": 0, "unknown": 0} for f in EVAL_FIELDS}
    for entry in gold:
        raw_path = FIXTURES_DIR / entry["file"]
        text = read_any(raw_path)
        pred = extractor_fn(text) or {}
        for f in EVAL_FIELDS:
            expected = entry.get(f)
            actual = pred.get(f)
            if actual in (None, "unknown", ""):
                counts[f]["unknown"] += 1
            elif actual == expected:
                counts[f]["correct"] += 1
            else:
                counts[f]["wrong"] += 1

    print(f"Extractor: {args.extractor} ({len(gold)} listings)")
    for f, c in counts.items():
        print(f"  {f:18s} correct={c['correct']:2d}  wrong={c['wrong']:2d}  unknown={c['unknown']:2d}")

    summary = {"extractor": args.extractor, "status": "ok", "total_listings": len(gold), "fields": counts}
    RESULTS_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
