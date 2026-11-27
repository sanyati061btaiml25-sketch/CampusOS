import { Opportunity } from '../types';

function escapeIcsText(value: string): string {
  return value
    .replace(/\r/g, '')
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\n/g, '\\n');
}

function formatDateCompact(isoDate: string): string {
  return isoDate.replace(/-/g, '');
}

/**
 * Generates RFC-5545 .ics calendar reminder files (Stage 9: Act -> .ics deadline reminders)
 */
export function buildOpportunityIcs(opportunities: Opportunity[]): string {
  const dated = opportunities.filter((o) => Boolean(o.deadline));
  const nowStamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';

  const events = dated.map((opp) => {
    const dt = formatDateCompact(opp.deadline!);
    return [
      'BEGIN:VEVENT',
      `UID:${opp.id}@campusos.local`,
      `DTSTAMP:${nowStamp}`,
      `DTSTART;VALUE=DATE:${dt}`,
      `SUMMARY:${escapeIcsText(`Apply: ${opp.title} (${opp.company})`)}`,
      `DESCRIPTION:${escapeIcsText(
        `Match Score: ${opp.score.total}%\\nCompensation: ${opp.compensation ?? 'Unstated'}\\nSource: ${opp.evidence.sourceUrl}`
      )}`,
      `URL:${opp.evidence.sourceUrl}`,
      'BEGIN:VALARM',
      'TRIGGER:-P2D',
      'ACTION:DISPLAY',
      'DESCRIPTION:CampusOS Deadline Reminder (2 days remaining)',
      'END:VALARM',
      'END:VEVENT',
    ].join('\r\n');
  });

  return [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//CampusOS//Autonomous Placement Agent//EN',
    'CALSCALE:GREGORIAN',
    ...events,
    'END:VCALENDAR',
  ].join('\r\n');
}

export function downloadIcsFile(opportunities: Opportunity[], filename: string): number {
  const dated = opportunities.filter((o) => Boolean(o.deadline));
  if (dated.length === 0) return 0;
  const content = buildOpportunityIcs(dated);
  const blob = new Blob([content], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
  return dated.length;
}
