"""
tests/test_readers.py – tests for document, email, JSON, and CSV readers.
"""

import datetime
import random
from pathlib import Path

import pytest

from campusos.readers import (
    IngestedDoc,
    decode_bytes,
    parse_date_strict,
    read_any,
    read_csv_lenient,
    read_json_lenient,
)


def test_decode_bytes():
    """cp1252 with pound sign and accents decodes with encoding_fallback; UTF-8 produces no findings."""
    # Pure UTF-8
    utf8_bytes = "Salary: £50,000 – Résumé".encode("utf-8")
    text, findings = decode_bytes(utf8_bytes)
    assert "£50,000" in text
    assert "Résumé" in text
    assert len(findings) == 0

    # cp1252 specific bytes: 0xa3 is £ in cp1252, invalid in UTF-8
    cp1252_bytes = b"Price: \xa3100 and caf\xe9"
    text_cp, findings_cp = decode_bytes(cp1252_bytes)
    assert "£100" in text_cp
    assert "café" in text_cp
    assert any(f.kind == "encoding_fallback" for f in findings_cp)


def test_truncated_and_invalid_json():
    """Truncated JSON recovers complete records; duplicate id, '20O4', and year 2031 are reported in records_bad."""
    truncated = """
    [
        {"id": 1, "title": "Good Job", "year": 2026},
        {"id": 2, "title": "Duplicate ID Job", "year": 2026},
        {"id": 2, "title": "Second Duplicate ID", "year": 2026},
        {"id": 3, "title": "Typo Year Job", "year": "20O4"},
        {"id": 4, "title": "Far Future Job", "year": 2031},
        {"id": 5, "title": "Incomplete Cutoff"
    """
    summary, rec_ok, rec_bad, findings = read_json_lenient(truncated)

    # Truncation was caught and recovered records
    assert any(f.kind == "truncated_json" for f in findings)

    # Valid record should be in rec_ok
    ok_ids = [r["id"] for r in rec_ok]
    assert 1 in ok_ids

    # Bad records should identify the issues
    bad_reasons = " ".join(b["reason"] for b in rec_bad)
    assert "Duplicate id" in bad_reasons
    assert "Non-integer value for year" in bad_reasons
    assert "Implausible future year" in bad_reasons


def test_csv_lenient_validations():
    """CSV with unbalanced quote, semicolon row, extra column, month 13, Nov 31, and duplicate id."""
    csv_text = """id,title,date,company
1,Software Engineer,2026-05-15,Acme
2,"Unbalanced quote row,2026-06-01,Beta
3;Semicolon delimiter row;2026-06-15;Gamma
4,Extra column row,2026-07-01,Delta,Surprise
5,Invalid month row,2026-13-10,Epsilon
6,Invalid leap day,2026-11-31,Zeta
1,Duplicate ID row,2026-08-01,Eta
7,Valid Final Row,2026-09-01,Theta
"""
    summary, rec_ok, rec_bad, findings = read_csv_lenient(csv_text)

    # Valid rows in rec_ok
    ok_ids = [r["id"] for r in rec_ok]
    assert "1" in ok_ids
    assert "7" in ok_ids

    # Bad rows reported with reasons and line numbers
    bad_lines = [b["line"] for b in rec_bad]
    bad_reasons = " ".join(b["reason"] for b in rec_bad)

    assert "Unbalanced quote" in bad_reasons
    assert "semicolon" in bad_reasons
    assert "Wrong column count" in bad_reasons
    assert "Invalid calendar date" in bad_reasons
    assert "Duplicate id" in bad_reasons


def test_csv_backwards_timestamps():
    """CSV with dates going backwards is caught in records_bad."""
    csv_text = """id,title,date
1,First Job,2026-05-10
2,Second Job,2026-05-01
"""
    summary, rec_ok, rec_bad, findings = read_csv_lenient(csv_text)
    assert len(rec_bad) >= 1
    assert any("Backwards timestamp" in b["reason"] for b in rec_bad)


def test_parse_date_strict():
    """parse_date_strict raises for impossible dates; valid dates succeed."""
    with pytest.raises(ValueError):
        parse_date_strict("2026-02-30")

    with pytest.raises(ValueError):
        parse_date_strict("2026-11-31")

    valid = parse_date_strict("2026-02-28")
    assert valid == datetime.date(2026, 2, 28)

    iso_valid = parse_date_strict("2026-10-15")
    assert iso_valid == datetime.date(2026, 10, 15)


def test_read_any_fuzz():
    """Fuzz read_any with random bytes, empty inputs, 5 MB lines, and unclosed tags: never raises."""
    # Empty input
    doc_empty = read_any(b"", name="test.html")
    assert doc_empty.text == ""

    # 5 MB line
    large_line = b"A" * (5 * 1024 * 1024)
    doc_large = read_any(large_line, name="large.txt")
    assert doc_large.kind == "text"

    # Deeply nested unclosed tags
    nested = ("<div><span>" * 500).encode("utf-8")
    doc_nested = read_any(nested, name="nested.html")
    assert doc_nested.kind == "html"

    # 200 random byte strings with fixed seed
    rng = random.Random(42)
    for _ in range(200):
        length = rng.randint(10, 2048)
        rand_bytes = rng.randbytes(length)
        ext = rng.choice(["html", "json", "csv", "eml", "txt"])
        doc = read_any(rand_bytes, name=f"fuzz.{ext}")
        assert isinstance(doc, IngestedDoc)


def test_trap_pack_inputs_optional():
    """If tests/trap-pack/inputs/ exists, read_any never raises on any file."""
    trap_dir = Path("tests/trap-pack/inputs")
    if not trap_dir.exists():
        pytest.skip("tests/trap-pack/inputs directory not present")

    for fpath in trap_dir.iterdir():
        if fpath.is_file():
            doc = read_any(fpath)
            assert isinstance(doc, IngestedDoc)
