import { DatabaseSync } from 'node:sqlite';

export interface OpportunityRow {
  id: string;
  canonicalKey: string;
  title: string;
  company: string;
  location: string;
  eligibilityStatus: string;
  verificationStatus: string;
  scamFlagsJson: string;
  scoreTotal: number;
  createdAt?: string;
}

export interface AuditEventRow {
  id: string;
  runId: string;
  stage: string;
  action: string;
  detail: string;
  createdAt?: string;
}

export function initDb(dbPath: string = 'campusos.db'): DatabaseSync {
  const db = new DatabaseSync(dbPath);
  db.exec(`
    PRAGMA journal_mode = WAL;

    CREATE TABLE IF NOT EXISTS opportunities (
      id TEXT PRIMARY KEY,
      canonical_key TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      company TEXT NOT NULL,
      location TEXT NOT NULL,
      eligibility_status TEXT NOT NULL,
      verification_status TEXT NOT NULL,
      scam_flags_json TEXT NOT NULL DEFAULT '[]',
      score_total INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS audit_events (
      id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      stage TEXT NOT NULL,
      action TEXT NOT NULL,
      detail TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY,
      mode TEXT NOT NULL,
      state TEXT NOT NULL,
      started_at TEXT NOT NULL DEFAULT (datetime('now')),
      ended_at TEXT
    );
  `);
  return db;
}

export function upsertOpportunity(db: DatabaseSync, opp: OpportunityRow): void {
  const stmt = db.prepare(`
    INSERT INTO opportunities (
      id, canonical_key, title, company, location,
      eligibility_status, verification_status, scam_flags_json, score_total
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(canonical_key) DO UPDATE SET
      title = excluded.title,
      eligibility_status = excluded.eligibility_status,
      verification_status = excluded.verification_status,
      scam_flags_json = excluded.scam_flags_json,
      score_total = excluded.score_total
  `);
  stmt.run(
    opp.id,
    opp.canonicalKey,
    opp.title,
    opp.company,
    opp.location,
    opp.eligibilityStatus,
    opp.verificationStatus,
    opp.scamFlagsJson,
    opp.scoreTotal
  );
}

export function getOpportunityByKey(db: DatabaseSync, canonicalKey: string): Record<string, unknown> | undefined {
  const stmt = db.prepare('SELECT * FROM opportunities WHERE canonical_key = ?');
  return stmt.get(canonicalKey) as Record<string, unknown> | undefined;
}

export function logAuditEvent(db: DatabaseSync, event: AuditEventRow): void {
  const stmt = db.prepare(`
    INSERT INTO audit_events (id, run_id, stage, action, detail)
    VALUES (?, ?, ?, ?, ?)
  `);
  stmt.run(event.id, event.runId, event.stage, event.action, event.detail);
}

export function getAuditEventsByRun(db: DatabaseSync, runId: string): Record<string, unknown>[] {
  const stmt = db.prepare('SELECT * FROM audit_events WHERE run_id = ? ORDER BY rowid ASC');
  return stmt.all(runId) as Record<string, unknown>[];
}
