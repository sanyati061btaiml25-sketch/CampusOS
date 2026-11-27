import React, { useState } from 'react';
import { CheckCircle2, Plus, UserCheck, X } from 'lucide-react';
import { StudentProfile } from '../types';

interface Props {
  profile: StudentProfile;
  onSaveProfile: (updated: StudentProfile) => void;
}

export const ProfileView: React.FC<Props> = ({ profile, onSaveProfile }) => {
  const [draft, setDraft] = useState<StudentProfile>(profile);
  const [skillInput, setSkillInput] = useState('');
  const [locInput, setLocInput] = useState('');
  const [savedNotice, setSavedNotice] = useState(false);

  const addSkill = () => {
    const clean = skillInput.trim();
    if (clean && !draft.skills.includes(clean)) {
      setDraft({ ...draft, skills: [...draft.skills, clean] });
      setSkillInput('');
    }
  };

  const removeSkill = (skill: string) => {
    setDraft({ ...draft, skills: draft.skills.filter((s) => s !== skill) });
  };

  const addLocation = () => {
    const clean = locInput.trim();
    if (clean && !draft.preferredLocations.includes(clean)) {
      setDraft({ ...draft, preferredLocations: [...draft.preferredLocations, clean] });
      setLocInput('');
    }
  };

  const removeLocation = (loc: string) => {
    setDraft({
      ...draft,
      preferredLocations: draft.preferredLocations.filter((l) => l !== loc),
    });
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const sanitized: StudentProfile = {
      ...draft,
      name: draft.name.trim().slice(0, 80) || 'Student',
      discipline: draft.discipline.trim().slice(0, 100),
      cgpa: Math.min(10, Math.max(0, Number(draft.cgpa) || 0)),
      minStipendMonthlyInr: Math.max(0, Math.round(Number(draft.minStipendMonthlyInr) || 0)),
    };
    setDraft(sanitized);
    onSaveProfile(sanitized);
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 2500);
  };

  return (
    <form onSubmit={handleSave} className="panel" style={{ maxWidth: 880 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 18,
          paddingBottom: 14,
          borderBottom: '1px solid var(--border-hairline)',
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
            <UserCheck size={18} /> Student Eligibility Profile
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>
            Configure once. Saving updates deterministic eligibility rules and re-scores all discovered listings immediately.
          </p>
        </div>
        <button type="submit" className="btn btn-primary">
          Save & Re-Score Opportunities
        </button>
      </div>

      {savedNotice && (
        <div
          className="banner"
          style={{
            background: 'var(--status-emerald-bg)',
            border: '1px solid var(--status-emerald-border)',
            color: 'var(--status-emerald-fg)',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontWeight: 600 }}>
            <CheckCircle2 size={16} /> Profile saved — all opportunity match scores and eligibility tags updated.
          </span>
        </div>
      )}

      <div className="form-grid">
        <div className="field">
          <label>Student Name</label>
          <input
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </div>
        <div className="field">
          <label>Degree</label>
          <select
            value={draft.degree}
            onChange={(e) => setDraft({ ...draft, degree: e.target.value })}
          >
            <option value="B.Tech">B.Tech</option>
            <option value="B.E.">B.E.</option>
            <option value="M.Tech">M.Tech</option>
            <option value="B.Sc">B.Sc</option>
            <option value="MCA">MCA</option>
          </select>
        </div>
        <div className="field">
          <label>Discipline / Branch</label>
          <input
            value={draft.discipline}
            onChange={(e) => setDraft({ ...draft, discipline: e.target.value })}
          />
        </div>
        <div className="field">
          <label>Graduation Year</label>
          <select
            value={draft.graduationYear}
            onChange={(e) =>
              setDraft({ ...draft, graduationYear: Number(e.target.value) })
            }
          >
            <option value={2026}>2026</option>
            <option value={2027}>2027</option>
            <option value={2028}>2028</option>
            <option value={2029}>2029</option>
          </select>
        </div>
        <div className="field">
          <label>Current CGPA</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="10"
            value={draft.cgpa}
            onChange={(e) => setDraft({ ...draft, cgpa: Number(e.target.value) })}
          />
        </div>
        <div className="field">
          <label>Minimum Monthly Stipend (INR)</label>
          <input
            type="number"
            step="5000"
            value={draft.minStipendMonthlyInr}
            onChange={(e) =>
              setDraft({ ...draft, minStipendMonthlyInr: Number(e.target.value) })
            }
          />
        </div>
      </div>

      {/* Skills Editor */}
      <div style={{ marginTop: 18 }}>
        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Verified Skills (used for 40% Skill Match weight)
        </label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 10 }}>
          {draft.skills.map((skill) => (
            <span key={skill} className="skill-chip">
              {skill}
              <button type="button" onClick={() => removeSkill(skill)} aria-label={`Remove ${skill}`}>
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, maxWidth: 360 }}>
          <input
            value={skillInput}
            onChange={(e) => setSkillInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addSkill();
              }
            }}
            placeholder="Add skill (e.g. Kubernetes, PyTorch)"
            style={{
              flex: 1,
              height: 36,
              padding: '0 10px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-strong)',
            }}
          />
          <button type="button" className="btn btn-secondary" onClick={addSkill}>
            <Plus size={14} /> Add
          </button>
        </div>
      </div>

      {/* Preferred Locations */}
      <div style={{ marginTop: 18 }}>
        <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Preferred Locations (15% Location Match weight)
        </label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 10 }}>
          {draft.preferredLocations.map((loc) => (
            <span key={loc} className="skill-chip">
              {loc}
              <button type="button" onClick={() => removeLocation(loc)} aria-label={`Remove ${loc}`}>
                <X size={13} />
              </button>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, maxWidth: 360 }}>
          <input
            value={locInput}
            onChange={(e) => setLocInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addLocation();
              }
            }}
            placeholder="Add city or Remote"
            style={{
              flex: 1,
              height: 36,
              padding: '0 10px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-strong)',
            }}
          />
          <button type="button" className="btn btn-secondary" onClick={addLocation}>
            <Plus size={14} /> Add
          </button>
        </div>
      </div>

      {/* Consent toggle */}
      <div
        style={{
          marginTop: 20,
          paddingTop: 16,
          borderTop: '1px solid var(--border-hairline)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <input
          id="draftConsent"
          type="checkbox"
          checked={draft.draftConsent}
          onChange={(e) => setDraft({ ...draft, draftConsent: e.target.checked })}
          style={{ accentColor: 'var(--brand-primary)' }}
        />
        <label htmlFor="draftConsent" style={{ fontSize: 13, color: 'var(--text-secondary)', cursor: 'pointer' }}>
          Allow CampusOS to prepare editable application checklists and outreach drafts from this profile (never auto-submits).
        </label>
      </div>
    </form>
  );
};
