import { Opportunity, ScoreBreakdown, StudentProfile } from '../types';

/**
 * Deterministic, transparent matching engine (Stage 6: Match).
 * Hard rules checked first (unknown is never assumed eligible), then weighted preferences:
 *   40% Skill / Role match
 *   20% Degree, Graduation Year & CGPA fit
 *   15% Location preference
 *   15% Deadline urgency
 *   10% Source verification confidence
 */
export function evaluateOpportunityMatch(
  opp: Omit<Opportunity, 'score' | 'eligibilityStatus'>,
  profile: StudentProfile,
  referenceDateIso = '2026-11-25'
): { score: ScoreBreakdown; eligibilityStatus: Opportunity['eligibilityStatus'] } {
  const profileSkillsLower = new Set(profile.skills.map((s) => s.trim().toLowerCase()));
  const matchedSkills: string[] = [];
  const missingSkills: string[] = [];

  for (const req of opp.requiredSkills) {
    if (profileSkillsLower.has(req.trim().toLowerCase())) {
      matchedSkills.push(req);
    } else {
      missingSkills.push(req);
    }
  }

  const skillRatio =
    opp.requiredSkills.length > 0 ? matchedSkills.length / opp.requiredSkills.length : 0.5;
  const skillScore = Math.round(skillRatio * 40);

  let degreeYearScore = 0;
  const reasons: string[] = [];

  if (matchedSkills.length > 0) {
    reasons.push(`Matches ${matchedSkills.slice(0, 3).join(', ')}`);
  }
  if (missingSkills.length > 0) {
    reasons.push(`Gap: ${missingSkills.slice(0, 2).join(', ')}`);
  }

  const degreeMatches =
    opp.requiredDegrees.length === 0 ||
    opp.requiredDegrees.some(
      (deg) =>
        profile.degree.toLowerCase().includes(deg.toLowerCase()) ||
        profile.discipline.toLowerCase().includes(deg.toLowerCase())
    );

  const yearKnown = opp.minGraduationYear !== null;
  const yearMatches = yearKnown ? opp.minGraduationYear === profile.graduationYear : false;
  const cgpaOk = opp.minCgpa === null || profile.cgpa >= opp.minCgpa;

  if (degreeMatches && yearMatches && cgpaOk) {
    degreeYearScore = 20;
    reasons.push(`${profile.degree} ${profile.graduationYear} eligible`);
  } else if (!cgpaOk && opp.minCgpa !== null) {
    degreeYearScore = 5;
    reasons.push(`Requires ${opp.minCgpa}+ CGPA (profile: ${profile.cgpa})`);
  } else if (degreeMatches && !yearKnown) {
    degreeYearScore = 10;
    reasons.push('Batch year unstated — verify manually');
  } else if (!degreeMatches) {
    degreeYearScore = 4;
    reasons.push(`Requires ${opp.requiredDegrees.join('/')}`);
  } else {
    degreeYearScore = 6;
    reasons.push(`Targets ${opp.minGraduationYear} batch`);
  }

  const prefLocs = profile.preferredLocations.map((l) => l.toLowerCase());
  const oppLocLower = opp.location.toLowerCase();
  const locationMatches =
    opp.workMode === 'Remote' ||
    prefLocs.some((loc) => oppLocLower.includes(loc) || loc.includes(oppLocLower));
  const locationScore = locationMatches ? 15 : 6;
  if (locationMatches) {
    reasons.push(opp.workMode === 'Remote' ? 'Remote friendly' : `${opp.cityTag} match`);
  }

  let urgencyScore = 5;
  let isExpired = false;
  if (opp.deadline) {
    const daysLeft = Math.ceil(
      (new Date(opp.deadline).getTime() - new Date(referenceDateIso).getTime()) / 86400000
    );
    if (daysLeft < 0) {
      isExpired = true;
      urgencyScore = 0;
      reasons.push(`Closed ${opp.deadline}`);
    } else if (daysLeft <= 5) {
      urgencyScore = 15;
      reasons.push(`Closes in ${daysLeft}d`);
    } else if (daysLeft <= 14) {
      urgencyScore = 11;
    } else {
      urgencyScore = 7;
    }
  } else {
    urgencyScore = 4;
    reasons.push('Deadline unstated');
  }

  const confidenceScore = Math.round(opp.sourceConfidence * 10);
  const total = Math.min(
    100,
    skillScore + degreeYearScore + locationScore + urgencyScore + confidenceScore
  );

  let eligibilityStatus: Opportunity['eligibilityStatus'] = 'eligible';
  if (isExpired) {
    eligibilityStatus = 'expired';
  } else if (
    opp.scamFlags.length > 0 ||
    opp.verificationStatus === 'conflict' ||
    opp.verificationStatus === 'uncertain' ||
    !yearKnown ||
    !opp.deadline ||
    !degreeMatches ||
    !yearMatches ||
    !cgpaOk
  ) {
    eligibilityStatus = 'needs_review';
  }

  return {
    eligibilityStatus,
    score: {
      skillScore,
      degreeYearScore,
      locationScore,
      urgencyScore,
      confidenceScore,
      total,
      matchedSkills,
      missingSkills,
      reasons,
    },
  };
}
