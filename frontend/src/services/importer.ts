import { Opportunity, StudentProfile } from '../types';
import { evaluateOpportunityMatch } from '../engine/matcher';
import { nowIstString, safeHttpUrl } from './api';

const INJECTION_PATTERNS = [
  /ignore\s+previous\s+instructions/i,
  /system\s+override/i,
  /exfiltrate/i,
  /\.env/i,
  /webhook\./i,
];

function detectScamFlags(text: string): string[] {
  const flags: string[] = [];
  if (/registration\s+fee|security\s+deposit|pay\s+₹|pay\s+\$/i.test(text)) {
    flags.push('Fee / payment requested');
  }
  if (/@gmail\.com|@yahoo\.com|whatsapp\s+only/i.test(text)) {
    flags.push('Personal email / informal contact');
  }
  return flags;
}

function containsInjection(text: string): boolean {
  return INJECTION_PATTERNS.some((rx) => rx.test(text));
}

/**
 * Safely validates, sanitizes, deduplicates, and scores JSON payloads
 * handed over by Member 1's backend/scraper.
 * Hostile prompt-injection payloads are dropped at the Tool Gateway (never shown on student dashboard).
 */
export function importTeammateOpportunitiesJson(
  rawJson: string,
  profile: StudentProfile,
  existing: Opportunity[]
): {
  imported: Opportunity[];
  mergedCount: number;
  blockedInjectionCount: number;
  rejectedCount: number;
} {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawJson);
  } catch {
    throw new Error('Invalid JSON syntax. Please check the JSON format from backend.');
  }

  const items: unknown[] = Array.isArray(parsed)
    ? parsed
    : typeof parsed === 'object' &&
      parsed !== null &&
      Array.isArray((parsed as { opportunities?: unknown[] }).opportunities)
    ? (parsed as { opportunities: unknown[] }).opportunities
    : [parsed];

  const existingKeys = new Set(existing.map((o) => o.canonicalKey));
  const imported: Opportunity[] = [];
  let mergedCount = 0;
  let blockedInjectionCount = 0;
  let rejectedCount = 0;

  items.forEach((item, index) => {
    if (!item || typeof item !== 'object') {
      rejectedCount += 1;
      return;
    }
    const rec = item as Record<string, unknown>;
    const title = String(rec.title ?? '').trim().slice(0, 120);
    const company = String(rec.company ?? '').trim().slice(0, 80);
    if (!title || !company) {
      rejectedCount += 1;
      return;
    }

    const rawUrl = String(rec.source_url ?? rec.sourceUrl ?? '');
    const safeUrl = safeHttpUrl(rawUrl) || 'https://example.com/unverified-source';
    const snippet = String(
      rec.snippet ?? rec.description ?? 'Imported from backend payload.'
    ).slice(0, 400);

    // Block hostile prompt injections silently from the student feed & log in gateway
    if (containsInjection(`${title} ${snippet} ${String(rec.draftNote ?? '')}`)) {
      blockedInjectionCount += 1;
      return;
    }

    const canonicalKey = String(
      rec.canonicalKey ??
        rec.canonical_key ??
        `${company.toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${title
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .slice(0, 28)}`
    );

    if (existingKeys.has(canonicalKey)) {
      mergedCount += 1;
      return;
    }
    existingKeys.add(canonicalKey);

    const rawDeadline = rec.deadline ? String(rec.deadline).slice(0, 10) : null;
    const validDeadline =
      rawDeadline && /^\d{4}-\d{2}-\d{2}$/.test(rawDeadline) ? rawDeadline : null;

    const rawStipend =
      typeof rec.monthlyStipendInr === 'number'
        ? Math.max(0, Math.round(rec.monthlyStipendInr))
        : typeof rec.monthly_stipend_inr === 'number'
        ? Math.max(0, Math.round(rec.monthly_stipend_inr))
        : null;

    const rawSkills = Array.isArray(rec.requiredSkills)
      ? rec.requiredSkills.map((s) => String(s).slice(0, 32))
      : Array.isArray(rec.required_skills)
      ? rec.required_skills.map((s) => String(s).slice(0, 32))
      : ['Python'];

    const workModeRaw = String(rec.workMode ?? rec.work_mode ?? 'Hybrid');
    const workMode =
      workModeRaw === 'Remote' || workModeRaw === 'On-site' ? workModeRaw : 'Hybrid';

    const oppTypeRaw = String(rec.opportunityType ?? rec.opportunity_type ?? 'Internship');
    const opportunityType =
      oppTypeRaw === 'Full-Time' || oppTypeRaw === 'Research' ? oppTypeRaw : 'Internship';

    const trackRaw = String(rec.track ?? 'Software & Backend');
    const track =
      trackRaw === 'AI / ML & Data' ||
      trackRaw === 'Frontend & Product' ||
      trackRaw === 'Cloud & DevOps'
        ? trackRaw
        : 'Software & Backend';

    const scamFlags = detectScamFlags(`${title} ${snippet}`);
    const verificationStatus =
      scamFlags.length > 0 || validDeadline === null ? 'uncertain' : 'verified';

    const base: Omit<Opportunity, 'score' | 'eligibilityStatus'> = {
      id: `imp-${Date.now()}-${index}`,
      canonicalKey,
      title,
      company,
      companyTagline: String(
        rec.companyTagline ?? rec.company_tagline ?? 'Imported Backend Record'
      ).slice(0, 60),
      opportunityType,
      durationLabel: String(rec.durationLabel ?? rec.duration_label ?? '6 Months').slice(0, 40),
      location: String(rec.location ?? 'Bengaluru, India').slice(0, 60),
      cityTag: String(
        rec.cityTag ?? rec.city_tag ?? (workMode === 'Remote' ? 'Remote' : 'Bengaluru')
      ).slice(0, 30),
      workMode,
      track,
      compensation: rec.compensation
        ? String(rec.compensation).slice(0, 40)
        : rawStipend
        ? `₹${rawStipend.toLocaleString('en-IN')} / month`
        : null,
      monthlyStipendInr: rawStipend,
      deadline: validDeadline,
      minGraduationYear:
        typeof rec.minGraduationYear === 'number'
          ? rec.minGraduationYear
          : typeof rec.min_graduation_year === 'number'
          ? rec.min_graduation_year
          : 2027,
      minCgpa:
        typeof rec.minCgpa === 'number' ? Math.min(10, Math.max(0, rec.minCgpa)) : null,
      requiredDegrees: Array.isArray(rec.requiredDegrees)
        ? rec.requiredDegrees.map((d) => String(d))
        : ['B.Tech'],
      requiredSkills: rawSkills,
      responsibilities: Array.isArray(rec.responsibilities)
        ? rec.responsibilities.map((r) => String(r).slice(0, 180))
        : ['Imported directly from backend pipeline JSON.'],
      verificationStatus,
      scamFlags,
      sourceConfidence: validDeadline && scamFlags.length === 0 ? 0.92 : 0.62,
      evidence: {
        sourceName: String(
          rec.sourceName ?? rec.source_name ?? 'Backend JSON Import'
        ).slice(0, 60),
        sourceUrl: safeUrl,
        checkedAt: nowIstString(),
        snippet,
        changeNote:
          scamFlags.length > 0
            ? `Parked in Review Queue (${scamFlags.join(', ')})`
            : 'Validated & scored on import.',
      },
      checklist: [{ id: 'c1', label: 'Verify official link and prepare resume PDF', done: false }],
      draftNote: String(
        rec.draftNote ??
          `Hello ${company} Team, I am a ${profile.graduationYear} ${profile.degree} candidate interested in the ${title} role.`
      ).slice(0, 500),
      bookmarked: false,
      applied: false,
      isNew: true,
    };

    const { score, eligibilityStatus } = evaluateOpportunityMatch(base, profile);
    imported.push({ ...base, score, eligibilityStatus });
  });

  return { imported, mergedCount, blockedInjectionCount, rejectedCount };
}
