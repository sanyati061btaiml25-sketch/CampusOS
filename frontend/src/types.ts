export type EligibilityStatus = 'eligible' | 'needs_review' | 'expired';
export type VerificationStatus = 'verified' | 'uncertain' | 'conflict';
export type AgentRunState = 'idle' | 'running' | 'completed' | 'killed' | 'error';
export type RunMode = 'mock' | 'replay' | 'live';
export type OpportunityType = 'Internship' | 'Full-Time' | 'Research';
export type WorkMode = 'Remote' | 'Hybrid' | 'On-site';
export type RoleTrack =
  | 'Software & Backend'
  | 'AI / ML & Data'
  | 'Frontend & Product'
  | 'Cloud & DevOps';

/**
 * Exact 11-stage explicit state machine from CampusOS: Architecture Guide
 */
export type AgentStage =
  | 'trigger'
  | 'plan'
  | 'fetch'
  | 'extract'
  | 'verify'
  | 'dedupe'
  | 'match'
  | 'rank'
  | 'decide'
  | 'act'
  | 'report';

export interface StudentProfile {
  name: string;
  degree: string;
  discipline: string;
  graduationYear: number;
  cgpa: number;
  skills: string[];
  preferredRoles: string[];
  preferredLocations: string[];
  minStipendMonthlyInr: number;
  draftConsent: boolean;
}

export interface ScoreBreakdown {
  skillScore: number;       // max 40
  degreeYearScore: number;  // max 20
  locationScore: number;    // max 15
  urgencyScore: number;     // max 15
  confidenceScore: number;  // max 10
  total: number;            // 0-100
  matchedSkills: string[];
  missingSkills: string[];
  reasons: string[];
}

export interface SourceEvidence {
  sourceName: string;
  sourceUrl: string;
  checkedAt: string;
  snippet: string;
  mergedFrom?: string[];
  changeNote?: string;
}

export interface ChecklistItem {
  id: string;
  label: string;
  done: boolean;
}

export interface Opportunity {
  id: string;
  canonicalKey: string;
  title: string;
  company: string;
  companyTagline: string;
  opportunityType: OpportunityType;
  durationLabel: string;
  location: string;
  cityTag: string;
  workMode: WorkMode;
  track: RoleTrack;
  compensation: string | null;
  monthlyStipendInr: number | null;
  deadline: string | null; // ISO YYYY-MM-DD or null when unknown
  minGraduationYear: number | null;
  minCgpa: number | null;
  requiredDegrees: string[];
  requiredSkills: string[];
  responsibilities: string[];
  eligibilityStatus: EligibilityStatus;
  verificationStatus: VerificationStatus;
  scamFlags: string[];
  sourceConfidence: number; // 0-1
  evidence: SourceEvidence;
  score: ScoreBreakdown;
  checklist: ChecklistItem[];
  draftNote: string;
  bookmarked: boolean;
  applied: boolean;
  dismissed?: boolean;
  isNew?: boolean;
}

export interface SourceFeed {
  id: string;
  name: string;
  type: 'Official API' | 'Public RSS' | 'University Feed' | 'Permitted Page';
  url: string;
  enabled: boolean;
  intervalHours: number;
  lastChecked: string;
  contentHash: string;
  circuitBreaker: 'closed' | 'open';
  status: 'healthy' | 'rate_limited' | 'error';
  itemsFound: number;
  robotsAllowed: boolean;
}

export interface AuditEvent {
  id: string;
  runId: string;
  timestamp: string;
  stage: AgentStage | 'kill_switch' | 'scheduler';
  kind: 'gateway_call' | 'decision' | 'warning' | 'error' | 'kill_switch';
  sourceName?: string;
  toolName?: string;
  summary: string;
  detail: string;
  allowlisted?: boolean;
}

export interface SandboxDigestMessage {
  id: string;
  runId: string;
  sentAt: string;
  recipient: string;
  subject: string;
  newCount: number;
  urgentCount: number;
  reviewCount: number;
  highlights: Array<{
    title: string;
    company: string;
    fit: number;
    deadline: string | null;
    url: string;
  }>;
}

export interface TrapPackResult {
  id: string;
  name: string;
  category: 'Prompt Injection' | 'Scam Red Flag' | 'Conflicting Dates' | 'HTTP 503 Outage' | 'Duplicate Payload';
  inputSummary: string;
  expectedOutcome: string;
  actualOutcome: string;
  passed: boolean;
  lastRunAt: string;
}

export interface RunTelemetry {
  runId: string;
  state: AgentRunState;
  runMode: RunMode;
  currentStage: AgentStage | null;
  progressPct: number;
  startedAt: string | null;
  finishedAt: string | null;
  heartbeatAt: string;
  requestsUsed: number;
  requestsLimit: number;
  tokensUsed: number;
  tokensLimit: number;
  estimatedCostUsd: number;
  costLimitUsd: number;
  elapsedSeconds: number;
  timeLimitSeconds: number;
  nextScheduledInMinutes: number;
  schedulerEnabled: boolean;
  activeSourceName: string | null;
  newCount: number;
  dedupedCount: number;
  killSwitchDbFlag: boolean;
  killSwitchFileFlag: boolean;
  killReason?: string;
}

export interface OpportunityFilters {
  query: string;
  locationQuery: string;
  statuses: EligibilityStatus[];
  types: OpportunityType[];
  workModes: WorkMode[];
  tracks: RoleTrack[];
  cities: string[];
  sources: string[];
  skills: string[];
  minStipendInr: number;
  minScore: number;
  deadlineWithinDays: number | null;
  verifiedOnly: boolean;
  savedOnly: boolean;
  closingSoonOnly: boolean;
}
