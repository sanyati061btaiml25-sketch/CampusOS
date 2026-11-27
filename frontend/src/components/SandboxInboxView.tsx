import React from 'react';
import {
  AlertTriangle,
  CalendarPlus,
  CheckCircle2,
  ExternalLink,
  Inbox,
  ShieldAlert,
  Trash2,
} from 'lucide-react';
import { Opportunity, SandboxDigestMessage } from '../types';
import { safeHttpUrl } from '../services/api';
import { CompanyMark } from './CompanyMark';
import { downloadIcsFile } from '../utils/ics';

interface Props {
  digests: SandboxDigestMessage[];
  reviewQueue: Opportunity[];
  eligibleOpportunities: Opportunity[];
  onApproveReviewItem: (id: string) => void;
  onDismissReviewItem: (id: string) => void;
  onInspectOpportunity: (id: string) => void;
}

export const SandboxInboxView: React.FC<Props> = ({
  digests,
  reviewQueue,
  eligibleOpportunities,
  onApproveReviewItem,
  onDismissReviewItem,
  onInspectOpportunity,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Action Outputs Header */}
      <div className="panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Inbox size={18} /> Autonomous Actions: Sandbox Inbox &amp; Review Queue
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 13.5, color: 'var(--text-muted)' }}>
            Stage 9 (Act) delivers digests to a whitelisted sandbox inbox, generates <code>.ics</code> deadline reminders, and parks uncertain listings here for human review.
          </p>
        </div>

        <button
          className="btn btn-primary"
          onClick={() => downloadIcsFile(eligibleOpportunities, 'campusos-shortlist-deadlines.ics')}
        >
          <CalendarPlus size={15} /> Download All Deadlines (.ics)
        </button>
      </div>

      {/* Review Queue (uncertain / conflicting / scam flags) */}
      <div className="panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={16} color="#b45309" />
            Review Queue ({reviewQueue.length} item{reviewQueue.length === 1 ? '' : 's'})
          </h3>
          <span className="pill pill-amber">Uncertain fields never guessed</span>
        </div>

        {reviewQueue.length === 0 ? (
          <p style={{ margin: 0, fontSize: 13.5, color: 'var(--text-muted)' }}>
            Review queue is empty. All uncertain or conflicting items have been resolved.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {reviewQueue.map((opp) => (
              <div
                key={opp.id}
                style={{
                  border: '1px solid var(--border-hairline)',
                  borderRadius: 'var(--radius-md)',
                  padding: 16,
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 14,
                  background: 'rgba(245, 158, 11, 0.08)',
                }}
              >
                <div style={{ display: 'flex', gap: 14, flex: 1, minWidth: 260 }}>
                  <CompanyMark company={opp.company} size={44} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 15 }}>{opp.title}</div>
                    <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                      {opp.company} · {opp.location} · Source: {opp.evidence.sourceName}
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13, color: 'var(--status-amber-fg)' }}>
                      <strong>Reason parked:</strong> {opp.score.reasons.join(' · ')}
                    </div>
                    {opp.scamFlags.length > 0 && (
                      <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
                        {opp.scamFlags.map((flag, i) => (
                          <span key={i} className="pill pill-red">
                            <ShieldAlert size={11} /> {flag}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="quote-box" style={{ marginTop: 10 }}>
                      {opp.evidence.snippet}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    className="btn btn-secondary"
                    style={{ height: 34 }}
                    onClick={() => onInspectOpportunity(opp.id)}
                  >
                    Inspect
                  </button>
                  <button
                    className="btn btn-primary"
                    style={{ height: 34 }}
                    onClick={() => onApproveReviewItem(opp.id)}
                  >
                    <CheckCircle2 size={14} /> Verify &amp; Approve
                  </button>
                  <button
                    className="btn btn-ghost"
                    style={{ height: 34, color: '#b91c1c' }}
                    onClick={() => onDismissReviewItem(opp.id)}
                  >
                    <Trash2 size={14} /> Dismiss
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Sandbox Inbox Digests */}
      <div className="panel">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
            Sandbox Digest Inbox ({digests.length})
          </h3>
          <span className="pill pill-indigo mono">aarav.sandbox@campusos.local</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {digests.map((msg) => (
            <div
              key={msg.id}
              style={{
                border: '1px solid var(--border-hairline)',
                borderRadius: 'var(--radius-md)',
                padding: 18,
                background: 'var(--bg-canvas)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>{msg.subject}</div>
                  <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>
                    To: <span className="mono">{msg.recipient}</span> · Run{' '}
                    <span className="mono">{msg.runId}</span>
                  </div>
                </div>
                <span className="mono" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {msg.sentAt}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {msg.highlights.map((h, i) => {
                  const safe = safeHttpUrl(h.url);
                  return (
                    <div
                      key={i}
                      style={{
                        background: 'var(--bg-surface)',
                        border: '1px solid var(--border-hairline)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '10px 14px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 10,
                      }}
                    >
                      <div>
                        <strong style={{ fontSize: 13.5 }}>{h.title}</strong>
                        <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
                          {h.company} · Deadline: {h.deadline ?? 'Unstated'}
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span className="pill pill-emerald">{h.fit}% Fit</span>
                        {safe && (
                          <a
                            href={safe}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: 'var(--brand-primary)', display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12.5, fontWeight: 600, textDecoration: 'none' }}
                          >
                            Link <ExternalLink size={12} />
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
