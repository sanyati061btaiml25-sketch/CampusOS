import {
  AgentStage,
  AuditEvent,
  Opportunity,
  OpportunityFilters,
  RunMode,
  RunTelemetry,
  SandboxDigestMessage,
  SourceFeed,
  StudentProfile,
} from '../types';
import { evaluateOpportunityMatch } from '../engine/matcher';

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const DEFAULT_RUN_MODE: RunMode =
  import.meta.env.VITE_API_MODE === 'fastapi' ? 'live' : 'mock';

/**
 * Prevents javascript:/data: URL XSS attacks from untrusted scraped links.
 */
export function safeHttpUrl(rawUrl: string): string | null {
  try {
    const parsed = new URL(rawUrl.trim());
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') {
      return parsed.toString();
    }
    return null;
  } catch {
    return null;
  }
}

export function createEmptyFilters(): OpportunityFilters {
  return {
    query: '',
    locationQuery: '',
    statuses: [],
    types: [],
    workModes: [],
    tracks: [],
    cities: [],
    sources: [],
    skills: [],
    minStipendInr: 0,
    minScore: 0,
    deadlineWithinDays: null,
    verifiedOnly: false,
    savedOnly: false,
    closingSoonOnly: false,
  };
}

export function applyOpportunityFilters(
  opportunities: Opportunity[],
  filters: OpportunityFilters,
  referenceDateIso = '2026-11-25'
): Opportunity[] {
  const q = filters.query.trim().toLowerCase();
  const locQ = filters.locationQuery.trim().toLowerCase();

  return opportunities.filter((o) => {
    if (o.dismissed) return false;
    if (filters.statuses.length > 0 && !filters.statuses.includes(o.eligibilityStatus)) {
      return false;
    }
    if (filters.types.length > 0 && !filters.types.includes(o.opportunityType)) {
      return false;
    }
    if (filters.workModes.length > 0 && !filters.workModes.includes(o.workMode)) {
      return false;
    }
    if (filters.tracks.length > 0 && !filters.tracks.includes(o.track)) {
      return false;
    }
    if (filters.cities.length > 0 && !filters.cities.includes(o.cityTag)) {
      return false;
    }
    if (filters.sources.length > 0 && !filters.sources.includes(o.evidence.sourceName)) {
      return false;
    }
    if (filters.skills.length > 0) {
      const oppSkills = new Set(o.requiredSkills.map((s) => s.toLowerCase()));
      const hasAnySelectedSkill = filters.skills.some((sk) =>
        oppSkills.has(sk.toLowerCase())
      );
      if (!hasAnySelectedSkill) return false;
    }
    if (filters.minStipendInr > 0) {
      if (o.monthlyStipendInr === null || o.monthlyStipendInr < filters.minStipendInr) {
        return false;
      }
    }
    if (o.score.total < filters.minScore) return false;
    if (filters.verifiedOnly && o.verificationStatus !== 'verified') return false;
    if (filters.savedOnly && !o.bookmarked) return false;
    if (filters.deadlineWithinDays !== null) {
      if (!o.deadline || o.eligibilityStatus === 'expired') return false;
      const days = Math.ceil(
        (new Date(o.deadline).getTime() - new Date(referenceDateIso).getTime()) / 86400000
      );
      if (days < 0 || days > filters.deadlineWithinDays) return false;
    }
    if (filters.closingSoonOnly) {
      if (!o.deadline || o.eligibilityStatus === 'expired') return false;
      const days = Math.ceil(
        (new Date(o.deadline).getTime() - new Date(referenceDateIso).getTime()) / 86400000
      );
      if (days < 0 || days > 7) return false;
    }
    if (locQ) {
      const locHay = `${o.location} ${o.cityTag} ${o.workMode}`.toLowerCase();
      if (!locHay.includes(locQ)) return false;
    }
    if (q) {
      const hay =
        `${o.title} ${o.company} ${o.companyTagline} ${o.location} ${o.track} ${o.requiredSkills.join(' ')} ${o.evidence.sourceName}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export async function fetchFromBackend<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`FastAPI ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export function nowIstString(): string {
  const d = new Date();
  return (
    d.toLocaleTimeString('en-IN', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }) + ' IST'
  );
}

export interface MockRunCallbacks {
  getTelemetry: () => RunTelemetry;
  isKilled: () => boolean;
  onTelemetry: (patch: Partial<RunTelemetry>) => void;
  onAudit: (event: AuditEvent) => void;
  onUpsertOpportunity: (opp: Opportunity) => void;
  onDeliverDigest: (digest: SandboxDigestMessage) => void;
  onUpdateSource: (id: string, patch: Partial<SourceFeed>) => void;
}

const DISCOVERABLE_BATCH: Array<Omit<Opportunity, 'score' | 'eligibilityStatus'>> = [
  {
    id: 'opp-zepto-new-13',
    canonicalKey: 'zepto-backend-ai-intern-2027',
    title: 'Software Engineer Intern — Search & Relevance',
    company: 'Zepto',
    companyTagline: 'Quick Commerce · High Growth',
    opportunityType: 'Internship',
    durationLabel: '6 Months · Hybrid',
    location: 'Bengaluru, Karnataka',
    cityTag: 'Bengaluru',
    workMode: 'Hybrid',
    track: 'Software & Backend',
    compensation: '₹50,000 / month',
    monthlyStipendInr: 50000,
    deadline: '2026-12-01',
    minGraduationYear: 2027,
    minCgpa: 7.5,
    requiredDegrees: ['B.Tech', 'Computer Science'],
    requiredSkills: ['Python', 'FastAPI', 'SQL', 'Docker', 'Git'],
    responsibilities: [
      'Tune query autocomplete latency and product relevance scoring services in FastAPI.',
      'Analyze search zero-result telemetry with SQL pipelines.',
    ],
    verificationStatus: 'verified',
    scamFlags: [],
    sourceConfidence: 0.95,
    evidence: {
      sourceName: 'YC Work at a Startup (Public API)',
      sourceUrl: 'https://www.workatastartup.com/jobs/zepto-search-intern-2027',
      checkedAt: 'Just now',
      snippet:
        '"Zepto Search & Discovery team seeks 2027 B.Tech CSE interns proficient in Python, FastAPI, SQL, Docker. Stipend: ₹50,000/mo. Closes Dec 1, 2026."',
      changeNote: 'Discovered during unattended autonomous run.',
    },
    checklist: [
      { id: 'c1', label: 'Review search ranking & query latency project notes', done: false },
      { id: 'c2', label: 'Export tailored 1-page resume PDF', done: false },
    ],
    draftNote:
      'Hello Zepto Engineering, I am a 2027 B.Tech CSE student experienced in Python, FastAPI, SQL, and Docker, excited to contribute to Search & Relevance.',
    bookmarked: false,
    applied: false,
    isNew: true,
  },
  {
    id: 'opp-fractal-new-14',
    canonicalKey: 'fractal-ml-intern-2027',
    title: 'Decision Science & LLM Evaluation Intern',
    company: 'Fractal Analytics',
    companyTagline: 'Enterprise AI · Analytics',
    opportunityType: 'Internship',
    durationLabel: '6 Months · Remote',
    location: 'Remote (India)',
    cityTag: 'Remote',
    workMode: 'Remote',
    track: 'AI / ML & Data',
    compensation: '₹35,000 / month',
    monthlyStipendInr: 35000,
    deadline: '2026-12-06',
    minGraduationYear: 2027,
    minCgpa: 7.0,
    requiredDegrees: ['B.Tech', 'Computer Science'],
    requiredSkills: ['Python', 'SQL', 'Git'],
    responsibilities: [
      'Build golden evaluation datasets for enterprise RAG and structured extraction.',
    ],
    verificationStatus: 'verified',
    scamFlags: [],
    sourceConfidence: 0.9,
    evidence: {
      sourceName: 'GitHub Tech Internships RSS',
      sourceUrl: 'https://careers.fractal.ai/internships/eval-2027',
      checkedAt: 'Just now',
      snippet:
        '"Remote internship for 2027 graduates. Skills: Python, SQL, reproducible Git workflows. Stipend INR 35k/mo. Apply before Dec 6, 2026."',
      changeNote: 'Discovered during unattended autonomous run.',
    },
    checklist: [
      { id: 'c1', label: 'Attach SQL & Python analytics notebook sample', done: false },
    ],
    draftNote:
      'Dear Fractal Team, I would love to bring my Python and SQL engineering background to your LLM Evaluation team.',
    bookmarked: false,
    applied: false,
    isNew: true,
  },
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Exact 11-stage explicit state machine:
 *   0 trigger -> 1 plan -> 2 fetch -> 3 extract -> 4 verify -> 5 dedupe
 *   -> 6 match -> 7 rank -> 8 decide -> 9 act -> 10 report
 */
export async function runMockAutonomousPipeline(
  profile: StudentProfile,
  sources: SourceFeed[],
  existingOpportunities: Opportunity[],
  cb: MockRunCallbacks
) {
  const runId = `run-${Date.now().toString().slice(-6)}`;
  const enabledSources = sources.filter((s) => s.enabled && s.circuitBreaker === 'closed');

  const stages: Array<{ stage: AgentStage; pct: number; delay: number }> = [
    { stage: 'trigger', pct: 8, delay: 320 },
    { stage: 'plan', pct: 16, delay: 350 },
    { stage: 'fetch', pct: 32, delay: 550 },
    { stage: 'extract', pct: 48, delay: 550 },
    { stage: 'verify', pct: 60, delay: 500 },
    { stage: 'dedupe', pct: 70, delay: 400 },
    { stage: 'match', pct: 80, delay: 380 },
    { stage: 'rank', pct: 88, delay: 300 },
    { stage: 'decide', pct: 93, delay: 350 },
    { stage: 'act', pct: 97, delay: 420 },
    { stage: 'report', pct: 100, delay: 300 },
  ];

  cb.onTelemetry({
    runId,
    state: 'running',
    currentStage: 'trigger',
    progressPct: 6,
    startedAt: nowIstString(),
    finishedAt: null,
    heartbeatAt: nowIstString(),
    activeSourceName: 'Scheduler Daemon',
    killReason: undefined,
  });

  let discoveredList: Opportunity[] = [];

  for (const step of stages) {
    await sleep(step.delay);
    if (cb.isKilled()) return;

    const tel = cb.getTelemetry();
    const nextRequests = Math.min(tel.requestsLimit, tel.requestsUsed + 1);
    const nextTokens = Math.min(tel.tokensLimit, tel.tokensUsed + 420);
    const nextCost = Number((tel.estimatedCostUsd + 0.0015).toFixed(4));
    const nextElapsed = tel.elapsedSeconds + 1;

    cb.onTelemetry({
      currentStage: step.stage,
      progressPct: step.pct,
      heartbeatAt: nowIstString(),
      requestsUsed: nextRequests,
      tokensUsed: nextTokens,
      estimatedCostUsd: nextCost,
      elapsedSeconds: nextElapsed,
    });

    if (step.stage === 'trigger') {
      cb.onAudit({
        id: `evt-${Date.now()}-trig`,
        runId,
        timestamp: nowIstString(),
        stage: 'trigger',
        kind: 'decision',
        summary: `Run ${runId} triggered (${tel.runMode.toUpperCase()} mode)`,
        detail: `Kill switch DB/file flags clear. Heartbeat recorded.`,
        allowlisted: true,
      });
    }

    if (step.stage === 'plan') {
      cb.onAudit({
        id: `evt-${Date.now()}-plan`,
        runId,
        timestamp: nowIstString(),
        stage: 'plan',
        kind: 'decision',
        summary: `Planned ${enabledSources.length} due sources (circuit breakers closed)`,
        detail: `Prioritized sources with approaching deadlines.`,
        allowlisted: true,
      });
    }

    if (step.stage === 'fetch') {
      const target = enabledSources[0]?.name ?? 'Allowlisted RSS';
      cb.onTelemetry({ activeSourceName: target });
      cb.onAudit({
        id: `evt-${Date.now()}-fetch`,
        runId,
        timestamp: nowIstString(),
        stage: 'fetch',
        kind: 'gateway_call',
        sourceName: target,
        toolName: 'gateway.fetch_allowlisted',
        summary: `Fetched ${enabledSources.length} feeds via Tool Gateway`,
        detail: `robots.txt verified; content hashes compared to skip unchanged pages.`,
        allowlisted: true,
      });
    }

    if (step.stage === 'extract') {
      cb.onTelemetry({ activeSourceName: 'Quarantined Extractor (No Tools)' });
      for (const candidate of DISCOVERABLE_BATCH) {
        const exists = existingOpportunities.some(
          (o) => o.canonicalKey === candidate.canonicalKey
        );
        if (!exists) {
          const { score, eligibilityStatus } = evaluateOpportunityMatch(candidate, profile);
          const built: Opportunity = {
            ...candidate,
            evidence: { ...candidate.evidence, checkedAt: nowIstString() },
            score,
            eligibilityStatus,
          };
          discoveredList.push(built);
          cb.onUpsertOpportunity(built);
        }
      }
      cb.onAudit({
        id: `evt-${Date.now()}-ext`,
        runId,
        timestamp: nowIstString(),
        stage: 'extract',
        kind: 'gateway_call',
        toolName: 'extractor.schema_only',
        summary: `Quarantined LLM emitted ${discoveredList.length} candidate records (zero tool access)`,
        detail: 'Extracted structured JSON schema strictly as untrusted data.',
        allowlisted: true,
      });
    }

    if (step.stage === 'verify') {
      cb.onAudit({
        id: `evt-${Date.now()}-ver`,
        runId,
        timestamp: nowIstString(),
        stage: 'verify',
        kind: 'decision',
        toolName: 'verifier.deterministic_check',
        summary: 'Verified URLs, ATS domains, verbatim deadline snippets & scam red flags',
        detail: 'No fee-charging or personal-email red flags found in new batch.',
        allowlisted: true,
      });
    }

    if (step.stage === 'dedupe') {
      cb.onAudit({
        id: `evt-${Date.now()}-dedupe`,
        runId,
        timestamp: nowIstString(),
        stage: 'dedupe',
        kind: 'decision',
        toolName: 'dedupe.canonical_merge',
        summary: 'Canonical key + fuzzy similarity check completed',
        detail: 'Zero duplicate cards emitted into shortlist.',
        allowlisted: true,
      });
    }

    if (step.stage === 'decide') {
      cb.onAudit({
        id: `evt-${Date.now()}-dec`,
        runId,
        timestamp: nowIstString(),
        stage: 'decide',
        kind: 'decision',
        summary: `Decided: ${discoveredList.length} ready for digest, uncertain items parked in Review Queue`,
        detail: 'Explicit decision log saved before Stage 9 Act.',
        allowlisted: true,
      });
    }

    if (step.stage === 'act') {
      const pool = [...discoveredList, ...existingOpportunities].filter(
        (o) => o.eligibilityStatus === 'eligible'
      );
      const top3 = [...pool]
        .sort((a, b) => b.score.total - a.score.total)
        .slice(0, 3)
        .map((o) => ({
          title: o.title,
          company: o.company,
          fit: o.score.total,
          deadline: o.deadline,
          url: o.evidence.sourceUrl,
        }));

      cb.onDeliverDigest({
        id: `dig-${Date.now()}`,
        runId,
        sentAt: nowIstString(),
        recipient: 'aarav.sandbox@campusos.local',
        subject: `CampusOS Digest (${runId}): +${discoveredList.length} New · ${pool.length} Eligible`,
        newCount: discoveredList.length,
        urgentCount: pool.filter((o) => o.deadline && o.deadline <= '2026-12-02').length,
        reviewCount: existingOpportunities.filter((o) => o.eligibilityStatus === 'needs_review')
          .length,
        highlights: top3,
      });

      cb.onAudit({
        id: `evt-${Date.now()}-act`,
        runId,
        timestamp: nowIstString(),
        stage: 'act',
        kind: 'gateway_call',
        toolName: 'gateway.send_sandbox_digest',
        summary: 'Sent digest to sandbox inbox & refreshed .ics calendar reminders',
        detail: 'Whitelisted recipient aarav.sandbox@campusos.local. Never auto-applied.',
        allowlisted: true,
      });
    }

    if (step.stage === 'report') {
      for (const s of enabledSources) {
        cb.onUpdateSource(s.id, { status: 'healthy', lastChecked: nowIstString() });
      }
      cb.onTelemetry({
        state: 'completed',
        currentStage: 'report',
        progressPct: 100,
        finishedAt: nowIstString(),
        activeSourceName: null,
        newCount: tel.newCount + discoveredList.length,
      });
      cb.onAudit({
        id: `evt-${Date.now()}-rep`,
        runId,
        timestamp: nowIstString(),
        stage: 'report',
        kind: 'decision',
        summary: `Closed run ${runId} · Written traces/${runId}.jsonl`,
        detail: 'Dashboard updated; daemon waiting for next scheduled trigger.',
        allowlisted: true,
      });
    }
  }
}
