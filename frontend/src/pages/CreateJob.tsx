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
  Lock,
  Eye,
  EyeOff,
  X,
  Folder,
  FolderOpen,
  HardDrive,
  UploadCloud,
  Search,
} from 'lucide-react';
import {
  isFileSystemAccessSupported,
  scanWithDirectoryPicker,
  scanWithFileList,
  type ScanProgress,
} from '../services/localSourceScanner';

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
  const [name, setName] = useState('');
  const [userEditedName, setUserEditedName] = useState(false);
  const [sourceRepo, setSourceRepo] = useState('');
  const [revision, setRevision] = useState('main');
  const [gitToken, setGitToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [isPrivateRepo, setIsPrivateRepo] = useState(false);

  const deriveProjectNameFromRepo = (url: string): string => {
    if (!url) return '';
    try {
      const clean = url.trim().replace(/\/+$/, '').replace(/\.git$/i, '');
      const segments = clean.split('/');
      const repoSegment = segments[segments.length - 1] || '';
      if (repoSegment && !['repo', 'git', 'github.com'].includes(repoSegment.toLowerCase())) {
        const formatted = repoSegment
          .replace(/[-_]/g, ' ')
          .replace(/\b\w/g, (c) => c.toUpperCase());
        return `${formatted} Modernization`;
      }
    } catch {
      // ignore
    }
    return '';
  };

  // Local Folder Source States
  const [sourceType, setSourceType] = useState<'git' | 'local'>('git');
  const [localPath, setLocalPath] = useState('');
  const [uploadedZipName, setUploadedZipName] = useState<string | null>(null);
  const [zipUploading, setZipUploading] = useState(false);
  const zipInputRef = useRef<HTMLInputElement | null>(null);
  const [localFolderName, setLocalFolderName] = useState('');
  const [previewSnapshotId, setPreviewSnapshotId] = useState<string | null>(null);
  const [snapshotFingerprint, setSnapshotFingerprint] = useState<string | null>(null);
  const [localScanProgress, setLocalScanProgress] = useState<ScanProgress | null>(null);
  const [localScanActive, setLocalScanActive] = useState(false);
  const [localWarnings, setLocalWarnings] = useState<string[]>([]);
  const [localScanSummary, setLocalScanSummary] = useState<{ fileCount: number; totalBytes: number } | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const fallbackInputRef = useRef<HTMLInputElement | null>(null);
  const [sourceStack, setSourceStack] = useState('Java 11 / Spring Boot 2.7 (Maven)');
  const [targetPlan, setTargetPlan] = useState('');
  const [budget, setBudget] = useState(15000);
  const [maxRepairAttempts, setMaxRepairAttempts] = useState(3);
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

  const handleDetectStack = async (repoUrl: string, rev: string, tokenOverride?: string) => {
    if (!repoUrl || !repoUrl.trim()) return;
    const reqId = ++latestReqIdRef.current;

    try {
      setDetecting(true);
      setDetectError(null);
      const activeToken = tokenOverride !== undefined ? tokenOverride : gitToken;
      const res = await api.detectSourceStack(
        repoUrl.trim(),
        rev?.trim() || 'main',
        undefined,
        activeToken.trim() || undefined
      );

      // Check if another request has been initiated since this one started
      if (reqId !== latestReqIdRef.current) return;

      setDetectedStack(res);
      if (res.source_revision && res.source_revision !== 'HEAD' && res.source_revision !== rev) {
        setRevision(res.source_revision);
      }
      setSourceStack(res.summary_stack);
      if (!userEditedName) {
        const derived = deriveProjectNameFromRepo(repoUrl);
        if (derived) {
          setName(derived);
        }
      }

      // If detection succeeded without any token, this repository is public
      if (!activeToken.trim()) {
        setIsPrivateRepo(false);
      }

      // Reset overrides on fresh detection
      setOverrides({});
      setEditingTier(null);
    } catch (err: any) {
      if (reqId === latestReqIdRef.current) {
        console.warn('Stack detection notice:', err);
        const errMsg = err.message || '';
        const isAuthOrPrivate =
          errMsg.includes('Authentication required') ||
          errMsg.includes('private') ||
          errMsg.includes('Personal Access Token') ||
          errMsg.includes('access denied') ||
          errMsg.includes('authentication failed') ||
          errMsg.includes('401') ||
          errMsg.includes('403') ||
          errMsg.includes('could not read Username');

        if (isAuthOrPrivate) {
          setIsPrivateRepo(true);
          setDetectError(
            'Private repository detected: A GitHub Personal Access Token (PAT) with Read-only access is required to analyze this repository.'
          );
        } else {
          setDetectError(errMsg || 'Stack detection failed. Please check repository coordinates and permissions.');
        }
      }
    } finally {
      if (reqId === latestReqIdRef.current) {
        setDetecting(false);
      }
    }
  };

  const handleDetectLocalPath = async (pathStr: string) => {
    if (!pathStr || !pathStr.trim()) return;
    const reqId = ++latestReqIdRef.current;
    try {
      setDetecting(true);
      setDetectError(null);
      const res = await api.detectSourceStack(pathStr.trim(), 'LOCAL', undefined, undefined, 'local');
      if (reqId !== latestReqIdRef.current) return;
      setDetectedStack(res);
      setPreviewSnapshotId(res.preview_snapshot_id || null);
      setSnapshotFingerprint(res.snapshot_fingerprint || null);
      setLocalWarnings(res.warnings || []);
      const folderName = pathStr.trim().split(/[\\/]/).filter(Boolean).pop() || 'project';
      setLocalFolderName(folderName);
      if (!userEditedName || !name) {
        const formatted = folderName.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        setName(`${formatted} Modernization`);
      }
      setUploadedZipName(null);
      setOverrides({});
      setEditingTier(null);
    } catch (err: any) {
      if (reqId !== latestReqIdRef.current) return;
      console.error('Local path detection error:', err);
      setDetectError(err.message || 'Failed to inspect local project path. Please verify the directory exists.');
    } finally {
      if (reqId === latestReqIdRef.current) {
        setDetecting(false);
      }
    }
  };

  const handleZipFileSelected = async (file: File) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.zip')) {
      setDetectError('Please select a valid .zip archive file.');
      return;
    }
    const cleanName = file.name.replace(/\.zip$/i, '');
    const reqId = ++latestReqIdRef.current;
    try {
      setZipUploading(true);
      setDetecting(true);
      setDetectError(null);
      setUploadedZipName(file.name);
      setLocalFolderName(cleanName);
      setLocalPath('');
      if (!userEditedName || !name) {
        const formatted = cleanName.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        setName(`${formatted} Modernization`);
      }

      const res = await api.detectLocalSourceStack(file, cleanName);
      if (reqId !== latestReqIdRef.current) return;
      setDetectedStack(res);
      setPreviewSnapshotId(res.preview_snapshot_id || null);
      setSnapshotFingerprint(res.snapshot_fingerprint || null);
      setLocalWarnings(res.warnings || []);
      setOverrides({});
      setEditingTier(null);
    } catch (err: any) {
      if (reqId !== latestReqIdRef.current) return;
      console.error('ZIP upload detection error:', err);
      setDetectError(err.message || 'Failed to analyze project ZIP archive.');
      setUploadedZipName(null);
    } finally {
      if (reqId === latestReqIdRef.current) {
        setZipUploading(false);
        setDetecting(false);
      }
    }
  };

  useEffect(() => {
    if (sourceType === 'local') return;
    if (!sourceRepo || sourceRepo.trim().length < 5) return;
    const timer = setTimeout(() => {
      handleDetectStack(sourceRepo, revision, gitToken);
    }, 600);
    return () => clearTimeout(timer);
  }, [sourceRepo, revision, gitToken, sourceType]);

  useEffect(() => {
    if (sourceType !== 'local') return;
    if (!localPath || localPath.trim().length < 3) return;
    const timer = setTimeout(() => {
      handleDetectLocalPath(localPath.trim());
    }, 700);
    return () => clearTimeout(timer);
  }, [localPath, sourceType]);

  // PAT section is shown only for private repositories (detected or manually toggled)
  const showPatSection = isPrivateRepo || gitToken.length > 0;

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

  const handlePickLocalFolder = async () => {
    try {
      setDetectError(null);
      setLocalWarnings([]);
      setLocalScanActive(true);
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const result = await scanWithDirectoryPicker((prog) => {
        setLocalScanProgress(prog);
      }, controller.signal);

      setLocalFolderName(result.sourceName);
      setLocalWarnings(result.warnings);
      setLocalScanSummary({ fileCount: result.fileCount, totalBytes: result.totalBytes });
      setLocalScanProgress(null);
      setDetecting(true);

      const res = await api.detectLocalSourceStack(result.bundleZip, result.sourceName);
      setDetectedStack(res);
      setPreviewSnapshotId(res.preview_snapshot_id || null);
      setSnapshotFingerprint(res.snapshot_fingerprint || null);
      setSourceStack(res.summary_stack);
      if (!userEditedName || !name) {
        const formatted = result.sourceName.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        setName(`${formatted} Modernization`);
      }
      setOverrides({});
      setEditingTier(null);
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // User cancelled picker dialog
      } else {
        console.error('Local folder scan error:', err);
        setDetectError(err.message || 'Failed to scan or upload local project folder.');
      }
    } finally {
      setLocalScanActive(false);
      setDetecting(false);
      abortControllerRef.current = null;
    }
  };

  const handleFallbackFolderSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    try {
      setDetectError(null);
      setLocalWarnings([]);
      setLocalScanActive(true);
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const result = await scanWithFileList(files, 'local-project', (prog) => {
        setLocalScanProgress(prog);
      }, controller.signal);

      setLocalFolderName(result.sourceName);
      setLocalWarnings(result.warnings);
      setLocalScanSummary({ fileCount: result.fileCount, totalBytes: result.totalBytes });
      setLocalScanProgress(null);
      setDetecting(true);

      const res = await api.detectLocalSourceStack(result.bundleZip, result.sourceName);
      setDetectedStack(res);
      setPreviewSnapshotId(res.preview_snapshot_id || null);
      setSnapshotFingerprint(res.snapshot_fingerprint || null);
      setSourceStack(res.summary_stack);
      if (!userEditedName || !name) {
        const formatted = result.sourceName.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        setName(`${formatted} Modernization`);
      }
      setOverrides({});
      setEditingTier(null);
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // User cancelled
      } else {
        console.error('Fallback folder scan error:', err);
        setDetectError(err.message || 'Failed to scan or upload local project folder.');
      }
    } finally {
      setLocalScanActive(false);
      setDetecting(false);
      abortControllerRef.current = null;
      if (e.target) e.target.value = '';
    }
  };

  const handleCancelLocalScan = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setLocalScanActive(false);
    setLocalScanProgress(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setLoading(true);
      setError(null);
      const hasOverrides = Object.keys(overrides).length > 0;

      const isLocal = sourceType === 'local';
      const cleanLocalPath = localPath.trim();
      const localRepoIdentifier = uploadedZipName
        ? `local://${uploadedZipName}`
        : (cleanLocalPath ? (cleanLocalPath.startsWith('local://') ? cleanLocalPath : `local://${cleanLocalPath}`) : `local://${localFolderName || 'project'}`);

      const cleanTargetPlan = targetPlan.trim();
      const firstLine = cleanTargetPlan.split('\n')[0].trim();
      const conciseTargetStack = (firstLine || 'TypeScript / Node.js 22 / NestJS').slice(0, 100);

      const derivedFallback = deriveProjectNameFromRepo(sourceRepo) || (localFolderName ? `${localFolderName} Modernization` : 'Legacy Modernization Project');
      const finalProjectName = name.trim() || derivedFallback;

      const created = await onSubmit({
        name: finalProjectName,
        source_repository: isLocal ? localRepoIdentifier : sourceRepo,
        source_revision: isLocal ? 'LOCAL' : revision,
        source_stack: sourceStack,
        target_stack: conciseTargetStack,
        budget,
        max_repair_attempts: maxRepairAttempts,
        constraints: cleanTargetPlan || undefined,
        pinned_commit: !isLocal ? (detectedStack?.resolved_commit || undefined) : undefined,
        user_overrides: hasOverrides ? overrides : undefined,
        stack_metadata: detectedStack || undefined,
        git_token: !isLocal ? (gitToken.trim() || undefined) : undefined,
        source_type: sourceType,
        preview_snapshot_id: isLocal ? (previewSnapshotId || undefined) : undefined,
        snapshot_fingerprint: isLocal ? (snapshotFingerprint || undefined) : undefined,
      });
      setGitToken('');
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
              <h2>1. Source Repository & Architecture Discovery</h2>
              <p>Provide a project identifier and select a Git repository or inspect a local project folder directly from your computer.</p>

              {/* Project Name Field */}
              <div className="form-field" style={{ marginBottom: '20px' }}>
                <label htmlFor="project-name" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                  <Layers size={14} color="var(--primary)" />
                  <span>Project Name</span>
                  <span style={{ color: 'var(--destructive, #ef4444)' }}>*</span>
                </label>
                <input
                  id="project-name"
                  type="text"
                  className="field"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setUserEditedName(true);
                  }}
                  placeholder="e.g., Cake Shop Modernization, SpendWise API"
                  required
                />
                <small>A descriptive name to identify this modernization pipeline in dashboards and approval gates.</small>
              </div>

              {/* Source Type Selector Tabs */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                <button
                  type="button"
                  onClick={() => {
                    setSourceType('git');
                    setDetectError(null);
                  }}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '8px 14px',
                    borderRadius: 'var(--radius-md)',
                    border: sourceType === 'git' ? '1px solid var(--primary)' : '1px solid var(--border)',
                    backgroundColor: sourceType === 'git' ? 'var(--accent)' : 'var(--card)',
                    color: sourceType === 'git' ? 'var(--primary)' : 'var(--muted-foreground)',
                    fontWeight: 600,
                    fontSize: '12px',
                    cursor: 'pointer',
                  }}
                >
                  <GitBranch size={14} />
                  <span>Git Remote Repository</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setSourceType('local');
                    setDetectError(null);
                  }}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '8px 14px',
                    borderRadius: 'var(--radius-md)',
                    border: sourceType === 'local' ? '1px solid var(--primary)' : '1px solid var(--border)',
                    backgroundColor: sourceType === 'local' ? 'var(--accent)' : 'var(--card)',
                    color: sourceType === 'local' ? 'var(--primary)' : 'var(--muted-foreground)',
                    fontWeight: 600,
                    fontSize: '12px',
                    cursor: 'pointer',
                  }}
                >
                  <Folder size={14} />
                  <span>Local Project Folder</span>
                </button>
              </div>



              {sourceType === 'git' ? (
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
                      if (!userEditedName) {
                        const derived = deriveProjectNameFromRepo(val);
                        if (derived) {
                          setName(derived);
                        }
                      }
                      if (detectError) setDetectError(null);
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

                <div className="form-field">
                  <label htmlFor="private-repo-toggle" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Lock size={14} color={showPatSection ? 'var(--primary)' : 'var(--muted-foreground)'} />
                    <span>Private Repository</span>
                  </label>
                  <div
                    style={{
                      height: '42px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '0 12px',
                      borderRadius: 'var(--radius-md)',
                      border: showPatSection ? '1px solid var(--primary)' : '1px solid var(--border)',
                      backgroundColor: showPatSection ? 'var(--accent)' : 'var(--card)',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                    onClick={() => {
                      const next = !showPatSection;
                      setIsPrivateRepo(next);
                      if (!next) {
                        setGitToken('');
                        handleDetectStack(sourceRepo, revision, '');
                      }
                    }}
                  >
                    <input
                      type="checkbox"
                      id="private-repo-toggle"
                      checked={showPatSection}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setIsPrivateRepo(checked);
                        if (!checked) {
                          setGitToken('');
                          handleDetectStack(sourceRepo, revision, '');
                        }
                      }}
                      style={{ cursor: 'pointer', accentColor: 'var(--primary)', width: '16px', height: '16px' }}
                    />
                    <span style={{ fontSize: '12px', fontWeight: 500, color: showPatSection ? 'var(--foreground)' : 'var(--muted-foreground)' }}>
                      {showPatSection ? 'Private repository enabled' : 'Requires Personal Access Token'}
                    </span>
                  </div>
                  <small>Enable if repository is private or requires credentials.</small>
                </div>

                {/* Private GitHub Repository Access Section - Only displayed when repository is private */}
                {showPatSection && (
                  <div
                    className="form-field span-two"
                    style={{
                      backgroundColor: 'var(--card)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)',
                      padding: '14px 16px',
                      marginTop: '4px',
                      marginBottom: '8px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <label
                        htmlFor="github-pat"
                        style={{
                          margin: 0,
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          color: 'var(--foreground)',
                        }}
                      >
                        <Lock size={14} color="var(--primary)" />
                        <span>Private Repository Access (GitHub Personal Access Token)</span>
                        <span
                          style={{
                            fontSize: '10px',
                            padding: '1px 6px',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor: 'var(--secondary)',
                            color: 'var(--primary)',
                            fontWeight: 600,
                          }}
                        >
                          Private Repo
                        </span>
                      </label>
                      <button
                        type="button"
                        onClick={() => {
                          setGitToken('');
                          setIsPrivateRepo(false);
                          handleDetectStack(sourceRepo, revision, '');
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--muted-foreground)',
                          fontSize: '11px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '2px 6px',
                        }}
                        title="Clear token and close private access section"
                      >
                        <X size={12} />
                        <span>{gitToken ? 'Clear Token' : 'Cancel'}</span>
                      </button>
                    </div>

                    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                      <input
                        id="github-pat"
                        type={showToken ? 'text' : 'password'}
                        className="field"
                        style={{ paddingRight: '40px', fontFamily: 'var(--font-mono)', fontSize: '13px' }}
                        value={gitToken}
                        onChange={(e) => setGitToken(e.target.value.trim())}
                        placeholder="github_pat_... or ghp_..."
                        autoComplete="off"
                        spellCheck={false}
                        autoFocus
                      />
                      <button
                        type="button"
                        onClick={() => setShowToken(!showToken)}
                        style={{
                          position: 'absolute',
                          right: '10px',
                          background: 'transparent',
                          border: 'none',
                          cursor: 'pointer',
                          color: 'var(--muted-foreground)',
                          display: 'flex',
                          alignItems: 'center',
                          padding: '4px',
                        }}
                        title={showToken ? 'Hide token' : 'Show token'}
                        aria-label={showToken ? 'Hide token' : 'Show token'}
                      >
                        {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>

                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: '8px',
                        marginTop: '8px',
                        fontSize: '11px',
                        color: 'var(--muted-foreground)',
                        lineHeight: '1.4',
                      }}
                    >
                      <Info size={14} style={{ flexShrink: 0, marginTop: '2px', color: 'var(--primary)' }} />
                      <div>
                        <span>
                          Required for private GitHub repositories. Provide a fine-grained PAT with <strong>Contents: Read-only</strong> access.
                          Never embed credentials into the repository URL. The token is kept strictly in memory for preview detection and job intake; it is never stored in browser storage, logs, or persistent database records.
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              ) : (
                /* Local Folder Path Input OR Direct ZIP Upload */
                <div>
                  <div className="form-grid">
                    <div className="form-field span-two">
                      <label htmlFor="local-project-path" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Folder size={14} color="var(--primary)" />
                        <span>Local Project Location (Folder Path on your PC)</span>
                      </label>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <input
                          id="local-project-path"
                          type="text"
                          className="field"
                          value={localPath}
                          onChange={(e) => {
                            setLocalPath(e.target.value);
                            if (uploadedZipName) {
                              setUploadedZipName(null);
                              setPreviewSnapshotId(null);
                            }
                            if (detectError) setDetectError(null);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              if (localPath.trim()) {
                                handleDetectLocalPath(localPath.trim());
                              }
                            }
                          }}
                          placeholder="e.g. C:\Users\EI 3\Desktop\my-legacy-app or /home/user/projects/legacy-app"
                        />
                        <button
                          type="button"
                          className="button button-primary"
                          onClick={() => {
                            if (localPath.trim()) {
                              handleDetectLocalPath(localPath.trim());
                            }
                          }}
                          disabled={detecting || !localPath.trim()}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', padding: '0 16px' }}
                        >
                          {detecting && !zipUploading ? (
                            <>
                              <RefreshCw size={14} className="spin" />
                              <span>Inspecting...</span>
                            </>
                          ) : (
                            <>
                              <Search size={14} />
                              <span>Detect Stack</span>
                            </>
                          )}
                        </button>
                      </div>
                      <small>
                        Paste the absolute folder path from your computer. Rebase inspects the manifests and source structure directly on this machine.
                      </small>
                    </div>
                  </div>

                  {/* Divider: OR */}
                  <div style={{ display: 'flex', alignItems: 'center', margin: '14px 0', gap: '12px' }}>
                    <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--border)' }} />
                    <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--muted-foreground)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      or
                    </span>
                    <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--border)' }} />
                  </div>

                  {/* Direct ZIP Upload Section */}
                  <div>
                    <input
                      type="file"
                      ref={zipInputRef}
                      accept=".zip,application/zip"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleZipFileSelected(file);
                        e.target.value = '';
                      }}
                    />

                    {uploadedZipName && detectedStack ? (
                      <div
                        style={{
                          padding: '12px 16px',
                          backgroundColor: 'var(--card)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-md)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          flexWrap: 'wrap',
                          gap: '12px',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <FileCode size={20} color="var(--primary)" />
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--foreground)' }}>
                                {uploadedZipName}
                              </span>
                              <span
                                style={{
                                  fontSize: '10px',
                                  padding: '2px 8px',
                                  borderRadius: 'var(--radius-full)',
                                  backgroundColor: 'var(--accent)',
                                  color: 'var(--primary)',
                                  fontWeight: 600,
                                }}
                              >
                                ZIP Staged for Intake
                              </span>
                            </div>
                            {snapshotFingerprint && (
                              <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--muted-foreground)', marginTop: '2px' }}>
                                Fingerprint: {snapshotFingerprint.slice(0, 16)}...
                              </div>
                            )}
                          </div>
                        </div>

                        <button
                          type="button"
                          className="button button-secondary button-sm"
                          onClick={() => zipInputRef.current?.click()}
                          style={{ fontSize: '11px' }}
                        >
                          Change ZIP
                        </button>
                      </div>
                    ) : (
                      <div
                        onClick={() => zipInputRef.current?.click()}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          const file = e.dataTransfer.files?.[0];
                          if (file) handleZipFileSelected(file);
                        }}
                        style={{
                          border: '1.5px dashed var(--border)',
                          borderRadius: 'var(--radius-md)',
                          padding: '18px 16px',
                          textAlign: 'center',
                          backgroundColor: 'var(--card)',
                          cursor: 'pointer',
                          transition: 'border-color 0.15s ease',
                        }}
                      >
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px' }}>
                          {zipUploading ? (
                            <>
                              <RefreshCw size={24} className="spin" color="var(--primary)" style={{ marginBottom: '4px' }} />
                              <span style={{ fontSize: '13px', fontWeight: 600 }}>Uploading and analyzing ZIP archive...</span>
                              <span style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Extracting manifests and computing canonical Merkle fingerprint</span>
                            </>
                          ) : (
                            <>
                              <UploadCloud size={24} color="var(--primary)" style={{ marginBottom: '2px', opacity: 0.85 }} />
                              <div style={{ fontSize: '13px', fontWeight: 600 }}>
                                Upload Project Archive (<span style={{ fontFamily: 'var(--font-mono)' }}>.ZIP</span>)
                              </div>
                              <span style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
                                Drag and drop a <code style={{ fontSize: '11px' }}>.zip</code> file here, or click to browse from your computer (max 100 MB)
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Verified On PC status badge for Folder Path mode */}
                  {detectedStack && sourceType === 'local' && !uploadedZipName && (
                    <div
                      style={{
                        marginTop: '12px',
                        padding: '10px 14px',
                        backgroundColor: 'var(--card)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-md)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        flexWrap: 'wrap',
                        gap: '12px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <FolderOpen size={16} color="var(--primary)" />
                        <span style={{ fontSize: '13px', fontWeight: 600 }}>{localFolderName || 'Local Project'}</span>
                        <span
                          style={{
                            fontSize: '10px',
                            padding: '2px 8px',
                            borderRadius: 'var(--radius-full)',
                            backgroundColor: 'var(--accent)',
                            color: 'var(--primary)',
                            fontWeight: 600,
                          }}
                        >
                          Verified On PC
                        </span>
                      </div>
                      {snapshotFingerprint && (
                        <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--muted-foreground)' }} title={snapshotFingerprint}>
                          Fingerprint: <strong>{snapshotFingerprint.slice(0, 12)}...</strong>
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="form-grid" style={{ marginTop: '16px' }}>
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
                        onClick={() => handleDetectStack(sourceRepo, revision, gitToken)}
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
                        onClick={() => handleDetectStack(sourceRepo, revision, gitToken)}
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
              <p>Specify your targeted technology stack, framework preferences, and architectural modernization plan.</p>

              <div className="form-grid">
                <div className="form-field span-two">
                  <label htmlFor="target-plan">Targeted Tech Stack & Modernization Plan</label>
                  <textarea
                    id="target-plan"
                    className="field"
                    rows={4}
                    value={targetPlan}
                    onChange={(e) => setTargetPlan(e.target.value)}
                    placeholder="Explain your targeted tech stack and modernization plan (e.g. Modernize to TypeScript 5.x / Node.js 22 LTS with NestJS framework. Preserve all ISO8583 settlement idempotency constraints.)"
                    required
                  />
                  <small>Injected into the Architect and CodeWriter prompt contracts to govern code generation.</small>
                </div>
              </div>
            </div>

            {/* Step 3: Guardrails & Budgets */}
            <div className="form-section">
              <h2>3. Autonomous Agent Guardrails</h2>
              <p>Hard limits to prevent runaway spend or cyclic loop repair deadlocks.</p>

              <div className="form-grid">
                <div className="form-field">
                  <label>Autonomous Budget Limit (₹ INR)</label>
                  <input
                    type="number"
                    className="field"
                    min={50}
                    max={1000000}
                    step={100}
                    value={budget}
                    onChange={(e) => setBudget(Number(e.target.value))}
                    onWheel={(e) => (e.target as HTMLElement).blur()}
                    placeholder="e.g. 15000"
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
                    onWheel={(e) => (e.target as HTMLElement).blur()}
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
