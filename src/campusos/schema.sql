-- =============================================================================
-- CampusOS . SQLite schema (WAL mode) 
-- PRAGMA notes:
--   journal_mode=WAL is stored in the database file (persists).
--   foreign_keys, busy_timeout, synchronous are PER CONNECTION: the app must
--   run them on EVERY new connection (daemon, dashboard, tests), not only here.
-- Rules for app code that this schema relies on:
--   * Trim and truncate all text from sources BEFORE insert (titles have trailing
--     spaces; location strings can be long). Never let a CHECK crash the run.
--   * Events/audit text is truncated in app code; the audit write must never fail.
--   * Reject non-http(s) apply URLs in app code (CHECK below is a backstop).
--   * Re-run matching only when the listing hash or the profile changed.
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;

-- =============================================================================
-- SOURCES (config: one row per board / API endpoint)
-- fetch_hosts       = hosts the GATEWAY may call for this source.
-- domain_allowlist  = registrable domains an APPLY LINK may point to (verify stage).
--                     These are different lists; do not mix them.
-- trust_tier comes from config only, never from page content.
-- =============================================================================
CREATE TABLE IF NOT EXISTS sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL UNIQUE,
    platform            TEXT    NOT NULL
                            CHECK (platform IN ('greenhouse','lever','ashby','himalayas','remotive','adzuna','email_file')),
    slug                TEXT,
    base_url            TEXT    NOT NULL,
    fetch_params        TEXT    NOT NULL DEFAULT '{}',   -- JSON, e.g. {"content":"true"} for Greenhouse descriptions
    fetch_hosts         TEXT    NOT NULL,                -- JSON array of hosts the gateway may fetch
    domain_allowlist    TEXT    NOT NULL,                -- JSON array of allowed apply-link domains (suffix match)
    robots_delay_s      REAL    NOT NULL DEFAULT 1.0,
    interval_s          INTEGER NOT NULL DEFAULT 3600,
    timeout_s           INTEGER NOT NULL DEFAULT 30,
    retry_max           INTEGER NOT NULL DEFAULT 2,
    attribution_text    TEXT,
    trust_tier          INTEGER NOT NULL DEFAULT 2 CHECK (trust_tier IN (1,2,3)),
    breaker_state       TEXT    NOT NULL DEFAULT 'closed'
                            CHECK (breaker_state IN ('closed','open','half_open')),
    breaker_failures    INTEGER NOT NULL DEFAULT 0,
    breaker_threshold   INTEGER NOT NULL DEFAULT 3,
    breaker_until       DATETIME,
    last_ok_at          DATETIME,
    enabled             INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    created_at          DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- =============================================================================
-- RUNS
-- Coverage lives ONLY in the coverage tables below (single source of truth).
-- =============================================================================
CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger         TEXT    NOT NULL DEFAULT 'scheduler'
                        CHECK (trigger IN ('scheduler','manual','resume','trap_pack')),
    state           TEXT    NOT NULL DEFAULT 'running'
                        CHECK (state IN ('running','done','stopped','failed')),
    stage           TEXT    DEFAULT 'plan',
    mode            TEXT    NOT NULL DEFAULT 'live'
                        CHECK (mode IN ('live','replay','mock','trap_pack')),
    started_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ended_at        DATETIME,
    stop_reason     TEXT,                                 -- 'kill_switch','budget_tokens','budget_usd','budget_time','user'
    budget_json     TEXT    NOT NULL DEFAULT '{}',        -- snapshot of caps at run start
    used_requests   INTEGER NOT NULL DEFAULT 0,
    used_tokens     INTEGER NOT NULL DEFAULT 0,
    used_usd        REAL    NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_runs_state      ON runs (state);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs (started_at DESC);

-- =============================================================================
-- SNAPSHOTS (one row per fetch attempt)
-- content_hash is NULL when nothing was fetched (error, timeout, breaker open).
-- Change detection = job ID + content hash. NEVER the source's updated_at
-- (bulk refreshes: Reddit 149/149, Stripe/Databricks ~100 jobs "updated this week").
-- =============================================================================
CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL REFERENCES sources(id),
    run_id          INTEGER REFERENCES runs(id),
    fetched_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    content_hash    TEXT,
    status          TEXT    NOT NULL DEFAULT 'ok'
                        CHECK (status IN ('ok','unchanged','error','timeout','circuit_open','rate_limited','blocked')),
    http_status     INTEGER,
    duration_ms     INTEGER,
    item_count      INTEGER,
    raw_ref         TEXT,                                 -- cached raw payload path (replay mode)
    error_detail    TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_source_fetched ON snapshots (source_id, fetched_at DESC);

-- =============================================================================
-- OPPORTUNITIES (canonical listing). status here is about the LISTING only.
-- Whether a listing is wrong for a person is per profile: see matches.eligibility.
-- Length CHECKs are generous; app code trims/truncates first.
-- =============================================================================
CREATE TABLE IF NOT EXISTS opportunities (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Identity
    source_id           INTEGER NOT NULL REFERENCES sources(id),
    external_id         TEXT    NOT NULL,
    canonical_key       TEXT    NOT NULL UNIQUE,          -- source_name + ':' + external_id
    group_key           TEXT,                             -- norm_company + ':' + norm_title (groups multi-city copies)
    snapshot_id         INTEGER REFERENCES snapshots(id),
    -- Basics (ATS structured fields, not LLM)
    title               TEXT    NOT NULL CHECK (length(title) <= 300),
    company             TEXT    NOT NULL CHECK (length(company) <= 200),
    apply_url           TEXT    NOT NULL
                            CHECK (apply_url LIKE 'https://%' OR apply_url LIKE 'http://%'),
                            -- stored as given; domain is checked in the verify stage (evidence kind 'domain_check')
    -- Location
    location_raw        TEXT    CHECK (length(location_raw) <= 1000),
    location_norm       TEXT,                             -- JSON array, e.g. ["Singapore"]
    countries_json      TEXT    NOT NULL DEFAULT '[]',    -- JSON array of ISO codes, e.g. ["IN","SG"]
    remote_ok           INTEGER NOT NULL DEFAULT 0 CHECK (remote_ok IN (0,1)),
    remote_scope        TEXT    NOT NULL DEFAULT 'unknown'
                            CHECK (remote_scope IN ('worldwide','region_limited','none','unknown')),
    remote_regions_json TEXT    NOT NULL DEFAULT '[]',    -- e.g. ["US"] for "Remote, US" (not open to India)
    -- Classification (rules first, LLM only for ambiguous)
    seniority           TEXT    NOT NULL DEFAULT 'unknown'
                            CHECK (seniority IN ('intern','new_grad','entry','mid','senior','unknown')),
    employment_type     TEXT    NOT NULL DEFAULT 'unknown'
                            CHECK (employment_type IN ('full_time','part_time','internship','contract','unknown')),
    -- Requirements (every field can be unknown)
    min_education       TEXT    NOT NULL DEFAULT 'unknown'
                            CHECK (min_education IN ('high_school','bachelor','master','phd','unknown')),
    grad_year_min       INTEGER,                          -- NULL = unknown; "New Grad 2027" -> 2027/2027
    grad_year_max       INTEGER,
    min_experience_yrs  REAL,                             -- NULL = unknown
    skills_json         TEXT    NOT NULL DEFAULT '[]' CHECK (length(skills_json) <= 4000),
    work_auth_statement TEXT    NOT NULL DEFAULT 'unknown' CHECK (length(work_auth_statement) <= 1000),
    language_req        TEXT    NOT NULL DEFAULT 'unknown' CHECK (length(language_req) <= 200),
    -- Deadline
    deadline            DATE,
    deadline_kind       TEXT    NOT NULL DEFAULT 'unknown'
                            CHECK (deadline_kind IN ('fixed','rolling','unknown')),
    deadline_evidence   TEXT    CHECK (length(deadline_evidence) <= 1000),
    posted_at           DATETIME,
    -- Trust and verification
    status              TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','verified','needs_review','expired')),
    confidence          REAL    NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0.0 AND 1.0),
    flags               TEXT    NOT NULL DEFAULT '[]',    -- ["domain_mismatch","possible_scam","conflict_deadline"]
    -- Lifecycle
    first_seen_at       DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen_at        DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_changed_at     DATETIME,
    removed_at          DATETIME,                         -- set when the job disappears from its board (-> expired)
    content_hash        TEXT    NOT NULL                  -- SHA-256 of normalised listing content
);
CREATE INDEX IF NOT EXISTS idx_opp_source     ON opportunities (source_id);
CREATE INDEX IF NOT EXISTS idx_opp_status     ON opportunities (status);
CREATE INDEX IF NOT EXISTS idx_opp_seniority  ON opportunities (seniority);
CREATE INDEX IF NOT EXISTS idx_opp_deadline   ON opportunities (deadline);
CREATE INDEX IF NOT EXISTS idx_opp_group_key  ON opportunities (group_key);
CREATE INDEX IF NOT EXISTS idx_opp_last_seen  ON opportunities (last_seen_at DESC);

-- What changed on a known listing (guide: "record what changed")
CREATE TABLE IF NOT EXISTS opportunity_changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    run_id          INTEGER REFERENCES runs(id),
    field           TEXT    NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    changed_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_changes_opp ON opportunity_changes (opportunity_id);

-- =============================================================================
-- EVIDENCE (several per opportunity)
-- =============================================================================
CREATE TABLE IF NOT EXISTS evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    kind            TEXT    NOT NULL
                        CHECK (kind IN ('deadline_verbatim','experience_verbatim','education_verbatim',
                                        'domain_check','link_check','corroboration','scam_flag','conflict',
                                        'seniority_rule','location_check')),
    snippet         TEXT    CHECK (length(snippet) <= 1000),
    source_url      TEXT,
    recorded_at     DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_evidence_opp ON evidence (opportunity_id);

-- =============================================================================
-- PROFILE and SEARCH INTENT (synthetic in tests; editable and clearable)
-- =============================================================================
CREATE TABLE IF NOT EXISTS profile (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    label               TEXT    NOT NULL UNIQUE,
    education_level     TEXT    NOT NULL DEFAULT 'bachelor'
                            CHECK (education_level IN ('high_school','bachelor','master','phd')),
    education_field     TEXT    CHECK (length(education_field) <= 100),
    currently_enrolled  INTEGER NOT NULL DEFAULT 1 CHECK (currently_enrolled IN (0,1)),
    graduation_year     INTEGER,
    experience_years    REAL    NOT NULL DEFAULT 0,       -- needed to compare with min_experience_yrs
    skills_json         TEXT    NOT NULL DEFAULT '[]' CHECK (length(skills_json) <= 2000),
    work_auth_json      TEXT    NOT NULL DEFAULT '{}',    -- {"india":true,"singapore":"visa_needed","us":false}
    preferred_locations TEXT    NOT NULL DEFAULT '[]',
    languages_json      TEXT    NOT NULL DEFAULT '["English"]',
    is_synthetic        INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic IN (0,1)),
    created_at          DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS search_intent (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id            INTEGER NOT NULL UNIQUE REFERENCES profile(id) ON DELETE CASCADE,
    role_keywords         TEXT    NOT NULL DEFAULT '[]',
    seniority_json        TEXT    NOT NULL DEFAULT '["intern"]',  -- array: any of intern,new_grad,entry,mid,senior
    locations_json        TEXT    NOT NULL DEFAULT '[]',
    remote_ok             INTEGER NOT NULL DEFAULT 1 CHECK (remote_ok IN (0,1)),
    deadline_horizon_days INTEGER NOT NULL DEFAULT 90,
    raw_input             TEXT    CHECK (length(raw_input) <= 1000),
    confirmed_at          DATETIME,                               -- NULL = not yet confirmed by the user
    created_at            DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- =============================================================================
-- MATCHES: ONE row per (opportunity, profile), updated in place.
-- (A row per run would grow by listings x profiles every 60 s in the demo.)
-- Re-evaluate only if opportunities.content_hash != evaluated_hash
-- or profile.updated_at != evaluated_profile_version.
-- =============================================================================
CREATE TABLE IF NOT EXISTS matches (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id            INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    profile_id                INTEGER NOT NULL REFERENCES profile(id) ON DELETE CASCADE,
    last_run_id               INTEGER REFERENCES runs(id),
    evaluated_hash            TEXT,
    evaluated_profile_version TEXT,
    eligibility               TEXT    NOT NULL DEFAULT 'unknown'
                                  CHECK (eligibility IN ('pass','fail','unknown')),
    eligibility_reasons       TEXT    NOT NULL DEFAULT '[]',
    score                     REAL    CHECK (score IS NULL OR score BETWEEN 0.0 AND 1.0),
    score_breakdown           TEXT    NOT NULL DEFAULT '{}',
    score_reasons             TEXT    NOT NULL DEFAULT '[]',
    decision                  TEXT    NOT NULL DEFAULT 'pending'
                                  CHECK (decision IN ('pending','notify','queue','skip','backed_off')),
    decision_reason           TEXT,
    ranked_position           INTEGER,
    first_notified_at         DATETIME,                   -- non-NULL = already in a digest; do not re-notify unless changed
    last_evaluated_at         DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (opportunity_id, profile_id)
);
CREATE INDEX IF NOT EXISTS idx_matches_decision ON matches (decision);
CREATE INDEX IF NOT EXISTS idx_matches_score    ON matches (score DESC);

-- =============================================================================
-- REVIEW QUEUE. At most ONE open item per (opportunity, reason), so a 60-second
-- schedule cannot flood the queue with copies.
-- =============================================================================
CREATE TABLE IF NOT EXISTS review_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_id  INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
    run_id          INTEGER REFERENCES runs(id),
    reason          TEXT    NOT NULL
                        CHECK (reason IN ('seniority_ambiguous','eligibility_unknown','domain_mismatch',
                                          'possible_scam','conflict','extract_failed','work_auth_unclear',
                                          'graduation_window_missing','experience_check_needed',
                                          'remote_scope_unclear','location_unclear','deadline_missing')),
    detail          TEXT    CHECK (length(detail) <= 500),
    created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    resolved_at     DATETIME,
    resolution      TEXT    CHECK (resolution IS NULL OR resolution IN ('accepted','rejected','ignored'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_open
    ON review_queue (opportunity_id, reason) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_review_resolved ON review_queue (resolved_at);

-- =============================================================================
-- ACTIONS (outward actions). Idempotent ACROSS runs:
--   one digest per run; one .ics per (opportunity, profile) ever
--   (if a deadline changes, UPDATE the existing row and regenerate the file).
-- Note: a plain UNIQUE over nullable columns would NOT prevent duplicate digests
-- (NULLs count as distinct in SQLite), so partial unique indexes are used.
-- =============================================================================
CREATE TABLE IF NOT EXISTS actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    type            TEXT    NOT NULL CHECK (type IN ('digest','ics')),
    target          TEXT    NOT NULL,                       -- whitelisted sandbox address or file path
    payload_ref     TEXT,
    status          TEXT    NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','sent','failed','cancelled')),
    error           TEXT,
    opportunity_id  INTEGER REFERENCES opportunities(id),
    profile_id      INTEGER REFERENCES profile(id),
    created_at      DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    sent_at         DATETIME,
    CHECK (type <> 'ics' OR (opportunity_id IS NOT NULL AND profile_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_actions_digest ON actions (run_id) WHERE type = 'digest';
CREATE UNIQUE INDEX IF NOT EXISTS uq_actions_ics    ON actions (opportunity_id, profile_id) WHERE type = 'ics';

-- =============================================================================
-- EVENTS: the audit trail (also appended to traces/run_<id>.jsonl).
-- No length CHECKs on purpose: the audit write must never fail. App code
-- truncates summaries (about 500 chars) and never stores full page content.
-- =============================================================================
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id),
    seq             INTEGER NOT NULL,
    ts              DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    type            TEXT    NOT NULL
                        CHECK (type IN ('run_start','run_end','stage_start','stage_end','tool_call',
                                        'decision','action','kill_switch','cancelled',
                                        'budget_exceeded','circuit_open','error')),
    stage           TEXT,
    tool            TEXT,                                   -- 'http_fetch','llm_extract','web_search','send_digest','write_ics'
    input_summary   TEXT,
    result_summary  TEXT,
    decision        TEXT,                                   -- notify | queue | skip | stopped | open_breaker | back_off
    reason          TEXT,
    error           TEXT,
    cost_usd        REAL    NOT NULL DEFAULT 0.0,
    tokens          INTEGER NOT NULL DEFAULT 0,
    opportunity_id  INTEGER REFERENCES opportunities(id),
    UNIQUE (run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events (run_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_type    ON events (type);
CREATE INDEX IF NOT EXISTS idx_events_ts      ON events (ts DESC);

-- =============================================================================
-- COVERAGE (per run) and per-profile counts. Replaces the hard-coded "profile B" column.
-- =============================================================================
CREATE TABLE IF NOT EXISTS coverage (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL UNIQUE REFERENCES runs(id),
    sources_checked     INTEGER NOT NULL DEFAULT 0,
    sources_skipped     INTEGER NOT NULL DEFAULT 0,        -- breaker open
    sources_failed      INTEGER NOT NULL DEFAULT 0,
    failed_json         TEXT    NOT NULL DEFAULT '[]',     -- [{"source":"lever_meesho","status":"timeout"}]
    listings_found      INTEGER NOT NULL DEFAULT 0,
    listings_unchanged  INTEGER NOT NULL DEFAULT 0,        -- skipped by content hash
    after_dedup         INTEGER NOT NULL DEFAULT 0,
    by_region_json      TEXT    NOT NULL DEFAULT '{}',     -- {"IN":12,"SG":4,"US":210,"EU":60,"REMOTE":9}
    not_covered_note    TEXT,                              -- honest "what we could not cover"
    created_at          DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS coverage_profile (
    run_id              INTEGER NOT NULL REFERENCES runs(id),
    profile_id          INTEGER NOT NULL REFERENCES profile(id),
    after_seniority     INTEGER NOT NULL DEFAULT 0,
    after_eligibility   INTEGER NOT NULL DEFAULT 0,
    notify_count        INTEGER NOT NULL DEFAULT 0,
    review_count        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, profile_id)
);

-- =============================================================================
-- DAEMON STATUS (heartbeat for the dashboard's "alive / stale"); exactly one row.
-- =============================================================================
CREATE TABLE IF NOT EXISTS daemon_status (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    pid             INTEGER,
    started_at      DATETIME,
    heartbeat_at    DATETIME,
    current_run_id  INTEGER REFERENCES runs(id),
    next_run_at     DATETIME
);
INSERT OR IGNORE INTO daemon_status (id) VALUES (1);

-- =============================================================================
-- SETTINGS (key-value runtime config)
-- =============================================================================
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('kill_switch',           'false'),
    ('interval_s',            '60'),      -- demo: 60; normal: 3600
    ('force_all_sources_due', 'true'),    -- demo only: ignore per-source interval_s so each run has work; set false normally
    ('mode',                  'live'),    -- live | replay | mock
    ('max_requests_per_run',  '200'),
    ('max_tokens_per_run',    '50000'),
    ('max_usd_per_run',       '0.50'),
    ('max_seconds_per_run',   '300'),
    ('notify_score_min',      '0.4'),
    ('max_description_chars', '4000'),    -- applied after HTML is stripped, before LLM extraction
    ('daemon_stale_after_s',  '30'),
    ('sandbox_inbox',         ''),        -- set before the first real run
    ('schema_version',        '2');

-- =============================================================================
-- SEED SOURCES: tested live on Nov 27 (all 200 OK). Final set.
-- Apply-link domains marked (check) must be confirmed from a real absolute_url at build time.
-- Optional or dropped sources are seeded disabled (enabled = 0) or left out.
-- =============================================================================
INSERT OR IGNORE INTO sources
    (name, platform, slug, base_url, fetch_params, fetch_hosts, domain_allowlist,
     trust_tier, robots_delay_s, interval_s, timeout_s, attribution_text, enabled)
VALUES
    ('greenhouse_coinbase',   'greenhouse', 'coinbase',   'https://boards-api.greenhouse.io/v1/boards/coinbase/jobs',
     '{"content":"true"}', '["boards-api.greenhouse.io"]', '["coinbase.com","greenhouse.io"]',            1, 0.5, 3600, 30, NULL, 1),
    ('greenhouse_stripe',     'greenhouse', 'stripe',     'https://boards-api.greenhouse.io/v1/boards/stripe/jobs',
     '{"content":"true"}', '["boards-api.greenhouse.io"]', '["stripe.com","greenhouse.io"]',              1, 0.5, 3600, 30, NULL, 1),
    ('greenhouse_databricks', 'greenhouse', 'databricks', 'https://boards-api.greenhouse.io/v1/boards/databricks/jobs',
     '{"content":"true"}', '["boards-api.greenhouse.io"]', '["databricks.com","greenhouse.io"]',          1, 0.5, 3600, 30, NULL, 1),
    ('greenhouse_pinterest',  'greenhouse', 'pinterest',  'https://boards-api.greenhouse.io/v1/boards/pinterest/jobs',
     '{"content":"true"}', '["boards-api.greenhouse.io"]', '["pinterestcareers.com","greenhouse.io"]',    1, 0.5, 3600, 30, NULL, 1),
    ('greenhouse_airbnb',     'greenhouse', 'airbnb',     'https://boards-api.greenhouse.io/v1/boards/airbnb/jobs',
     '{"content":"true"}', '["boards-api.greenhouse.io"]', '["airbnb.com","greenhouse.io"]',              1, 0.5, 3600, 30, NULL, 1),
    ('greenhouse_groww',      'greenhouse', 'groww',      'https://boards-api.greenhouse.io/v1/boards/groww/jobs',
     '{"content":"true"}', '["boards-api.greenhouse.io"]', '["groww.in","greenhouse.io"]',                 1, 0.5, 3600, 30, NULL, 1),   -- (check) apply domain; Groww is on GREENHOUSE, not Lever
    ('lever_meesho',          'lever',      'meesho',     'https://api.lever.co/v0/postings/meesho',
     '{"mode":"json"}',    '["api.lever.co"]',             '["meesho.com","lever.co"]',                    1, 1.0, 3600, 30, NULL, 1),   -- slow: 13.8 s seen
    ('himalayas',             'himalayas',  NULL,         'https://himalayas.app/jobs/api',
     '{"limit":"20"}',     '["himalayas.app"]',            '["himalayas.app"]',
     2, 1.0, 7200, 30, 'Jobs listed via Himalayas (himalayas.app)', 1),
    -- Optional / fallback (disabled until the core loop works)
    ('ashby_plaid',           'ashby',      'plaid',      'https://api.ashbyhq.com/posting-api/job-board/plaid',
     '{}',                 '["api.ashbyhq.com"]',          '["plaid.com","ashbyhq.com"]',                  1, 0.5, 3600, 30, NULL, 0),
    ('remotive',              'remotive',   NULL,         'https://remotive.com/api/remote-jobs',
     '{"limit":"20"}',     '["remotive.com"]',             '["remotive.com"]',
     2, 1.0, 86400, 30, 'Remote jobs via Remotive (remotive.com)', 0);

-- =============================================================================
-- SEED PROFILES (synthetic) and their search intents (looked up by label, not by id)
-- =============================================================================
INSERT OR IGNORE INTO profile
    (label, education_level, education_field, currently_enrolled, graduation_year, experience_years,
     skills_json, work_auth_json, preferred_locations, languages_json, is_synthetic)
VALUES
    ('profile_a_tech',    'bachelor', 'Computer Science', 1, 2028, 0,
     '["Python","SQL","Git","basic ML"]',
     '{"india":true,"singapore":"visa_needed","europe":"visa_needed","us":false,"remote":true}',
     '["India","Singapore","Europe","Remote"]', '["English"]', 1),
    ('profile_b_finance', 'bachelor', 'Commerce',         1, 2027, 0,
     '["Excel","financial analysis","content writing"]',
     '{"india":true,"singapore":"visa_needed","us":false,"remote":true}',
     '["India","Remote","Singapore"]',          '["English"]', 1),
    ('profile_c_analyst', 'bachelor', 'Business Analytics', 0, 2020, 5,
     '["SQL","Excel","financial modelling","dashboards"]',
     '{"india":true,"singapore":"visa_needed","us":false,"remote":true}',
     '["India","Remote"]',                      '["English"]', 1);

INSERT OR IGNORE INTO search_intent
    (profile_id, role_keywords, seniority_json, locations_json, remote_ok, deadline_horizon_days)
VALUES
    ((SELECT id FROM profile WHERE label='profile_a_tech'),
     '["software","data","machine learning","backend","ML"]', '["intern"]',
     '["India","Singapore","Europe","Remote"]', 1, 120),
    ((SELECT id FROM profile WHERE label='profile_b_finance'),
     '["finance","accounting","marketing","operations","content"]', '["intern","new_grad","entry"]',
     '["India","Remote","Singapore"]', 1, 90),
    ((SELECT id FROM profile WHERE label='profile_c_analyst'),
     '["analyst","finance","analytics","operations"]', '["mid","senior"]',
     '["India","Remote"]', 1, 60);