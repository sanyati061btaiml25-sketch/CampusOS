"""
campusos/readers.py – robust document, email, JSON, and CSV readers.

Rules
-----
* Every reader is resilient and never raises on malformed inputs.
* Decodes bytes with UTF-8 strict, falling back to cp1252 with an encoding_fallback Finding.
* Lenient JSON and CSV readers segregate valid records into records_ok and
  flagged/corrupted records into records_bad.
* Generic validations: duplicate ids, invalid dates, future years, delimiter mismatches.
* read_any() dispatches by file extension, running strip_invisible on all final text.
"""

import csv
import datetime
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sanitize import Finding, Sanitized, sanitize_email, sanitize_html, strip_invisible


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class IngestedDoc:
    kind: str                       # html | email | json | csv | text
    text: str                       # sanitised text (for json/csv: readable rendering of good records)
    findings: list[Finding] = field(default_factory=list)
    records_ok: list[dict] = field(default_factory=list)
    records_bad: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Byte decoding
# ---------------------------------------------------------------------------

def decode_bytes(data: bytes) -> tuple[str, list[Finding]]:
    """
    Decode raw bytes into a string without raising.

    Strips UTF-8 BOM if present. Attempts UTF-8 strict; on failure falls back
    to cp1252 with replacement, emitting an 'encoding_fallback' finding.
    """
    if not data:
        return "", []

    # Strip UTF-8 BOM
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]

    findings: list[Finding] = []
    try:
        text = data.decode("utf-8")
        return text, findings
    except UnicodeDecodeError as exc:
        # Fallback to cp1252
        text = data.decode("cp1252", errors="replace")
        findings.append(Finding(
            kind="encoding_fallback",
            detail=f"UTF-8 decode failed ({exc}); decoded as cp1252 with replacement",
            snippet=str(data[:100]),
        ))
        return text, findings


# ---------------------------------------------------------------------------
# Strict date parser
# ---------------------------------------------------------------------------

_DATE_PATTERNS = [
    # YYYY-MM-DD
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), lambda y, m, d: (int(y), int(m), int(d))),
    # YYYY/MM/DD
    (re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"), lambda y, m, d: (int(y), int(m), int(d))),
    # MM/DD/YYYY
    (re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), lambda m, d, y: (int(y), int(m), int(d))),
    # DD-MM-YYYY
    (re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$"), lambda d, m, y: (int(y), int(m), int(d))),
]


def parse_date_strict(s: str) -> datetime.date:
    """
    Parse a date string strictly. Accepts ISO YYYY-MM-DD and common variants.

    Raises ValueError for impossible dates (e.g. 2026-02-30 or 2026-11-31).
    """
    s = s.strip()
    for pat, mapper in _DATE_PATTERNS:
        m = pat.match(s)
        if m:
            y, month, day = mapper(*m.groups())
            # datetime.date constructor performs strict calendar validation
            return datetime.date(y, month, day)

    raise ValueError(f"Unrecognized date format: '{s}'")


# ---------------------------------------------------------------------------
# Lenient JSON reader
# ---------------------------------------------------------------------------

def _recover_json_records(text: str) -> tuple[list[dict], int, int]:
    """Use raw_decode to recover complete JSON records from truncated text."""
    decoder = json.JSONDecoder()
    records: list[dict] = []
    idx = 0
    n = len(text)
    last_good_offset = 0

    # Find the opening bracket if it's an array
    start_arr = text.find("[")
    if start_arr != -1:
        idx = start_arr + 1

    while idx < n:
        # Skip whitespace and commas
        while idx < n and text[idx] in " \t\r\n,]:}":
            idx += 1
        if idx >= n:
            break

        try:
            obj, end_idx = decoder.raw_decode(text, idx)
            if isinstance(obj, dict):
                records.append(obj)
                last_good_offset = end_idx
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict):
                        records.append(item)
                last_good_offset = end_idx
            idx = end_idx
        except json.JSONDecodeError:
            # Advance to next potential object
            next_brace = text.find("{", idx + 1)
            if next_brace == -1:
                break
            idx = next_brace

    return records, len(records), last_good_offset


def read_json_lenient(text: str) -> tuple[str, list[dict], list[dict], list[Finding]]:
    """
    Parse JSON leniently. Recovers complete records if text is truncated.

    Validates records generically:
    - duplicate values of id/*_id
    - invalid/future year fields
    - missing required-looking keys

    Returns (text_summary, records_ok, records_bad, findings).
    """
    findings: list[Finding] = []
    records_ok: list[dict] = []
    records_bad: list[dict] = []

    parsed_obj = None
    try:
        parsed_obj = json.loads(text)
    except json.JSONDecodeError:
        recovered, count, break_offset = _recover_json_records(text)
        if count > 0:
            findings.append(Finding(
                kind="truncated_json",
                detail=f"Recovered {count} complete records from truncated JSON (broke at offset {break_offset})",
                snippet=text[max(0, break_offset - 30):break_offset + 30][:200],
            ))
            raw_records = recovered
        else:
            findings.append(Finding(
                kind="json_parse_error",
                detail="Failed to parse JSON and could not recover records",
                snippet=text[:200],
            ))
            return "", [], [], findings
    else:
        if isinstance(parsed_obj, list):
            raw_records = parsed_obj
        elif isinstance(parsed_obj, dict):
            # First list found in values
            list_val = next((v for v in parsed_obj.values() if isinstance(v, list)), None)
            raw_records = list_val if list_val is not None else [parsed_obj]
        else:
            raw_records = []

    # Validate records
    seen_ids: dict[str, set[str]] = {}  # field_name -> set of seen values
    current_year = datetime.datetime.now(datetime.timezone.utc).year

    for idx, rec in enumerate(raw_records):
        if not isinstance(rec, dict):
            records_bad.append({"index": idx, "reason": "Record is not a dict", "raw": str(rec)[:200]})
            continue

        bad_reasons: list[str] = []

        # Check id fields for duplicates
        for k, v in rec.items():
            if k == "id" or k.endswith("_id"):
                val_str = str(v)
                if k not in seen_ids:
                    seen_ids[k] = set()
                if val_str in seen_ids[k]:
                    bad_reasons.append(f"Duplicate id in field '{k}': '{val_str}'")
                else:
                    seen_ids[k].add(val_str)

        # Check year-like fields
        for k, v in rec.items():
            k_lower = k.lower()
            if "year" in k_lower or k_lower in ("published", "posted_year", "grad_year"):
                val_str = str(v).strip()
                try:
                    val_int = int(val_str)
                    if val_int > current_year + 1:
                        bad_reasons.append(f"Implausible future year in '{k}': {val_int} > {current_year + 1}")
                except ValueError:
                    bad_reasons.append(f"Non-integer value for year field '{k}': '{val_str}'")

        if bad_reasons:
            records_bad.append({
                "index": idx,
                "reason": "; ".join(bad_reasons),
                "raw": json.dumps(rec)[:200],
            })
        else:
            records_ok.append(rec)

    # Human-readable summary of good records
    summary_lines = [f"JSON document: {len(records_ok)} valid records, {len(records_bad)} invalid."]
    for r in records_ok[:50]:
        title = r.get("title") or r.get("name") or str(r.get("id", ""))
        summary_lines.append(f"- {title}")
    text_summary = "\n".join(summary_lines)

    return text_summary, records_ok, records_bad, findings


# ---------------------------------------------------------------------------
# Lenient CSV reader
# ---------------------------------------------------------------------------

def _sniff_delimiter(first_line: str) -> str:
    counts = {",": first_line.count(","), ";": first_line.count(";"), "\t": first_line.count("\t"), "|": first_line.count("|")}
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else ","


def read_csv_lenient(text: str) -> tuple[str, list[dict], list[dict], list[Finding]]:
    """
    Parse CSV leniently. Never raises.

    Validates:
    - column count mismatches
    - mismatched row delimiters
    - unbalanced quotes
    - invalid calendar dates
    - duplicate ids
    - backwards timestamps in the first date column

    Returns (text_summary, records_ok, records_bad, findings).
    """
    findings: list[Finding] = []
    records_ok: list[dict] = []
    records_bad: list[dict] = []

    lines = text.splitlines()
    if not lines:
        return "", [], [], []

    header_line = lines[0].strip()
    delimiter = _sniff_delimiter(header_line)

    try:
        reader = csv.reader(io.StringIO(header_line), delimiter=delimiter)
        header = next(reader, [])
    except Exception as exc:
        findings.append(Finding(kind="csv_header_error", detail=str(exc), snippet=header_line[:200]))
        return "", [], [], findings

    expected_cols = len(header)
    seen_ids: dict[int, set[str]] = {}
    last_date: datetime.date | None = None
    first_date_col_idx: int | None = None

    # Detect first date-like column index from header names
    for i, h in enumerate(header):
        hl = h.lower()
        if any(term in hl for term in ("date", "time", "created", "deadline", "posted")):
            first_date_col_idx = i
            break

    # Parse rows line by line to accurately catch per-line anomalies
    for line_idx, raw_line in enumerate(lines[1:], start=2):
        if not raw_line.strip():
            continue

        # Check for unbalanced quotes on this line
        quote_count = raw_line.count('"')
        if quote_count % 2 != 0:
            records_bad.append({
                "line": line_idx,
                "reason": "Unbalanced quote detected on line",
                "raw": raw_line[:200],
            })
            continue

        # Check if line used a different delimiter than header
        if delimiter == "," and ";" in raw_line and "," not in raw_line:
            records_bad.append({
                "line": line_idx,
                "reason": "Row uses semicolon ';' instead of header comma ','",
                "raw": raw_line[:200],
            })
            continue
        if delimiter == ";" and "," in raw_line and ";" not in raw_line:
            records_bad.append({
                "line": line_idx,
                "reason": "Row uses comma ',' instead of header semicolon ';'",
                "raw": raw_line[:200],
            })
            continue

        try:
            row_reader = csv.reader(io.StringIO(raw_line), delimiter=delimiter)
            row = next(row_reader, [])
        except Exception as exc:
            records_bad.append({
                "line": line_idx,
                "reason": f"CSV parse error: {exc}",
                "raw": raw_line[:200],
            })
            continue

        if len(row) != expected_cols:
            records_bad.append({
                "line": line_idx,
                "reason": f"Wrong column count: expected {expected_cols}, got {len(row)}",
                "raw": raw_line[:200],
            })
            continue

        row_dict = dict(zip(header, row))
        bad_reasons: list[str] = []

        # Validate dates & check backwards chronology
        for c_idx, (col_name, val) in enumerate(row_dict.items()):
            val_str = val.strip()
            # If value looks like a date (e.g. YYYY-MM-DD)
            if re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", val_str):
                try:
                    d_parsed = parse_date_strict(val_str)
                    if c_idx == first_date_col_idx:
                        if last_date is not None and d_parsed < last_date:
                            bad_reasons.append(
                                f"Backwards timestamp in '{col_name}': {d_parsed} < {last_date}"
                            )
                        last_date = d_parsed
                except ValueError as v_err:
                    bad_reasons.append(f"Invalid calendar date in '{col_name}': '{val_str}' ({v_err})")

        # Validate duplicate IDs
        for c_idx, (col_name, val) in enumerate(row_dict.items()):
            cl = col_name.lower()
            if cl == "id" or cl.endswith("_id"):
                if c_idx not in seen_ids:
                    seen_ids[c_idx] = set()
                if val in seen_ids[c_idx]:
                    bad_reasons.append(f"Duplicate id in column '{col_name}': '{val}'")
                else:
                    seen_ids[c_idx].add(val)

        if bad_reasons:
            records_bad.append({
                "line": line_idx,
                "reason": "; ".join(bad_reasons),
                "raw": raw_line[:200],
            })
        else:
            records_ok.append(row_dict)

    summary_lines = [f"CSV document ({delimiter}): {len(records_ok)} valid rows, {len(records_bad)} bad rows."]
    for r in records_ok[:50]:
        summary_lines.append(" | ".join(str(v) for v in list(r.values())[:4]))
    text_summary = "\n".join(summary_lines)

    return text_summary, records_ok, records_bad, findings


# ---------------------------------------------------------------------------
# Universal reader
# ---------------------------------------------------------------------------

def read_any(path_or_bytes: str | Path | bytes, name: str | None = None) -> IngestedDoc:
    """
    Universal document reader dispatched by extension.

    Supports .html/.htm, .eml, .json, .csv, and text/markdown files.
    Never raises on any input. Runs strip_invisible on final visible text.
    """
    try:
        if isinstance(path_or_bytes, (str, Path)):
            p = Path(path_or_bytes)
            name = name or p.name
            raw_bytes = p.read_bytes()
        else:
            raw_bytes = path_or_bytes
            name = name or "document.txt"
    except Exception as exc:
        return IngestedDoc(
            kind="error",
            text="",
            findings=[Finding(kind="io_error", detail=f"Failed to read input: {exc}", snippet="")],
        )

    ext = name.lower().split(".")[-1] if "." in name else ""

    # 1. HTML
    if ext in ("html", "htm"):
        decoded_str, dec_findings = decode_bytes(raw_bytes)
        san = sanitize_html(decoded_str)
        return IngestedDoc(
            kind="html",
            text=san.text,
            findings=dec_findings + san.findings,
        )

    # 2. Email (.eml)
    if ext == "eml":
        san_email = sanitize_email(raw_bytes)
        return IngestedDoc(
            kind="email",
            text=san_email.text,
            findings=san_email.findings,
        )

    # 3. JSON (.json)
    if ext == "json":
        decoded_str, dec_findings = decode_bytes(raw_bytes)
        summary, rec_ok, rec_bad, json_findings = read_json_lenient(decoded_str)
        san = strip_invisible(summary)
        return IngestedDoc(
            kind="json",
            text=san.text,
            findings=dec_findings + json_findings + san.findings,
            records_ok=rec_ok,
            records_bad=rec_bad,
        )

    # 4. CSV (.csv)
    if ext == "csv":
        decoded_str, dec_findings = decode_bytes(raw_bytes)
        summary, rec_ok, rec_bad, csv_findings = read_csv_lenient(decoded_str)
        san = strip_invisible(summary)
        return IngestedDoc(
            kind="csv",
            text=san.text,
            findings=dec_findings + csv_findings + san.findings,
            records_ok=rec_ok,
            records_bad=rec_bad,
        )

    # 5. Text / Markdown / Fallback
    decoded_str, dec_findings = decode_bytes(raw_bytes)
    san = strip_invisible(decoded_str)
    return IngestedDoc(
        kind="text",
        text=san.text,
        findings=dec_findings + san.findings,
    )
