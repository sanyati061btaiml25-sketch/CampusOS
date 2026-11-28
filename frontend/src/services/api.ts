import {
  AgentStage,
  ApiErrorPayload,
  ApiStatusResponse,
  ApiTrapPackResponse,
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
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  'http://localhost:8000';

export const IS_FASTAPI_MODE = import.meta.env.VITE_API_MODE === 'fastapi';

export const DEFAULT_RUN_MODE: RunMode = IS_FASTAPI_MODE ? 'live' : 'mock';

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

export class ApiClientError extends Error {
  status: number;
  code: string;
  detail: string;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.detail || `API ${status}: ${payload.error}`);
    this.status = status;
    this.code = payload.error || 'internal';
    this.detail = payload.detail || this.message;
  }
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
    const raw = await res.text();
    try {
      const parsed = JSON.parse(raw) as Partial<ApiErrorPayload>;
      if (parsed && typeof parsed.error === 'string') {
        throw new ApiClientError(res.status, {
          error: parsed.error,
          detail: typeof parsed.detail === 'string' ? parsed.detail : raw,
        });
      }
    } catch (err) {
      if (err instanceof ApiClientError) throw err;
    }
    throw new ApiClientError(res.status, {
      error: res.status === 404 ? 'not_found' : res.status === 409 ? 'conflict' : 'internal',
      detail: raw || `FastAPI ${res.status}`,
    });
  }
  return res.json() as Promise<T>;
}

/* -------------------------------------------------------------------------
 * CampusOS API Contract (v1) Endpoints
 * ---------------------------------------------------------------------- */

export interface ApiListResponse<T> {
  items: T[];
  total: number;
}

export interface ApiOpportunityItem {
  id: number | string;
  title: string;
  company: string;
  apply_url: string;
  location_raw?: string | null;
  location_norm?: string[];
  countries?: string[];
  remote_ok?: boolean;
  remote_scope?: string;
  seniority?: string;
  employment_type?: string;
  min_experience_yrs?: number | null;
  grad_year_min?: number | null;
  skills?: string[];
  deadline?: string | null;
  deadline_kind?: string;
  deadline_evidence?: string | null;
  posted_at?: string | null;
  status?: 'pending' | 'verified' | 'needs_review' | 'expired';
  confidence?: number;
  flags?: string[];
  first_seen_at?: string;
  last_changed_at?: string | null;
  also_in?: string[];
  source?: { id: number; name: string; platform: string };
  match?: {
    eligibility: 'pass' | 'fail' | 'unknown';
    eligibility_reasons: string[];
    score: number | null;
    score_breakdown: Record<string, number>;
    score_reasons: string[];
    decision: 'pending' | 'notify' | 'queue' | 'skip' | 'backed_off';
    decision_reason: string | null;
    ranked_position: number | null;
  };
  evidence?: Array<{ kind: string; snippet: string | null; source_url: string | null; recorded_at: string }>;
}

export interface ApiEventItem {
  seq: number;
  ts: string;
  type: string;
  stage: string | null;
  tool: string | null;
  input_summary: string | null;
  result_summary: string | null;
  decision: string | null;
  reason: string | null;
  error: string | null;
  cost_usd: number;
  tokens: number;
  opportunity_id: number | null;
}

export interface ApiSourceItem {
  id: number;
  name: string;
  platform: string;
  enabled: boolean;
  trust_tier: number;
  breaker_state: 'closed' | 'open' | 'half_open';
  breaker_failures: number;
  last_ok_at: string | null;
  interval_s: number;
  last_snapshot?: {
    status: string;
    item_count: number | null;
    fetched_at: string;
    http_status: number | null;
  } | null;
}

export interface ApiReviewQueueItem {
  id: number;
  reason: string;
  detail: string | null;
  created_at: string;
  resolved_at: string | null;
  resolution: 'accepted' | 'rejected' | 'ignored' | null;
  opportunity?: ApiOpportunityItem;
}

export interface ApiActionItem {
  id: number;
  run_id: number;
  type: 'digest' | 'ics';
  target: string;
  payload_ref: string | null;
  status: string;
  error: string | null;
  opportunity_id: number | null;
  profile_id: number | null;
  created_at: string;
  sent_at: string | null;
}

export function mapApiOpportunityToUi(item: ApiOpportunityItem): Opportunity {
  const elig = item.match?.eligibility;
  const eligibilityStatus: Opportunity['eligibilityStatus'] =
    item.status === 'expired'
      ? 'expired'
      : elig === 'pass' && item.status === 'verified'
      ? 'eligible'
      : 'needs_review';

  const verificationStatus: Opportunity['verificationStatus'] =
    item.status === 'verified'
      ? 'verified'
      : (item.flags || []).includes('conflict_deadline')
      ? 'conflict'
      : 'uncertain';

  const scorePct =
    item.match?.score != null ? Math.round(item.match.score * 100) : Math.round((item.confidence ?? 0.5) * 100);

  const city = item.location_norm?.[0] || item.location_raw || 'Remote';
  const empType: Opportunity['opportunityType'] =
    item.employment_type === 'full_time' ? 'Full-Time' : 'Internship';

  return {
    id: String(item.id),
    canonicalKey: `${item.source?.name || 'source'}:${item.id}`,
    title: item.title,
    company: item.company,
    companyTagline: `${item.source?.platform || 'official'} · ${city}`,
    opportunityType: empType,
    durationLabel: empType === 'Internship' ? 'Internship' : 'Full-Time',
    location: item.location_raw || city,
    cityTag: city,
    workMode: item.remote_ok ? 'Remote' : 'On-site',
    track: 'Software & Backend',
    compensation: null,
    monthlyStipendInr: null,
    deadline: item.deadline || null,
    minGraduationYear: item.grad_year_min ?? null,
    minCgpa: null,
    requiredDegrees: ['B.Tech'],
    requiredSkills: item.skills || [],
    responsibilities: item.evidence?.map((e) => e.snippet || '').filter(Boolean) || [],
    eligibilityStatus,
    verificationStatus,
    scamFlags: item.flags || [],
    sourceConfidence: item.confidence ?? 0.5,
    evidence: {
      sourceName: item.source?.name || 'Official Source',
      sourceUrl: item.apply_url,
      checkedAt: item.first_seen_at || '',
      snippet: item.deadline_evidence || item.evidence?.[0]?.snippet || 'Verified via backend pipeline.',
      mergedFrom: item.also_in,
    },
    score: {
      skillScore: Math.round((item.match?.score_breakdown?.skills ?? 0.3) * 100),
      degreeYearScore: 18,
      locationScore: Math.round((item.match?.score_breakdown?.location ?? 0.12) * 100),
      urgencyScore: 10,
      confidenceScore: Math.round((item.confidence ?? 0.8) * 10),
      total: scorePct,
      matchedSkills: item.skills || [],
      missingSkills: [],
      reasons: item.match?.score_reasons || item.match?.eligibility_reasons || [],
    },
    checklist: [],
    draftNote: item.match?.decision_reason || '',
    bookmarked: false,
    applied: false,
    alsoIn: item.also_in,
  };
}

export function getApiStatus() {
  return fetchFromBackend<ApiStatusResponse>('/api/status');
}

export function getApiRuns(limit = 50, offset = 0) {
  return fetchFromBackend<ApiListResponse<Record<string, unknown>>>(
    `/api/runs?limit=${limit}&offset=${offset}`
  );
}

export function getApiRunById(id: number | string) {
  return fetchFromBackend<Record<string, unknown>>(`/api/runs/${id}`);
}

export function getApiOpportunities(params?: {
  profile_id?: number;
  status?: string;
  seniority?: string;
  decision?: string;
  q?: string;
  limit?: number;
  offset?: number;
}) {
  const sp = new URLSearchParams();
  if (params?.profile_id != null) sp.set('profile_id', String(params.profile_id));
  if (params?.status) sp.set('status', params.status);
  if (params?.seniority) sp.set('seniority', params.seniority);
  if (params?.decision) sp.set('decision', params.decision);
  if (params?.q) sp.set('q', params.q);
  sp.set('limit', String(params?.limit ?? 50));
  sp.set('offset', String(params?.offset ?? 0));
  return fetchFromBackend<ApiListResponse<ApiOpportunityItem>>(`/api/opportunities?${sp.toString()}`);
}

export function getApiOpportunityById(id: number | string) {
  return fetchFromBackend<ApiOpportunityItem>(`/api/opportunities/${id}`);
}

export function getApiEvents(params?: { run_id?: number; after_seq?: number; limit?: number }) {
  const sp = new URLSearchParams();
  if (params?.run_id != null) sp.set('run_id', String(params.run_id));
  if (params?.after_seq != null) sp.set('after_seq', String(params.after_seq));
  sp.set('limit', String(params?.limit ?? 100));
  return fetchFromBackend<ApiListResponse<ApiEventItem>>(`/api/events?${sp.toString()}`);
}

export function getApiCoverage(runId?: number) {
  const q = runId != null ? `?run_id=${runId}` : '';
  return fetchFromBackend<Record<string, unknown>>(`/api/coverage${q}`);
}

export function getApiSources() {
  return fetchFromBackend<ApiListResponse<ApiSourceItem>>('/api/sources');
}

export function getApiReviewQueue(resolved = false) {
  return fetchFromBackend<ApiListResponse<ApiReviewQueueItem>>(
    `/api/review-queue?resolved=${resolved}`
  );
}

export function getApiActions(runId?: number) {
  const q = runId != null ? `?run_id=${runId}` : '';
  return fetchFromBackend<ApiListResponse<ApiActionItem>>(`/api/actions${q}`);
}

export function getActionFileUrl(actionId: number | string): string {
  return `${API_BASE_URL}/api/actions/${actionId}/file`;
}

export function getApiProfiles() {
  return fetchFromBackend<ApiListResponse<Record<string, unknown>>>('/api/profiles');
}

export function getApiProfileById(id: number | string) {
  return fetchFromBackend<Record<string, unknown>>(`/api/profiles/${id}`);
}

export async function getApiTrapPack(): Promise<ApiTrapPackResponse> {
  try {
    return await fetchFromBackend<ApiTrapPackResponse>('/api/trap-pack');
  } catch (err) {
    if (err instanceof ApiClientError && err.status === 404) {
      return { notRunYet: true };
    }
    throw err;
  }
}

export function postKillSwitch(on: boolean) {
  return fetchFromBackend<{ kill_switch: boolean }>('/api/kill-switch', {
    method: 'POST',
    body: JSON.stringify({ on }),
  });
}

export function postRunRequest() {
  return fetchFromBackend<{ requested: boolean }>('/api/runs/request', {
    method: 'POST',
  });
}

export function postReviewResolution(
  id: number | string,
  resolution: 'accepted' | 'rejected' | 'ignored'
) {
  return fetchFromBackend<Record<string, unknown>>(`/api/review/${id}`, {
    method: 'POST',
    body: JSON.stringify({ resolution }),
  });
}

export function putProfile(id: number | string, payload: Record<string, unknown>) {
  return fetchFromBackend<Record<string, unknown>>(`/api/profiles/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function putProfileSearchIntent(id: number | string, payload: Record<string, unknown>) {
  return fetchFromBackend<Record<string, unknown>>(`/api/profiles/${id}/search-intent`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function postImportJson(payload: unknown) {
  return fetchFromBackend<Record<string, unknown>>('/api/import', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
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
