"""
campusos/sanitize.py – deterministic text, HTML, and email sanitizer.

Rules
-----
* Untrusted text passes through here BEFORE any LLM sees it.
* Nothing is silently hidden from the human: every removal is recorded as a Finding.
* Detection is structural, not keyword-based. Benign text containing phrases
  like "ignore previous instructions" produces ZERO findings.
* Long base64/hex blobs (>= 40 chars) in attributes/meta tags are reported as
  encoded_blob and NEVER decoded.
"""

import email
import email.policy
import html.parser
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    kind: str      # hidden_element | html_comment | offscreen_text | zero_width | bidi_control |
                   # control_chars | encoded_blob | long_alt_text | script_or_style
    detail: str    # short human-readable explanation
    snippet: str   # up to 200 chars of what was removed (never more)


@dataclass
class Sanitized:
    text: str                  # visible, normalised text only
    findings: list[Finding]


@dataclass
class SanitizedEmail:
    from_addr: str
    reply_to: str
    subject: str
    message_id: str
    text: str                  # sanitised visible body
    attachments: list[dict]    # [{"filename": str, "text": str}]
    findings: list[Finding]


# ---------------------------------------------------------------------------
# Invisible & control character stripping
# ---------------------------------------------------------------------------

# Zero-width and invisible formatting characters
# U+200B..U+200F, U+2060..U+2064, U+FEFF, U+00AD
_ZERO_WIDTH_CHARS = {
    '\u200b', '\u200c', '\u200d', '\u200e', '\u200f',
    '\u2060', '\u2061', '\u2062', '\u2063', '\u2064',
    '\ufeff', '\u00ad',
}

# Bidirectional overrides and isolates
# U+202A..U+202E, U+2066..U+2069
_BIDI_CONTROLS = {
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
    '\u2066', '\u2067', '\u2068', '\u2069',
}


def strip_invisible(text: str) -> Sanitized:
    """
    Remove zero-width, bidi, and unprintable control characters, then NFKC-normalise.

    Findings are reported with count and surrounding context snippet.
    """
    if not text:
        return Sanitized(text="", findings=[])

    findings: list[Finding] = []
    zw_count = 0
    bidi_count = 0
    ctrl_count = 0
    zw_snippets: list[str] = []
    bidi_snippets: list[str] = []
    ctrl_snippets: list[str] = []

    out_chars: list[str] = []
    n = len(text)

    for i, c in enumerate(text):
        if c in _ZERO_WIDTH_CHARS:
            zw_count += 1
            if len(zw_snippets) < 3:
                start = max(0, i - 15)
                end = min(n, i + 15)
                zw_snippets.append(text[start:end])
            continue

        if c in _BIDI_CONTROLS:
            bidi_count += 1
            if len(bidi_snippets) < 3:
                start = max(0, i - 15)
                end = min(n, i + 15)
                bidi_snippets.append(text[start:end])
            continue

        cp = ord(c)
        # Control characters except newline (\n=0x0a) and tab (\t=0x09)
        if (cp < 32 and c not in ('\n', '\t', '\r')) or cp == 127 or (128 <= cp <= 159):
            ctrl_count += 1
            if len(ctrl_snippets) < 3:
                start = max(0, i - 15)
                end = min(n, i + 15)
                ctrl_snippets.append(text[start:end])
            continue

        out_chars.append(c)

    cleaned = "".join(out_chars)
    # NFKC normalisation
    normalised = unicodedata.normalize("NFKC", cleaned)

    if zw_count > 0:
        snip = " ... ".join(zw_snippets)[:200]
        findings.append(Finding(
            kind="zero_width",
            detail=f"Removed {zw_count} zero-width / invisible formatting characters",
            snippet=snip,
        ))

    if bidi_count > 0:
        snip = " ... ".join(bidi_snippets)[:200]
        findings.append(Finding(
            kind="bidi_control",
            detail=f"Removed {bidi_count} bidirectional control characters",
            snippet=snip,
        ))

    if ctrl_count > 0:
        snip = " ... ".join(ctrl_snippets)[:200]
        findings.append(Finding(
            kind="control_chars",
            detail=f"Removed {ctrl_count} unprintable control characters",
            snippet=snip,
        ))

    return Sanitized(text=normalised, findings=findings)


# ---------------------------------------------------------------------------
# HTML Sanitizer
# ---------------------------------------------------------------------------

_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

_BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "tr", "table", "blockquote",
}

_SUPPRESS_TAGS = {"script", "style", "noscript", "template"}

_BLOB_PATTERN = re.compile(r'^[A-Za-z0-9+/=_-]{40,}$')


def _is_color_white(val: str) -> bool:
    v = val.strip().lower().replace(" ", "")
    return v in {"#fff", "#ffffff", "white", "rgb(255,255,255)", "rgba(255,255,255,1)"}


def _is_dark_bg(val: str) -> bool:
    v = val.strip().lower().replace(" ", "")
    if v in {"#000", "#000000", "black", "rgb(0,0,0)"}:
        return True
    if v.startswith("#") and len(v) in (4, 7):
        try:
            if len(v) == 4:
                r, g, b = [int(x * 2, 16) for x in v[1:]]
            else:
                r = int(v[1:3], 16)
                g = int(v[3:5], 16)
                b = int(v[5:7], 16)
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            return luminance < 128
        except ValueError:
            pass
    return False


def _parse_styles(style_str: str) -> dict[str, str]:
    styles = {}
    for part in style_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            styles[k.strip().lower()] = v.strip().lower()
    return styles


def _is_hidden_by_style(styles: dict[str, str], parent_has_dark_bg: bool) -> tuple[bool, str, str]:
    """Return (is_hidden, kind, detail)."""
    # 1. display: none
    if styles.get("display") == "none":
        return True, "hidden_element", "display:none"

    # 2. visibility: hidden
    if styles.get("visibility") == "hidden":
        return True, "hidden_element", "visibility:hidden"

    # 3. opacity: 0
    op = styles.get("opacity")
    if op is not None:
        try:
            if float(op) == 0.0:
                return True, "hidden_element", "opacity:0"
        except ValueError:
            pass

    # 4. font-size: 0
    fs = styles.get("font-size")
    if fs is not None and (fs in ("0", "0px", "0pt", "0em", "0rem") or fs.startswith("0.")):
        try:
            num = re.findall(r"[\d.]+", fs)
            if num and float(num[0]) == 0.0:
                return True, "hidden_element", "font-size:0"
        except ValueError:
            pass

    # 5. Zero dimension with overflow: hidden
    overflow = styles.get("overflow", "")
    w = styles.get("width", "")
    h = styles.get("height", "")
    if "hidden" in overflow:
        if w in ("0", "0px") or h in ("0", "0px"):
            return True, "hidden_element", "zero-size element with overflow:hidden"

    # 6. text-indent <= -999
    ti = styles.get("text-indent", "")
    if ti:
        num = re.findall(r"-?\d+", ti)
        if num and int(num[0]) <= -999:
            return True, "offscreen_text", f"text-indent:{ti}"

    # 7. Offscreen positioning
    for pos_prop in ("left", "top", "margin-left", "margin-top"):
        val = styles.get(pos_prop, "")
        if val:
            num = re.findall(r"-?\d+", val)
            if num and int(num[0]) <= -999:
                return True, "offscreen_text", f"offscreen positioning {pos_prop}:{val}"

    # 8. Same colour as background (e.g. white on white)
    color = styles.get("color", "")
    bg = styles.get("background-color") or styles.get("background", "")
    if color and _is_color_white(color):
        if not parent_has_dark_bg and (not bg or _is_color_white(bg)):
            return True, "hidden_element", f"white text on light background (color:{color})"

    return False, "", ""


def _selector_matches(selector: str, tag: str, elem_id: str, classes: set[str]) -> bool:
    """Check if a CSS selector (.class, #id, tag, tag.class) matches the given element."""
    sel = selector.strip().lower()
    if not sel:
        return False
    if sel.startswith("#"):
        return sel[1:] == elem_id.lower()
    if "." in sel:
        parts = sel.split(".")
        stag = parts[0]
        required_classes = [c for c in parts[1:] if c]
        return (not stag or stag == tag.lower()) and all(c in classes for c in required_classes)
    return sel == tag.lower()


def _parse_css_rules(css_text: str) -> list[tuple[list[str], dict[str, str]]]:
    """
    Parse simple CSS rules from style blocks.
    Returns list of (selectors_list, styles_dict).
    Ignores @media, @import, comments, and unparseable constructs without raising.
    """
    rules: list[tuple[list[str], dict[str, str]]] = []
    if not css_text:
        return rules

    try:
        # Strip comments /* ... */
        clean = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
        # Strip @import lines
        clean = re.sub(r"@import\s+[^;]+;", "", clean, flags=re.IGNORECASE)
        # Strip @media and other at-rule blocks with nested braces
        clean = re.sub(r"@media\b[^{]*\{(?:[^{}]*\{[^{}]*\})*?[^{}]*\}", "", clean, flags=re.DOTALL | re.IGNORECASE)
        # Strip any other @ directives
        clean = re.sub(r"@[^{;]+;", "", clean)

        # Match selector { declarations }
        for match in re.finditer(r"([^{}]+)\{([^{}]+)\}", clean):
            raw_sel = match.group(1).strip()
            raw_decl = match.group(2).strip()

            if not raw_sel or not raw_decl or raw_sel.startswith("@"):
                continue

            selectors = [s.strip() for s in raw_sel.split(",") if s.strip()]
            if not selectors:
                continue

            styles = _parse_styles(raw_decl)
            if styles:
                rules.append((selectors, styles))
    except Exception:
        pass

    return rules


class _HTMLSanitizerParser(html.parser.HTMLParser):
    def __init__(self, css_rules: list[tuple[list[str], dict[str, str]]] | None = None):
        super().__init__(convert_charrefs=True)
        self.css_rules = css_rules or []
        self.findings: list[Finding] = []
        self.visible_chunks: list[str] = []
        self.hidden_stack: list[dict] = []  # dict with keys: tag, kind, detail, text_buf
        self.head_depth = 0
        self.in_title = False
        self.bg_stack: list[bool] = [False] # stack of has_dark_bg

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # Check attributes for long encoded blobs
        for k, v in attr_dict.items():
            if not v:
                continue
            # Meta content or data-* or generic attributes
            is_target_attr = (tag == "meta" and k == "content") or k.startswith("data-") or len(v) >= 40
            if is_target_attr and _BLOB_PATTERN.match(v.strip()):
                self.findings.append(Finding(
                    kind="encoded_blob",
                    detail=f"Long encoded blob in <{tag} {k}>",
                    snippet=v[:200],
                ))

        # Check img alt text
        if tag == "img":
            alt = attr_dict.get("alt", "")
            if len(alt) > 200:
                self.findings.append(Finding(
                    kind="long_alt_text",
                    detail=f"Image alt text exceeds 200 chars ({len(alt)} chars)",
                    snippet=alt[:200],
                ))
            # <img> is a void tag, no text content
            return

        if tag == "head":
            self.head_depth += 1
            return
        if self.head_depth > 0:
            if tag == "title":
                self.in_title = True
            return

        # Track element identity for stylesheet rules
        elem_id = attr_dict.get("id", "")
        classes = set(attr_dict.get("class", "").lower().split())

        # Collect style rules matching this element from stylesheets
        combined_styles: dict[str, str] = {}
        for selectors, rule_styles in self.css_rules:
            if any(_selector_matches(sel, tag, elem_id, classes) for sel in selectors):
                combined_styles.update(rule_styles)

        # Inline styles override stylesheet styles
        style_str = attr_dict.get("style", "")
        inline_styles = _parse_styles(style_str)
        combined_styles.update(inline_styles)

        parent_dark = self.bg_stack[-1]
        bg = combined_styles.get("background-color") or combined_styles.get("background", "")
        has_dark = _is_dark_bg(bg) if bg else parent_dark
        if tag not in _VOID_TAGS:
            self.bg_stack.append(has_dark)

        # Check suppression tags (script, style, etc.)
        if tag in _SUPPRESS_TAGS:
            self.hidden_stack.append({
                "tag": tag,
                "kind": "script_or_style",
                "detail": f"<{tag}> element content removed",
                "text_buf": [],
            })
            return

        # Check hidden attribute or styles
        is_hidden = False
        hide_kind = ""
        hide_detail = ""

        if "hidden" in attr_dict:
            is_hidden = True
            hide_kind = "hidden_element"
            hide_detail = "hidden attribute present"
        else:
            is_hidden, hide_kind, hide_detail = _is_hidden_by_style(combined_styles, parent_dark)

        if is_hidden:
            if tag not in _VOID_TAGS:
                self.hidden_stack.append({
                    "tag": tag,
                    "kind": hide_kind,
                    "detail": f"<{tag}> {hide_detail}",
                    "text_buf": [],
                })
            else:
                self.findings.append(Finding(
                    kind=hide_kind,
                    detail=f"<{tag}> {hide_detail}",
                    snippet="",
                ))
            return

        # Visible container element
        if tag in _BLOCK_TAGS:
            self.visible_chunks.append("\n")
        elif tag == "li":
            self.visible_chunks.append("\n• ")
        elif tag == "br":
            self.visible_chunks.append("\n")

    def handle_endtag(self, tag: str):
        tag = tag.lower()

        if tag == "head":
            self.head_depth = max(0, self.head_depth - 1)
            return
        if self.head_depth > 0:
            if tag == "title":
                self.in_title = False
            return

        if tag not in _VOID_TAGS and len(self.bg_stack) > 1:
            self.bg_stack.pop()

        if self.hidden_stack:
            if self.hidden_stack[-1]["tag"] == tag:
                frame = self.hidden_stack.pop()
                hidden_content = "".join(frame["text_buf"]).strip()
                if hidden_content or frame["kind"] in ("script_or_style", "hidden_element", "offscreen_text"):
                    self.findings.append(Finding(
                        kind=frame["kind"],
                        detail=frame["detail"],
                        snippet=hidden_content[:200],
                    ))
            return

        if tag in _BLOCK_TAGS:
            self.visible_chunks.append("\n")

    def handle_data(self, data: str):
        if self.head_depth > 0:
            if self.in_title:
                self.visible_chunks.append(data)
            return

        if self.hidden_stack:
            # Capture for snippet reporting
            self.hidden_stack[-1]["text_buf"].append(data)
            return

        self.visible_chunks.append(data)

    def handle_comment(self, data: str):
        self.findings.append(Finding(
            kind="html_comment",
            detail="HTML comment removed",
            snippet=data.strip()[:200],
        ))


def sanitize_html(html_content: str) -> Sanitized:
    """
    Parse and clean HTML using stdlib html.parser.

    Preserves visible text in order with paragraph/list formatting.
    Removes and reports scripts, styles, comments, offscreen text, hidden elements
    (via inline style, HTML attributes, or stylesheet rules), and long encoded blobs.
    """
    if not html_content:
        return Sanitized(text="", findings=[])

    # Extract CSS rules from all <style> blocks
    css_rules: list[tuple[list[str], dict[str, str]]] = []
    try:
        for block in re.findall(r"<style\b[^>]*>(.*?)</style>", html_content, flags=re.DOTALL | re.IGNORECASE):
            css_rules.extend(_parse_css_rules(block))
    except Exception:
        pass

    parser = _HTMLSanitizerParser(css_rules=css_rules)
    try:
        parser.feed(html_content)
        parser.close()
    except Exception as exc:
        parser.findings.append(Finding(
            kind="html_parse_error",
            detail=f"HTML parsing error: {exc}",
            snippet="",
        ))

    raw_visible = "".join(parser.visible_chunks)

    # Clean whitespace: preserve paragraph breaks, collapse intra-line spaces
    lines = []
    for raw_line in raw_visible.splitlines():
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    text = "\n".join(lines)

    # Run strip_invisible on the final visible text
    stripped = strip_invisible(text)
    combined_findings = parser.findings + stripped.findings

    return Sanitized(text=stripped.text, findings=combined_findings)


# ---------------------------------------------------------------------------
# Email Sanitizer
# ---------------------------------------------------------------------------

def sanitize_email(raw: bytes) -> SanitizedEmail:
    """
    Parse an RFC 822 email message using stdlib email package.

    Prefers HTML body (sanitized via sanitize_html), falling back to plain text.
    Decodes text-based attachments (.ics, .txt, .csv) up to 100 KB.
    Never raises on malformed MIME.
    """
    findings: list[Finding] = []
    from_addr = ""
    reply_to = ""
    subject = ""
    message_id = ""
    body_text = ""
    attachments: list[dict] = []

    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        from_addr = str(msg.get("From", "") or "")
        reply_to = str(msg.get("Reply-To", "") or "")
        subject = str(msg.get("Subject", "") or "")
        message_id = str(msg.get("Message-ID", "") or "")

        html_part = None
        text_part = None

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", "") or "").lower()
                content_type = part.get_content_type()
                filename = part.get_filename() or ""

                if "attachment" in content_disposition or filename:
                    # Attachment
                    ext = filename.lower().split(".")[-1] if "." in filename else ""
                    if ext in ("ics", "txt", "csv"):
                        try:
                            payload = part.get_payload(decode=True) or b""
                            # Cap at 100 KB
                            payload = payload[:100 * 1024]
                            text_decoded = payload.decode("utf-8", errors="replace")
                            san_att = strip_invisible(text_decoded)
                            findings.extend(san_att.findings)
                            attachments.append({
                                "filename": filename,
                                "text": san_att.text,
                            })
                        except Exception as exc:
                            findings.append(Finding(
                                kind="attachment_decode_error",
                                detail=f"Attachment '{filename}' decode error: {exc}",
                                snippet="",
                            ))
                    continue

                if content_type == "text/html" and html_part is None:
                    html_part = part.get_content()
                elif content_type == "text/plain" and text_part is None:
                    text_part = part.get_content()
        else:
            ctype = msg.get_content_type()
            if ctype == "text/html":
                html_part = msg.get_content()
            else:
                text_part = msg.get_content()

        if html_part:
            san = sanitize_html(html_part if isinstance(html_part, str) else str(html_part))
            body_text = san.text
            findings.extend(san.findings)
        elif text_part:
            san = strip_invisible(text_part if isinstance(text_part, str) else str(text_part))
            body_text = san.text
            findings.extend(san.findings)

    except Exception as exc:
        findings.append(Finding(
            kind="malformed_mime",
            detail=f"MIME parse error: {exc}",
            snippet=str(raw[:200]),
        ))

    return SanitizedEmail(
        from_addr=from_addr,
        reply_to=reply_to,
        subject=subject,
        message_id=message_id,
        text=body_text,
        attachments=attachments,
        findings=findings,
    )
