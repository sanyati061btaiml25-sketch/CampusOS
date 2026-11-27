import React, { useState } from 'react';
import {
  AlertOctagon,
  CheckCircle2,
  Play,
  Plus,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { SourceFeed, TrapPackResult } from '../types';
import { safeHttpUrl } from '../services/api';

interface Props {
  sources: SourceFeed[];
  trapResults: TrapPackResult[];
  isRunning: boolean;
  isKilled: boolean;
  onToggleSource: (id: string) => void;
  onTestSource: (id: string) => void;
  onToggleCircuitBreaker: (id: string) => void;
  onAddSource: (
    source: Omit<
      SourceFeed,
      'id' | 'lastChecked' | 'status' | 'itemsFound' | 'contentHash' | 'circuitBreaker'
    >
  ) => void;
  onRunTrapPack: () => void;
}

export const SourcesAndTrapsView: React.FC<Props> = ({
  sources,
  trapResults,
  isRunning,
  isKilled,
  onToggleSource,
  onTestSource,
  onToggleCircuitBreaker,
  onAddSource,
  onRunTrapPack,
}) => {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [type, setType] = useState<SourceFeed['type']>('Public RSS');
  const [intervalHours, setIntervalHours] = useState(6);
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const safeUrl = safeHttpUrl(url);
    if (!name.trim()) {
      setFormError('Please enter a source name.');
      return;
    }
    if (!safeUrl) {
      setFormError('Only valid http:// or https:// URLs are allowed.');
      return;
    }
    const clampedInterval = Math.min(168, Math.max(1, Math.round(intervalHours || 6)));
    setFormError(null);
    onAddSource({
      name: name.trim().slice(0, 80),
      url: safeUrl,
      type,
      intervalHours: clampedInterval,
      enabled: true,
      robotsAllowed: true,
    });
    setName('');
    setUrl('');
  };

  const passedCount = trapResults.filter((t) => t.passed).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Allowlisted Sources + Content Hashing + Circuit Breakers */}
      <div className="panel">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 14,
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>
              Allowlisted Sources, Content Hashes &amp; Circuit Breakers
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 13.5, color: 'var(--text-muted)' }}>
              Fetchers enforce robots.txt, bounded retries, snapshot hashing (skipping LLM when unchanged), and per-source circuit breakers.
            </p>
          </div>
          <span className="pill pill-emerald">
            <ShieldCheck size={13} /> Gateway Allowlist Enforced
          </span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Source &amp; URL</th>
                <th>Snapshot Hash</th>
                <th>Circuit Breaker</th>
                <th>Last Checked</th>
                <th>Health</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src) => (
                <tr key={src.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{src.name}</div>
                    <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>
                      {src.url}
                    </div>
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {src.contentHash}
                  </td>
                  <td>
                    <button
                      type="button"
                      className={`pill ${src.circuitBreaker === 'closed' ? 'pill-emerald' : 'pill-red'}`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => onToggleCircuitBreaker(src.id)}
                      title="Toggle circuit breaker state"
                    >
                      {src.circuitBreaker === 'closed' ? 'Closed (Active)' : 'Open (Backed Off)'}
                    </button>
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {src.lastChecked}
                  </td>
                  <td>
                    {src.status === 'healthy' ? (
                      <span className="pill pill-emerald">
                        <CheckCircle2 size={12} /> Healthy
                      </span>
                    ) : (
                      <span className="pill pill-red">
                        <AlertOctagon size={12} /> Isolated
                      </span>
                    )}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <button
                        className="btn btn-secondary"
                        style={{ height: 30, padding: '0 10px', fontSize: 12 }}
                        onClick={() => onTestSource(src.id)}
                        disabled={isRunning || isKilled}
                      >
                        <RefreshCw size={12} /> Poll
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{ height: 30, padding: '0 10px', fontSize: 12 }}
                        onClick={() => onToggleSource(src.id)}
                      >
                        {src.enabled ? 'Disable' : 'Enable'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Add Allowlisted Source */}
        <form
          onSubmit={handleSubmit}
          style={{
            marginTop: 18,
            paddingTop: 16,
            borderTop: '1px solid var(--border-hairline)',
            display: 'grid',
            gridTemplateColumns: '1.2fr 1.6fr 0.8fr 0.6fr auto',
            gap: 10,
            alignItems: 'end',
          }}
        >
          <div className="field">
            <label>Source Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Unstop Public Engineering RSS"
            />
          </div>
          <div className="field">
            <label>Public Feed / API URL</label>
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://..."
            />
          </div>
          <div className="field">
            <label>Connector</label>
            <select value={type} onChange={(e) => setType(e.target.value as SourceFeed['type'])}>
              <option value="Public RSS">Public RSS</option>
              <option value="Official API">Official API</option>
              <option value="University Feed">University Feed</option>
              <option value="Permitted Page">Permitted Page</option>
            </select>
          </div>
          <div className="field">
            <label>Interval (h)</label>
            <input
              type="number"
              min={1}
              max={168}
              value={intervalHours}
              onChange={(e) => setIntervalHours(Number(e.target.value))}
            />
          </div>
          <button type="submit" className="btn btn-primary" style={{ height: 40 }}>
            <Plus size={14} /> Add Source
          </button>
        </form>
        {formError && (
          <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--status-red-fg)' }}>
            {formError}
          </div>
        )}
      </div>

      {/* Trap Pack Runner Results (Isolated from student dashboard) */}
      <div className="panel">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 14,
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>
              Trap Pack Runner Results (<code>trap_pack/</code>)
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 13.5, color: 'var(--text-muted)' }}>
              Adversarial &amp; malformed-input verification suite ({passedCount}/{trapResults.length} passed). Kept strictly isolated from the student Opportunities feed.
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={onRunTrapPack}
            disabled={isRunning || isKilled}
          >
            <Play size={14} /> Run Trap Pack Suite
          </button>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Test Case</th>
                <th>Category</th>
                <th>Expected Guardrail</th>
                <th>Observed Result</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {trapResults.map((tr) => (
                <tr key={tr.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{tr.name}</div>
                    <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>
                      {tr.inputSummary}
                    </div>
                  </td>
                  <td>
                    <span className="pill pill-slate">{tr.category}</span>
                  </td>
                  <td style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
                    {tr.expectedOutcome}
                  </td>
                  <td style={{ fontSize: 12.5 }}>{tr.actualOutcome}</td>
                  <td>
                    <span className={`pill ${tr.passed ? 'pill-emerald' : 'pill-red'}`}>
                      {tr.passed ? 'PASS' : 'FAIL'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
