import type { CharacterizationReport, SchemaAnalysis, DataMigrationPlan } from '../types/phase5';
import type { EvidenceArtifact, FinalDelivery, JobReport } from '../types/phase7';
import type { ModuleAttempt, ModuleCheck, ModuleExecutionBoard, ModuleReview } from '../types/phase6';
import type {
  Job,
  GateDetail,
  AgentRun,
  AgentTrace,
  Artifact,
  AuditEvent,
  User,
  DecisionOutcome,
  WorkflowState,
  VersionedGate,
  WorkflowEvent,
} from '../types/domain';
import type {
  JobListResponse,
  JobCreateRequest,
  GateDecisionRequest,
  GateDecisionResponse,
  PendingGatesResponse,
  VerificationReportResponse,
  DeliveryReportResponse,
  DetectedStackResponse,
} from '../types/api';
import type {
  RepositorySnapshot,
  RepositoryInventory,
  LegacyModel,
  LegacyModule,
  EvidenceRef,
  AnalysisConflict,
  TargetBlueprint,
  FeasibilityReport,
  FeasibilityCapability,
  G1DecisionRecord,
  G1DecisionBatchRequest,
  FileInventoryItem,
  DetectedTechnologyProfile,
  ConversionPlan,
  ConversionPlanValidation,
} from '../types/phase4';

const API_BASE = '/api/v1';

let currentUser: User | null = null;

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const errMsg = err.error?.message || err.detail || `Request failed with status ${res.status}`;
    throw new Error(errMsg);
  }

  return await res.json();
}

export const api = {
  async getFinalDelivery(jobId: string): Promise<FinalDelivery> {
    return request(`/jobs/${jobId}/delivery`);
  },
  async getJobReport(jobId: string, version?: number): Promise<EvidenceArtifact<JobReport>> {
    return request(`/jobs/${jobId}/report${version ? `?version=${version}` : ''}`);
  },
  async startIntegration(jobId: string, idempotencyKey: string): Promise<{ run_id: string; status: string }> {
    return request(`/jobs/${jobId}/integration-runs`, { method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }) });
  },
  async submitFinalReview(jobId: string, reportHash: string, idempotencyKey: string): Promise<unknown> {
    return request(`/jobs/${jobId}/g4/submit`, { method: 'POST', body: JSON.stringify({ report_hash: reportHash, idempotency_key: idempotencyKey }) });
  },
  async createPullRequest(jobId: string, reportHash: string, idempotencyKey: string): Promise<FinalDelivery['pull_request']> {
    return request(`/jobs/${jobId}/pull-request`, { method: 'POST', body: JSON.stringify({ report_hash: reportHash, idempotency_key: idempotencyKey }) });
  },
  async decideFinalGate(gateId: string, hashes: Record<string, string>, decision: 'APPROVED' | 'REJECTED', rationale: string, idempotencyKey: string): Promise<unknown> {
    return request(`/gates/${gateId}/decision`, { method: 'POST', body: JSON.stringify({ decision, rationale, artifact_hashes: hashes, idempotency_key: idempotencyKey }) });
  },
  async getModuleAttempts(jobId: string): Promise<ModuleExecutionBoard> {
    return request(`/jobs/${encodeURIComponent(jobId)}/module-attempts`);
  },

  async getModuleAttempt(attemptId: string): Promise<ModuleAttempt> {
    return request(`/module-attempts/${encodeURIComponent(attemptId)}`);
  },

  async getModuleAttemptDiff(attemptId: string): Promise<{ diff: string; changed_files: string[] }> {
    return request(`/module-attempts/${encodeURIComponent(attemptId)}/diff`);
  },

  async getModuleAttemptChecks(attemptId: string): Promise<{ checks: ModuleCheck[]; results: unknown[] }> {
    return request(`/module-attempts/${encodeURIComponent(attemptId)}/test-results`);
  },

  async getModuleAttemptReview(attemptId: string): Promise<ModuleReview> {
    return request(`/module-attempts/${encodeURIComponent(attemptId)}/review`);
  },

  async queueModuleConversion(jobId: string, moduleId: string, idempotencyKey: string): Promise<ModuleAttempt> {
    return request(`/jobs/${encodeURIComponent(jobId)}/modules/${encodeURIComponent(moduleId)}/conversion-runs`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }),
    });
  },

  async requestModuleRepair(attemptId: string, idempotencyKey: string, rationale: string): Promise<ModuleAttempt> {
    return request(`/module-attempts/${encodeURIComponent(attemptId)}/repair`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey, rationale }),
    });
  },

  async requestModuleWaiver(attemptId: string, findingId: string, rationale: string): Promise<Record<string, unknown>> {
    return request(`/module-attempts/${encodeURIComponent(attemptId)}/waivers`, {
      method: 'POST', body: JSON.stringify({ finding_id: findingId, rationale }),
    });
  },

  async getCharacterizationReport(jobId: string): Promise<CharacterizationReport> {
    return request(`/jobs/${jobId}/characterization-report`);
  },

  async runCharacterization(jobId: string, payload: Record<string, unknown>): Promise<CharacterizationReport> {
    return request(`/jobs/${jobId}/characterization-runs`, { method: 'POST', body: JSON.stringify(payload) });
  },

  async freezeCharacterization(jobId: string, suiteId: string, contentHash: string): Promise<{ gate_id: string }> {
    return request(`/jobs/${jobId}/g2/freeze`, {
      method: 'POST', body: JSON.stringify({ suite_id: suiteId, content_hash: contentHash }),
    });
  },

  async getSchemaAnalysis(jobId: string): Promise<SchemaAnalysis> {
    return request(`/jobs/${jobId}/schema-analysis`);
  },

  async getDataMigrationPlan(jobId: string): Promise<DataMigrationPlan> {
    return request(`/jobs/${jobId}/data-migration-plan`);
  },

  async validateDataMigrationPlan(jobId: string, tables: unknown[]): Promise<Record<string, unknown>> {
    return request(`/jobs/${jobId}/data-migration-plan/validate`, {
      method: 'POST', body: JSON.stringify({ tables }),
    });
  },

  // Auth
  async login(email: string, password: string): Promise<User> {
    const cleanEmail = email.trim().toLowerCase();
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: cleanEmail, password }),
      credentials: 'include',
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || 'Invalid email or password.');
    }

    const data = await res.json();
    currentUser = {
      user_id: data.user_id,
      email: data.email,
      full_name: data.full_name,
      role: data.role,
      status: data.status,
      permissions: data.permissions || [],
      created_at: data.created_at,
    };
    return currentUser;
  },

  async register(
    fullName: string,
    email: string,
    password: string,
    role: 'SUPER_ADMIN' | 'ADMIN' | 'REVIEWER' | 'DEVELOPER' | 'VIEWER' = 'DEVELOPER'
  ): Promise<User> {
    const cleanEmail = email.trim().toLowerCase();
    const cleanName = fullName.trim();
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: cleanName, email: cleanEmail, password, role }),
      credentials: 'include',
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || 'Registration failed. Please check your details.');
    }

    const data = await res.json();
    currentUser = {
      user_id: data.user_id,
      email: data.email,
      full_name: data.full_name,
      role: data.role,
      status: data.status,
      permissions: data.permissions || [],
      created_at: data.created_at,
    };
    return currentUser;
  },

  async logout(): Promise<void> {
    try {
      await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
    } catch {
      // ignore network errors on logout
    }
    currentUser = null;
  },

  async getMe(): Promise<User | null> {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        method: 'GET',
        credentials: 'include',
      });
      if (res.status === 401 || res.status === 403 || !res.ok) {
        currentUser = null;
        return null;
      }
      const data = await res.json();
      currentUser = {
        user_id: data.user_id,
        email: data.email,
        full_name: data.full_name,
        role: data.role,
        status: data.status,
        permissions: data.permissions || [],
        created_at: data.created_at,
      };
      return currentUser;
    } catch {
      currentUser = null;
      return null;
    }
  },

  // Jobs
  async getJobs(limit = 50, offset = 0, statusFilter?: string): Promise<JobListResponse> {
    const safeLimit = Math.max(1, limit || 50);
    const safeOffset = Math.max(0, offset || 0);
    const query = new URLSearchParams({ limit: String(safeLimit), offset: String(safeOffset) });
    if (statusFilter) query.set('status', statusFilter);
    return request<JobListResponse>(`/jobs?${query.toString()}`, { method: 'GET' });
  },

  async getJob(jobId: string): Promise<Job> {
    return request<Job>(`/jobs/${jobId}`, { method: 'GET' });
  },

  async createJob(req: JobCreateRequest): Promise<Job> {
    return request<Job>('/jobs', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  },

  async detectSourceStack(
    sourceRepository: string,
    sourceRevision: string = 'main',
    jobId?: string,
    accessToken?: string,
    sourceType: string = 'git'
  ): Promise<DetectedStackResponse> {
    return request<DetectedStackResponse>('/jobs/detect-stack', {
      method: 'POST',
      body: JSON.stringify({
        source_repository: sourceRepository,
        source_revision: sourceRevision,
        job_id: jobId,
        access_token: accessToken || undefined,
        source_type: sourceType,
      }),
    });
  },

  async detectLocalSourceStack(
    bundleZip: Blob,
    sourceName: string,
    jobId?: string
  ): Promise<DetectedStackResponse> {
    const formData = new FormData();
    formData.append('bundle', bundleZip, `${sourceName}.zip`);
    formData.append('source_name', sourceName);
    if (jobId) formData.append('job_id', jobId);

    const res = await fetch(`${API_BASE}/jobs/detect-stack/local`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const errMsg = err.error?.message || err.detail || `Upload detection failed with status ${res.status}`;
      throw new Error(errMsg);
    }

    return await res.json();
  },

  async intakeJob(
    jobId: string,
    gitToken?: string,
    previewSnapshotId?: string,
    snapshotFingerprint?: string
  ): Promise<Job> {
    return request<Job>(`/jobs/${jobId}/intake`, {
      method: 'POST',
      body: JSON.stringify({
        git_token: gitToken || undefined,
        preview_snapshot_id: previewSnapshotId || undefined,
        snapshot_fingerprint: snapshotFingerprint || undefined,
      }),
    });
  },

  async intakeJobLocal(
    jobId: string,
    bundleZip: Blob,
    expectedFingerprint?: string
  ): Promise<Job> {
    const formData = new FormData();
    formData.append('bundle', bundleZip, 'intake.zip');
    if (expectedFingerprint) formData.append('expected_fingerprint', expectedFingerprint);

    const res = await fetch(`${API_BASE}/jobs/${jobId}/intake/local`, {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const errMsg = err.error?.message || err.detail || `Local intake failed with status ${res.status}`;
      throw new Error(errMsg);
    }

    return await res.json();
  },

  async pauseJob(jobId: string): Promise<Job> {
    return request<Job>(`/jobs/${jobId}/pause`, { method: 'POST' });
  },

  async resumeJob(jobId: string): Promise<Job> {
    return request<Job>(`/jobs/${jobId}/resume`, { method: 'POST' });
  },

  async cancelJob(jobId: string): Promise<Job> {
    return request<Job>(`/jobs/${jobId}/cancel`, { method: 'POST' });
  },

  async getWorkflow(jobId: string): Promise<WorkflowState> {
    return request<WorkflowState>(`/jobs/${jobId}/workflow`, { method: 'GET' });
  },

  async getWorkflowEvents(jobId: string, limit = 25): Promise<WorkflowEvent[]> {
    const response = await request<{ items: WorkflowEvent[]; next_cursor?: string }>(`/jobs/${jobId}/events?limit=${limit}`, { method: 'GET' });
    return response.items || [];
  },

  async getVersionedGate(gateId: string): Promise<VersionedGate> {
    return request<VersionedGate>(`/gates/${gateId}`, { method: 'GET' });
  },

  async decideVersionedGate(
    gate: VersionedGate,
    decision: DecisionOutcome,
    rationale: string,
    options: Record<string, string> = {},
  ): Promise<{ decision_id: string; gate: VersionedGate; job_status: string; idempotent_replay: boolean }> {
    return request(`/gates/${gate.gate_id}/decision`, {
      method: 'POST',
      body: JSON.stringify({
        decision,
        rationale,
        options,
        artifact_hashes: gate.artifact_hashes,
        idempotency_key: crypto.randomUUID(),
      }),
    });
  },

  // Gates
  async getPendingGates(): Promise<PendingGatesResponse> {
    return request<PendingGatesResponse>('/gates/pending', { method: 'GET' });
  },

  async getAllGates(jobId?: string): Promise<GateDetail[]> {
    if (jobId) {
      return request<GateDetail[]>(`/jobs/${jobId}/gates`, { method: 'GET' });
    }
    const pending = await this.getPendingGates();
    return pending.items;
  },

  async submitGateDecision(gateId: string, req: GateDecisionRequest, jobId?: string): Promise<GateDecisionResponse> {
    const isVersionedGateId = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(gateId);
    if (isVersionedGateId) {
      const gate = await this.getVersionedGate(gateId);
      const result = await request<{ decision_id: string; gate: VersionedGate; job_status: string; idempotent_replay: boolean }>(
        `/gates/${gateId}/decision`,
        {
          method: 'POST',
          body: JSON.stringify({
            ...req,
            artifact_hashes: gate.artifact_hashes,
            idempotency_key: crypto.randomUUID(),
          }),
        },
      );
      return {
        decision_id: result.decision_id,
        job_id: gate.job_id,
        gate_id: gate.gate_id,
        gate_type: gate.gate_type,
        decision: req.decision,
        rationale: req.rationale,
        reviewer: 'Current reviewer',
        decided_at: result.gate.decided_at || new Date().toISOString(),
      };
    }
    // If gateId has format G1-<job_id>, parse job_id
    let targetJobId = jobId;
    if (!targetJobId && gateId.includes('-')) {
      const parts = gateId.split('-');
      if (parts.length > 1) {
        targetJobId = parts.slice(1).join('-');
      }
    }
    if (!targetJobId) {
      targetJobId = localStorage.getItem('rebase_active_job_id') || '';
    }
    if (!targetJobId) {
      throw new Error('No target job specified for gate decision');
    }

    return request<GateDecisionResponse>(
      `/jobs/${targetJobId}/gates/${gateId}/decisions`,
      {
        method: 'POST',
        body: JSON.stringify(req),
      }
    );
  },

  // Artifacts
  async getArtifacts(jobId: string): Promise<Artifact[]> {
    const res = await request<{ items: Artifact[]; total: number }>(
      `/jobs/${jobId}/artifacts`,
      { method: 'GET' }
    );
    return res.items || [];
  },

  async getArtifactContent(jobId: string, artifactId: string): Promise<{
    artifact_id: string;
    artifact_type: string;
    version: number;
    content_hash: string;
    content: any;
  }> {
    return request<{
      artifact_id: string;
      artifact_type: string;
      version: number;
      content_hash: string;
      content: any;
    }>(`/jobs/${jobId}/artifacts/${artifactId}/content`, { method: 'GET' });
  },

  // Agents
  async getAgents(jobId: string): Promise<AgentRun[]> {
    const res = await request<{ items: AgentRun[]; total: number }>(
      `/jobs/${jobId}/agent-runs`,
      { method: 'GET' }
    );
    return res.items || [];
  },

  async getAgentTrace(runId: string): Promise<AgentTrace> {
    return request<AgentTrace>(`/agent-runs/${runId}/trace`, { method: 'GET' });
  },

  async cancelAgentRun(runId: string): Promise<{ run_id: string; status: string; message: string; cancelled_at: string }> {
    return request(`/agent-runs/${runId}/cancel`, { method: 'POST' });
  },

  // Audit Logs (platform-wide or scoped to job)
  async getAuditLogs(jobId?: string, limit = 50, offset = 0, actorType?: string): Promise<{ items: AuditEvent[]; total: number }> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (actorType && actorType !== 'ALL') {
      params.set('actor_type', actorType);
    }
    const path = jobId ? `/jobs/${jobId}/audit?${params.toString()}` : `/audit?${params.toString()}`;
    return request<{ items: AuditEvent[]; total: number }>(path, { method: 'GET' });
  },

  // Verification Report
  async getVerificationReport(jobId: string): Promise<VerificationReportResponse> {
    return request<VerificationReportResponse>(
      `/jobs/${jobId}/reports/verification`,
      { method: 'GET' }
    );
  },

  // Delivery Report
  async getDeliveryReport(jobId: string): Promise<DeliveryReportResponse> {
    return request<DeliveryReportResponse>(
      `/jobs/${jobId}/reports/delivery`,
      { method: 'GET' }
    );
  },

  // System Health
  async getSystemHealth(): Promise<{ status: string; database: string; version: string }> {
    return request<{ status: string; database: string; version: string }>(
      '/health',
      { method: 'GET' }
    );
  },

  // Phase 4: Intake & Repository Inventory
  async getRepository(jobId: string): Promise<{
    snapshot: RepositorySnapshot;
    inventory: RepositoryInventory;
    files: FileInventoryItem[];
    directories: string[];
    tech_profile: DetectedTechnologyProfile;
    source_ref: string;
    commit_sha?: string | null;
    file_count: number;
    archive_size_bytes: number;
    content_hash: string;
    inventory_hash: string;
    created_at: string;
  }> {
    const raw = await request<any>(`/jobs/${jobId}/repository`, { method: 'GET' });
    const files: FileInventoryItem[] = raw.files || raw.inventory?.files || [];
    const directories: string[] = raw.directories || raw.inventory?.directories || [];
    const tech_profile: DetectedTechnologyProfile = raw.tech_profile || raw.snapshot?.tech_profile || {
      primary_language: 'Unknown',
      languages: {},
      frameworks: [],
      build_systems: [],
      package_managers: [],
      manifest_files: [],
      config_files: [],
      test_frameworks: [],
      database_dialects: [],
      confidence: 1.0,
    };
    const metadata = raw.metadata || raw.snapshot?.metadata || {};
    const inventory_hash: string = raw.inventory_hash || raw.inventory?.inventory_hash || '';
    const content_hash: string = raw.content_hash || raw.snapshot?.content_hash || '';
    const file_count: number = raw.file_count || files.length;

    const snapshot: RepositorySnapshot = raw.snapshot || {
      snapshot_id: raw.snapshot_id || `snap-${jobId}`,
      job_id: jobId,
      version: raw.version || 1,
      metadata: {
        repository_id: metadata.repository_id || jobId,
        source_type: raw.source_type || metadata.source_type || 'git',
        source_ref: raw.source_ref || metadata.source_ref || '',
        commit_sha: raw.commit_sha || metadata.commit_sha || null,
        content_hash,
        archive_size_bytes: raw.archive_size_bytes || 0,
        file_count,
        acquired_at: raw.created_at || new Date().toISOString(),
        analyzer_version: 'v4.0',
      },
      tech_profile,
      inventory_hash,
      created_at: raw.created_at || new Date().toISOString(),
      content_hash,
    };

    const inventory: RepositoryInventory = raw.inventory || {
      inventory_id: raw.inventory_id || `inv-${jobId}`,
      snapshot_id: snapshot.snapshot_id,
      job_id: jobId,
      total_files: file_count,
      total_bytes: raw.archive_size_bytes || 0,
      files,
      directories,
      inventory_hash,
      created_at: raw.created_at || new Date().toISOString(),
    };

    return {
      ...raw,
      snapshot,
      inventory,
      files,
      directories,
      tech_profile,
      source_ref: raw.source_ref || snapshot.metadata.source_ref,
      commit_sha: raw.commit_sha || snapshot.metadata.commit_sha,
      file_count,
      archive_size_bytes: raw.archive_size_bytes || 0,
      content_hash,
      inventory_hash,
      created_at: raw.created_at || snapshot.created_at,
    };
  },

  async getModules(jobId: string): Promise<{ legacy_model_version: number; modules: LegacyModule[]; total: number }> {
    return request<{ legacy_model_version: number; modules: LegacyModule[]; total: number }>(
      `/jobs/${jobId}/modules`,
      { method: 'GET' }
    );
  },

  // Phase 4: Legacy Analyzer & Reconciliation
  async getAnalysis(jobId: string): Promise<{
    legacy_model: LegacyModel;
    evidence_refs: EvidenceRef[];
    conflicts: AnalysisConflict[];
    confidence_score: number;
    analysis_version: number;
  }> {
    return request<{
      legacy_model: LegacyModel;
      evidence_refs: EvidenceRef[];
      conflicts: AnalysisConflict[];
      confidence_score: number;
      analysis_version: number;
    }>(`/jobs/${jobId}/analysis`, { method: 'GET' });
  },

  async retryAnalysis(jobId: string, reason: string, constraints?: Record<string, any>): Promise<{ run_id: string; status: string; message: string }> {
    return request<{ run_id: string; status: string; message: string }>(
      `/jobs/${jobId}/analysis/retry`,
      {
        method: 'POST',
        body: JSON.stringify({ reason, constraints: constraints || {} }),
      }
    );
  },

  // Phase 4: Feasibility & G1 Human Decisions
  async getFeasibility(jobId: string): Promise<{
    feasibility_report: FeasibilityReport;
    gaps_requiring_g1: FeasibilityCapability[];
    readiness_summary: Record<string, any>;
  }> {
    return request<{
      feasibility_report: FeasibilityReport;
      gaps_requiring_g1: FeasibilityCapability[];
      readiness_summary: Record<string, any>;
    }>(`/jobs/${jobId}/feasibility`, { method: 'GET' });
  },

  async submitFeasibilityDecisions(
    jobId: string,
    payload: G1DecisionBatchRequest
  ): Promise<{
    applied_decisions: G1DecisionRecord[];
    blueprint_version: number | null;
    rerun_triggered: boolean;
    status: string;
  }> {
    return request<{
      applied_decisions: G1DecisionRecord[];
      blueprint_version: number | null;
      rerun_triggered: boolean;
      status: string;
    }>(`/jobs/${jobId}/feasibility/decisions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Phase 4: Target Blueprint
  async getBlueprint(jobId: string): Promise<{
    target_blueprint: TargetBlueprint;
    version: number;
    is_locked: boolean;
  }> {
    return request<{
      target_blueprint: TargetBlueprint;
      version: number;
      is_locked: boolean;
    }>(`/jobs/${jobId}/blueprint`, { method: 'GET' });
  },

  // Phase 4: Conversion Plan & DAG
  async getConversionPlan(jobId: string): Promise<{
    conversion_plan: ConversionPlan;
    validation_status: ConversionPlanValidation;
    total_tasks: number;
    total_waves: number;
  }> {
    return request<{
      conversion_plan: ConversionPlan;
      validation_status: ConversionPlanValidation;
      total_tasks: number;
      total_waves: number;
    }>(`/jobs/${jobId}/conversion-plan`, { method: 'GET' });
  },

  async submitConversionPlanRevision(
    jobId: string,
    payload: { revision_reason: string; module_overrides?: Record<string, any>; task_overrides?: Record<string, any> }
  ): Promise<{
    plan_id: string;
    version: number;
    validation_status: ConversionPlanValidation;
  }> {
    return request<{
      plan_id: string;
      version: number;
      validation_status: ConversionPlanValidation;
    }>(`/jobs/${jobId}/conversion-plan/revisions`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
