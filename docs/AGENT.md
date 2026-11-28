# CampusOS – Architecture (AGENT.md)

## Overview

CampusOS is an **autonomous opportunity-finding agent**. It watches public job boards, deduplicates listings by content hash, and builds a searchable local database. Eligibility matching, scoring, review routing, and digest delivery are in progress.

**It never auto-applies.**

---

## Pipeline Stages

```
scheduler tick  (daemon.py – every interval_s seconds)
    └─ runner.execute_run()
           │
           ├─ plan    Load settings, check kill switch (DB) + kill file (disk)   ✅
           │          Pick due sources (last_ok_at NULL or overdue)
           │
           ├─ fetch   gateway.fetch() per source                                  ✅
           │          • Host allowlist enforced before any network call
           │          • Circuit breaker (closed → open → half_open)
           │          • Retry up to retry_max times with robots_delay_s delay
           │          • Writes one snapshots row per attempt
           │
           ├─ parse   Platform-specific normaliser                                ✅
           │          • greenhouse: unwrap {"jobs":[...]}
           │          • lever:      top-level list of postings
           │          • himalayas:  {"jobs":[...]}
           │          • Trims titles, validates apply URLs (http/https only)
           │          • Builds content_hash = SHA-256(normalised fields)
           │
           ├─ upsert  Content-hash dedup per canonical_key                       ✅
           │          • new      → INSERT opportunities
           │          • changed  → UPDATE + write opportunity_changes row
           │          • unchanged→ UPDATE last_seen_at only
           │
           ├─ match   [stub – in progress]                                       🔧
           │          Planned: rules-first eligibility × profile, 0–1 score,
           │          notify / queue / skip decision per (opportunity, profile)
           │
           └─ done    Finalise run row, write coverage summary                   ✅
                      Clear daemon_status.current_run_id, append audit events
```

Planned stages not yet in the pipeline:
- **extract** — LLM-assisted field extraction for ambiguous listings
- **verify** — apply-link domain check, corroboration
- **actions** — digest file + .ics calendar invite generation
- **review** — route flagged items to `review_queue`
- **replay** — re-run from saved raw payloads in `data/raw/`

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| SQLite + WAL | Single-file, zero-config; WAL allows concurrent reads during writes |
| Content-hash dedup | Boards like Databricks refresh 100+ jobs as "updated this week"; timestamp-based dedup would re-process everything |
| Rules first, LLM only for ambiguous | Deterministic, auditable, cheap; LLM only called when rule output is `unknown` |
| One `matches` row per (opp, profile) | Re-evaluating everything per run would grow O(listings × profiles × runs) |
| Circuit breaker in DB | Survives restarts; dashboard can inspect and reset state |
| Partial unique indexes for actions | SQLite NULLs are distinct, so `UNIQUE(run_id)` would not prevent duplicate digests |
| stdlib-only HTTP + no framework | Zero extra dependencies; judges can audit the whole transport layer |

---

## State Machine

```
runs.state:   running → done
                      → stopped   (kill_switch, kill_file, budget cap)
                      → failed    (unhandled exception)

runs.stage:   plan → fetch → parse → upsert → match → done
```

---

## Sources (10 seeded, 8 enabled)

| Name | Platform | Trust tier | Enabled |
|---|---|---|---|
| greenhouse_coinbase | greenhouse | 1 | ✅ |
| greenhouse_stripe | greenhouse | 1 | ✅ |
| greenhouse_databricks | greenhouse | 1 | ✅ |
| greenhouse_pinterest | greenhouse | 1 | ✅ |
| greenhouse_airbnb | greenhouse | 1 | ✅ |
| greenhouse_groww | greenhouse | 1 | ✅ |
| lever_meesho | lever | 1 | ✅ |
| himalayas | himalayas | 2 | ✅ |
| ashby_plaid | ashby | 1 | disabled |
| remotive | remotive | 2 | disabled |

---

## Profiles (Synthetic Seeds)

| Label | Field | Seniority target |
|---|---|---|
| profile_a_tech | Computer Science | intern |
| profile_b_finance | Commerce | intern / new_grad / entry |
| profile_c_analyst | Business Analytics | mid / senior |
