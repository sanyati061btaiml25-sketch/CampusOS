import test from 'node:test';
import assert from 'node:assert/strict';
import {
  initDb,
  upsertOpportunity,
  getOpportunityByKey,
  logAuditEvent,
  getAuditEventsByRun,
} from '../database/db.ts';

test('SQLite initializes schema and stores/retrieves an opportunity', () => {
  const db = initDb(':memory:');
  try {
    upsertOpportunity(db, {
      id: 'opp-101',
      canonicalKey: 'nova-ai-intern',
      title: 'AI Research Intern',
      company: 'Nova Labs',
      location: 'Remote',
      eligibilityStatus: 'eligible',
      verificationStatus: 'verified',
      scamFlagsJson: '[]',
      scoreTotal: 88,
    });

    const row = getOpportunityByKey(db, 'nova-ai-intern');
    assert.ok(row, 'Expected opportunity row to be found');
    assert.equal(row.title, 'AI Research Intern');
    assert.equal(row.score_total, 88);
  } finally {
    db.close();
  }
});

test('SQLite deduplicates opportunities by canonical_key on upsert', () => {
  const db = initDb(':memory:');
  try {
    upsertOpportunity(db, {
      id: 'opp-201',
      canonicalKey: 'dup-key-1',
      title: 'Frontend Intern',
      company: 'PixelWorks',
      location: 'Pune',
      eligibilityStatus: 'needs_review',
      verificationStatus: 'uncertain',
      scamFlagsJson: '[]',
      scoreTotal: 70,
    });

    upsertOpportunity(db, {
      id: 'opp-202',
      canonicalKey: 'dup-key-1',
      title: 'Frontend Intern (Updated)',
      company: 'PixelWorks',
      location: 'Pune',
      eligibilityStatus: 'eligible',
      verificationStatus: 'verified',
      scamFlagsJson: '[]',
      scoreTotal: 85,
    });

    const countRow = db.prepare('SELECT COUNT(*) AS cnt FROM opportunities').get() as { cnt: number };
    assert.equal(countRow.cnt, 1);

    const updated = getOpportunityByKey(db, 'dup-key-1');
    assert.equal(updated?.title, 'Frontend Intern (Updated)');
    assert.equal(updated?.score_total, 85);
  } finally {
    db.close();
  }
});

test('SQLite logs audit events and persists trap/scam flags', () => {
  const db = initDb(':memory:');
  try {
    upsertOpportunity(db, {
      id: 'opp-trap-1',
      canonicalKey: 'trap-fee-listing',
      title: 'Quick Cash Internship',
      company: 'ShadyCorp',
      location: 'Remote',
      eligibilityStatus: 'needs_review',
      verificationStatus: 'conflict',
      scamFlagsJson: JSON.stringify(['Registration fee requested', 'Personal Gmail contact']),
      scoreTotal: 12,
    });

    logAuditEvent(db, {
      id: 'evt-trap-1',
      runId: 'run-trap-check',
      stage: 'verify',
      action: 'TRAP_FLAGGED',
      detail: 'Flagged registration fee and personal email; not acted on.',
    });

    const opp = getOpportunityByKey(db, 'trap-fee-listing');
    assert.ok(opp);
    const flags = JSON.parse(String(opp.scam_flags_json));
    assert.deepEqual(flags, ['Registration fee requested', 'Personal Gmail contact']);

    const events = getAuditEventsByRun(db, 'run-trap-check');
    assert.equal(events.length, 1);
    assert.equal(events[0].action, 'TRAP_FLAGGED');
  } finally {
    db.close();
  }
});
