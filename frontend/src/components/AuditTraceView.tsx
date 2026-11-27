import React, { useState } from 'react';
import {
  Activity,
  Download,
  Lock,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { AgentStage, AuditEvent, RunMode, RunTelemetry } from '../types';

interface Props {
  telemetry: RunTelemetry;
  events: AuditEvent[];
  onChangeRunMode: (mode: RunMode) => void;
  onExportTrace: () => void;
}

const STAGES: Array<{ key: AgentStage; label: string }> = [
  { key: 'trigger', label: '0. Trigger' },
  { key: 'plan', label: '1. Plan' },
  { key: 'fetch', label: '2. Fetch' },
  { key: 'extract', label: '3. Extract' },
  { key: 'verify', label: '4. Verify' },
  { key: 'dedupe', label: '5. Dedupe' },
  { key: 'match', label: '6. Match' },
  { key: 'rank', label: '7. Rank' },
  { key: 'decide', label: '8. Decide' },
  { key: 'act', label: '9. Act' },
  { key: 'report', label: '10. Report' },
];

export const AuditTraceView: React.FC<Props> = ({
  telemetry,
  events,
  onChangeRunMode,
  onExportTrace,
}) => {
  const [kindFilter, setKindFilter] = useState<string>('all');

  const filtered =
    kindFilter === 'all' ? events : events.filter((e) => e.kind === kindFilter);

  const currentIdx = telemetry.currentStage
    ? STAGES.findIndex((s) => s.key === telemetry.currentStage)
    : -1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Tool Gateway & 11-Stage State Machine */}
      <div className="panel">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 16,
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Activity size={18} /> Tool Gateway &amp; 11-Stage Run Loop
            </h2>
            <p style={{ margin: '4px 0 0', fontSize: 13.5, color: 'var(--text-muted)' }}>
              Every tool call passes through one Tool Gateway: kill-switch check → allowlist → per-run budgets → execute → audit log.
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <div style={{ display: 'inline-flex', border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
              {(['mock', 'replay', 'live'] as RunMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => onChangeRunMode(mode)}
                  style={{
                    border: 'none',
                    padding: '6px 12px',
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: 'pointer',
                    textTransform: 'capitalize',
                    background: telemetry.runMode === mode ? 'var(--brand-primary)' : '#ffffff',
                    color: telemetry.runMode === mode ? '#ffffff' : 'var(--text-secondary)',
                  }}
                >
                  {mode}
                </button>
              ))}
            </div>

            <button className="btn-primary" onClick={onExportTrace}>
              <Download size={14} /> Export traces/{telemetry.runId}.jsonl
            </button>
          </div>
        </div>

        {/* Gateway Choke-Point Telemetry Grid */}
        <div className="facts-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', marginBottom: 16 }}>
          <div className="fact-box">
            <div className="fact-label">Kill Switch (DB + File Flag)</div>
            <div className="fact-val" style={{ color: telemetry.killSwitchDbFlag ? '#b91c1c' : '#047857' }}>
              {telemetry.killSwitchDbFlag || telemetry.killSwitchFileFlag ? 'ENGAGED (HALTED)' : 'CLEAR (ARMED)'}
            </div>
          </div>
          <div className="fact-box">
            <div className="fact-label">Requests Budget</div>
            <div className="fact-val mono">
              {telemetry.requestsUsed} / {telemetry.requestsLimit}
            </div>
          </div>
          <div className="fact-box">
            <div className="fact-label">Token Budget</div>
            <div className="fact-val mono">
              {telemetry.tokensUsed.toLocaleString()} / {telemetry.tokensLimit.toLocaleString()}
            </div>
          </div>
          <div className="fact-box">
            <div className="fact-label">Spend &amp; Time Cap</div>
            <div className="fact-val mono">
              ${telemetry.estimatedCostUsd.toFixed(3)} / ${telemetry.costLimitUsd.toFixed(2)} · {telemetry.elapsedSeconds}s/{telemetry.timeLimitSeconds}s
            </div>
          </div>
          <div className="fact-box">
            <div className="fact-label">Daemon Heartbeat</div>
            <div className="fact-val mono">{telemetry.heartbeatAt}</div>
          </div>
        </div>

        {/* 11-Stage Stepper */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
            gap: 7,
          }}
        >
          {STAGES.map((stage, idx) => {
            const isActive = telemetry.state === 'running' && idx === currentIdx;
            const isDone =
              telemetry.state === 'completed' ||
              (currentIdx > idx && telemetry.state !== 'idle');
            return (
              <div
                key={stage.key}
                style={{
                  padding: '9px 10px',
                  borderRadius: 'var(--radius-sm)',
                  border: isActive
                    ? '1.5px solid var(--brand-primary)'
                    : isDone
                    ? '1px solid var(--status-emerald-border)'
                    : '1px solid var(--border-hairline)',
                  background: isActive
                    ? 'var(--brand-soft-bg)'
                    : isDone
                    ? 'var(--status-emerald-bg)'
                    : 'var(--bg-canvas)',
                  fontSize: 12,
                  fontWeight: isActive || isDone ? 600 : 500,
                  color: isActive
                    ? 'var(--brand-primary)'
                    : isDone
                    ? 'var(--status-emerald-fg)'
                    : 'var(--text-secondary)',
                }}
              >
                {stage.label}
              </div>
            );
          })}
        </div>
      </div>

      {/* Audit Log Stream */}
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
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 7 }}>
            <Terminal size={15} /> SQLite Event Log ({filtered.length} events)
          </h3>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {[
              ['all', 'All'],
              ['gateway_call', 'Gateway Calls'],
              ['decision', 'Decisions'],
              ['warning', 'Warnings'],
              ['kill_switch', 'Kill Switch'],
            ].map(([val, label]) => (
              <button
                key={val}
                className={kindFilter === val ? 'btn btn-primary' : 'btn btn-secondary'}
                style={{ height: 30, padding: '0 11px', fontSize: 12 }}
                onClick={() => setKindFilter(val)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Stage</th>
                <th>Type</th>
                <th>Gateway / Decision Detail</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((evt) => (
                <tr key={evt.id}>
                  <td className="mono" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                    {evt.timestamp}
                  </td>
                  <td>
                    <span className="pill pill-slate mono">{evt.stage}</span>
                  </td>
                  <td>
                    {evt.kind === 'kill_switch' && (
                      <span className="pill pill-red">
                        <Lock size={11} /> Kill Switch
                      </span>
                    )}
                    {evt.kind === 'error' && <span className="pill pill-red">Error</span>}
                    {evt.kind === 'warning' && <span className="pill pill-amber">Warning</span>}
                    {evt.kind === 'gateway_call' && (
                      <span className="pill pill-indigo">
                        <ShieldCheck size={11} /> Gateway
                      </span>
                    )}
                    {evt.kind === 'decision' && <span className="pill pill-emerald">Decision</span>}
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{evt.summary}</div>
                    <div style={{ fontSize: 12.5, color: 'var(--text-secondary)', marginTop: 2 }}>
                      {evt.detail}
                    </div>
                    {evt.toolName && (
                      <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 3 }}>
                        tool: {evt.toolName}
                        {evt.sourceName ? ` · source: ${evt.sourceName}` : ''}
                      </div>
                    )}
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
