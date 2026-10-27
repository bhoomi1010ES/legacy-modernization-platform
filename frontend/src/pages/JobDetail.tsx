import React, { useState, useEffect } from 'react';
import type { Job, GateDetail, Artifact, AgentRun, WorkflowEvent, WorkflowState } from '../types/domain';
import type {
  RepositorySnapshot,
  RepositoryInventory,
  LegacyModel,
  FeasibilityReport,
  FeasibilityCapability,
  TargetBlueprint,
  ConversionPlan,
} from '../types/phase4';
import { StatusBadge } from '../components/StatusBadge';
import { PipelineProgress } from '../components/PipelineProgress';
import { WorkflowProgress } from '../components/WorkflowProgress';
import { GateReviewModal } from '../components/GateReviewModal';
import { InventoryBrowser } from '../components/phase4/InventoryBrowser';
import { FeasibilityView } from '../components/phase4/FeasibilityView';
import { BlueprintView } from '../components/phase4/BlueprintView';
import { ConversionPlanView } from '../components/phase4/ConversionPlanView';
import { GateDetailExplanationView } from '../components/GateDetailExplanationView';
import { api } from '../services/api';
import {
  Layers,
  GitBranch,
  Play,
  Pause,
  XCircle,
  ShieldAlert,
  ExternalLink,
  Cpu,
  FileText,
  CheckCircle2,
  Clock,
  ArrowRight,
  FolderTree,
  Boxes,
} from 'lucide-react';

interface JobDetailProps {
  jobId: string;
  onNavigate: (path: string) => void;
  onGateDecision: (gateId: string, decision: any, rationale: string, waivers?: any[], options?: Record<string, string>) => Promise<void>;
}

export const JobDetail: React.FC<JobDetailProps> = ({ jobId, onNavigate, onGateDecision }) => {
  const [job, setJob] = useState<Job | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'inventory' | 'feasibility' | 'blueprint' | 'planner' | 'tests' | 'verification' | 'agents'>('overview');
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [agents, setAgents] = useState<AgentRun[]>([]);
  const [activeGate, setActiveGate] = useState<GateDetail | null>(null);
  const [gates, setGates] = useState<GateDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [workflowEvents, setWorkflowEvents] = useState<WorkflowEvent[]>([]);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  // Phase 4 states
  const [repositoryData, setRepositoryData] = useState<{ snapshot: RepositorySnapshot; inventory: RepositoryInventory } | null>(null);
  const [legacyModel, setLegacyModel] = useState<LegacyModel | null>(null);
  const [feasibilityReport, setFeasibilityReport] = useState<FeasibilityReport | null>(null);
  const [gapsRequiringG1, setGapsRequiringG1] = useState<FeasibilityCapability[]>([]);
  const [targetBlueprint, setTargetBlueprint] = useState<TargetBlueprint | null>(null);
  const [conversionPlan, setConversionPlan] = useState<ConversionPlan | null>(null);

  useEffect(() => {
    loadJobData();
  }, [jobId]);

  const loadJobData = async () => {
    try {
      setLoading(true);
      const j = await api.getJob(jobId);
      setJob(j);

      const [
        workflowResult,
        eventsResult,
        artifactResult,
        agentResult,
        gateResult,
        repoResult,
        analysisResult,
        feasResult,
        bpResult,
        planResult,
      ] = await Promise.allSettled([
        api.getWorkflow(jobId),
        api.getWorkflowEvents(jobId),
        api.getArtifacts(jobId),
        api.getAgents(jobId),
        api.getAllGates(jobId),
        api.getRepository(jobId),
        api.getAnalysis(jobId),
        api.getFeasibility(jobId),
        api.getBlueprint(jobId),
        api.getConversionPlan(jobId),
      ]);

      setWorkflow(workflowResult.status === 'fulfilled' ? workflowResult.value : null);
      setWorkflowEvents(eventsResult.status === 'fulfilled' ? eventsResult.value : []);
      setArtifacts(artifactResult.status === 'fulfilled' ? artifactResult.value : []);
      setAgents(agentResult.status === 'fulfilled' ? agentResult.value : []);
      const fetchedGates = gateResult.status === 'fulfilled' ? gateResult.value : [];
      setGates(fetchedGates);
      const jobGate = fetchedGates.find((g) => g.job_id === jobId && g.status === 'PENDING');
      setActiveGate(jobGate || null);

      if (repoResult.status === 'fulfilled') setRepositoryData(repoResult.value);
      if (analysisResult.status === 'fulfilled') setLegacyModel(analysisResult.value.legacy_model);
      if (feasResult.status === 'fulfilled') {
        setFeasibilityReport(feasResult.value.feasibility_report);
        setGapsRequiringG1(feasResult.value.gaps_requiring_g1 || []);
      }
      if (bpResult.status === 'fulfilled') setTargetBlueprint(bpResult.value.target_blueprint);
      if (planResult.status === 'fulfilled') setConversionPlan(planResult.value.conversion_plan);
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    if (!job) return;
    try { setActionBusy(true); setActionError(''); await api.pauseJob(job.job_id); await loadJobData(); }
    catch (error) { setActionError(error instanceof Error ? error.message : 'Unable to pause workflow.'); }
    finally { setActionBusy(false); }
  };

  const handleResume = async () => {
    if (!job) return;
    try { setActionBusy(true); setActionError(''); await api.resumeJob(job.job_id); await loadJobData(); }
    catch (error) { setActionError(error instanceof Error ? error.message : 'Unable to resume workflow.'); }
    finally { setActionBusy(false); }
  };

  const handleCancel = async () => {
    if (!job || !confirm('Are you sure you want to cancel this modernization job?')) return;
    try { setActionBusy(true); setActionError(''); await api.cancelJob(job.job_id); await loadJobData(); }
    catch (error) { setActionError(error instanceof Error ? error.message : 'Unable to cancel workflow.'); }
    finally { setActionBusy(false); }
  };

  if (loading || !job) {
    return <div style={{ padding: '40px', textAlign: 'center' }}>Loading job details...</div>;
  }

  return (
    <div>
      {/* Top Header */}
      <div className="page-heading">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <h1>{job.name}</h1>
            <StatusBadge status={job.status} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '11px', color: 'var(--muted-foreground)' }}>
            <span>Job ID: <strong style={{ color: 'var(--foreground)' }}>{job.job_id}</strong></span>
            <span>•</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <GitBranch size={12} />
              {job.source_repository} ({job.source_revision})
            </span>
            {job.integration_branch && (
              <>
                <span>•</span>
                <span>Branch: <strong style={{ color: 'var(--primary)' }}>{job.integration_branch}</strong></span>
              </>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="heading-actions">
          {activeGate && (activeGate.allowed_actions === undefined || activeGate.allowed_actions.length > 0) && (
            <button
              className="button button-primary"
              onClick={() => setActiveGate(activeGate)}
            >
              <ShieldAlert size={14} />
              <span>Review Gate {activeGate.gate_type}</span>
            </button>
          )}

          {workflow?.allowed_actions.includes('pause') && (
            <button className="button button-secondary" onClick={handlePause} disabled={actionBusy}>
              <Pause size={14} />
              <span>Pause Job</span>
            </button>
          )}

          {workflow?.allowed_actions.includes('resume') && (
            <button className="button button-secondary" onClick={handleResume} disabled={actionBusy}>
              <Play size={14} />
              <span>Resume Job</span>
            </button>
          )}

          {(workflow?.allowed_actions.includes('cancel') ?? (job.status !== 'COMPLETED' && job.status !== 'CANCELLED')) && (
            <button className="button button-secondary" onClick={handleCancel} disabled={actionBusy}>
              <XCircle size={14} />
              <span>Cancel</span>
            </button>
          )}
        </div>
      </div>

      {actionError && <div className="safe-error"><ShieldAlert size={16} /><div><strong>Workflow action failed</strong><span>{actionError}</span></div></div>}
      {workflow ? <WorkflowProgress workflow={workflow} events={workflowEvents} /> : <PipelineProgress status={job.status} />}

      {/* Multi-Tab Navigation */}
      <div className="tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Job Overview
        </button>
        <button
          className={`tab ${activeTab === 'inventory' ? 'active' : ''}`}
          onClick={() => setActiveTab('inventory')}
        >
          Repository Inventory
        </button>
        <button
          className={`tab ${activeTab === 'feasibility' ? 'active' : ''}`}
          onClick={() => setActiveTab('feasibility')}
        >
          Target Feasibility (Gate G1)
        </button>
        <button
          className={`tab ${activeTab === 'tests' ? 'active' : ''}`}
          onClick={() => setActiveTab('tests')}
        >
          Characterization Suite (Gate G2)
        </button>
        <button
          className={`tab ${activeTab === 'blueprint' ? 'active' : ''}`}
          onClick={() => setActiveTab('blueprint')}
        >
          Target Blueprint
        </button>
        <button
          className={`tab ${activeTab === 'planner' ? 'active' : ''}`}
          onClick={() => setActiveTab('planner')}
        >
          Conversion Plan & DAG (Gate G3)
        </button>
        <button
          className={`tab ${activeTab === 'verification' ? 'active' : ''}`}
          onClick={() => setActiveTab('verification')}
        >
          Verification & Drift (Gate G4)
        </button>
        <button
          className={`tab ${activeTab === 'agents' ? 'active' : ''}`}
          onClick={() => setActiveTab('agents')}
        >
          Active Specialist Agents ({agents.length})
        </button>
      </div>

      {/* Tab 1: Overview */}
      {activeTab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
          <div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '20px', backgroundColor: 'var(--card)', marginBottom: '20px' }}>
              <h2 style={{ fontSize: '15px', fontWeight: 650, marginBottom: '14px' }}>Modernization Stack Coordinates</h2>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Source Stack:</span>
                  <div style={{ fontWeight: 600, marginTop: '4px' }}>{job.source_stack}</div>
                </div>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Target Stack:</span>
                  <div style={{ fontWeight: 600, color: 'var(--primary)', marginTop: '4px' }}>{job.target_stack}</div>
                </div>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Discovered Modules:</span>
                  <div style={{ fontWeight: 600, marginTop: '4px' }}>{legacyModel?.modules.length ?? job.modules} domain packages</div>
                </div>
                <div>
                  <span style={{ color: 'var(--muted-foreground)' }}>Max Inner-Loop Retries:</span>
                  <div style={{ fontWeight: 600, marginTop: '4px' }}>{job.max_repair_attempts} attempts / module</div>
                </div>
              </div>
            </div>

            {/* Generated Artifacts Table */}
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', backgroundColor: 'var(--secondary)', borderBottom: '1px solid var(--border)', fontWeight: 650, fontSize: '12px' }}>
                Verified Deliverable Artifacts ({artifacts.length})
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Type & Version</th>
                    <th>SHA-256 Checksum</th>
                    <th>Producing Agent</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {artifacts.map((a) => (
                    <tr key={a.artifact_id}>
                      <td>
                        <strong>{a.artifact_type}</strong> v{a.version}
                      </td>
                      <td>
                        <code style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}>
                          {a.content_hash.substring(0, 18)}...
                        </code>
                      </td>
                      <td>{a.producing_agent}</td>
                      <td>{new Date(a.created_at).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Right Column: Spend & Guardrails */}
          <div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '20px', backgroundColor: 'var(--card)' }}>
              <h2 style={{ fontSize: '15px', fontWeight: 650, marginBottom: '14px' }}>Autonomous Budget</h2>
              <div style={{ fontSize: '24px', fontWeight: 700, marginBottom: '4px' }}>
                ₹{job.cost.toFixed(2)}
                <span style={{ fontSize: '13px', color: 'var(--muted-foreground)', fontWeight: 400 }}> / ₹{job.budget.toFixed(2)}</span>
              </div>
              <div className="progress-track" style={{ width: '100%', height: '8px', margin: '12px 0' }}>
                <div
                  className="progress-fill"
                  style={{ width: `${Math.min(100, (job.cost / job.budget) * 100)}%` }}
                />
              </div>
              <small style={{ color: 'var(--muted-foreground)' }}>
                {((job.cost / job.budget) * 100).toFixed(1)}% of maximum autonomous spend cap consumed.
              </small>

              <div style={{ marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: '11px', fontWeight: 600, marginBottom: '6px' }}>Autonomous Controls:</div>
                <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  Container Sandboxes: <strong>Rootless gVisor</strong><br />
                  Secret Redaction: <strong>Enforced</strong><br />
                  Human Oversight: <strong>Mandatory G1–G4</strong><br />
                  Phase 4 Boundary: <strong>Analysis & Planning Only (No CodeWriter)</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Inventory & Discovered Modules */}
      {activeTab === 'inventory' && (
        <InventoryBrowser
          snapshot={repositoryData?.snapshot || null}
          inventory={repositoryData?.inventory || null}
          legacyModel={legacyModel}
        />
      )}

      {/* Tab 3: Feasibility & G1 Decisions */}
      {activeTab === 'feasibility' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <GateDetailExplanationView
            gateType="G1"
            job={job}
            gate={gates.find((g) => g.gate_type === 'G1') || activeGate}
            feasibilityReport={feasibilityReport}
          />
          <FeasibilityView
            jobId={job.job_id}
            feasibilityReport={feasibilityReport}
            gapsRequiringG1={gapsRequiringG1}
            onDecisionSubmitted={loadJobData}
          />
        </div>
      )}

      {/* Tab 4: Target Blueprint */}
      {activeTab === 'blueprint' && (
        <BlueprintView blueprint={targetBlueprint} />
      )}

      {/* Tab 5: Conversion Plan & DAG (G3) */}
      {activeTab === 'planner' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <GateDetailExplanationView
            gateType="G3"
            job={job}
            gate={gates.find((g) => g.gate_type === 'G3') || activeGate}
            conversionPlan={conversionPlan}
          />
          <ConversionPlanView
            plan={conversionPlan}
            onRevisionRequested={async (reason) => {
              await api.submitConversionPlanRevision(job.job_id, { revision_reason: reason });
              await loadJobData();
            }}
          />
        </div>
      )}

      {/* Tab 6: Characterization Suite (G2) */}
      {activeTab === 'tests' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <GateDetailExplanationView
            gateType="G2"
            job={job}
            gate={gates.find((g) => g.gate_type === 'G2') || activeGate}
          />
        </div>
      )}

      {/* Tab 7: Verification & Diff (G4) */}
      {activeTab === 'verification' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <GateDetailExplanationView
            gateType="G4"
            job={job}
            gate={gates.find((g) => g.gate_type === 'G4') || activeGate}
          />
          <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '24px', backgroundColor: 'var(--card)' }}>
            <h2 style={{ fontSize: '16px', fontWeight: 650, marginBottom: '10px' }}>Dual-Harness Behavioral Verification (Gate G4)</h2>
            <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '20px' }}>
              Both legacy and converted services executed against identical fixtures. Zero unintended regressions detected.
            </p>
            <button className="button button-primary" onClick={() => onNavigate('/verification')}>
              Open Full Verification Suite
              <ArrowRight size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Tab 8: Agents */}
      {activeTab === 'agents' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
          {agents.map((ag) => (
            <div key={ag.run_id} style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <strong style={{ fontSize: '13px' }}>{ag.agent_name}</strong>
                <StatusBadge status={ag.status} />
              </div>
              <p style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginBottom: '10px' }}>
                {ag.role_description}
              </p>
              <div style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
                Tokens: {ag.input_tokens + ag.output_tokens} · Cost: ₹{ag.cost_usd.toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Gate Review Dialog */}
      {activeGate && (
        <GateReviewModal
          gate={activeGate}
          job={job}
          onClose={() => setActiveGate(null)}
          onSubmit={async (decision, rationale, waivers, options) => {
            await onGateDecision(activeGate.gate_id, decision, rationale, waivers, options);
            await loadJobData();
          }}
        />
      )}
    </div>
  );
};
