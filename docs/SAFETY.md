# CampusOS – Safety Constraints (SAFETY.md)

## Core Guarantee

**CampusOS never auto-applies.**

The agent reads listings and writes to a local database. It has no browser, no form-submission capability, and no credentials for any application portal. The apply URL is stored and surfaced so the *human* can click it.

---

## Kill Switch

Two independent kill mechanisms — both working:

| Mechanism | How to trigger | Status |
|---|---|---|
| DB setting | `UPDATE settings SET value='true' WHERE key='kill_switch'` | ✅ Working |
| Kill file | Create the file at `$KILL_FILE` (default: `data/KILL`) | ✅ Working |

The daemon checks the kill file before each run and the runner re-reads `kill_switch` from the DB before every source fetch, as well as before and after every network request and retry attempt inside the gateway. Kill-switch latency is bounded by the per-request timeout (capped at 20 s).

---

## Heartbeat

✅ **Working.** The daemon maintains a continuous background heartbeat thread that updates `daemon_status.heartbeat_at` every 5 seconds for the entire lifetime of the process, including during long runs as well as during idle sleep.

---

## Budget Caps (per run)

All caps are stored in `settings` and snapshotted into `runs.budget_json` at run start:

| Setting key | Default | Enforced |
|---|---|---|
| `max_requests_per_run` | 200 | ✅ Working — counts HTTP requests via shared Budget |
| `max_seconds_per_run` | 300 | ✅ Working — wall-clock check before each source |
| `max_tokens_per_run` | 50 000 | 📋 Planned — LLM stage not yet built |
| `max_usd_per_run` | \$0.50 | 📋 Planned — LLM stage not yet built |

When an enforced cap is hit the run ends with `state='stopped'`, `runs.used_requests` recorded, and the reason in `stop_reason`.

---

## Host Allowlist

✅ **Working.** The gateway only fetches hosts listed in `sources.fetch_hosts` (a JSON array per source row). Any attempt to fetch a host outside that list returns `status='blocked'` before any network call is made.

---

## Apply-Link Domain Allowlist

✅ **Working.** After parsing, each listing's `apply_url` is checked against `sources.domain_allowlist` using suffix domain matching. If the domain is not in the allowlist, the listing is preserved but `"domain_mismatch"` is appended to its `flags` array and its status is marked `'needs_review'`.

---

## Sanitizer and Readers (Structural Prompt Defense)

✅ **Working (Modules & Test Suite).**
- `src/campusos/sanitize.py`:
  - `strip_invisible()`: Strips zero-width/formatting characters (U+200B..U+200F, U+2060..U+2064, U+FEFF, U+00AD), bidi control characters (U+202A..U+202E, U+2066..U+2069), and unprintable control characters. Normalises with Unicode NFKC.
  - `sanitize_html()`: Stdlib HTML parser that removes HTML comments, script/style/template/noscript tags, hidden elements (`display:none`, `visibility:hidden`, `opacity:0`, `font-size:0`, zero dimensions with overflow hidden, `text-indent <= -999`, offscreen positioning, and white-on-white text without darker background) configured via inline style attributes OR stylesheet classes and IDs (`.class`, `#id`, `tag`, `tag.class`, comma-separated lists).
  - Encoded blobs (base64/hex $\ge 40$ characters in attributes or meta content) are reported as `encoded_blob` findings and **never decoded**.
  - `sanitize_email()`: Parses MIME messages, sanitising HTML bodies and plain text fallbacks, and extracting `.ics`/`.txt`/`.csv` attachments (capped at 100 KB).
  - All removals are recorded in structured `Finding` objects (`kind`, `detail`, `snippet`). Visible benign text (even quoting injection phrases) produces zero findings and remains intact.
- `src/campusos/readers.py`:
  - `decode_bytes()`: UTF-8 strict with graceful fallback to cp1252.
  - `read_json_lenient()`: Recovers complete records from truncated JSON via `raw_decode` and segregates bad records (duplicate IDs, non-integer or future years) into `records_bad`.
  - `read_csv_lenient()`: Delimiter sniffing, line-level error segregation (unbalanced quotes, mismatched delimiters, invalid calendar dates, backwards timestamps).
  - `parse_date_strict()`: Reusable calendar date validation.
  - `read_any()`: Universal dispatcher by file extension, running `strip_invisible()` on all output text.

📋 **Planned Integration:**
- The sanitizer and readers are built and thoroughly unit-tested as standalone defensive components. They are **not yet wired into `runner.py`** (which currently handles structured ATS JSON feeds rather than free-form descriptions).
- The LLM field extractor and the structured output validator remain **planned**.

---

## Audit Trail

✅ **Working (DB side).** Every pipeline event is recorded in the `events` table (append-only). The daemon never deletes or updates event rows.

📋 **Planned.** Mirroring events to `traces/run_<id>.jsonl` on disk is not yet implemented. No trace files are committed to the repo.

---

## Data Boundaries

| Data | Stored | Sent outbound |
|---|---|---|
| Listing title / URL | ✅ DB | 📋 digest (planned) |
| Full page HTML | ❌ never | ❌ never |
| User PII | ❌ only synthetic profiles | ❌ never |
| LLM prompts | 📋 planned (≤ 500 char summary in events) | ❌ never |
