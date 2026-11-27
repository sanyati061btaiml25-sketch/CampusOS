import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Bookmark,
  CalendarPlus,
  CheckCircle2,
  Copy,
  ExternalLink,
  EyeOff,
  FileCheck2,
  Plus,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import { Opportunity } from '../types';
import { safeHttpUrl } from '../services/api';
import { CompanyMark } from './CompanyMark';
import { downloadIcsFile } from '../utils/ics';

interface Props {
  opportunity: Opportunity | null;
  onCloseMobile?: () => void;
  onToggleChecklist: (oppId: string, itemId: string) => void;
  onAddChecklistItem: (oppId: string, label: string) => void;
  onUpdateDraft: (oppId: string, draft: string) => void;
  onToggleBookmark: (oppId: string) => void;
  onToggleApplied: (oppId: string) => void;
  onDismiss: (oppId: string) => void;
}

type DetailTab = 'overview' | 'score' | 'prep';

export const OpportunityDetailPane: React.FC<Props> = ({
  opportunity,
  onCloseMobile,
  onToggleChecklist,
  onAddChecklistItem,
  onUpdateDraft,
  onToggleBookmark,
  onToggleApplied,
  onDismiss,
}) => {
  const [subTab, setSubTab] = useState<DetailTab>('overview');
  const [newTask, setNewTask] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setSubTab('overview');
    setNewTask('');
  }, [opportunity?.id]);

  if (!opportunity) return null;

  const { score, evidence } = opportunity;
  const safeUrl = safeHttpUrl(evidence.sourceUrl);

  const handleCopyDraft = () => {
    navigator.clipboard?.writeText(opportunity.draftNote);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = newTask.trim().slice(0, 120);
    if (!clean) return;
    onAddChecklistItem(opportunity.id, clean);
    setNewTask('');
  };

  return (
    <div className="detail-pane">
      {/* Header */}
      <div className="detail-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <CompanyMark company={opportunity.company} size={48} />
            <div>
              <h2 style={{ margin: 0, fontSize: 19, fontWeight: 700, lineHeight: 1.3 }}>
                {opportunity.title}
              </h2>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 3 }}>
                <strong>{opportunity.company}</strong> · {opportunity.location} ({opportunity.workMode})
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                <span className="pill pill-slate">{opportunity.opportunityType}</span>
                <span className="pill pill-slate">{opportunity.track}</span>
                {opportunity.verificationStatus === 'verified' ? (
                  <span className="pill pill-emerald">
                    <ShieldCheck size={12} /> Verified ({Math.round(opportunity.sourceConfidence * 100)}%)
                  </span>
                ) : (
                  <span className="pill pill-amber">
                    <AlertTriangle size={12} /> In Review Queue
                  </span>
                )}
              </div>
            </div>
          </div>
          {onCloseMobile && (
            <button className="btn btn-ghost" onClick={onCloseMobile} aria-label="Close details">
              <X size={18} />
            </button>
          )}
        </div>

        {/* Action Row */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
          {safeUrl ? (
            <a
              className="btn-primary"
              href={safeUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ textDecoration: 'none' }}
            >
              Apply on Official Source <ExternalLink size={14} />
            </a>
          ) : (
            <span className="pill pill-red">
              <ShieldAlert size={12} /> Unsafe Source URL Blocked
            </span>
          )}
          {opportunity.deadline && (
            <button
              className="btn btn-secondary"
              onClick={() =>
                downloadIcsFile([opportunity], `${opportunity.canonicalKey}-deadline.ics`)
              }
              title="Download calendar reminder (.ics) with 2-day alert"
            >
              <CalendarPlus size={14} /> Calendar (.ics)
            </button>
          )}
          <button
            className="btn btn-secondary"
            onClick={() => onToggleBookmark(opportunity.id)}
          >
            <Bookmark size={14} fill={opportunity.bookmarked ? 'currentColor' : 'none'} />
            {opportunity.bookmarked ? 'Saved' : 'Save'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => onToggleApplied(opportunity.id)}
          >
            <CheckCircle2 size={14} />
            {opportunity.applied ? 'Applied' : 'Mark Applied'}
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => onDismiss(opportunity.id)}
            title="Hide this listing from feed"
          >
            <EyeOff size={14} /> Hide
          </button>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="detail-tabs">
        <button
          className={`detail-tab ${subTab === 'overview' ? 'active' : ''}`}
          onClick={() => setSubTab('overview')}
        >
          Overview &amp; Evidence
        </button>
        <button
          className={`detail-tab ${subTab === 'score' ? 'active' : ''}`}
          onClick={() => setSubTab('score')}
        >
          Match Math ({score.total}%)
        </button>
        <button
          className={`detail-tab ${subTab === 'prep' ? 'active' : ''}`}
          onClick={() => setSubTab('prep')}
        >
          Checklist &amp; Draft
        </button>
      </div>

      {/* Tab Body */}
      <div className="detail-body">
        {subTab === 'overview' && (
          <>
            <div className="facts-grid">
              <div className="fact-box">
                <div className="fact-label">Compensation</div>
                <div className="fact-val">{opportunity.compensation ?? 'Not disclosed'}</div>
              </div>
              <div className="fact-box">
                <div className="fact-label">Deadline</div>
                <div className="fact-val mono">
                  {opportunity.deadline ?? 'Unstated (verify)'}
                </div>
              </div>
              <div className="fact-box">
                <div className="fact-label">Batch &amp; Min CGPA</div>
                <div className="fact-val">
                  {opportunity.minGraduationYear ?? 'Unstated'} ·{' '}
                  {opportunity.minCgpa !== null ? `${opportunity.minCgpa}+ CGPA` : 'CGPA unstated'}
                </div>
              </div>
              <div className="fact-box">
                <div className="fact-label">Duration</div>
                <div className="fact-val">{opportunity.durationLabel}</div>
              </div>
            </div>

            <div className="section-card">
              <h4>Role Scope &amp; Key Responsibilities</h4>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, color: 'var(--text-secondary)' }}>
                {opportunity.responsibilities.map((r, i) => (
                  <li key={i} style={{ marginBottom: 5 }}>
                    {r}
                  </li>
                ))}
              </ul>
            </div>

            <div className="section-card">
              <h4>
                <ShieldCheck size={15} /> Verbatim Source Evidence
              </h4>
              <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginBottom: 8 }}>
                <strong>Source:</strong> {evidence.sourceName} · <strong>Checked:</strong>{' '}
                <span className="mono">{evidence.checkedAt}</span>
              </div>
              <div className="quote-box">{evidence.snippet}</div>
              {evidence.mergedFrom && evidence.mergedFrom.length > 1 && (
                <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--text-secondary)' }}>
                  <strong>Deduplicated across:</strong> {evidence.mergedFrom.join(' + ')}
                </div>
              )}
              {evidence.changeNote && (
                <div style={{ marginTop: 6, fontSize: 12.5, color: 'var(--brand-primary)' }}>
                  <strong>Audit Note:</strong> {evidence.changeNote}
                </div>
              )}
            </div>
          </>
        )}

        {subTab === 'score' && (
          <div className="section-card">
            <h4>Deterministic Fit Breakdown — {score.total}%</h4>
            <p style={{ margin: '0 0 12px', fontSize: 12.5, color: 'var(--text-muted)' }}>
              Transparent rule weights (never an opaque probability). Unknown fields are never assumed eligible.
            </p>
            <div className="breakdown-row">
              <span>Skills &amp; Stack (40)</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(score.skillScore / 40) * 100}%` }} />
              </div>
              <strong className="mono">{score.skillScore}/40</strong>
            </div>
            <div className="breakdown-row">
              <span>Batch &amp; CGPA (20)</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${(score.degreeYearScore / 20) * 100}%` }}
                />
              </div>
              <strong className="mono">{score.degreeYearScore}/20</strong>
            </div>
            <div className="breakdown-row">
              <span>Location (15)</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${(score.locationScore / 15) * 100}%` }}
                />
              </div>
              <strong className="mono">{score.locationScore}/15</strong>
            </div>
            <div className="breakdown-row">
              <span>Urgency (15)</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${(score.urgencyScore / 15) * 100}%` }}
                />
              </div>
              <strong className="mono">{score.urgencyScore}/15</strong>
            </div>
            <div className="breakdown-row" style={{ marginBottom: 0 }}>
              <span>Verification (10)</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${(score.confidenceScore / 10) * 100}%` }}
                />
              </div>
              <strong className="mono">{score.confidenceScore}/10</strong>
            </div>

            {score.matchedSkills.length > 0 && (
              <div style={{ marginTop: 14, fontSize: 13 }}>
                <strong style={{ color: 'var(--status-emerald-fg)' }}>Matched Skills:</strong>{' '}
                {score.matchedSkills.join(', ')}
              </div>
            )}
            {score.missingSkills.length > 0 && (
              <div style={{ marginTop: 6, fontSize: 13 }}>
                <strong style={{ color: 'var(--status-amber-fg)' }}>Skill Gaps to Prep:</strong>{' '}
                {score.missingSkills.join(', ')}
              </div>
            )}
          </div>
        )}

        {subTab === 'prep' && (
          <>
            <div className="section-card">
              <h4>
                <FileCheck2 size={15} /> Application Checklist
              </h4>
              {opportunity.checklist.length === 0 ? (
                <p style={{ margin: '0 0 10px', fontSize: 13, color: 'var(--text-muted)' }}>
                  No automated tasks yet. Add your own preparation steps below.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
                  {opportunity.checklist.map((item) => (
                    <label
                      key={item.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 9,
                        fontSize: 13.5,
                        cursor: 'pointer',
                        textDecoration: item.done ? 'line-through' : 'none',
                        color: item.done ? 'var(--text-muted)' : 'var(--text-primary)',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={item.done}
                        onChange={() => onToggleChecklist(opportunity.id, item.id)}
                        style={{ accentColor: 'var(--brand-primary)' }}
                      />
                      {item.label}
                    </label>
                  ))}
                </div>
              )}

              <form onSubmit={handleAddTask} style={{ display: 'flex', gap: 8 }}>
                <input
                  value={newTask}
                  onChange={(e) => setNewTask(e.target.value)}
                  placeholder="Add custom preparation step..."
                  style={{
                    flex: 1,
                    height: 34,
                    padding: '0 10px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-strong)',
                    fontSize: 13,
                  }}
                />
                <button type="submit" className="btn btn-secondary" style={{ height: 34 }}>
                  <Plus size={14} /> Add
                </button>
              </form>
            </div>

            <div className="section-card">
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 8,
                }}
              >
                <h4 style={{ margin: 0 }}>Editable Outreach Draft</h4>
                <button className="btn btn-secondary" style={{ height: 30 }} onClick={handleCopyDraft}>
                  <Copy size={13} />
                  {copied ? 'Copied' : 'Copy Draft'}
                </button>
              </div>
              <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--text-muted)' }}>
                Human-in-the-loop safety: CampusOS never auto-submits or contacts recruiters.
              </p>
              <textarea
                rows={4}
                value={opportunity.draftNote}
                onChange={(e) => onUpdateDraft(opportunity.id, e.target.value)}
                style={{
                  width: '100%',
                  padding: 10,
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-strong)',
                  fontSize: 13.5,
                  lineHeight: 1.5,
                  resize: 'vertical',
                }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
};
