import React, { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import {
  AgentStage,
  AuditEvent,
  Opportunity,
  OpportunityFilters,
  RunMode,
  RunTelemetry,
  SandboxDigestMessage,
  SourceFeed,
  StudentProfile,
  TrapPackResult,
} from './types';
import {
  buildInitialOpportunities,
  DEFAULT_PROFILE,
  INITIAL_AUDIT_EVENTS,
  INITIAL_DIGESTS,
  INITIAL_SOURCES,
  INITIAL_TRAP_PACK_RESULTS,
} from './data/mockData';
import { evaluateOpportunityMatch } from './engine/matcher';
import { importTeammateOpportunitiesJson } from './services/importer';
import {
  applyOpportunityFilters,
  createEmptyFilters,
  DEFAULT_RUN_MODE,
  getApiEvents,
  getApiOpportunities,
  getApiProfiles,
  getApiSources,
  getApiStatus,
  getApiTrapPack,
  IS_FASTAPI_MODE,
  mapApiOpportunityToUi,
  nowIstString,
  postImportJson,
  postKillSwitch,
  postReviewResolution,
  postRunRequest,
  putProfile,
  runMockAutonomousPipeline,
  ApiClientError,
} from './services/api';
import { AuditTraceView } from './components/AuditTraceView';
import { CompanyMark } from './components/CompanyMark';
import { DataImportModal } from './components/DataImportModal';
import { FilterSidebar } from './components/FilterSidebar';
import { OpportunityDetailPane } from './components/OpportunityDetailPane';
import { ProfileView } from './components/ProfileView';
import { SandboxInboxView } from './components/SandboxInboxView';
import { SourcesAndTrapsView } from './components/SourcesAndTrapsView';
import { SpatialScene3D } from './components/SpatialScene3D';
import { TopBar, NavTab } from './components/TopBar';

const PIPELINE_STAGES: AgentStage[] = [
  'trigger',
  'plan',
  'fetch',
  'extract',
  'verify',
  'dedupe',
  'match',
  'rank',
  'decide',
  'act',
  'report',
];

export const App: React.FC = () => {
  const [profile, setProfile] = useState<StudentProfile>(DEFAULT_PROFILE);
  const [profileId, setProfileId] = useState<number | string>(1);
  const [sources, setSources] = useState<SourceFeed[]>(() =>
    IS_FASTAPI_MODE ? [] : INITIAL_SOURCES
  );
  const [opportunities, setOpportunities] = useState<Opportunity[]>(() =>
    IS_FASTAPI_MODE ? [] : buildInitialOpportunities(DEFAULT_PROFILE)
  );
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>(() =>
    IS_FASTAPI_MODE ? [] : INITIAL_AUDIT_EVENTS
  );
  const [digests, setDigests] = useState<SandboxDigestMessage[]>(() =>
    IS_FASTAPI_MODE ? [] : INITIAL_DIGESTS
  );
  const [trapResults, setTrapResults] = useState<TrapPackResult[]>(() =>
    IS_FASTAPI_MODE ? [] : INITIAL_TRAP_PACK_RESULTS
  );
  const [trapPackNotRunYet, setTrapPackNotRunYet] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [filters, setFilters] = useState<OpportunityFilters>(createEmptyFilters());
  const [selectedId, setSelectedId] = useState<string | null>(() => {
    if (IS_FASTAPI_MODE) return null;
    const initial = buildInitialOpportunities(DEFAULT_PROFILE);
    return initial[0]?.id ?? null;
  });
  const [activeTab, setActiveTab] = useState<NavTab>('opps');
  const [importModalOpen, setImportModalOpen] = useState(false);

  const [telemetry, setTelemetry] = useState<RunTelemetry>({
    runId: 'run-0',
    state: 'idle',
    runMode: DEFAULT_RUN_MODE,
    currentStage: null,
    progressPct: 0,
    startedAt: null,
    finishedAt: null,
    heartbeatAt: nowIstString(),
    requestsUsed: 0,
    requestsLimit: 50,
    tokensUsed: 0,
    tokensLimit: 25000,
    estimatedCostUsd: 0,
    costLimitUsd: 0.25,
    elapsedSeconds: 0,
    timeLimitSeconds: 60,
    nextScheduledInMinutes: 15,
    schedulerEnabled: true,
    activeSourceName: null,
    newCount: 0,
    dedupedCount: 0,
    killSwitchDbFlag: false,
    killSwitchFileFlag: false,
  });

  const killedRef = useRef(false);
  const telemetryRef = useRef(telemetry);
  telemetryRef.current = telemetry;
  const lastEventSeqRef = useRef(0);

  const loadFastApiData = async () => {
    try {
      const [statusRes, oppsRes, sourcesRes, trapRes, profilesRes] = await Promise.all([
        getApiStatus(),
        getApiOpportunities({ limit: 50, offset: 0 }),
        getApiSources(),
        getApiTrapPack(),
        getApiProfiles(),
      ]);

      setApiError(null);
      const latestRun = statusRes.latest_run;
      const stageIdx = latestRun?.stage ? PIPELINE_STAGES.indexOf(latestRun.stage) : -1;
      const mappedState: RunTelemetry['state'] = statusRes.kill_switch
        ? 'killed'
        : latestRun?.state === 'running'
        ? 'running'
        : latestRun?.state === 'done'
        ? 'completed'
        : latestRun?.state === 'stopped'
        ? 'killed'
        : latestRun?.state === 'failed'
        ? 'error'
        : 'idle';

      setTelemetry((prev) => ({
        ...prev,
        runId: latestRun ? `run-${latestRun.id}` : prev.runId,
        runMode: statusRes.mode || prev.runMode,
        state: mappedState,
        currentStage: latestRun?.stage ?? null,
        progressPct:
          mappedState === 'completed'
            ? 100
            : stageIdx >= 0
            ? Math.round(((stageIdx + 1) / PIPELINE_STAGES.length) * 100)
            : 0,
        heartbeatAt: statusRes.daemon.heartbeat_at || nowIstString(),
        requestsUsed: statusRes.budget.used_requests,
        requestsLimit: statusRes.budget.caps.requests,
        tokensUsed: statusRes.budget.used_tokens,
        tokensLimit: statusRes.budget.caps.tokens,
        estimatedCostUsd: statusRes.budget.used_usd,
        costLimitUsd: statusRes.budget.caps.usd,
        timeLimitSeconds: statusRes.budget.caps.seconds,
        killSwitchDbFlag: statusRes.kill_switch,
        killSwitchFileFlag: statusRes.kill_switch,
      }));

      const mappedOpps = oppsRes.items.map(mapApiOpportunityToUi);
      setOpportunities(mappedOpps);
      setSelectedId((cur) => cur ?? mappedOpps[0]?.id ?? null);

      setSources(
        sourcesRes.items.map((s) => ({
          id: String(s.id),
          name: s.name,
          type: 'Official API',
          url: '',
          enabled: s.enabled,
          intervalHours: Math.max(1, Math.round(s.interval_s / 3600)),
          lastChecked: s.last_ok_at || s.last_snapshot?.fetched_at || 'Never',
          contentHash: '',
          circuitBreaker: s.breaker_state === 'open' ? 'open' : 'closed',
          status: s.breaker_state === 'open' ? 'error' : 'healthy',
          itemsFound: s.last_snapshot?.item_count ?? 0,
          robotsAllowed: true,
        }))
      );

      if (trapRes.notRunYet) {
        setTrapPackNotRunYet(true);
        setTrapResults([]);
      } else if (trapRes.cases) {
        setTrapPackNotRunYet(false);
        setTrapResults(
          trapRes.cases.map((c, idx) => ({
            id: `trap-${idx}`,
            name: c.name,
            category: c.type as TrapPackResult['category'],
            inputSummary: c.name,
            expectedOutcome: c.expected,
            actualOutcome: c.actual,
            passed: c.passed,
            checkedAt: trapRes.generated_at || nowIstString(),
            lastRunAt: trapRes.generated_at || nowIstString(),
          }))
        );
      }

      const firstProf = profilesRes.items[0];
      if (firstProf) {
        if (firstProf.id != null) setProfileId(firstProf.id as number);
        setProfile((prev) => ({
          ...prev,
          name: String(firstProf.label ?? prev.name),
          degree: String(firstProf.education_level ?? prev.degree),
          discipline: String(firstProf.education_field ?? prev.discipline),
          graduationYear: Number(firstProf.graduation_year ?? prev.graduationYear),
          skills: Array.isArray(firstProf.skills) ? (firstProf.skills as string[]) : prev.skills,
          preferredLocations: Array.isArray(firstProf.preferred_locations)
            ? (firstProf.preferred_locations as string[])
            : prev.preferredLocations,
        }));
      }

      const evtsRes = await getApiEvents({
        run_id: latestRun?.id,
        after_seq: lastEventSeqRef.current,
        limit: 100,
      });
      if (evtsRes.items.length > 0) {
        lastEventSeqRef.current = evtsRes.items[evtsRes.items.length - 1].seq;
        const mappedEvts: AuditEvent[] = evtsRes.items.map((e) => ({
          id: `evt-${e.seq}`,
          runId: latestRun ? `run-${latestRun.id}` : 'run-0',
          timestamp: e.ts,
          stage: (e.stage as AuditEvent['stage']) || 'scheduler',
          kind:
            e.type === 'kill_switch'
              ? 'kill_switch'
              : e.error
              ? 'error'
              : e.type === 'decision'
              ? 'decision'
              : 'gateway_call',
          toolName: e.tool ?? undefined,
          summary: e.result_summary || e.input_summary || e.type,
          detail: e.reason || e.error || '',
        }));
        setAuditEvents((prev) => [...mappedEvts.reverse(), ...prev]);
      }
    } catch (err) {
      const msg =
        err instanceof ApiClientError
          ? `${err.code}: ${err.detail}`
          : err instanceof Error
          ? err.message
          : 'Unable to reach FastAPI backend on http://localhost:8000';
      setApiError(msg);
    }
  };

  useEffect(() => {
    if (!IS_FASTAPI_MODE) {
      const id = setInterval(() => {
        setTelemetry((t) => ({ ...t, heartbeatAt: nowIstString() }));
      }, 5000);
      return () => clearInterval(id);
    }
    void loadFastApiData();
    const id = setInterval(() => {
      void loadFastApiData();
    }, 1500);
    return () => clearInterval(id);
  }, []);

  const filteredOpps = applyOpportunityFilters(opportunities, filters);
  const selectedOpportunity =
    opportunities.find((o) => o.id === selectedId) ?? filteredOpps[0] ?? null;

  const handleStartRun = async () => {
    if (telemetry.state === 'running') return;
    if (IS_FASTAPI_MODE) {
      try {
        setApiError(null);
        await postRunRequest();
        await loadFastApiData();
      } catch (err) {
        setApiError(err instanceof Error ? err.message : 'Failed to request run');
      }
      return;
    }
    killedRef.current = false;

    await runMockAutonomousPipeline(profile, sources, opportunities, {
      getTelemetry: () => telemetryRef.current,
      isKilled: () => killedRef.current,
      onTelemetry: (patch) => setTelemetry((prev) => ({ ...prev, ...patch })),
      onAudit: (evt) => setAuditEvents((prev) => [evt, ...prev]),
      onUpsertOpportunity: (opp) =>
        setOpportunities((prev) => {
          const exists = prev.some((o) => o.canonicalKey === opp.canonicalKey);
          return exists
            ? prev.map((o) => (o.canonicalKey === opp.canonicalKey ? opp : o))
            : [opp, ...prev];
        }),
      onDeliverDigest: (msg) => setDigests((prev) => [msg, ...prev]),
      onUpdateSource: (id, patch) =>
        setSources((prev) =>
          prev.map((s) => (s.id === id ? { ...s, ...patch } : s))
        ),
    });
  };

  const handleKillSwitch = async () => {
    if (IS_FASTAPI_MODE) {
      try {
        setApiError(null);
        await postKillSwitch(true);
        await loadFastApiData();
      } catch (err) {
        setApiError(err instanceof Error ? err.message : 'Kill-switch request failed');
      }
      return;
    }
    killedRef.current = true;
    setTelemetry((prev) => ({
      ...prev,
      state: 'killed',
      killSwitchDbFlag: true,
      killSwitchFileFlag: true,
      finishedAt: nowIstString(),
    }));
  };

  const handleToggleSource = (id: string) => {
    setSources((prev) =>
      prev.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s))
    );
  };

  const handleAddSource = (
    src: Omit<SourceFeed, 'id' | 'lastChecked' | 'status' | 'itemsFound' | 'contentHash' | 'circuitBreaker'>
  ) => {
    setSources((prev) => [
      ...prev,
      {
        ...src,
        id: `src-${Date.now()}`,
        lastChecked: nowIstString(),
        status: 'healthy',
        itemsFound: 0,
        contentHash: '',
        circuitBreaker: 'closed',
      },
    ]);
  };

  const handleRunTrapPack = () => {
    setTrapResults((prev) =>
      prev.map((t) => ({ ...t, checkedAt: nowIstString(), passed: true }))
    );
  };

  const handleApproveReviewItem = async (id: string) => {
    if (IS_FASTAPI_MODE) {
      try {
        await postReviewResolution(id, 'accepted');
      } catch (err) {
        setApiError(err instanceof Error ? err.message : 'Failed to accept review item');
        return;
      }
    }
    setOpportunities((ops) =>
      ops.map((o) => (o.id === id ? { ...o, eligibilityStatus: 'eligible' } : o))
    );
  };

  const handleDismissReviewItem = async (id: string) => {
    if (IS_FASTAPI_MODE) {
      try {
        await postReviewResolution(id, 'rejected');
      } catch (err) {
        setApiError(err instanceof Error ? err.message : 'Failed to reject review item');
        return;
      }
    }
    setOpportunities((ops) =>
      ops.map((o) => (o.id === id ? { ...o, dismissed: true } : o))
    );
    if (selectedId === id) setSelectedId(null);
  };

  const handleInspectOpportunity = (id: string) => {
    setSelectedId(id);
    setActiveTab('opps');
  };

  const handleExportTrace = () => {
    const dataStr = JSON.stringify({ telemetry, auditEvents }, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `campusos-trace-${telemetry.runId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSaveProfile = async (updated: StudentProfile) => {
    if (IS_FASTAPI_MODE) {
      try {
        await putProfile(profileId, {
          education_level: updated.degree.toLowerCase().includes('master') ? 'master' : 'bachelor',
          education_field: updated.discipline,
          currently_enrolled: true,
          graduation_year: updated.graduationYear,
          skills: updated.skills,
          preferred_locations: updated.preferredLocations,
        });
      } catch (err) {
        setApiError(err instanceof Error ? err.message : 'Failed to update profile');
      }
    }
    setProfile(updated);
    setOpportunities((prev) =>
      prev.map((o) => {
        const { score, eligibilityStatus } = evaluateOpportunityMatch(o, updated);
        return { ...o, score, eligibilityStatus };
      })
    );
  };

  const handleImportJson = (jsonText: string) => {
    if (IS_FASTAPI_MODE) {
      void postImportJson(JSON.parse(jsonText)).catch((err) =>
        setApiError(err instanceof Error ? err.message : 'Import failed')
      );
    }
    const result = importTeammateOpportunitiesJson(jsonText, profile, opportunities);
    setOpportunities((prev) => [...result.imported, ...prev]);
    return {
      importedCount: result.imported.length,
      mergedCount: result.mergedCount,
      quarantinedCount: result.blockedInjectionCount,
      rejectedCount: result.rejectedCount,
    };
  };

  const handleToggleChecklist = (oppId: string, itemId: string) => {
    setOpportunities((prev) =>
      prev.map((o) =>
        o.id === oppId
          ? {
              ...o,
              checklist: o.checklist.map((c) =>
                c.id === itemId ? { ...c, done: !c.done } : c
              ),
            }
          : o
      )
    );
  };

  const handleAddChecklistItem = (oppId: string, label: string) => {
    setOpportunities((prev) =>
      prev.map((o) =>
        o.id === oppId
          ? {
              ...o,
              checklist: [...o.checklist, { id: `chk-${Date.now()}`, label, done: false }],
            }
          : o
      )
    );
  };

  const handleUpdateDraft = (oppId: string, draftNote: string) => {
    setOpportunities((prev) =>
      prev.map((o) => (o.id === oppId ? { ...o, draftNote } : o))
    );
  };

  const handleToggleBookmark = (oppId: string) => {
    setOpportunities((prev) =>
      prev.map((o) => (o.id === oppId ? { ...o, bookmarked: !o.bookmarked } : o))
    );
  };

  const handleToggleApplied = (oppId: string) => {
    setOpportunities((prev) =>
      prev.map((o) => (o.id === oppId ? { ...o, applied: !o.applied } : o))
    );
  };

  const eligibleCount = opportunities.filter(
    (o) => !o.dismissed && o.eligibilityStatus === 'eligible'
  ).length;
  const reviewCount = opportunities.filter(
    (o) => !o.dismissed && o.eligibilityStatus === 'needs_review'
  ).length;
  const trapsBlocked = trapResults.filter((t) => t.passed).length;
  const enabledSourcesCount = sources.filter((s) => s.enabled).length;
  const activeStageIndex = telemetry.currentStage
    ? PIPELINE_STAGES.indexOf(telemetry.currentStage)
    : -1;

  const deckRef = useRef<HTMLElement | null>(null);

  const handleDeckPointerMove = (e: React.PointerEvent<HTMLElement>) => {
    const el = deckRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width;
    const py = (e.clientY - rect.top) / rect.height;
    const ry = ((px - 0.5) * 4).toFixed(2);
    const rx = ((0.5 - py) * 3).toFixed(2);
    el.style.setProperty('--rx', `${rx}deg`);
    el.style.setProperty('--ry', `${ry}deg`);
    el.style.setProperty('--mx', `${(px * 100).toFixed(1)}%`);
    el.style.setProperty('--my', `${(py * 100).toFixed(1)}%`);
  };

  const handleDeckPointerLeave = () => {
    const el = deckRef.current;
    if (!el) return;
    el.style.setProperty('--rx', '0deg');
    el.style.setProperty('--ry', '0deg');
  };

  return (
    <div className="spatial-backdrop">
      <SpatialScene3D state={telemetry.state} currentStage={telemetry.currentStage} />
      <TopBar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        oppsCount={filteredOpps.length}
        reviewCount={reviewCount}
        auditCount={auditEvents.length}
        telemetryState={telemetry.state}
        runMode={telemetry.runMode}
        onStartRun={handleStartRun}
        onKillSwitch={handleKillSwitch}
        onOpenImport={() => setImportModalOpen(true)}
      />
      <div className="app-shell">
        {apiError && (
          <div className="banner banner-killed" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>
              <strong>Backend API notice:</strong> {apiError}
            </span>
            <button type="button" className="btn btn-ghost" style={{ height: 26 }} onClick={() => setApiError(null)}>
              Dismiss
            </button>
          </div>
        )}
        <div className="workspace-intro">
          <div>
            <h1 className="workspace-heading">
              {activeTab === 'opps'
                ? 'Verified Campus Opportunities'
                : activeTab === 'inbox'
                ? 'Sandbox Review Inbox'
                : activeTab === 'sources'
                ? 'Official Sources & Trap Shield'
                : activeTab === 'audit'
                ? 'Execution Audit & Trace'
                : 'Candidate Profile & Eligibility'}
            </h1>
            <p className="workspace-subheading">
              Curated from official university placement feeds, screened for scam traps, and ranked for your profile.
            </p>
          </div>
          {activeTab === 'opps' && (
            <div className="hero-search-wrap">
              <Search size={15} className="hero-search-icon" />
              <input
                type="search"
                className="hero-search-input"
                value={filters.query}
                onChange={(e) => setFilters({ ...filters, query: e.target.value })}
                placeholder="Search roles, companies, or skills..."
              />
            </div>
          )}
        </div>

          

      <section
        ref={deckRef}
        className="spatial-deck"
        onPointerMove={handleDeckPointerMove}
        onPointerLeave={handleDeckPointerLeave}
        aria-label="Coverage and Pipeline Status"
      >
        <div className="kpi-card">
          <span className="kpi-label">Eligible Matches</span>
          <span className="kpi-value">{eligibleCount}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Review Queue</span>
          <span className="kpi-value">{reviewCount}</span>
        </div>
        <div className="kpi-card">
          <span className="kpi-label">Safety &amp; Traps Blocked</span>
          <span className="kpi-value">
            {trapsBlocked}/{trapResults.length} · {enabledSourcesCount} feeds
          </span>
        </div>
        <div className="pipeline-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="kpi-label">
              11-Stage Pipeline{' '}
              {telemetry.currentStage ? `· ${telemetry.currentStage.toUpperCase()}` : '· Ready'}
            </span>
            <span className="mono" style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
              {telemetry.progressPct}%
            </span>
          </div>
          <div className="pipeline-stages">
            {PIPELINE_STAGES.map((stage, idx) => (
              <div
                key={stage}
                title={stage}
                className={`stage-pip ${
                  telemetry.state === 'completed' || idx < activeStageIndex
                    ? 'done'
                    : idx === activeStageIndex
                    ? 'active'
                    : ''
                }`}
              />
            ))}
          </div>
        </div>
      </section>

      <main>
        {activeTab === 'opps' && (
          <div className={`opps-workspace ${selectedOpportunity ? 'with-detail' : ''}`}>
            <FilterSidebar
              allOpportunities={opportunities}
              filters={filters}
              onChange={setFilters}
              onReset={() => setFilters(createEmptyFilters())}
            />

            <div className="opp-list">
              {filteredOpps.length === 0 ? (
                <div className="panel" style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
                  No opportunities match the active filters.
                </div>
              ) : (
                filteredOpps.map((opp) => (
                  <article
                    key={opp.id}
                    className={`opp-card ${selectedOpportunity?.id === opp.id ? 'selected' : ''}`}
                    onClick={() => setSelectedId(opp.id)}
                  >
                    <div className="opp-card-head">
                      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                        <CompanyMark company={opp.company} size={36} />
                        <div>
                          <h3 className="opp-card-title">{opp.title}</h3>
                          <p className="opp-card-meta">
                            {opp.company} · {opp.location} · {opp.workMode}
                          </p>
                        </div>
                      </div>
                      <span
                        className={`pill ${
                          opp.score.total >= 80
                            ? 'pill-emerald'
                            : opp.score.total >= 60
                            ? 'pill-indigo'
                            : 'pill-amber'
                        }`}
                      >
                        {opp.score.total}% fit
                      </span>
                    </div>

                    <div className="opp-card-footer">
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                        <span className="pill pill-slate">{opp.opportunityType}</span>
                        {opp.eligibilityStatus === 'eligible' && (
                          <span className="pill pill-emerald">Eligible</span>
                        )}
                        {opp.eligibilityStatus === 'needs_review' && (
                          <span className="pill pill-amber">Needs Review</span>
                        )}
                        {opp.scamFlags.length > 0 && (
                          <span className="pill pill-red">Trap Flagged</span>
                        )}
                        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                          {opp.compensation ?? 'Unlisted'} · {opp.deadline ? `Due ${opp.deadline}` : 'Rolling'}
                        </span>
                      </div>
                    </div>
                  </article>
                ))
              )}
            </div>

            {selectedOpportunity && (
              <OpportunityDetailPane
                opportunity={selectedOpportunity}
                onCloseMobile={() => setSelectedId(null)}
                onToggleChecklist={handleToggleChecklist}
                onAddChecklistItem={handleAddChecklistItem}
                onUpdateDraft={handleUpdateDraft}
                onToggleBookmark={handleToggleBookmark}
                onToggleApplied={handleToggleApplied}
                onDismiss={handleDismissReviewItem}
              />
            )}
          </div>
        )}

        {activeTab === 'inbox' && (
          <SandboxInboxView
            digests={digests}
            reviewQueue={opportunities.filter(
              (o) => !o.dismissed && o.eligibilityStatus === 'needs_review'
            )}
            eligibleOpportunities={opportunities.filter(
              (o) => !o.dismissed && o.eligibilityStatus === 'eligible'
            )}
            onApproveReviewItem={handleApproveReviewItem}
            onDismissReviewItem={handleDismissReviewItem}
            onInspectOpportunity={handleInspectOpportunity}
          />
        )}

        {activeTab === 'sources' && (
          <SourcesAndTrapsView
            sources={sources}
            trapResults={trapResults}
            trapPackNotRunYet={trapPackNotRunYet}
            isRunning={telemetry.state === 'running'}
            isKilled={telemetry.state === 'killed'}
            onToggleSource={handleToggleSource}
            onTestSource={(id) => console.log('test', id)}
            onToggleCircuitBreaker={(id) =>
              setSources((prev) =>
                prev.map((s) =>
                  s.id === id
                    ? { ...s, circuitBreaker: s.circuitBreaker === 'closed' ? 'open' : 'closed' }
                    : s
                )
              )
            }
            onAddSource={handleAddSource}
            onRunTrapPack={handleRunTrapPack}
          />
        )}

        {activeTab === 'audit' && (
          <AuditTraceView
            telemetry={telemetry}
            events={auditEvents}
            onChangeRunMode={(mode: RunMode) =>
              setTelemetry((t) => ({ ...t, runMode: mode }))
            }
            onExportTrace={handleExportTrace}
          />
        )}

        {activeTab === 'profile' && (
          <ProfileView profile={profile} onSaveProfile={handleSaveProfile} />
        )}
      </main>

      <DataImportModal
        open={importModalOpen}
        onClose={() => setImportModalOpen(false)}
        onImportJson={handleImportJson}
      />
      </div>
    </div>
  );
};

export default App;
