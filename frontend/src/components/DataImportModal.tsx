import React, { useState } from 'react';
import { CheckCircle2, Code2, Upload, X } from 'lucide-react';

interface Props {
  open: boolean;
  onClose: () => void;
  onImportJson: (jsonText: string) => {
    importedCount: number;
    mergedCount: number;
    quarantinedCount: number;
    rejectedCount: number;
  };
}

const SAMPLE_PAYLOAD = `[
  {
    "title": "AI Platform Engineering Intern",
    "company": "Groww",
    "companyTagline": "WealthTech · Bengaluru",
    "opportunityType": "Internship",
    "location": "Bengaluru, Karnataka",
    "cityTag": "Bengaluru",
    "workMode": "Hybrid",
    "track": "Software & Backend",
    "monthlyStipendInr": 50000,
    "deadline": "2026-12-09",
    "minGraduationYear": 2027,
    "minCgpa": 7.5,
    "requiredSkills": ["Python", "FastAPI", "SQL", "Docker"],
    "sourceName": "Member 1 FastAPI Scraper",
    "sourceUrl": "https://groww.in/careers/ai-platform-intern-2027",
    "snippet": "Open to 2027 B.Tech CSE (7.5+ CGPA). Python, FastAPI, SQL, Docker. ₹50,000/mo."
  }
]`;

export const DataImportModal: React.FC<Props> = ({ open, onClose, onImportJson }) => {
  const [jsonText, setJsonText] = useState(SAMPLE_PAYLOAD);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);

  if (!open) return null;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith('.json') && file.type !== 'application/json') {
      setError('Only .json files are permitted here.');
      return;
    }
    if (file.size > 1_000_000) {
      setError('File too large (max 1 MB).');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setJsonText(String(reader.result ?? ''));
      setError(null);
    };
    reader.readAsText(file);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const stats = onImportJson(jsonText);
      setError(null);
      setResult(
        `Imported ${stats.importedCount} new listing(s) · ${stats.mergedCount} duplicate(s) merged · ${stats.quarantinedCount} trap(s) blocked.`
      );
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : 'Failed to parse JSON');
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Code2 size={18} /> Import Backend JSON Data (Member 1 Handshake)
            </h3>
            <p style={{ margin: '4px 0 0', fontSize: 13.5, color: 'var(--text-muted)' }}>
              Upload a <code>.json</code> export or paste scraped output from Member 1. CampusOS automatically validates URLs, blocks prompt injections, deduplicates, and scores against your profile.
            </p>
          </div>
          <button className="btn-primary" onClick={onClose} aria-label="Close modal">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
            <label className="btn btn-secondary" style={{ cursor: 'pointer' }}>
              <Upload size={14} /> Upload .json file
              <input
                type="file"
                accept=".json,application/json"
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
            </label>
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                setJsonText(SAMPLE_PAYLOAD);
                setError(null);
                setResult(null);
              }}
            >
              Load Sample Schema
            </button>
          </div>

          <textarea
            className="mono"
            rows={11}
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            style={{
              width: '100%',
              padding: 12,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-strong)',
              fontSize: 12.5,
              lineHeight: 1.5,
              background: 'var(--bg-subtle)',
              color: 'var(--text-primary)',
            }}
          />

          {error && (
            <div className="banner banner-killed" style={{ marginBottom: 0 }}>
              {error}
            </div>
          )}

          {result && (
            <div
              className="banner"
              style={{
                marginBottom: 0,
                background: 'var(--status-emerald-bg)',
                border: '1px solid var(--status-emerald-border)',
                color: 'var(--status-emerald-fg)',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 600 }}>
                <CheckCircle2 size={16} /> {result}
              </span>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Close
            </button>
            <button type="submit" className="btn btn-primary">
              Validate, Deduplicate &amp; Import
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
