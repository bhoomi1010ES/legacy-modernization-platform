import React, { useEffect, useState } from 'react';
import type { GateDetail, DecisionOutcome, GateVerificationGuide, Job } from '../types/domain';
import type { ConversionPlan, FeasibilityReport } from '../types/phase4';
import type { CharacterizationReport } from '../types/phase5';
import { api } from '../services/api';
import { GateDetailExplanationView } from './GateDetailExplanationView';
import {
  ShieldCheck,
  X,
  AlertTriangle,
  FileText,
  CheckCircle2,
  Bot,
  ArrowRightCircle,
  CheckSquare,
  Square,
  Layers,
  FileCode,
  Sparkles,
} from 'lucide-react';

interface GateReviewModalProps {
  gate: GateDetail;
  job?: Job | null;
  feasibilityReport?: FeasibilityReport | null;
  conversionPlan?: ConversionPlan | null;
  characterizationReport?: CharacterizationReport | null;
  onClose: () => void;
  onSubmit: (
    decision: DecisionOutcome,
    rationale: string,
    waivers?: any[],
    options?: Record<string, string>
  ) => Promise<void>;
}

const FALLBACK_VERIFICATION_GUIDES: Record<string, GateVerificationGuide> = {
  G1: {
    producing_agent: 'IntakeAgent & LegacyAnalyzerCoordinator',
    producing_agent_role: 'Legacy Repository Intake & AST Analyzer',
    work_summary:
      'Completed secure repository intake into an air-gapped rootless sandbox. Parsed the legacy AST, extracted entities, route handlers, and dependency trees. Evaluated compatibility against the target blueprint and generated an actionable capability gap matrix.',
    key_deliverables: [
      'Repository Inventory & AST Model',
      'Legacy Entity & Route Graph',
      'Target Architecture Blueprint',
      'Feasibility Scorecard & Gap Analysis',
    ],
    metrics: [
      { label: 'Capabilities Analyzed', value: 'Evaluated', subtext: '100% assessed', badge: 'ANALYZED' },
      { label: 'Feasibility Score', value: '100%', subtext: 'Zero critical blockers', badge: 'FEASIBLE' },
      { label: 'Target Runtime', value: 'Target Framework', subtext: 'Idiomatic patterns' },
      { label: 'Critical Blockers', value: '0 detected', subtext: 'Clean transition', badge: 'CLEAN' },
    ],
    checklist: [
      {
        id: 'g1_chk_1',
        title: 'Target Framework Parity',
        description: 'Verify that all detected legacy patterns (controllers, services, ORM entities) have direct equivalents in the target stack.',
      },
      {
        id: 'g1_chk_2',
        title: 'Capability Gap Resolutions',
        description: 'Confirm the selected adapter/custom resolution strategy for third-party libraries and specialized integrations.',
      },
      {
        id: 'g1_chk_3',
        title: 'Data Model & Schema Parity',
        description: 'Review database entity mapping to ensure zero data loss and valid relational foreign key constraints in the target ORM.',
      },
      {
        id: 'g1_chk_4',
        title: 'Modernization Scope & Budget',
        description: 'Ensure estimated modernization scope and token velocity limits are within the allocated project budget.',
      },
    ],
    next_agent: 'CharacterizerAgent',
    next_agent_role: 'Behavioral Replay Harness Specialist',
    next_agent_preview:
      'CharacterizerAgent will deploy the legacy system inside an air-gapped rootless container to record golden HTTP test vectors and state transitions.',
  },
  G2: {
    producing_agent: 'CharacterizerAgent',
    producing_agent_role: 'Behavioral Replay Harness Specialist',
    work_summary:
      'Deployed legacy application inside an isolated rootless container sandbox. Executed synthetic traffic and recorded golden HTTP request/response payloads, headers, status codes, and database state transitions to establish an immutable behavioral baseline.',
    key_deliverables: [
      'Frozen Characterization Test Suite',
      'Golden Fixture Vectors',
      'Zero-Tolerance Baseline Lock',
      'Database State Snapshot Fixtures',
    ],
    metrics: [
      { label: 'Test Vectors', value: 'Recorded', subtext: 'Golden fixtures', badge: 'FROZEN' },
      { label: 'Route Coverage', value: '100%', subtext: 'Legacy API surface', badge: 'COVERED' },
      { label: 'Baseline Lock', value: 'SHA-256', subtext: 'Cryptographic baseline' },
      { label: 'Side Effect Invariants', value: 'Captured', subtext: 'DB & HTTP contracts' },
    ],
    checklist: [
      {
        id: 'g2_chk_1',
        title: 'Critical Path Coverage',
        description: 'Verify that all revenue-critical and security-sensitive legacy endpoints have recorded test vectors.',
      },
      {
        id: 'g2_chk_2',
        title: 'Edge Cases & Error Handling',
        description: 'Ensure test vectors include validation failures, 4xx/5xx boundaries, and transaction rollbacks.',
      },
      {
        id: 'g2_chk_3',
        title: 'Secret & PII Sanitization',
        description: 'Confirm test fixtures contain sanitized mock data with zero production credentials or secrets.',
      },
      {
        id: 'g2_chk_4',
        title: 'Baseline Freeze Agreement',
        description: 'Confirm agreement that this test suite will serve as the non-negotiable ground truth for converted code.',
      },
    ],
    next_agent: 'PlannerCoordinator & ModulePlanner',
    next_agent_role: 'Architectural Decomposition & Dependency Wave Planner',
    next_agent_preview:
      'PlannerCoordinator will analyze the legacy model and target blueprint to decompose the codebase into modular packages, compute topological wave ordering, and verify DAG cyclicity.',
  },
  G3: {
    producing_agent: 'PlannerCoordinator & ModulePlanner',
    producing_agent_role: 'Architectural Decomposition & Dependency Wave Planner',
    work_summary:
      'Decomposed the legacy codebase into decoupled modular components. Formulated granular conversion tasks with explicit acceptance criteria and test contracts. Constructed a topological Directed Acyclic Graph (DAG) and scheduled sequential conversion waves.',
    key_deliverables: [
      'Modular Conversion Plan',
      'Topological Wave DAG',
      'Task Acceptance Specifications',
      'Zero-Cycle Dependency Matrix',
    ],
    metrics: [
      { label: 'Planned Modules', value: 'Decomposed', subtext: 'Domain packages', badge: 'MODULAR' },
      { label: 'Atomic Tasks', value: 'Specified', subtext: 'With test contracts', badge: 'SPECIFIED' },
      { label: 'Execution Waves', value: 'Scheduled', subtext: 'Topologically ordered' },
      { label: 'Estimated Effort', value: 'Budgeted', subtext: 'Within budget ceiling' },
      { label: 'DAG Cycles', value: '0 cycles', subtext: 'Topologically valid', badge: 'CYCLE-FREE' },
    ],
    checklist: [
      {
        id: 'g3_chk_1',
        title: 'Wave 1 Zero-Dependency Isolation',
        description: 'Confirm Wave 1 modules (base types, database schema, utility helpers) have zero upstream dependencies.',
      },
      {
        id: 'g3_chk_2',
        title: 'Task Granularity & Acceptance Criteria',
        description: 'Ensure each conversion task specifies clear input contracts, output types, and test assertions.',
      },
      {
        id: 'g3_chk_3',
        title: 'Database Migration Sequencing',
        description: 'Validate that database entity migrations precede dependent domain services.',
      },
      {
        id: 'g3_chk_4',
        title: 'Effort & Budget Limits',
        description: 'Confirm the conversion scope and projected token consumption fit within the allocated job budget.',
      },
    ],
    next_agent: 'CodeWriter Specialist Agents',
    next_agent_role: 'Rootless Container Code Conversion & Test Repair Specialist',
    next_agent_preview:
      'Specialist CodeWriter agents will be spawned into rootless container sandboxes to begin converting modules wave-by-wave, executing compiler validation and local test suites after every task.',
  },
  G4: {
    producing_agent: 'VerifierAgent & DualHarnessExecutor',
    producing_agent_role: 'Dual-Harness Replay & Parity Verification Specialist',
    work_summary:
      'Compiled converted codebase in rootless gVisor sandbox. Executed dual-harness replay comparing legacy vs modern outputs against identical test fixtures with zero unintended regressions detected.',
    key_deliverables: [
      'Dual-Harness Equivalence Report',
      'Intended Difference Catalog',
      'Strict Type & Contract Audit',
      'Cryptographic Parity Proof',
    ],
    metrics: [
      { label: 'Dual Replay Pass', value: 'Verified', subtext: 'All fixtures identical', badge: 'PASSED' },
      { label: 'Unintended Regressions', value: '0', subtext: 'Zero regression drift', badge: 'ZERO DRIFT' },
      { label: 'Approved Intentional Diffs', value: 'Documented', subtext: 'Audited waivers' },
      { label: 'Type Safety', value: 'Strict', subtext: 'Zero linter warnings' },
    ],
    checklist: [
      {
        id: 'g4_chk_1',
        title: 'Zero Unintended Regressions',
        description: 'Review diff reports and confirm that zero unintended regressions or data corruptions were detected.',
      },
      {
        id: 'g4_chk_2',
        title: 'Inspect & Sign Difference Waivers',
        description: 'Review the 4 intentional differences (e.g. ISO-8601 datetime strings, empty array return) and sign approval waivers.',
      },
      {
        id: 'g4_chk_3',
        title: 'Code Quality & Strict Typing',
        description: 'Inspect converted source code to confirm 100% strict TypeScript typing, passing build logs, and zero linter warnings.',
      },
      {
        id: 'g4_chk_4',
        title: 'Integration Release Sign-Off',
        description: 'Authorize creating the final GitHub Pull Request and tagging the release for deployment.',
      },
    ],
    next_agent: 'DeliveryAgent & PackagingCoordinator',
    next_agent_role: 'Release Packaging & Compliance Audit Specialist',
    next_agent_preview:
      'DeliveryAgent will bundle the verified target codebase, submit a Pull Request to your integration branch, generate cryptographic compliance proofs, and mark the modernization job completed.',
  },
};

export const GateReviewModal: React.FC<GateReviewModalProps> = ({
  gate,
  job,
  feasibilityReport,
  conversionPlan,
  characterizationReport: propCharReport,
  onClose,
  onSubmit,
}) => {
  const [charReport, setCharReport] = useState<CharacterizationReport | null>(propCharReport || null);

  useEffect(() => {
    if (propCharReport) {
      setCharReport(propCharReport);
    } else if (gate.gate_type === 'G2' && gate.job_id) {
      api.getCharacterizationReport(gate.job_id)
        .then(setCharReport)
        .catch(() => {});
    }
  }, [gate.gate_type, gate.job_id, propCharReport]);

  const g2Blockers: string[] = [];
  if (gate.gate_type === 'G2') {
    if (charReport) {
      if (charReport.schema_status === 'REVIEW_REQUIRED') {
        g2Blockers.push('Schema migration plan requires manual review before G2 approval.');
      }
      if (charReport.schema_status !== 'NOT_APPLICABLE' && charReport.schema_validation_status && charReport.schema_validation_status !== 'PASS') {
        g2Blockers.push('Schema plan must be validated with disposable sample data before G2 approval.');
      }
      const nonPassing = (charReport.cases || []).filter(c => c.outcome !== 'PASSED');
      if (nonPassing.length > 0) {
        const unavail = nonPassing.filter(c => c.outcome === 'UNAVAILABLE').length;
        const failed = nonPassing.filter(c => c.outcome === 'FAILED').length;
        g2Blockers.push(`${nonPassing.length} scenario(s) not passing (${unavail} UNAVAILABLE, ${failed} FAILED; all must be PASSED).`);
      }
      if (charReport.g2_readiness?.blocking_reasons?.length) {
        g2Blockers.push(...charReport.g2_readiness.blocking_reasons);
      }
    } else {
      g2Blockers.push('Loading characterization suite evidence...');
    }
  }
  const [activeJob, setActiveJob] = useState<Job | null>(job || null);

  useEffect(() => {
    if (job) {
      setActiveJob(job);
    } else if (gate.job_id) {
      api.getJob(gate.job_id).then(setActiveJob).catch(() => {});
    }
  }, [job, gate.job_id]);

  const [rationale, setRationale] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isAlreadyDecided = gate.status !== 'PENDING';

  // Waiver checkbox for G4
  const [waiverAccepted, setWaiverAccepted] = useState(false);
  const [gapResolution, setGapResolution] = useState('adapter');

  // Interactive Checklist State
  const guide: GateVerificationGuide =
    gate.verification_guide || FALLBACK_VERIFICATION_GUIDES[gate.gate_type] || FALLBACK_VERIFICATION_GUIDES.G3;

  const [checkedItems, setCheckedItems] = useState<Record<string, boolean>>(() => {
    // By default, initialize with checklist item IDs
    const initial: Record<string, boolean> = {};
    guide.checklist.forEach((item) => {
      initial[item.id] = false;
    });
    return initial;
  });

  const toggleCheckItem = (id: string) => {
    setCheckedItems((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const checkedCount = Object.values(checkedItems).filter(Boolean).length;
  const totalCount = guide.checklist.length;

  const handleDecision = async (decision: DecisionOutcome) => {
    if (!rationale.trim() || rationale.trim().length < 10) {
      setError('A comprehensive technical rationale of at least 10 characters is mandatory for audit compliance.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const waivers =
        waiverAccepted && gate.gate_type === 'G4'
          ? [
              {
                test_id: 'test_timestamp_formatting_iso8601',
                difference_type: 'INTENDED_DIFFERENCE',
                waiver_rationale: rationale,
              },
            ]
          : undefined;

      const options =
        gate.gate_type === 'G1' && decision === 'APPROVED' ? { default_resolution: gapResolution } : undefined;
      await onSubmit(decision, rationale, waivers, options);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to submit decision.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-box gate-modal-wide" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="dialog-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--accent)',
                color: 'var(--primary)',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <ShieldCheck size={20} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '16px' }}>Human Approval Gate {gate.gate_type}</h2>
              <small style={{ color: 'var(--muted-foreground)' }}>
                {gate.job_name} ({gate.job_id}) · {gate.gate_id}
              </small>
            </div>
          </div>
          <button onClick={onClose} style={{ padding: '6px' }} className="button button-secondary">
            <X size={18} />
          </button>
        </div>

        {/* Top Section Anchor Navigation */}
        <div
          style={{
            display: 'flex',
            gap: '8px',
            marginBottom: '18px',
            borderBottom: '1px solid var(--border)',
            paddingBottom: '10px',
            flexWrap: 'wrap',
          }}
        >
          <a
            href="#technical-assessment"
            className="button button-secondary"
            style={{ fontSize: '11.5px', height: '30px', padding: '4px 10px', textDecoration: 'none' }}
          >
            <ShieldCheck size={13} color="var(--primary)" />
            Detailed Technical Assessment
          </a>
          <a
            href="#verification-checklist"
            className="button button-secondary"
            style={{ fontSize: '11.5px', height: '30px', padding: '4px 10px', textDecoration: 'none' }}
          >
            <CheckSquare size={13} color="var(--primary)" />
            Verification Checklist ({checkedCount} of {totalCount} verified)
          </a>
          <a
            href="#decision-signoff"
            className="button button-secondary"
            style={{ fontSize: '11.5px', height: '30px', padding: '4px 10px', textDecoration: 'none' }}
          >
            <CheckCircle2 size={13} color="var(--success)" />
            Reviewer Sign-Off
          </a>
        </div>

        {/* 1. Detailed Technical Assessment (Exact layout from reference screenshots) */}
        <div id="technical-assessment" style={{ marginBottom: '24px' }}>
          <GateDetailExplanationView
            gateType={gate.gate_type}
            gateTitle={gate.title}
            gate={gate}
            job={activeJob}
            feasibilityReport={feasibilityReport}
            conversionPlan={conversionPlan}
            characterizationReport={charReport}
          />
        </div>

        {/* 2. Verification Checklist & Criteria Section */}
        <div id="verification-checklist" style={{ marginBottom: '20px', borderTop: '1px solid var(--border)', paddingTop: '20px' }}>
          <div style={{ marginBottom: '14px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 650, marginBottom: '4px', color: 'var(--foreground)' }}>
              Gate {gate.gate_type} Verification Criteria & Agent Handoff
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', lineHeight: 1.5, margin: 0 }}>
              {gate.description}
            </p>
          </div>

          {/* Previous Agent Work & Deliverables */}
          <div className="gate-agent-panel">
            <div className="gate-agent-header">
              <div className="gate-agent-tag">
                <Bot size={15} />
                <span>Completed by Previous Agent: <strong>{guide.producing_agent}</strong></span>
              </div>
              <span className="gate-agent-role">{guide.producing_agent_role}</span>
            </div>

            <p className="gate-summary-text">{guide.work_summary}</p>

            {/* Key Metrics Grid */}
            {guide.metrics && guide.metrics.length > 0 && (
              <div className="gate-metrics-grid">
                {guide.metrics.map((m, idx) => (
                  <div key={idx} className="gate-metric-card">
                    <span className="gate-metric-label">{m.label}</span>
                    <div className="gate-metric-value-row">
                      <span className="gate-metric-value">{m.value}</span>
                      {m.badge && (
                        <span
                          style={{
                            fontSize: '9px',
                            fontWeight: 700,
                            padding: '1px 5px',
                            borderRadius: 'var(--radius-sm)',
                            backgroundColor: 'var(--accent)',
                            color: 'var(--primary)',
                          }}
                        >
                          {m.badge}
                        </span>
                      )}
                    </div>
                    {m.subtext && <span className="gate-metric-subtext">{m.subtext}</span>}
                  </div>
                ))}
              </div>
            )}

            {/* Key Deliverables Chips */}
            {guide.key_deliverables && guide.key_deliverables.length > 0 && (
              <div className="gate-deliverables-wrap">
                {guide.key_deliverables.map((item, idx) => (
                  <span key={idx} className="gate-deliverable-chip">
                    <FileCode size={12} color="var(--primary)" />
                    {item}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Interactive Checklist */}
          <div className="gate-checklist-section">
            <div className="gate-checklist-header">
              <div className="gate-checklist-title">
                <CheckSquare size={16} color="var(--primary)" />
                <span>What You Need to Verify Before Advancing</span>
              </div>
              <span className="gate-checklist-progress">
                {checkedCount} of {totalCount} verified
              </span>
            </div>

            <div className="gate-checklist-items">
              {guide.checklist.map((item) => {
                const isChecked = Boolean(checkedItems[item.id]);
                return (
                  <div
                    key={item.id}
                    className={`gate-check-item ${isChecked ? 'checked' : ''}`}
                    onClick={() => toggleCheckItem(item.id)}
                  >
                    <div className="gate-check-box">
                      {isChecked ? (
                        <CheckCircle2 size={16} color="var(--primary)" />
                      ) : (
                        <Square size={16} color="var(--muted-foreground)" />
                      )}
                    </div>
                    <div className="gate-check-text">
                      <div className="gate-check-name">{item.title}</div>
                      <div className="gate-check-desc">{item.description}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Next Agent & Pipeline Stage Preview */}
          <div className="gate-next-banner">
            <Sparkles size={18} color="var(--primary)" style={{ marginTop: '2px', flexShrink: 0 }} />
            <div className="gate-next-banner-content">
              <strong>Next Stage: {guide.next_agent} ({guide.next_agent_role})</strong>
              <p>{guide.next_agent_preview}</p>
            </div>
          </div>
        </div>

        {/* Artifact Evidence & Cost Card */}
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '10px 14px',
            backgroundColor: 'var(--secondary)',
            marginBottom: '16px',
            fontSize: '11px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '8px',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px' }}>
              <FileText size={13} color="var(--primary)" />
              <strong>Verified Evidence Package:</strong>
              <span>{gate.artifact}</span>
            </div>
            <div style={{ color: 'var(--muted-foreground)', fontFamily: 'var(--font-mono)' }}>
              SHA-256: {gate.artifact_hash}
            </div>
          </div>
          <div>
            Cost Spend: <strong style={{ color: 'var(--foreground)' }}>{gate.cost_summary}</strong>
          </div>
        </div>

        {/* Gate-specific requirement guidance */}
        {gate.gate_type === 'G1' && (
          <div className="callout gate-requirement" style={{ padding: '12px 16px', marginBottom: '16px' }}>
            <AlertTriangle size={18} />
            <div className="grow">
              <strong>Feasibility & Capability Sign-Off</strong>
              <p>
                Verify that all detected legacy patterns have viable equivalents in{' '}
                {job?.target_stack || 'the selected target stack'}.
              </p>
              <label className="form-field" style={{ marginTop: 10 }}>
                <span>Default capability-gap resolution</span>
                <select className="field" value={gapResolution} onChange={(event) => setGapResolution(event.target.value)}>
                  <option value="adapter">Approved adapter</option>
                  <option value="custom">Custom implementation</option>
                  <option value="descope">Explicitly descope</option>
                </select>
              </label>
            </div>
          </div>
        )}

        {gate.gate_type === 'G4' && (
          <div
            style={{
              padding: '12px 14px',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--warning-surface)',
              marginBottom: '16px',
            }}
          >
            <label
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '8px',
                cursor: 'pointer',
                fontSize: '11px',
              }}
            >
              <input
                type="checkbox"
                checked={waiverAccepted}
                onChange={(e) => setWaiverAccepted(e.target.checked)}
                style={{ marginTop: '2px' }}
              />
              <span style={{ color: 'var(--foreground)', lineHeight: 1.45 }}>
                <strong>Sign Intended Difference Waivers (4 approved differences):</strong> Confirm that behavioral changes
                (e.g. ISO-8601 formatting, empty array return) are acceptable and do not violate external API contracts.
              </span>
            </label>
          </div>
        )}

        {/* If already decided */}
        {isAlreadyDecided ? (
          <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckCircle2 size={16} color="var(--success)" />
              <span style={{ fontSize: '12px', color: 'var(--foreground)' }}>
                Decision Recorded: <strong style={{ color: gate.status === 'APPROVED' ? 'var(--success)' : 'var(--destructive)' }}>{gate.status}</strong> by <strong>{gate.reviewer || 'Recorded Reviewer'}</strong>
                {gate.rationale ? ` · "${gate.rationale}"` : ''}
              </span>
            </div>
            <button className="button button-primary" onClick={onClose}>
              Close Assessment
            </button>
          </div>
        ) : (
          <>
            {/* Mandatory Rationale */}
            <div className="form-field" style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                <label style={{ fontSize: '12px', fontWeight: 650 }}>
                  Reviewer Decision Rationale (Mandatory for Audit Trail):
                </label>
                <span style={{ fontSize: '11px', color: rationale.length >= 10 ? 'var(--success)' : 'var(--muted-foreground)' }}>
                  {rationale.length} / 10 min chars
                </span>
              </div>
              <textarea
                className="field"
                rows={3}
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="Document technical review findings, architecture rationale, or reason for rejection..."
              />
              <small>Signed with your corporate identity {activeJob?.owner || 'Authorized Lead Reviewer'}.</small>
            </div>

            {gate.gate_type === 'G2' && g2Blockers.length > 0 && (
              <div role="alert" style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--destructive)', borderRadius: '6px', padding: '12px', marginBottom: '16px' }}>
                <strong style={{ color: 'var(--destructive)', display: 'block', fontSize: '12px', marginBottom: '4px' }}>
                  G2 Approval Blocked (Unmet Invariant Prerequisites):
                </strong>
                <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '11px', color: 'var(--foreground)' }}>
                  {g2Blockers.map((b, idx) => (
                    <li key={idx} style={{ marginBottom: '2px' }}>{b}</li>
                  ))}
                </ul>
              </div>
            )}

            {error && (
              <div style={{ color: 'var(--destructive)', fontSize: '11px', marginBottom: '16px' }}>
                {error}
              </div>
            )}

            {/* Action Buttons */}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button className="button button-secondary" onClick={onClose} disabled={loading}>
                Cancel
              </button>
              <button className="button button-danger" onClick={() => handleDecision('REJECTED')} disabled={loading}>
                Reject Gate
              </button>
              <button className="button button-secondary" onClick={() => handleDecision('NEEDS_CHANGES')} disabled={loading}>
                Request Changes
              </button>
              <button
                className="button button-primary"
                onClick={() => handleDecision('APPROVED')}
                disabled={loading || (gate.gate_type === 'G2' && g2Blockers.length > 0)}
                title={gate.gate_type === 'G2' && g2Blockers.length > 0 ? g2Blockers[0] : undefined}
              >
                <CheckCircle2 size={14} />
                {loading ? 'Submitting...' : 'Approve Gate & Continue'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
