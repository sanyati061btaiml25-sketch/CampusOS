import fs from 'node:fs';
import path from 'node:path';
import { initDb, upsertOpportunity, getOpportunityByKey, logAuditEvent, getAuditEventsByRun } from './db.ts';

const tempDbPath = path.join(process.cwd(), 'campusos-roundtrip-temp.db');

try {
  const db = initDb(tempDbPath);

  upsertOpportunity(db, {
    id: 'opp-1',
    canonicalKey: 'acme-swe-intern-2026',
    title: 'Software Engineering Intern',
    company: 'Acme Cloud',
    location: 'Bengaluru (Hybrid)',
    eligibilityStatus: 'eligible',
    verificationStatus: 'verified',
    scamFlagsJson: JSON.stringify([]),
    scoreTotal: 92,
  });

  logAuditEvent(db, {
    id: 'evt-1',
    runId: 'run-demo-001',
    stage: 'verify',
    action: 'VERIFIED_LISTING',
    detail: 'Official domain and deadline verified.',
  });

  const savedOpp = getOpportunityByKey(db, 'acme-swe-intern-2026');
  const savedEvents = getAuditEventsByRun(db, 'run-demo-001');

  if (!savedOpp || savedOpp.title !== 'Software Engineering Intern') {
    throw new Error('Opportunity round-trip failed');
  }
  if (savedEvents.length !== 1 || savedEvents[0].action !== 'VERIFIED_LISTING') {
    throw new Error('Audit event round-trip failed');
  }

  db.close();
  console.log('✅ SQLite round-trip succeeded – database created, rows inserted, queried, and verified.');
} finally {
  for (const suffix of ['', '-wal', '-shm']) {
    const target = tempDbPath + suffix;
    if (fs.existsSync(target)) {
      fs.unlinkSync(target);
    }
  }
}
