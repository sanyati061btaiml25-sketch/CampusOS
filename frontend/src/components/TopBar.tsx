import React from 'react';
import { Play, Square, Upload } from 'lucide-react';
import { AgentRunState } from '../types';

export type NavTab = 'opps' | 'inbox' | 'sources' | 'audit' | 'profile';

interface TopBarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  oppsCount: number;
  reviewCount: number;
  auditCount: number;
  telemetryState: AgentRunState;
  onStartRun: () => void;
  onKillSwitch: () => void;
  onOpenImport: () => void;
}

const STATE_LABEL: Record<AgentRunState, string> = {
  idle: 'Ready',
  running: 'Running',
  completed: 'Updated',
  killed: 'Stopped',
  error: 'Error',
};

export const TopBar: React.FC<TopBarProps> = ({
  activeTab,
  onSelectTab,
  oppsCount,
  reviewCount,
  auditCount,
  telemetryState,
  onStartRun,
  onKillSwitch,
  onOpenImport,
}) => {
  return (
    <header className="site-header">
      <div className="site-header-inner">
        {/* Left: Brand Lockup */}
        <a
          href="#top"
          className="brand-lockup"
          onClick={(e) => {
            e.preventDefault();
            onSelectTab('opps');
          }}
        >
          <span className="brand-emblem" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L20.5 7V17L12 22L3.5 17V7L12 2Z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinejoin="round"
              />
              <circle cx="12" cy="12" r="3" fill="currentColor" />
            </svg>
          </span>
          <span className="brand-name">CampusOS</span>
        </a>

        {/* Center: Primary Navigation */}
        <nav className="header-nav" aria-label="Primary sections">
          <button
            type="button"
            className={`nav-link ${activeTab === 'opps' ? 'active' : ''}`}
            onClick={() => onSelectTab('opps')}
          >
            Opportunities
            <span className="nav-count">{oppsCount}</span>
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === 'inbox' ? 'active' : ''}`}
            onClick={() => onSelectTab('inbox')}
          >
            Sandbox Inbox
            {reviewCount > 0 && <span className="nav-badge">{reviewCount}</span>}
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === 'sources' ? 'active' : ''}`}
            onClick={() => onSelectTab('sources')}
          >
            Sources &amp; Traps
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => onSelectTab('audit')}
          >
            Audit &amp; Trace
            <span className="nav-count">{auditCount}</span>
          </button>
          <button
            type="button"
            className={`nav-link ${activeTab === 'profile' ? 'active' : ''}`}
            onClick={() => onSelectTab('profile')}
          >
            Profile
          </button>
        </nav>

        {/* Right: Status & Actions */}
        <div className="header-actions">
          <div className={`status-pill ${telemetryState}`}>
            <span className="status-pill-dot" />
            <span>{STATE_LABEL[telemetryState]}</span>
          </div>
          {telemetryState === 'running' ? (
            <button type="button" className="btn btn-danger" onClick={onKillSwitch}>
              <Square size={13} />
              Stop
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={onStartRun}>
              <Play size={13} />
              Run Agent
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={onOpenImport}>
            <Upload size={13} />
            Import
          </button>
        </div>
      </div>
    </header>
  );
};

export default TopBar;
