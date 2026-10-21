import type {
  Job,
  GateDetail,
  AgentRun,
  Artifact,
  AuditEvent,
  User,
  DecisionOutcome,
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
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
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

  async detectSourceStack(sourceRepository: string, sourceRevision: string = 'main', jobId?: string): Promise<DetectedStackResponse> {
    return request<DetectedStackResponse>('/jobs/detect-stack', {
      method: 'POST',
      body: JSON.stringify({
        source_repository: sourceRepository,
        source_revision: sourceRevision,
        job_id: jobId,
      }),
    });
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
    // If gateId has format G1-<job_id>, parse job_id
    let targetJobId = jobId;
    if (!targetJobId && gateId.includes('-')) {
      const parts = gateId.split('-');
      if (parts.length > 1) {
        targetJobId = parts.slice(1).join('-');
      }
    }
    if (!targetJobId) {
      targetJobId = 'JOB-0248';
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

  // Agents
  async getAgents(jobId: string): Promise<AgentRun[]> {
    const res = await request<{ items: AgentRun[]; total: number }>(
      `/jobs/${jobId}/agents`,
      { method: 'GET' }
    );
    return res.items || [];
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
};
