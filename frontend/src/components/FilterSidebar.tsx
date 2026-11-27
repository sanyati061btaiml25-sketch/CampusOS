import React, { useState } from 'react';
import { ChevronDown, ChevronRight, RotateCcw, Search, SlidersHorizontal } from 'lucide-react';
import {
  EligibilityStatus,
  Opportunity,
  OpportunityFilters,
  OpportunityType,
  RoleTrack,
  WorkMode,
} from '../types';

interface Props {
  allOpportunities: Opportunity[];
  filters: OpportunityFilters;
  onChange: (next: OpportunityFilters) => void;
  onReset: () => void;
}

function toggleArrayItem<T>(arr: T[], item: T): T[] {
  return arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item];
}

export const FilterSidebar: React.FC<Props> = ({
  allOpportunities,
  filters,
  onChange,
  onReset,
}) => {
  const [skillSearch, setSkillSearch] = useState('');
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    score: true,
    deadline: true,
    type: true,
    status: true,
    mode: true,
    city: true,
    track: false,
    stipend: true,
    skills: true,
    sources: false,
  });

  const toggleSec = (key: string) =>
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));

  const activeList = allOpportunities.filter((o) => !o.dismissed);
  const countWhere = (pred: (o: Opportunity) => boolean) =>
    activeList.filter(pred).length;

  const cities = Array.from(new Set(activeList.map((o) => o.cityTag))).sort();
  const sources = Array.from(new Set(activeList.map((o) => o.evidence.sourceName))).sort();
  const allSkills = Array.from(new Set(activeList.flatMap((o) => o.requiredSkills))).sort();
  const visibleSkills = skillSearch.trim()
    ? allSkills.filter((s) => s.toLowerCase().includes(skillSearch.trim().toLowerCase()))
    : allSkills.slice(0, 10);

  return (
    <aside className="filter-rail" aria-label="Opportunity Filters">
      <div className="filter-rail-head">
        <strong style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 14.5 }}>
          <SlidersHorizontal size={15} /> Filters
        </strong>
        <button
          type="button"
          className="btn btn-ghost"
          style={{ height: 28, padding: '0 8px', fontSize: 12.5, color: 'var(--brand-primary)' }}
          onClick={() => {
            setSkillSearch('');
            onReset();
          }}
        >
          <RotateCcw size={12} /> Clear all
        </button>
      </div>

      {/* 1. Minimum Fit Score Segmented Selector */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('score')}>
          <span>Minimum Match Fit</span>
          {openSections.score ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.score && (
          <div className="filter-section-body">
            <div className="segmented-row">
              {[0, 60, 75, 85].map((val) => (
                <button
                  key={val}
                  type="button"
                  className={`seg-btn ${filters.minScore === val ? 'active' : ''}`}
                  onClick={() => onChange({ ...filters, minScore: val })}
                >
                  {val === 0 ? 'All' : `${val}%+`}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 2. Deadline Window */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('deadline')}>
          <span>Deadline Window</span>
          {openSections.deadline ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.deadline && (
          <div className="filter-section-body">
            {(
              [
                [null, 'Anytime'],
                [3, 'Urgent (Next 3 days)'],
                [7, 'Closing this week (≤ 7d)'],
                [14, 'Next 14 days'],
              ] as Array<[number | null, string]>
            ).map(([days, label]) => (
              <label key={String(days)} className="filter-check">
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="radio"
                    name="deadlineWindow"
                    checked={filters.deadlineWithinDays === days}
                    onChange={() => onChange({ ...filters, deadlineWithinDays: days })}
                  />
                  {label}
                </span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* 3. Opportunity Type */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('type')}>
          <span>Opportunity Type</span>
          {openSections.type ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.type && (
          <div className="filter-section-body">
            {(['Internship', 'Full-Time', 'Research'] as OpportunityType[]).map((t) => (
              <label key={t} className="filter-check">
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={filters.types.includes(t)}
                    onChange={() =>
                      onChange({ ...filters, types: toggleArrayItem(filters.types, t) })
                    }
                  />
                  {t}
                </span>
                <span className="filter-count">{countWhere((o) => o.opportunityType === t)}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* 4. Eligibility & Review */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('status')}>
          <span>Eligibility &amp; Status</span>
          {openSections.status ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.status && (
          <div className="filter-section-body">
            {(
              [
                ['eligible', 'Eligible Now'],
                ['needs_review', 'In Review Queue'],
                ['expired', 'Expired Archive'],
              ] as Array<[EligibilityStatus, string]>
            ).map(([val, label]) => (
              <label key={val} className="filter-check">
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={filters.statuses.includes(val)}
                    onChange={() =>
                      onChange({ ...filters, statuses: toggleArrayItem(filters.statuses, val) })
                    }
                  />
                  {label}
                </span>
                <span className="filter-count">
                  {countWhere((o) => o.eligibilityStatus === val)}
                </span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* 5. Work Mode */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('mode')}>
          <span>Work Mode</span>
          {openSections.mode ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.mode && (
          <div className="filter-section-body">
            {(['Remote', 'Hybrid', 'On-site'] as WorkMode[]).map((m) => (
              <label key={m} className="filter-check">
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={filters.workModes.includes(m)}
                    onChange={() =>
                      onChange({
                        ...filters,
                        workModes: toggleArrayItem(filters.workModes, m),
                      })
                    }
                  />
                  {m}
                </span>
                <span className="filter-count">{countWhere((o) => o.workMode === m)}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* 6. Location */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('city')}>
          <span>Location</span>
          {openSections.city ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.city && (
          <div className="filter-section-body">
            {cities.map((city) => (
              <label key={city} className="filter-check">
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={filters.cities.includes(city)}
                    onChange={() =>
                      onChange({ ...filters, cities: toggleArrayItem(filters.cities, city) })
                    }
                  />
                  {city}
                </span>
                <span className="filter-count">{countWhere((o) => o.cityTag === city)}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* 7. Minimum Compensation */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('stipend')}>
          <span>Compensation Floor</span>
          {openSections.stipend ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.stipend && (
          <div className="filter-section-body">
            <select
              value={filters.minStipendInr}
              onChange={(e) => onChange({ ...filters, minStipendInr: Number(e.target.value) })}
              style={{
                height: 36,
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--border-strong)',
                padding: '0 10px',
                fontSize: 13,
                background: 'var(--bg-surface)',
                color: 'var(--text-primary)',
              }}
            >
              <option value={0}>Any Stipend / CTC</option>
              <option value={30000}>₹30,000+ / month</option>
              <option value={45000}>₹45,000+ / month</option>
              <option value={60000}>₹60,000+ / month</option>
            </select>
          </div>
        )}
      </div>

      {/* 8. Skills Search & Multi-select */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('skills')}>
          <span>Skills &amp; Stack</span>
          {openSections.skills ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.skills && (
          <div className="filter-section-body">
            <div style={{ position: 'relative', marginBottom: 4 }}>
              <Search
                size={13}
                color="#64748b"
                style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)' }}
              />
              <input
                value={skillSearch}
                onChange={(e) => setSkillSearch(e.target.value)}
                placeholder="Filter skills..."
                style={{
                  width: '100%',
                  height: 32,
                  padding: '0 8px 0 28px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-strong)',
                  fontSize: 12.5,
                }}
              />
            </div>
            <div className="skill-filter-wrap">
              {visibleSkills.map((skill) => {
                const active = filters.skills.includes(skill);
                return (
                  <button
                    key={skill}
                    type="button"
                    className={`skill-filter-chip ${active ? 'active' : ''}`}
                    onClick={() =>
                      onChange({ ...filters, skills: toggleArrayItem(filters.skills, skill) })
                    }
                  >
                    {skill}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* 9. Role Track */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('track')}>
          <span>Role Domain</span>
          {openSections.track ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.track && (
          <div className="filter-section-body">
            {(
              [
                'Software & Backend',
                'AI / ML & Data',
                'Frontend & Product',
                'Cloud & DevOps',
              ] as RoleTrack[]
            ).map((tr) => (
              <label key={tr} className="filter-check">
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={filters.tracks.includes(tr)}
                    onChange={() =>
                      onChange({ ...filters, tracks: toggleArrayItem(filters.tracks, tr) })
                    }
                  />
                  {tr}
                </span>
                <span className="filter-count">{countWhere((o) => o.track === tr)}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* 10. Source Feeds */}
      <div className="filter-section">
        <button type="button" className="filter-section-trigger" onClick={() => toggleSec('sources')}>
          <span>Source Feeds</span>
          {openSections.sources ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
        {openSections.sources && (
          <div className="filter-section-body">
            {sources.map((src) => (
              <label key={src} className="filter-check">
                <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}>
                  <input
                    type="checkbox"
                    checked={filters.sources.includes(src)}
                    onChange={() =>
                      onChange({ ...filters, sources: toggleArrayItem(filters.sources, src) })
                    }
                  />
                  {src}
                </span>
              </label>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
};
