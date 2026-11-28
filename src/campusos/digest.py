"""Plain-text and HTML digest renderer for CampusOS."""

from __future__ import annotations

from dataclasses import dataclass
import html
from urllib.parse import urlparse


@dataclass
class Digest:
    subject: str
    text: str
    html: str


def _safe_http_url(raw_url: object) -> str | None:
    if not isinstance(raw_url, str):
        return None
    cleaned = raw_url.strip()
    if not cleaned or any(ch in cleaned for ch in ("\r", "\n", "\t")):
        return None
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
        return cleaned
    return None


def _run_date_label(run: dict) -> str:
    for key in ("date", "started_at", "ended_at"):
        val = run.get(key)
        if isinstance(val, str) and len(val) >= 10:
            return val[:10]
    return "undated"


def _norm_score(raw: object) -> float:
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    return 0.0


def _fmt_item_text(item: dict) -> list[str]:
    title = str(item.get("title") or "unknown")
    company = str(item.get("company") or "unknown")
    location = str(item.get("location_raw") or "unknown")
    seniority = str(item.get("seniority") or "unknown")
    pct = round(_norm_score(item.get("score")) * 100)
    reasons = [str(r) for r in (item.get("reasons") or [])[:3]]
    deadline = item.get("deadline") or "unknown"
    evidence = item.get("deadline_evidence")
    raw_url = str(item.get("apply_url") or "unknown")
    flags = [str(f) for f in (item.get("flags") or [])]

    flag_marker = f" [FLAGS: {', '.join(flags)}]" if flags else ""
    lines = [
        f"- {title} at {company} ({location}, {seniority}) — {pct}% match{flag_marker}",
        f"  Deadline: {deadline}" + (f' | Evidence: "{evidence}"' if evidence else ""),
    ]
    if reasons:
        lines.append(f"  Reasons: {'; '.join(reasons)}")
    lines.append(f"  Apply: {raw_url}")
    return lines


def _fmt_item_html(item: dict) -> str:
    title = html.escape(str(item.get("title") or "unknown"), quote=True)
    company = html.escape(str(item.get("company") or "unknown"), quote=True)
    location = html.escape(str(item.get("location_raw") or "unknown"), quote=True)
    seniority = html.escape(str(item.get("seniority") or "unknown"), quote=True)
    pct = round(_norm_score(item.get("score")) * 100)
    reasons = [html.escape(str(r), quote=True) for r in (item.get("reasons") or [])[:3]]
    deadline = html.escape(str(item.get("deadline") or "unknown"), quote=True)
    evidence = item.get("deadline_evidence")
    flags = [html.escape(str(f), quote=True) for f in (item.get("flags") or [])]

    safe_url = _safe_http_url(item.get("apply_url"))
    if safe_url:
        esc_url = html.escape(safe_url, quote=True)
        link_html = f'<a href="{esc_url}" rel="noopener noreferrer">{esc_url}</a>'
    else:
        link_html = html.escape(str(item.get("apply_url") or "unknown"), quote=True)

    flags_html = (
        f' <strong class="flag-marker">[FLAGS: {", ".join(flags)}]</strong>'
        if flags
        else ""
    )
    ev_html = (
        f' &middot; Evidence: <em>&ldquo;{html.escape(str(evidence), quote=True)}&rdquo;</em>'
        if evidence
        else ""
    )
    reasons_html = (
        f"<p>Reasons: {'; '.join(reasons)}</p>"
        if reasons
        else ""
    )

    return (
        "<li>"
        f"<strong>{title}</strong> at {company} ({location}, {seniority}) &mdash; {pct}% match{flags_html}"
        f"<p>Deadline: {deadline}{ev_html}</p>"
        f"{reasons_html}"
        f"<p>Apply: {link_html}</p>"
        "</li>"
    )


def render_digest(
    items: list[dict],
    *,
    profile_label: str,
    run: dict,
    review_count: int = 0,
    coverage: dict | None = None,
) -> Digest:
    """Render a deterministic plain-text and HTML digest for at most 15 items."""
    sorted_items = sorted(items, key=lambda it: _norm_score(it.get("score")), reverse=True)[:15]
    date_label = _run_date_label(run)
    count = len(sorted_items)

    if count == 0:
        subject = f"CampusOS Digest ({date_label}) — no new matches this run"
    else:
        subject = f"CampusOS Digest ({date_label}) — {count} matches for {profile_label}"

    new_items = [it for it in sorted_items if it.get("is_new") or not it.get("is_changed")]
    changed_items = [it for it in sorted_items if it.get("is_changed") and not it.get("is_new")]

    cov = coverage or {}
    x_sources = int(cov.get("sources_checked", 0))
    y_listings = int(cov.get("listings_found", 0))
    z_candidates = int(cov.get("after_dedup", 0))
    footer_cov = f"Checked {x_sources} sources, {y_listings} listings, {z_candidates} candidates"
    footer_disclaimer = "CampusOS never applies on your behalf. Review every link yourself."

    # Plain text
    text_lines = [subject, f"Profile: {profile_label}", ""]
    if count == 0:
        text_lines.append("no new matches this run")
        text_lines.append("")
    else:
        text_lines.append(f"New ({len(new_items)})")
        if new_items:
            for it in new_items:
                text_lines.extend(_fmt_item_text(it))
        else:
            text_lines.append("None")
        text_lines.append("")

        text_lines.append(f"Changed ({len(changed_items)})")
        if changed_items:
            for it in changed_items:
                text_lines.extend(_fmt_item_text(it))
        else:
            text_lines.append("None")
        text_lines.append("")

    text_lines.append(f"Needs your review ({review_count})")
    text_lines.append("")
    text_lines.append(footer_cov)
    text_lines.append(footer_disclaimer)
    text_body = "\n".join(text_lines)

    # HTML
    esc_subject = html.escape(subject, quote=True)
    esc_profile = html.escape(profile_label, quote=True)
    html_parts = [
        "<!doctype html>",
        "<html><body>",
        f"<h1>{esc_subject}</h1>",
        f"<p>Profile: <strong>{esc_profile}</strong></p>",
    ]
    if count == 0:
        html_parts.append("<p>no new matches this run</p>")
    else:
        html_parts.append(f"<h2>New ({len(new_items)})</h2>")
        if new_items:
            html_parts.append("<ul>" + "".join(_fmt_item_html(it) for it in new_items) + "</ul>")
        else:
            html_parts.append("<p>None</p>")

        html_parts.append(f"<h2>Changed ({len(changed_items)})</h2>")
        if changed_items:
            html_parts.append("<ul>" + "".join(_fmt_item_html(it) for it in changed_items) + "</ul>")
        else:
            html_parts.append("<p>None</p>")

    html_parts.append(f"<h2>Needs your review ({review_count})</h2>")
    html_parts.append(f"<footer><p>{html.escape(footer_cov, quote=True)}</p><p>{html.escape(footer_disclaimer, quote=True)}</p></footer>")
    html_parts.append("</body></html>")

    return Digest(subject=subject, text=text_body, html="\n".join(html_parts))
