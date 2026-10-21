import React, { useState, useEffect } from 'react';
import type { Job, GateDetail, AgentRun, Artifact, User } from './types/domain';
import type { JobCreateRequest } from './types/api';
import { api } from './services/api';
import { Layout } from './components/Layout';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Jobs } from './pages/Jobs';
import { CreateJob } from './pages/CreateJob';
import { JobDetail } from './pages/JobDetail';
import { ApprovalGates } from './pages/ApprovalGates';
import { AgentWorkspace } from './pages/AgentWorkspace';
import { Artifacts } from './pages/Artifacts';
import { Verification } from './pages/Verification';
import { Reports } from './pages/Reports';
import { Audit } from './pages/Audit';
import { Catalog } from './pages/Catalog';
import { Settings } from './pages/Settings';
import { CodeWorkspace } from './pages/CodeWorkspace';

export const App: React.FC = () => {
  const [currentPath, setCurrentPath] = useState<string>(() => {
    return window.location.hash.slice(1) || '/dashboard';
  });

  const [user, setUser] = useState<User | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [gates, setGates] = useState<GateDetail[]>([]);
  const [agents, setAgents] = useState<AgentRun[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);

  // Synchronize hash routing
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.slice(1);
      if (hash) {
        setCurrentPath(hash);
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const navigate = (path: string) => {
    setCurrentPath(path);
    window.location.hash = path;
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      setLoading(true);
      const me = await api.getMe();
      setUser(me);

      if (me) {
        const jobRes = await api.getJobs().catch(() => ({ items: [], total: 0 }));
        setJobs(jobRes.items);

        const allGates = await api.getAllGates().catch(() => []);
        setGates(allGates);

        const firstJobId = jobRes.items[0]?.job_id;
        if (firstJobId) {
          const ags = await api.getAgents(firstJobId).catch(() => []);
          setAgents(ags);
          const arts = await api.getArtifacts(firstJobId).catch(() => []);
          setArtifacts(arts);
        } else {
          setAgents([]);
          setArtifacts([]);
        }
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGateDecision = async (
    gateId: string,
    decision: any,
    rationale: string,
    waivers?: any[]
  ) => {
    await api.submitGateDecision(gateId, { decision, rationale, waivers });
    const updatedGates = await api.getAllGates();
    setGates(updatedGates);
    const updatedJobs = await api.getJobs();
    setJobs(updatedJobs.items);
  };

  const handleCreateJob = async (req: JobCreateRequest) => {
    const created = await api.createJob(req);
    const updatedJobs = await api.getJobs();
    setJobs(updatedJobs.items);
    return created;
  };

  const handleLogin = async (authenticatedUser: User) => {
    setUser(authenticatedUser);
    try {
      const jobRes = await api.getJobs().catch(() => ({ items: [], total: 0 }));
      setJobs(jobRes.items);
      const allGates = await api.getAllGates().catch(() => []);
      setGates(allGates);
      const firstJobId = jobRes.items[0]?.job_id;
      if (firstJobId) {
        const ags = await api.getAgents(firstJobId).catch(() => []);
        setAgents(ags);
        const arts = await api.getArtifacts(firstJobId).catch(() => []);
        setArtifacts(arts);
      }
    } catch {
      // ignore
    }
    navigate('/dashboard');
  };

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    setJobs([]);
    setGates([]);
    setAgents([]);
    setArtifacts([]);
    navigate('/login');
  };

  if (loading && !user) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '100vh', fontFamily: 'var(--font-sans)' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '18px', fontWeight: 650, color: 'var(--primary)', marginBottom: '8px' }}>
            Rebase Modernization Platform
          </div>
          <div style={{ fontSize: '12px', color: 'var(--muted-foreground)' }}>
            Connecting to governance contracts...
          </div>
        </div>
      </div>
    );
  }

  // Isolated Login screen
  if (currentPath === '/login' || !user) {
    return <Login onSuccess={handleLogin} />;
  }

  const pendingGatesCount = gates.filter((g) => g.status === 'PENDING').length;

  const renderContent = () => {
    if (currentPath === '/dashboard') {
      return (
        <Dashboard
          jobs={jobs}
          gates={gates}
          onNavigate={navigate}
          onRefreshGates={async () => {
            const all = await api.getAllGates();
            setGates(all);
          }}
          onGateDecision={handleGateDecision}
        />
      );
    }
    if (currentPath === '/jobs') {
      return <Jobs jobs={jobs} onNavigate={navigate} />;
    }
    if (currentPath === '/jobs/new') {
      return <CreateJob onSubmit={handleCreateJob} onNavigate={navigate} />;
    }
    if (currentPath.startsWith('/jobs/')) {
      const jobId = currentPath.replace('/jobs/', '');
      return (
        <JobDetail
          jobId={jobId}
          onNavigate={navigate}
          onGateDecision={handleGateDecision}
        />
      );
    }
    if (currentPath === '/approvals') {
      return (
        <ApprovalGates
          gates={gates}
          onRefreshGates={async () => {
            const all = await api.getAllGates();
            setGates(all);
          }}
          onGateDecision={handleGateDecision}
          onNavigate={navigate}
        />
      );
    }
    if (currentPath === '/agents') {
      return <AgentWorkspace agents={agents} />;
    }
    if (currentPath === '/artifacts') {
      return <Artifacts artifacts={artifacts} />;
    }
    if (currentPath === '/verification') {
      return <Verification onNavigate={navigate} />;
    }
    if (currentPath === '/reports') {
      return <Reports />;
    }
    if (currentPath === '/audit') {
      return <Audit />;
    }
    if (currentPath === '/catalog') {
      return <Catalog />;
    }
    if (currentPath === '/settings') {
      return <Settings />;
    }
    if (currentPath === '/code') {
      return <CodeWorkspace />;
    }

    return (
      <Dashboard
        jobs={jobs}
        gates={gates}
        onNavigate={navigate}
        onRefreshGates={async () => {
          const all = await api.getAllGates();
          setGates(all);
        }}
        onGateDecision={handleGateDecision}
      />
    );
  };

  return (
    <Layout
      currentPath={currentPath}
      onNavigate={navigate}
      user={user}
      pendingGatesCount={pendingGatesCount}
      onLogout={handleLogout}
    >
      {renderContent()}
    </Layout>
  );
};
