import React, { useState, useEffect, useMemo, useRef } from 'react';
import type { Job, WorkflowState, WorkflowEvent, GateDetail } from '../types/domain';
import type { FileInventoryItem, DetectedTechnologyProfile } from '../types/phase4';
import { api } from '../services/api';
import { ProjectExplorer } from '../components/workspace/ProjectExplorer';
import { AgentExecution } from '../components/workspace/AgentExecution';
import { ActivityLog } from '../components/workspace/ActivityLog';
import { FileAnalysisStatus } from '../components/workspace/FileStatusIndicator';
import { GateReviewModal } from '../components/GateReviewModal';
import { Loader2, AlertCircle } from 'lucide-react';

interface CodeWorkspaceProps {
  jobs?: Job[];
  initialJobId?: string;
  onNavigate?: (path: string) => void;
}

export const CodeWorkspace: React.FC<CodeWorkspaceProps> = ({ jobs: propJobs, initialJobId, onNavigate }) => {
  const [jobs, setJobs] = useState<Job[]>(propJobs || []);
  const [selectedJobId, setSelectedJobId] = useState<string>(() => {
    if (initialJobId) return initialJobId;
    try {
      const hash = window.location.hash;
      const match = hash.match(/job_id=([a-f0-9-]+)/i);
      if (match && match[1]) return match[1];
      const saved = localStorage.getItem('rebase_active_job_id');
      if (saved) return saved;
    } catch {
      // ignore
    }
    return '';
  });
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);

  // Repository Inventory state
  const [files, setFiles] = useState<FileInventoryItem[]>([]);
  const [directories, setDirectories] = useState<string[]>([]);
  const [techProfile, setTechProfile] = useState<DetectedTechnologyProfile | null>(null);
  const [sourceRef, setSourceRef] = useState<string>('');
  const [commitSha, setCommitSha] = useState<string | null>(null);

  // Execution & Live Event state
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [events, setEvents] = useState<WorkflowEvent[]>([]);
  const [gates, setGates] = useState<GateDetail[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [activeGateForReview, setActiveGateForReview] = useState<GateDetail | null>(null);

  const [loading, setLoading] = useState<boolean>(true);
  const [loadingRepo, setLoadingRepo] = useState<boolean>(false);
  const [intakeRunning, setIntakeRunning] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const filesCountRef = useRef<number>(0);
  useEffect(() => {
    filesCountRef.current = files.length;
  }, [files]);

  const pollTimerRef = useRef<number | null>(null);

  const handleRunIntake = async () => {
    if (!selectedJobId || intakeRunning) return;
    try {
      setIntakeRunning(true);
      setError(null);
      await api.intakeJob(selectedJobId);
      const repo = await api.getRepository(selectedJobId).catch(() => null);
      if (repo && repo.files) {
        setFiles(repo.files);
        setDirectories(repo.directories || []);
        setTechProfile(repo.tech_profile || null);
        setSourceRef(repo.source_ref || '');
        setCommitSha(repo.commit_sha || null);
        const firstCodeFile =
          repo.files.find((f) => !f.is_documentation && !f.is_config) || repo.files[0];
        if (firstCodeFile) setSelectedFile(firstCodeFile.path);
      }
      const [updatedEvents, updatedJob] = await Promise.all([
        api.getWorkflowEvents(selectedJobId, 100).catch(() => null),
        api.getJob(selectedJobId).catch(() => null),
      ]);
      if (updatedEvents) setEvents(updatedEvents);
      if (updatedJob) setSelectedJob(updatedJob);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute repository intake.');
    } finally {
      setIntakeRunning(false);
    }
  };

  // Helper to resolve the best active job
  const resolveInitialJob = (jobList: Job[]): string => {
    if (!jobList || jobList.length === 0) return '';
    try {
      const saved = localStorage.getItem('rebase_active_job_id');
      if (saved && jobList.some((j) => j.job_id === saved)) return saved;
    } catch {
      // ignore
    }

    // Prioritize the user's primary active projects (Cake Shop or Spendwise)
    const cakeShop = jobList.find((j) => j.name.toLowerCase().includes('cake'));
    if (cakeShop) return cakeShop.job_id;

    const spendwise = jobList.find((j) => j.name.toLowerCase().includes('spendwise'));
    if (spendwise) return spendwise.job_id;

    const activeJob = jobList.find(
      (j) =>
        j.status.startsWith('AWAITING_GATE_') ||
        j.status === 'CHARACTERIZING' ||
        j.status === 'ANALYZING' ||
        j.status === 'CONVERTING' ||
        j.status === 'INTAKE'
    );
    return activeJob ? activeJob.job_id : jobList[0].job_id;
  };

  // Sync propJobs if supplied
  useEffect(() => {
    if (propJobs && propJobs.length > 0) {
      setJobs(propJobs);
      if (!selectedJobId) {
        setSelectedJobId(resolveInitialJob(propJobs));
      }
    }
  }, [propJobs]);

  // 1. Initial Load: Fetch Jobs List
  useEffect(() => {
    let mounted = true;
    const fetchJobs = async () => {
      try {
        setLoading(true);
        const res = await api.getJobs(100, 0); // Correct limit=100, offset=0
        if (!mounted) return;
        const jobList = res.items || [];
        if (jobList.length > 0) {
          setJobs(jobList);
          if (!selectedJobId) {
            setSelectedJobId(resolveInitialJob(jobList));
          }
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to fetch modernization jobs.');
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };

    fetchJobs();
    return () => {
      mounted = false;
    };
  }, []);

  // 2. When selectedJobId changes, load job details, repo inventory, workflow, and events
  useEffect(() => {
    if (!selectedJobId) return;

    try {
      localStorage.setItem('rebase_active_job_id', selectedJobId);
    } catch {
      // ignore
    }

    let mounted = true;

    const loadJobWorkspace = async () => {
      setLoadingRepo(true);
      setError(null);

      try {
        const [jobRes, repoRes, workflowRes, eventsRes, gatesRes] = await Promise.allSettled([
          api.getJob(selectedJobId),
          api.getRepository(selectedJobId),
          api.getWorkflow(selectedJobId),
          api.getWorkflowEvents(selectedJobId, 100),
          api.getAllGates(selectedJobId),
        ]);

        if (!mounted) return;

        if (jobRes.status === 'fulfilled') {
          setSelectedJob(jobRes.value);
        }

        if (repoRes.status === 'fulfilled') {
          const repo = repoRes.value;
          const currentFiles = repo.files || [];
          setFiles(currentFiles);
          setDirectories(repo.directories || []);
          setTechProfile(repo.tech_profile || null);
          setSourceRef(repo.source_ref || '');
          setCommitSha(repo.commit_sha || null);

          // Select first file if needed
          if (currentFiles.length > 0) {
            const hasFile = selectedFile && currentFiles.some((f) => f.path === selectedFile);
            if (!hasFile) {
              const firstCodeFile =
                currentFiles.find((f) => !f.is_documentation && !f.is_config) || currentFiles[0];
              setSelectedFile(firstCodeFile.path);
            }
          } else {
            setSelectedFile(null);
          }
        } else {
          // If repository snapshot not yet present, clear repo state gracefully
          setFiles([]);
          setDirectories([]);
          setTechProfile(null);
          setSelectedFile(null);
        }

        if (workflowRes.status === 'fulfilled') {
          setWorkflow(workflowRes.value);
        }

        if (eventsRes.status === 'fulfilled') {
          setEvents(eventsRes.value || []);
        }

        if (gatesRes.status === 'fulfilled') {
          setGates(gatesRes.value || []);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load job repository and execution state.');
        }
      } finally {
        if (mounted) setLoadingRepo(false);
      }
    };

    loadJobWorkspace();

    // Set up real-time event polling stream (3s interval)
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
    }

    pollTimerRef.current = window.setInterval(async () => {
      try {
        const [updatedEvents, updatedWorkflow, updatedJob] = await Promise.all([
          api.getWorkflowEvents(selectedJobId, 100).catch(() => null),
          api.getWorkflow(selectedJobId).catch(() => null),
          api.getJob(selectedJobId).catch(() => null),
        ]);

        if (updatedEvents) setEvents(updatedEvents);
        if (updatedWorkflow) setWorkflow(updatedWorkflow);
        if (updatedJob) setSelectedJob(updatedJob);

        // If files are not yet loaded in UI (e.g. intake just finished), poll repository
        if (filesCountRef.current === 0) {
          try {
            const repo = await api.getRepository(selectedJobId);
            if (repo && repo.files && repo.files.length > 0) {
              setFiles(repo.files);
              setDirectories(repo.directories || []);
              setTechProfile(repo.tech_profile || null);
              setSourceRef(repo.source_ref || '');
              setCommitSha(repo.commit_sha || null);
              const firstCodeFile =
                repo.files.find((f) => !f.is_documentation && !f.is_config) || repo.files[0];
              if (firstCodeFile) {
                setSelectedFile(firstCodeFile.path);
              }
            }
          } catch {
            // Repo inventory not yet ready
          }
        }
      } catch {
        // Silently tolerate temporary polling errors in background
      }
    }, 3000);

    return () => {
      mounted = false;
      if (pollTimerRef.current) {
        window.clearInterval(pollTimerRef.current);
      }
    };
  }, [selectedJobId]);

  // Derive file analysis statuses from files, workflow, and events
  const { fileStatuses, activeAnalyzingFile } = useMemo(() => {
    const statuses: Record<string, FileAnalysisStatus> = {};
    let activeFile: string | null = null;

    // Default status from file flags
    files.forEach((file) => {
      if (file.is_manifest || file.is_config) {
        statuses[file.path] = 'ANALYZED';
      } else {
        statuses[file.path] = 'PENDING';
      }
    });

    // Check events for file analysis
    events.forEach((evt) => {
      const typeStr = evt.event_type.toLowerCase();
      const p = (evt.payload || {}) as Record<string, any>;
      const targetPath = (p.path || p.file || p.source_path) as string | undefined;

      if (targetPath && typeof targetPath === 'string' && statuses[targetPath] !== undefined) {
        if (typeStr.includes('file.analysis.completed') || typeStr.includes('analyzed')) {
          statuses[targetPath] = 'ANALYZED';
        } else if (typeStr.includes('file.analysis.started') || typeStr.includes('analyzing')) {
          statuses[targetPath] = 'ANALYZING';
          activeFile = targetPath;
        } else if (typeStr.includes('warning')) {
          statuses[targetPath] = 'WARNING';
        } else if (typeStr.includes('error') || typeStr.includes('failed')) {
          statuses[targetPath] = 'ERROR';
        }
      }
    });

    // If job is in active analysis and no active file was explicitly set,
    // designate the first pending/code file as currently analyzing for live visibility
    if (
      selectedJob?.status === 'ANALYZING' ||
      selectedJob?.status === 'CHARACTERIZING' ||
      selectedJob?.status === 'AWAITING_GATE_G1'
    ) {
      const pendingFiles = files.filter(
        (f) => !f.is_documentation && statuses[f.path] === 'PENDING'
      );
      if (pendingFiles.length > 0 && !activeFile) {
        activeFile = pendingFiles[0].path;
        statuses[activeFile] = 'ANALYZING';
      }
    }

    return { fileStatuses: statuses, activeAnalyzingFile: activeFile };
  }, [files, events, selectedJob]);

  // Selected file item metadata
  const selectedFileItem = useMemo(() => {
    if (!selectedFile) return null;
    return files.find((f) => f.path === selectedFile) || null;
  }, [files, selectedFile]);

  // Handle Gate Review modal opening
  const handleOpenGateReview = (gateType: 'G1' | 'G2' | 'G3') => {
    const matchingGate =
      gates.find((g) => g.job_id === selectedJobId && g.gate_type === gateType && g.status === 'PENDING') ||
      gates.find((g) => g.job_id === selectedJobId && g.status === 'PENDING') ||
      gates[0];

    if (matchingGate) {
      setActiveGateForReview(matchingGate);
    }
  };

  const handleGateDecisionSubmit = async (
    gateId: string,
    decision: any,
    rationale: string,
    waivers?: any[],
    options?: Record<string, string>
  ) => {
    await api.submitGateDecision(gateId, { decision, rationale, waivers, options });
    setActiveGateForReview(null);

    // Refresh immediately
    if (selectedJobId) {
      const [updatedJob, updatedWorkflow, updatedGates] = await Promise.all([
        api.getJob(selectedJobId).catch(() => null),
        api.getWorkflow(selectedJobId).catch(() => null),
        api.getAllGates(selectedJobId).catch(() => []),
      ]);
      if (updatedJob) setSelectedJob(updatedJob);
      if (updatedWorkflow) setWorkflow(updatedWorkflow);
      if (updatedGates) setGates(updatedGates);
    }
  };

  if (loading && jobs.length === 0) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: 'calc(100vh - 120px)',
          gap: '12px',
          color: 'var(--muted-foreground)',
        }}
      >
        <Loader2 size={24} className="spin-animation" color="var(--primary)" />
        <span style={{ fontSize: '13px', fontWeight: 600 }}>Loading Multi-Agent Execution Workspace...</span>
      </div>
    );
  }

  return (
    <div
      className="code-workspace-container"
      style={{
        display: 'flex',
        flexDirection: 'row',
        height: 'calc(100vh - 68px)',
        width: '100%',
        overflow: 'hidden',
        backgroundColor: 'var(--background, #f8fafc)',
      }}
    >
      {/* Panel 2: Project Explorer (300px fixed width, independent scroll) */}
      <div
        style={{
          width: '300px',
          flexShrink: 0,
          height: '100%',
          overflow: 'hidden',
        }}
      >
        <ProjectExplorer
          jobs={jobs}
          selectedJob={selectedJob}
          onSelectJob={(id) => setSelectedJobId(id)}
          files={files}
          directories={directories}
          techProfile={techProfile}
          sourceRef={sourceRef}
          commitSha={commitSha}
          selectedFile={selectedFile}
          onSelectFile={(filePath) => setSelectedFile(filePath)}
          fileStatuses={fileStatuses}
          activeAnalyzingFile={activeAnalyzingFile}
          onRunIntake={handleRunIntake}
          intakeRunning={intakeRunning}
          loading={loadingRepo}
        />
      </div>

      {/* Panel 3: Agent Execution (flexible width, independent scroll) */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          height: '100%',
          overflow: 'hidden',
        }}
      >
        <AgentExecution
          job={selectedJob}
          workflow={workflow}
          events={events}
          selectedFile={selectedFile}
          selectedFileItem={selectedFileItem}
          fileStatuses={fileStatuses}
          activeAnalyzingFile={activeAnalyzingFile}
          onOpenGateReview={handleOpenGateReview}
          onRunIntake={handleRunIntake}
          intakeRunning={intakeRunning}
          loading={loadingRepo}
        />
      </div>

      {/* Panel 4: Real-time Activity Log (360px fixed width, independent scroll) */}
      <div
        style={{
          width: '360px',
          flexShrink: 0,
          height: '100%',
          overflow: 'hidden',
        }}
      >
        <ActivityLog
          events={events}
          activeAnalyzingFile={activeAnalyzingFile}
          onRefresh={async () => {
            if (selectedJobId) {
              const res = await api.getWorkflowEvents(selectedJobId, 100).catch(() => []);
              setEvents(res);
            }
          }}
          isStreaming={true}
        />
      </div>

      {/* Gate Review Modal (when Action Required G1 or G3 is clicked) */}
      {activeGateForReview && (
        <GateReviewModal
          gate={activeGateForReview}
          onClose={() => setActiveGateForReview(null)}
          onSubmit={(decision, rationale, waivers, options) =>
            handleGateDecisionSubmit(activeGateForReview.gate_id, decision, rationale, waivers, options)
          }
        />
      )}
    </div>
  );
};
