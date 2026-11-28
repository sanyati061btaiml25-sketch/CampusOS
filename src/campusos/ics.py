"""RFC 5545 (.ics) calendar renderer for CampusOS deadline reminders."""

from __future__ import annotations

import datetime
import re
from urllib.parse import urlparse

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_NEWLINES_RE = re.compile(r"\r\n|\r|\n")


def _strip_controls(value: str) -> str:
    """Remove ASCII control characters while preserving printable Unicode."""
    return _CONTROL_CHARS_RE.sub("", value)


def _clean_single_line(value: str | None, max_len: int) -> str:
    """Normalize a field into a single safe line and cap its length."""
    if not value:
        return ""
    cleaned = _NEWLINES_RE.sub(" ", str(value))
    cleaned = _strip_controls(cleaned).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned


def _escape_ics_text(value: str) -> str:
    """Escape text per RFC 5545 Section 3.3.11 (backslash, semicolon, comma, newline)."""
    text = _strip_controls(value)
    text = _NEWLINES_RE.sub("\n", text)
    text = text.replace("\\", "\\\\")
    text = text.replace(";", "\\;")
    text = text.replace(",", "\\,")
    text = text.replace("\n", "\\n")
    return text


def _fold_line_octets(line: str, max_octets: int = 75) -> str:
    """Fold a content line at 75 UTF-8 octets without splitting multibyte chars."""
    encoded = line.encode("utf-8")
    if len(encoded) <= max_octets:
        return line

    chunks: list[str] = []
    current_chars: list[str] = []
    current_bytes = 0
    limit = max_octets

    for ch in line:
        ch_bytes = len(ch.encode("utf-8"))
        if current_bytes + ch_bytes > limit and current_chars:
            chunks.append("".join(current_chars))
            current_chars = [ch]
            current_bytes = ch_bytes
            limit = max_octets - 1  # account for leading space on continuation line
        else:
            current_chars.append(ch)
            current_bytes += ch_bytes

    if current_chars:
        chunks.append("".join(current_chars))

    return "\r\n ".join(chunks)


def _validate_http_url(raw_url: str) -> str:
    """Ensure apply_url is a valid http(s) URL without control characters."""
    if not isinstance(raw_url, str):
        raise ValueError("apply_url must be a string")
    cleaned = _strip_controls(raw_url).strip()
    if any(ch in cleaned for ch in ("\r", "\n", " ", "\t")):
        raise ValueError("apply_url must not contain whitespace or line breaks")
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"apply_url must be an http(s) URL: {raw_url!r}")
    return cleaned


def build_ics(
    *,
    uid_key: str,
    title: str,
    company: str,
    deadline: datetime.date,
    apply_url: str,
    evidence: str | None,
    profile_label: str,
    now: datetime.datetime | None = None,
) -> str:
    """Build a deterministic, injection-safe RFC 5545 calendar reminder."""
    if not isinstance(deadline, datetime.date):
        raise ValueError("deadline must be a datetime.date")
    if isinstance(deadline, datetime.datetime):
        deadline_date = deadline.date()
    else:
        deadline_date = deadline

    ref_now = now if now is not None else datetime.datetime.now(datetime.timezone.utc)
    if ref_now.tzinfo is None:
        ref_utc = ref_now.replace(tzinfo=datetime.timezone.utc)
    else:
        ref_utc = ref_now.astimezone(datetime.timezone.utc)

    if deadline_date < ref_utc.date():
        raise ValueError(f"deadline {deadline_date.isoformat()} is in the past")

    safe_url = _validate_http_url(apply_url)

    safe_uid_key = re.sub(r"[^A-Za-z0-9._:-]", "-", _clean_single_line(uid_key, 120)) or "item"
    safe_title = _clean_single_line(title, 120) or "Opportunity"
    safe_company = _clean_single_line(company, 80) or "Unknown Company"
    safe_evidence = _clean_single_line(evidence, 300)
    safe_profile = _clean_single_line(profile_label, 80) or "default"

    dtstamp = ref_utc.strftime("%Y%m%dT%H%M%SZ")
    dtstart = deadline_date.strftime("%Y%m%d")
    dtend = (deadline_date + datetime.timedelta(days=1)).strftime("%Y%m%d")

    summary = _escape_ics_text(f"Deadline: {safe_title} - {safe_company}")
    desc_parts = [f"Apply: {safe_url}"]
    if safe_evidence:
        desc_parts.append(f"Evidence: {safe_evidence}")
    desc_parts.append(f"Profile: {safe_profile}")
    description = _escape_ics_text("\n".join(desc_parts))

    alarm_desc = _escape_ics_text(f"Application deadline reminder: {safe_title} - {safe_company}")

    raw_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CampusOS//Deadline Reminder//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{safe_uid_key}@campusos.invalid",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        f"URL:{safe_url}",
        "BEGIN:VALARM",
        "TRIGGER:-P3D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{alarm_desc}",
        "END:VALARM",
        "BEGIN:VALARM",
        "TRIGGER:-P1D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{alarm_desc}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]

    folded = [_fold_line_octets(line, 75) for line in raw_lines]
    return "\r\n".join(folded) + "\r\n"
