import React, { useState, useEffect, useRef } from 'react';
import type {
  JobCreateRequest,
  DetectedStackResponse,
  TierComponent,
  DatabaseComponent,
} from '../types/api';
import { api } from '../services/api';
import {
  Layers,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  RefreshCw,
  Edit2,
  Check,
  Code2,
  Cpu,
  Wrench,
  GitBranch,
  RotateCcw,
  Database,
  Globe,
  Server,
  AlertTriangle,
  FileCode,
  Info,
} from 'lucide-react';

interface CreateJobProps {
  onSubmit: (req: JobCreateRequest) => Promise<any>;
  onNavigate: (path: string) => void;
}

interface TierOverrides {
  frontend?: {
    technology?: string;
    primary_language?: string;
    build_tool_or_driver?: string;
  };
  backend?: {
    technology?: string;
    primary_language?: string;
    build_tool_or_driver?: string;
  };
  database?: {
    engine?: string;
    orm_or_driver?: string;
    migration_tool?: string;
  };
}

export const CreateJob: React.FC<CreateJobProps> = ({ onSubmit, onNavigate }) => {
  const [name, setName] = useState('Payment Gateway Modernization');
  const [sourceRepo, setSourceRepo] = useState('https://github.com/acme/payment-gateway');
  const [revision, setRevision] = useState('main');
  const [sourceStack, setSourceStack] = useState('Java 11 / Spring Boot 2.7 (Maven)');
  const [targetStack] = useState('TypeScript / Node.js 22 / NestJS');
  const [budget, setBudget] = useState(150);
  const [maxRepairAttempts, setMaxRepairAttempts] = useState(3);
  const [constraints, setConstraints] = useState('Preserve all ISO8583 settlement idempotency constraints.');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Stack Detection & Editing States
  const [detectedStack, setDetectedStack] = useState<DetectedStackResponse | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [detectError, setDetectError] = useState<string | null>(null);

  // Three-Tier Independent Overrides
  const [overrides, setOverrides] = useState<TierOverrides>({});
  const [editingTier, setEditingTier] = useState<'frontend' | 'backend' | 'database' | null>(null);

  // Edit buffer values
  const [editFrontendTech, setEditFrontendTech] = useState('');
  const [editFrontendLang, setEditFrontendLang] = useState('');
  const [editFrontendBuild, setEditFrontendBuild] = useState('');

  const [editBackendTech, setEditBackendTech] = useState('');
  const [editBackendLang, setEditBackendLang] = useState('');
  const [editBackendBuild, setEditBackendBuild] = useState('');

  const [editDbEngine, setEditDbEngine] = useState('');
  const [editDbDriver, setEditDbDriver] = useState('');
  const [editDbMigration, setEditDbMigration] = useState('');

  // Race-condition guard for async preview requests
  const latestReqIdRef = useRef(0);

  const handleDetectStack = async (repoUrl: string, rev: string) => {
    if (!repoUrl || !repoUrl.trim()) return;
    const reqId = ++latestReqIdRef.current;

    try {
      setDetecting(true);
      setDetectError(null);
      const res = await api.detectSourceStack(repoUrl.trim(), rev?.trim() || 'main');

      // Check if another request has been initiated since this one started
      if (reqId !== latestReqIdRef.current) return;

      setDetectedStack(res);
      if (res.source_revision && res.source_revision !== 'HEAD' && res.source_revision !== rev) {
        setRevision(res.source_revision);
      }
      setSourceStack(res.summary_stack);

      // Reset overrides on fresh detection
      setOverrides({});
      setEditingTier(null);
    } catch (err: any) {
      if (reqId === latestReqIdRef.current) {
        console.warn('Stack detection notice:', err);
        setDetectError(err.message || 'Stack detection failed. Please check repository coordinates and permissions.');
      }
    } finally {
      if (reqId === latestReqIdRef.current) {
        setDetecting(false);
      }
    }
  };

  useEffect(() => {
    if (!sourceRepo || sourceRepo.trim().length < 5) return;
    const timer = setTimeout(() => {
      handleDetectStack(sourceRepo, revision);
    }, 500);
    return () => clearTimeout(timer);
  }, [sourceRepo, revision]);

  // Derive effective tier values
  const rawFrontend = detectedStack?.tiers?.frontend?.primary;
  const rawBackend = detectedStack?.tiers?.backend?.primary;
  const rawDb = detectedStack?.tiers?.database?.primary;

  const effectiveFrontend = {
    technology: overrides.frontend?.technology ?? (rawFrontend?.technology || 'None detected'),
    primary_language: overrides.frontend?.primary_language ?? (rawFrontend?.primary_language || 'N/A'),
    build_tool: overrides.frontend?.build_tool_or_driver ?? (rawFrontend?.build_tool_or_driver || 'None'),
    isOverridden: !!overrides.frontend,
  };

  const effectiveBackend = {
    technology: overrides.backend?.technology ?? (rawBackend?.technology || 'None detected'),
    primary_language: overrides.backend?.primary_language ?? (rawBackend?.primary_language || 'N/A'),
    build_tool: overrides.backend?.build_tool_or_driver ?? (rawBackend?.build_tool_or_driver || 'None'),
    isOverridden: !!overrides.backend,
  };

  const effectiveDb = {
    engine: overrides.database?.engine ?? (rawDb?.engine || 'Stateless / None declared'),
    orm_or_driver: overrides.database?.orm_or_driver ?? (rawDb?.orm_or_driver || 'None declared'),
    migration_tool: overrides.database?.migration_tool ?? (rawDb?.migration_tool || 'None'),
    isOverridden: !!overrides.database,
  };

  const startEditTier = (tier: 'frontend' | 'backend' | 'database') => {
    if (tier === 'frontend') {
      setEditFrontendTech(effectiveFrontend.technology === 'None detected' ? 'React SPA' : effectiveFrontend.technology);
      setEditFrontendLang(effectiveFrontend.primary_language === 'N/A' ? 'TypeScript' : effectiveFrontend.primary_language);
      setEditFrontendBuild(effectiveFrontend.build_tool === 'None' ? 'Vite' : effectiveFrontend.build_tool);
    } else if (tier === 'backend') {
      setEditBackendTech(effectiveBackend.technology === 'None detected' ? 'FastAPI' : effectiveBackend.technology);
      setEditBackendLang(effectiveBackend.primary_language === 'N/A' ? 'Python' : effectiveBackend.primary_language);
      setEditBackendBuild(effectiveBackend.build_tool === 'None' ? 'pip' : effectiveBackend.build_tool);
    } else if (tier === 'database') {
      setEditDbEngine(effectiveDb.engine.startsWith('Stateless') ? 'PostgreSQL' : effectiveDb.engine);
      setEditDbDriver(effectiveDb.orm_or_driver === 'None declared' ? 'SQLAlchemy' : effectiveDb.orm_or_driver);
      setEditDbMigration(effectiveDb.migration_tool === 'None' ? 'Alembic' : effectiveDb.migration_tool);
    }
    setEditingTier(tier);
  };

  const applyTierEdit = (tier: 'frontend' | 'backend' | 'database') => {
    if (tier === 'frontend') {
      setOverrides((prev) => ({
        ...prev,
        frontend: {
          technology: editFrontendTech,
          primary_language: editFrontendLang,
          build_tool_or_driver: editFrontendBuild,
        },
      }));
    } else if (tier === 'backend') {
      setOverrides((prev) => ({
        ...prev,
        backend: {
          technology: editBackendTech,
          primary_language: editBackendLang,
          build_tool_or_driver: editBackendBuild,
        },
      }));
    } else if (tier === 'database') {
      setOverrides((prev) => ({
        ...prev,
        database: {
          engine: editDbEngine,
          orm_or_driver: editDbDriver,
          migration_tool: editDbMigration,
        },
      }));
    }
    setEditingTier(null);
  };

  const resetTier = (tier: 'frontend' | 'backend' | 'database') => {
    setOverrides((prev) => {
      const next = { ...prev };
      delete next[tier];
      return next;
    });
    setEditingTier(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setLoading(true);
      setError(null);
      const hasOverrides = Object.keys(overrides).length > 0;

      const created = await onSubmit({
        name,
        source_repository: sourceRepo,
        source_revision: revision,
        source_stack: sourceStack,
        target_stack: targetStack,
        budget,
        max_repair_attempts: maxRepairAttempts,
        constraints,
        pinned_commit: detectedStack?.resolved_commit || undefined,
        user_overrides: hasOverrides ? overrides : undefined,
        stack_metadata: detectedStack || undefined,
      });
      onNavigate(`/jobs/${created.job_id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to initialize modernization job');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Initialize Modernization Wizard</h1>
          <p className="subtitle">
            Configure repository source, three-tier architecture characterization, and autonomous agent budget guardrails.
          </p>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary" onClick={() => onNavigate('/jobs')}>
            Cancel
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--danger-surface)',
            color: 'var(--destructive)',
            borderRadius: 'var(--radius-md)',
            fontSize: '12px',
            marginBottom: '24px',
          }}
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="form-layout">
          {/* Main Form Fields */}
          <div>
            {/* Step 1: Source Discovery */}
            <div className="form-section">
              <h2>1. Legacy Source Repository</h2>
              <p>Specify the repository coordinates and branch revision for intake discovery.</p>

              <div className="form-grid">
                <div className="form-field span-two">
                  <label htmlFor="repo-url">Repository URL</label>
                  <input
                    id="repo-url"
                    type="text"
                    className="field"
                    value={sourceRepo}
                    onChange={(e) => {
                      let val = e.target.value.trim();
                      const urlRegex = /(https?:\/\/[^\s]+)/g;
                      const matches = val.match(urlRegex);
                      if (matches && matches.length > 1) {
                        val = matches[0];
                      }
                      setSourceRepo(val);
                    }}
                    placeholder="https://github.com/org/repo"
                    required
                  />
                  <small>Accepts public and authenticated HTTPS Git clone endpoints.</small>
                </div>

                <div className="form-field">
                  <label htmlFor="repo-revision">Revision / Branch</label>
                  <input
                    id="repo-revision"
                    type="text"
                    className="field"
                    value={revision}
                    onChange={(e) => setRevision(e.target.value)}
                    placeholder="main or SHA"
                    required
                  />
                  <small>Target branch or pinned commit hash for characterization.</small>
                </div>

                <div className="form-field span-two">
                  {/* Card Section Header */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '10px',
                      flexWrap: 'wrap',
                      gap: '8px',
                    }}
                  >
                    <label
                      style={{
                        margin: 0,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        fontSize: '13px',
                        fontWeight: 600,
                        color: 'var(--foreground)',
                      }}
                    >
                      <Sparkles size={16} color="var(--primary)" />
                      <span>Detected Legacy Architecture Stack (Three-Tier)</span>
                    </label>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      {detecting && (
                        <span
                          style={{
                            fontSize: '11px',
                            color: 'var(--primary)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          <RefreshCw size={12} className="spin" />
                          <span>Ephemeral repository preview...</span>
                        </span>
                      )}
                      {!detecting && detectedStack?.scan_status && (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '3px 8px',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor:
                              detectedStack.scan_status === 'COMPLETED'
                                ? 'var(--accent)'
                                : detectedStack.scan_status === 'PARTIAL'
                                ? 'var(--warning-surface)'
                                : 'var(--danger-surface)',
                            color:
                              detectedStack.scan_status === 'COMPLETED'
                                ? 'var(--primary)'
                                : detectedStack.scan_status === 'PARTIAL'
                                ? 'var(--warning)'
                                : 'var(--destructive)',
                            fontWeight: 600,
                          }}
                        >
                          ● {detectedStack.scan_status}
                        </span>
                      )}
                      {!detecting && detectedStack && (
                        <span
                          style={{
                            fontSize: '11px',
                            padding: '3px 8px',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor: Object.keys(overrides).length > 0 ? 'var(--warning-surface)' : 'var(--accent)',
                            color: Object.keys(overrides).length > 0 ? 'var(--warning)' : 'var(--primary)',
                            fontWeight: 600,
                            border: Object.keys(overrides).length > 0
                              ? '1px solid rgba(180, 83, 9, 0.25)'
                              : '1px solid rgba(19, 122, 91, 0.25)',
                          }}
                        >
                          {Object.keys(overrides).length > 0
                            ? `● Customized (${Object.keys(overrides).length} tier overrides)`
                            : `● ${Math.round((detectedStack.confidence_score || 0.98) * 100)}% Confidence`}
                        </span>
                      )}
                      <button
                        type="button"
                        className="button button-secondary button-sm"
                        onClick={() => handleDetectStack(sourceRepo, revision)}
                        disabled={detecting}
                        title="Re-scan and fetch manifests from repository"
                        style={{ padding: '4px 10px', fontSize: '11px', height: '28px' }}
                      >
                        <RefreshCw size={12} className={detecting ? 'spin' : ''} />
                        <span>Fetch from Repo</span>
                      </button>
                    </div>
                  </div>

                  {detectError && (
                    <div
                      style={{
                        padding: '10px 14px',
                        backgroundColor: 'var(--danger-surface)',
                        color: 'var(--destructive)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '12px',
                        marginBottom: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <span>⚠️ {detectError}</span>
                      <button
                        type="button"
                        className="button button-secondary button-sm"
                        onClick={() => handleDetectStack(sourceRepo, revision)}
                        style={{ fontSize: '11px', height: '24px' }}
                      >
                        Retry
                      </button>
                    </div>
                  )}

                  {/* Empty / Inconclusive Notice */}
                  {detectedStack && detectedStack.scan_status === 'INCONCLUSIVE' && (
                    <div
                      style={{
                        padding: '10px 14px',
                        backgroundColor: 'var(--warning-surface)',
                        color: 'var(--warning)',
                        borderRadius: 'var(--radius-md)',
                        fontSize: '12px',
                        marginBottom: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                      }}
                    >
                      <AlertTriangle size={15} />
                      <span>
                        No application code detected. Repository contains documentation or empty structure. You can
                        manually customize tiers below.
                      </span>
                    </div>
                  )}

                  {/* Main Container */}
                  <div
                    style={{
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-lg)',
                      backgroundColor: 'var(--card)',
                      overflow: 'hidden',
                      boxShadow: 'var(--shadow-soft)',
                    }}
                  >
                    {/* Header Strip */}
                    <div
                      style={{
                        padding: '10px 16px',
                        backgroundColor: 'var(--secondary)',
                        borderBottom: '1px solid var(--border)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '11px',
                        flexWrap: 'wrap',
                        gap: '8px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <GitBranch size={13} color="var(--primary)" />
                        <span style={{ fontWeight: 600 }}>Ephemeral Preview:</span>
                        <code style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted-foreground)' }}>
                          {detectedStack?.detection_method || 'Static Manifest & DDL Analysis'}
                        </code>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', color: 'var(--muted-foreground)' }}>
                        {detectedStack?.resolved_commit && (
                          <span>
                            Pinned Commit: <strong style={{ color: 'var(--foreground)' }}>{detectedStack.resolved_commit.slice(0, 8)}</strong>
                          </span>
                        )}
                        <span>
                          Branch: <strong style={{ color: 'var(--foreground)' }}>{revision}</strong>
                        </span>
                      </div>
                    </div>

                    {detectedStack?.warnings && detectedStack.warnings.length > 0 && (
                      <div
                        style={{
                          margin: '12px 16px 0 16px',
                          padding: '8px 12px',
                          backgroundColor: 'var(--warning-surface)',
                          color: 'var(--warning)',
                          borderRadius: 'var(--radius-md)',
                          fontSize: '11px',
                        }}
                      >
                        <strong>Scan Diagnostics:</strong>
                        <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
                          {detectedStack.warnings.map((w, idx) => (
                            <li key={idx}>{w}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Three-Tier Responsive Card Grid */}
                    <div style={{ padding: '16px' }}>
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                          gap: '16px',
                          marginBottom: '16px',
                        }}
                      >
                        {/* ========================================================= */}
                        {/* 1. FRONTEND TIER CARD */}
                        {/* ========================================================= */}
                        <div
                          style={{
                            padding: '16px',
                            backgroundColor: 'var(--background)',
                            border: effectiveFrontend.isOverridden
                              ? '1px solid rgba(180, 83, 9, 0.4)'
                              : '1px solid var(--border)',
                            borderRadius: 'var(--radius-md)',
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between',
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <div
                                  style={{
                                    width: '28px',
                                    height: '28px',
                                    borderRadius: '6px',
                                    backgroundColor: 'var(--accent)',
                                    display: 'grid',
                                    placeItems: 'center',
                                  }}
                                >
                                  <Globe size={15} color="var(--primary)" />
                                </div>
                                <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--foreground)' }}>
                                  🌐 Frontend Tier
                                </span>
                              </div>
                              <span
                                style={{
                                  fontSize: '10px',
                                  padding: '2px 6px',
                                  borderRadius: 'var(--radius-full)',
                                  backgroundColor: effectiveFrontend.isOverridden
                                    ? 'var(--warning-surface)'
                                    : (rawFrontend ? 'var(--accent)' : 'var(--secondary)'),
                                  color: effectiveFrontend.isOverridden
                                    ? 'var(--warning)'
                                    : (rawFrontend ? 'var(--primary)' : 'var(--muted-foreground)'),
                                  fontWeight: 600,
                                }}
                              >
                                {effectiveFrontend.isOverridden ? 'User Override' : (rawFrontend ? 'Detected' : 'None detected')}
                              </span>
                            </div>

                            {/* View / Edit Mode */}
                            {editingTier === 'frontend' ? (
                              <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Framework</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editFrontendTech}
                                    onChange={(e) => setEditFrontendTech(e.target.value)}
                                    placeholder="React SPA, Vue, Angular, None"
                                  />
                                </div>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Language</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editFrontendLang}
                                    onChange={(e) => setEditFrontendLang(e.target.value)}
                                    placeholder="TypeScript, JavaScript, HTML"
                                  />
                                </div>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Build Tool</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editFrontendBuild}
                                    onChange={(e) => setEditFrontendBuild(e.target.value)}
                                    placeholder="Vite, Webpack, npm"
                                  />
                                </div>
                                <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                                  <button
                                    type="button"
                                    className="button button-primary button-sm"
                                    onClick={() => applyTierEdit('frontend')}
                                    style={{ flex: 1, height: '26px', fontSize: '11px' }}
                                  >
                                    Apply
                                  </button>
                                  <button
                                    type="button"
                                    className="button button-secondary button-sm"
                                    onClick={() => setEditingTier(null)}
                                    style={{ height: '26px', fontSize: '11px' }}
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div style={{ marginTop: '6px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Framework: </span>
                                  <strong style={{ color: 'var(--foreground)', fontSize: '13px' }}>
                                    {effectiveFrontend.technology}
                                  </strong>
                                </div>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Language: </span>
                                  <span>{effectiveFrontend.primary_language}</span>
                                </div>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Build Tool: </span>
                                  <span>{effectiveFrontend.build_tool}</span>
                                </div>
                                {rawFrontend?.evidence && rawFrontend.evidence.length > 0 && (
                                  <div style={{ marginTop: '4px', fontSize: '10px', color: 'var(--muted-foreground)' }}>
                                    Evidence: {rawFrontend.evidence[0].file}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>

                          <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                            {effectiveFrontend.isOverridden && (
                              <button
                                type="button"
                                onClick={() => resetTier('frontend')}
                                className="button button-secondary button-sm"
                                style={{ height: '24px', fontSize: '10px', padding: '0 8px' }}
                              >
                                Reset
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => startEditTier('frontend')}
                              className="button button-secondary button-sm"
                              style={{ height: '24px', fontSize: '10px', padding: '0 8px' }}
                            >
                              <Edit2 size={10} />
                              <span>{effectiveFrontend.isOverridden ? 'Edit Override' : 'Override Tier'}</span>
                            </button>
                          </div>
                        </div>

                        {/* ========================================================= */}
                        {/* 2. BACKEND TIER CARD */}
                        {/* ========================================================= */}
                        <div
                          style={{
                            padding: '16px',
                            backgroundColor: 'var(--background)',
                            border: effectiveBackend.isOverridden
                              ? '1px solid rgba(180, 83, 9, 0.4)'
                              : '1px solid var(--border)',
                            borderRadius: 'var(--radius-md)',
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between',
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <div
                                  style={{
                                    width: '28px',
                                    height: '28px',
                                    borderRadius: '6px',
                                    backgroundColor: 'var(--accent)',
                                    display: 'grid',
                                    placeItems: 'center',
                                  }}
                                >
                                  <Server size={15} color="var(--primary)" />
                                </div>
                                <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--foreground)' }}>
                                  ⚙️ Backend Tier
                                </span>
                              </div>
                              <span
                                style={{
                                  fontSize: '10px',
                                  padding: '2px 6px',
                                  borderRadius: 'var(--radius-full)',
                                  backgroundColor: effectiveBackend.isOverridden
                                    ? 'var(--warning-surface)'
                                    : (rawBackend ? 'var(--accent)' : 'var(--secondary)'),
                                  color: effectiveBackend.isOverridden
                                    ? 'var(--warning)'
                                    : (rawBackend ? 'var(--primary)' : 'var(--muted-foreground)'),
                                  fontWeight: 600,
                                }}
                              >
                                {effectiveBackend.isOverridden ? 'User Override' : (rawBackend ? 'Detected' : 'None detected')}
                              </span>
                            </div>

                            {/* View / Edit Mode */}
                            {editingTier === 'backend' ? (
                              <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Framework</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editBackendTech}
                                    onChange={(e) => setEditBackendTech(e.target.value)}
                                    placeholder="Spring Boot, FastAPI, Laravel, Express"
                                  />
                                </div>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Language / Runtime</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editBackendLang}
                                    onChange={(e) => setEditBackendLang(e.target.value)}
                                    placeholder="Java, Python, PHP, TypeScript, Go"
                                  />
                                </div>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Build Tool</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editBackendBuild}
                                    onChange={(e) => setEditBackendBuild(e.target.value)}
                                    placeholder="Maven, Gradle, Poetry, Composer"
                                  />
                                </div>
                                <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                                  <button
                                    type="button"
                                    className="button button-primary button-sm"
                                    onClick={() => applyTierEdit('backend')}
                                    style={{ flex: 1, height: '26px', fontSize: '11px' }}
                                  >
                                    Apply
                                  </button>
                                  <button
                                    type="button"
                                    className="button button-secondary button-sm"
                                    onClick={() => setEditingTier(null)}
                                    style={{ height: '26px', fontSize: '11px' }}
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div style={{ marginTop: '6px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Framework: </span>
                                  <strong style={{ color: 'var(--foreground)', fontSize: '13px' }}>
                                    {effectiveBackend.technology}
                                  </strong>
                                </div>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Language: </span>
                                  <span>{effectiveBackend.primary_language}</span>
                                </div>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Build Tool: </span>
                                  <span>{effectiveBackend.build_tool}</span>
                                </div>
                                {rawBackend?.evidence && rawBackend.evidence.length > 0 && (
                                  <div style={{ marginTop: '4px', fontSize: '10px', color: 'var(--muted-foreground)' }}>
                                    Evidence: {rawBackend.evidence[0].file}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>

                          <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                            {effectiveBackend.isOverridden && (
                              <button
                                type="button"
                                onClick={() => resetTier('backend')}
                                className="button button-secondary button-sm"
                                style={{ height: '24px', fontSize: '10px', padding: '0 8px' }}
                              >
                                Reset
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => startEditTier('backend')}
                              className="button button-secondary button-sm"
                              style={{ height: '24px', fontSize: '10px', padding: '0 8px' }}
                            >
                              <Edit2 size={10} />
                              <span>{effectiveBackend.isOverridden ? 'Edit Override' : 'Override Tier'}</span>
                            </button>
                          </div>
                        </div>

                        {/* ========================================================= */}
                        {/* 3. DATABASE & PERSISTENCE TIER CARD */}
                        {/* ========================================================= */}
                        <div
                          style={{
                            padding: '16px',
                            backgroundColor: 'var(--background)',
                            border: effectiveDb.isOverridden
                              ? '1px solid rgba(180, 83, 9, 0.4)'
                              : '1px solid var(--border)',
                            borderRadius: 'var(--radius-md)',
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'space-between',
                          }}
                        >
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <div
                                  style={{
                                    width: '28px',
                                    height: '28px',
                                    borderRadius: '6px',
                                    backgroundColor: 'var(--accent)',
                                    display: 'grid',
                                    placeItems: 'center',
                                  }}
                                >
                                  <Database size={15} color="var(--primary)" />
                                </div>
                                <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--foreground)' }}>
                                  🗄️ Database Tier
                                </span>
                              </div>
                              <span
                                style={{
                                  fontSize: '10px',
                                  padding: '2px 6px',
                                  borderRadius: 'var(--radius-full)',
                                  backgroundColor: effectiveDb.isOverridden
                                    ? 'var(--warning-surface)'
                                    : (rawDb ? 'var(--accent)' : 'var(--secondary)'),
                                  color: effectiveDb.isOverridden
                                    ? 'var(--warning)'
                                    : (rawDb ? 'var(--primary)' : 'var(--muted-foreground)'),
                                  fontWeight: 600,
                                }}
                              >
                                {effectiveDb.isOverridden ? 'User Override' : (rawDb ? 'Detected' : 'Stateless')}
                              </span>
                            </div>

                            {/* View / Edit Mode */}
                            {editingTier === 'database' ? (
                              <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Database Engine</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editDbEngine}
                                    onChange={(e) => setEditDbEngine(e.target.value)}
                                    placeholder="MySQL, PostgreSQL, SQLite, MongoDB"
                                  />
                                </div>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>ORM / Driver</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editDbDriver}
                                    onChange={(e) => setEditDbDriver(e.target.value)}
                                    placeholder="Hibernate, SQLAlchemy, Eloquent, Prisma"
                                  />
                                </div>
                                <div>
                                  <label style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>Migration Tool</label>
                                  <input
                                    type="text"
                                    className="field"
                                    value={editDbMigration}
                                    onChange={(e) => setEditDbMigration(e.target.value)}
                                    placeholder="Flyway, Liquibase, Alembic, Laravel Migrations"
                                  />
                                </div>
                                <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                                  <button
                                    type="button"
                                    className="button button-primary button-sm"
                                    onClick={() => applyTierEdit('database')}
                                    style={{ flex: 1, height: '26px', fontSize: '11px' }}
                                  >
                                    Apply
                                  </button>
                                  <button
                                    type="button"
                                    className="button button-secondary button-sm"
                                    onClick={() => setEditingTier(null)}
                                    style={{ height: '26px', fontSize: '11px' }}
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <div style={{ marginTop: '6px', fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '5px' }}>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Engine: </span>
                                  <strong style={{ color: 'var(--foreground)', fontSize: '13px' }}>
                                    {effectiveDb.engine}
                                  </strong>
                                </div>
                                {rawDb?.inferred_from && !effectiveDb.isOverridden && (
                                  <div>
                                    <span style={{ color: 'var(--muted-foreground)' }}>Inferred From: </span>
                                    <span
                                      style={{
                                        fontSize: '10px',
                                        padding: '1px 5px',
                                        borderRadius: '3px',
                                        backgroundColor: 'var(--secondary)',
                                        color: 'var(--muted-foreground)',
                                        fontFamily: 'var(--font-mono)',
                                      }}
                                    >
                                      {rawDb.inferred_from} ({Math.round(rawDb.confidence * 100)}%)
                                    </span>
                                  </div>
                                )}
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>ORM / Driver: </span>
                                  <span>{effectiveDb.orm_or_driver}</span>
                                </div>
                                <div>
                                  <span style={{ color: 'var(--muted-foreground)' }}>Migrations: </span>
                                  <span>{effectiveDb.migration_tool}</span>
                                </div>
                                {rawDb?.schema_artifacts && rawDb.schema_artifacts.length > 0 && (
                                  <div style={{ marginTop: '4px', fontSize: '10px', color: 'var(--muted-foreground)' }}>
                                    Artifacts: {rawDb.schema_artifacts[0]}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>

                          <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'flex-end', gap: '6px' }}>
                            {effectiveDb.isOverridden && (
                              <button
                                type="button"
                                onClick={() => resetTier('database')}
                                className="button button-secondary button-sm"
                                style={{ height: '24px', fontSize: '10px', padding: '0 8px' }}
                              >
                                Reset
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => startEditTier('database')}
                              className="button button-secondary button-sm"
                              style={{ height: '24px', fontSize: '10px', padding: '0 8px' }}
                            >
                              <Edit2 size={10} />
                              <span>{effectiveDb.isOverridden ? 'Edit Override' : 'Override Tier'}</span>
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Monorepo Sub-Components if detected */}
                      {detectedStack?.components && detectedStack.components.length > 1 && (
                        <div
                          style={{
                            padding: '10px 12px',
                            backgroundColor: 'var(--secondary)',
                            borderRadius: 'var(--radius-md)',
                            fontSize: '12px',
                            marginBottom: '14px',
                          }}
                        >
                          <strong style={{ display: 'block', marginBottom: '6px' }}>
                            📦 Monorepo Sub-Components ({detectedStack.components.length})
                          </strong>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                            {detectedStack.components.map((comp) => (
                              <div
                                key={comp.component_id}
                                style={{
                                  padding: '6px 10px',
                                  backgroundColor: 'var(--card)',
                                  border: '1px solid var(--border)',
                                  borderRadius: 'var(--radius-sm)',
                                  fontSize: '11px',
                                }}
                              >
                                <strong style={{ color: 'var(--primary)' }}>{comp.name || 'Root'}:</strong>{' '}
                                <span>
                                  {comp.primary_language} / {comp.framework} ({comp.build_tool})
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Canonical Contract Summary Strip */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '10px 14px',
                          backgroundColor: 'var(--muted)',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--border)',
                          flexWrap: 'wrap',
                          gap: '8px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--muted-foreground)' }}>
                            Effective Profile:
                          </span>
                          <code
                            style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: '12px',
                              fontWeight: 700,
                              color: 'var(--primary)',
                            }}
                          >
                            {effectiveBackend.technology} + {effectiveFrontend.technology} + {effectiveDb.engine}
                          </code>
                        </div>
                        {Object.keys(overrides).length > 0 && (
                          <span style={{ fontSize: '11px', color: 'var(--warning)', fontWeight: 600 }}>
                            ⚠️ User overrides will be preserved separately from automated scan findings.
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <small style={{ marginTop: '6px', display: 'block' }}>
                    Static preview executed inside an isolated OS temporary directory with hooks disabled. Fully customizable prior to launching autonomous agents.
                  </small>
                </div>
              </div>
            </div>

            {/* Step 2: Target Stack */}
            <div className="form-section">
              <h2>2. Target Architecture Stack</h2>
              <p>Phase 0 vertical slice canonical target architecture specification.</p>

              <div className="form-grid">
                <div className="form-field span-two">
                  <label>Target Framework & Runtime</label>
                  <input
                    type="text"
                    className="field"
                    value={targetStack}
                    disabled
                    style={{ backgroundColor: 'var(--secondary)' }}
                  />
                  <small>Locked for V1 vertical slice: TypeScript 5.x / Node.js 22 LTS / NestJS framework.</small>
                </div>

                <div className="form-field span-two">
                  <label>Architectural Constraints & Requirements</label>
                  <textarea
                    className="field"
                    rows={3}
                    value={constraints}
                    onChange={(e) => setConstraints(e.target.value)}
                  />
                  <small>Injected into the Architect and CodeWriter prompt contracts.</small>
                </div>
              </div>
            </div>

            {/* Step 3: Guardrails & Budgets */}
            <div className="form-section">
              <h2>3. Autonomous Agent Guardrails</h2>
              <p>Hard limits to prevent runaway spend or cyclic loop repair deadlocks.</p>

              <div className="form-grid">
                <div className="form-field">
                  <label>Autonomous Budget Limit ($ USD)</label>
                  <input
                    type="number"
                    className="field"
                    min={10}
                    max={1000}
                    value={budget}
                    onChange={(e) => setBudget(Number(e.target.value))}
                    required
                  />
                  <small>Execution pauses automatically if 100% budget reached.</small>
                </div>

                <div className="form-field">
                  <label>Max Inner-Loop Repair Retries</label>
                  <input
                    type="number"
                    className="field"
                    min={1}
                    max={5}
                    value={maxRepairAttempts}
                    onChange={(e) => setMaxRepairAttempts(Number(e.target.value))}
                    required
                  />
                  <small>Number of compile/test repair attempts per module (default: 3).</small>
                </div>
              </div>
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => onNavigate('/jobs')}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="button button-primary"
                disabled={loading}
              >
                {loading ? 'Starting Agents...' : 'Launch Modernization Job'}
                <ArrowRight size={14} />
              </button>
            </div>
          </div>

          {/* Aside Information Card */}
          <aside className="form-aside">
            <div style={{ position: 'sticky', top: '100px' }}>
              <div
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '20px',
                  backgroundColor: 'var(--card)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontWeight: 600,
                    marginBottom: '16px',
                    color: 'var(--foreground)',
                  }}
                >
                  <ShieldCheck size={18} color="var(--primary)" />
                  <span>Enforced Governance</span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontSize: '12px' }}>
                  <div>
                    <strong style={{ display: 'block', marginBottom: '2px' }}>Gate G1 (Feasibility):</strong>
                    <span style={{ color: 'var(--muted-foreground)' }}>
                      Human sign-off on capability gaps before code generation begins.
                    </span>
                  </div>

                  <div>
                    <strong style={{ display: 'block', marginBottom: '2px' }}>Gate G2 (Characterization):</strong>
                    <span style={{ color: 'var(--muted-foreground)' }}>
                      Approval of frozen legacy test suite and golden vectors.
                    </span>
                  </div>

                  <div>
                    <strong style={{ display: 'block', marginBottom: '2px' }}>Gate G3 (Blueprint):</strong>
                    <span style={{ color: 'var(--muted-foreground)' }}>
                      Module DAG review and wave conversion strategy.
                    </span>
                  </div>

                  <div>
                    <strong style={{ display: 'block', marginBottom: '2px' }}>Gate G4 (Delivery):</strong>
                    <span style={{ color: 'var(--muted-foreground)' }}>
                      Final equivalence verification and waiver approvals.
                    </span>
                  </div>
                </div>

                <div
                  style={{
                    marginTop: '20px',
                    paddingTop: '16px',
                    borderTop: '1px solid var(--border)',
                    fontSize: '11px',
                    color: 'var(--muted-foreground)',
                  }}
                >
                  Append-only audit trail recorded for all agent steps and human decisions.
                </div>
              </div>
            </div>
          </aside>
        </div>
      </form>
    </div>
  );
};
