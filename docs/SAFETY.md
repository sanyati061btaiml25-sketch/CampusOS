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
