import React, { useState, useMemo } from 'react';
import type { Job } from '../../types/domain';
import type { FileInventoryItem, DetectedTechnologyProfile } from '../../types/phase4';
import { FileStatusIndicator, FileAnalysisStatus } from './FileStatusIndicator';
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  FileSpreadsheet,
  FileJson,
  Search,
  X,
  ChevronDown,
  ChevronRight,
  GitBranch,
  GitCommit,
  Layers,
  Code2,
  Box,
  Loader2,
  CheckCircle2,
} from 'lucide-react';

interface ProjectExplorerProps {
  jobs: Job[];
  selectedJob: Job | null;
  onSelectJob: (jobId: string) => void;
  files: FileInventoryItem[];
  directories: string[];
  techProfile?: DetectedTechnologyProfile | null;
  sourceRef?: string;
  commitSha?: string | null;
  selectedFile: string | null;
  onSelectFile: (filePath: string) => void;
  fileStatuses?: Record<string, FileAnalysisStatus>;
  activeAnalyzingFile?: string | null;
  onRunIntake?: () => void;
  intakeRunning?: boolean;
  loading?: boolean;
}

export const ProjectExplorer: React.FC<ProjectExplorerProps> = ({
  jobs,
  selectedJob,
  onSelectJob,
  files,
  directories,
  techProfile,
  sourceRef,
  commitSha,
  selectedFile,
  onSelectFile,
  fileStatuses = {},
  activeAnalyzingFile,
  onRunIntake,
  intakeRunning = false,
  loading = false,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [collapsedDirs, setCollapsedDirs] = useState<Record<string, boolean>>({});

  const toggleDirectory = (dirPath: string) => {
    setCollapsedDirs((prev) => ({
      ...prev,
      [dirPath]: !prev[dirPath],
    }));
  };

  // Extract repo short name from source_ref or job name
  const repoName = useMemo(() => {
    if (!sourceRef && !selectedJob) return 'repository';
    const ref = sourceRef || selectedJob?.source_repository || '';
    const parts = ref.split('/');
    const last = parts[parts.length - 1];
    return last.replace(/\.git$/, '') || selectedJob?.name || 'repository';
  }, [sourceRef, selectedJob]);

  // Clean commit SHA display (short 7 chars)
  const shortSha = useMemo(() => {
    const sha = commitSha || selectedJob?.source_revision || 'main';
    return sha.length > 7 && !sha.includes('/') ? sha.substring(0, 7) : sha;
  }, [commitSha, selectedJob]);

  // File type icon resolver
  const getFileIcon = (filePath: string) => {
    const lower = filePath.toLowerCase();
    if (lower.endsWith('.py')) return <FileCode size={13} color="#3b82f6" />;
    if (lower.endsWith('.ts') || lower.endsWith('.tsx')) return <FileCode size={13} color="#2563eb" />;
    if (lower.endsWith('.js') || lower.endsWith('.jsx')) return <FileCode size={13} color="#eab308" />;
    if (lower.endsWith('.html')) return <Code2 size={13} color="#f97316" />;
    if (lower.endsWith('.css')) return <Code2 size={13} color="#06b6d4" />;
    if (lower.endsWith('.json') || lower.endsWith('.yaml') || lower.endsWith('.yml') || lower.endsWith('.toml')) {
      return <FileJson size={13} color="#10b981" />;
    }
    if (lower.endsWith('.md') || lower.endsWith('.txt')) return <FileText size={13} color="#8b5cf6" />;
    if (lower.endsWith('.sql') || lower.endsWith('.csv')) return <FileSpreadsheet size={13} color="#14b8a6" />;
    return <FileCode size={13} color="var(--muted-foreground)" />;
  };

  // Filter files based on search
  const filteredFiles = useMemo(() => {
    if (!searchQuery.trim()) return files;
    const query = searchQuery.toLowerCase().trim();
    return files.filter((f) => f.path.toLowerCase().includes(query));
  }, [files, searchQuery]);

  // Determine hierarchical tree or directory groups
  interface TreeNode {
    name: string;
    path: string;
    isDir: boolean;
    children: TreeNode[];
    fileItem?: FileInventoryItem;
  }

  const fileTree = useMemo(() => {
    const root: TreeNode = { name: '', path: '', isDir: true, children: [] };

    filteredFiles.forEach((file) => {
      const normalizedPath = file.path.replace(/\\/g, '/');
      const parts = normalizedPath.split('/').filter(Boolean);
      let current = root;

      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        const isLast = i === parts.length - 1;
        const currentPath = parts.slice(0, i + 1).join('/');

        if (isLast) {
          current.children.push({
            name: part,
            path: file.path,
            isDir: false,
            children: [],
            fileItem: file,
          });
        } else {
          let nextDir = current.children.find((c) => c.isDir && c.name === part);
          if (!nextDir) {
            nextDir = {
              name: part,
              path: currentPath,
              isDir: true,
              children: [],
            };
            current.children.push(nextDir);
          }
          current = nextDir;
        }
      }
    });

    // Sort: directories first, then alphabetical
    const sortNodes = (node: TreeNode) => {
      node.children.sort((a, b) => {
        if (a.isDir && !b.isDir) return -1;
        if (!a.isDir && b.isDir) return 1;
        return a.name.localeCompare(b.name);
      });
      node.children.forEach(sortNodes);
    };

    sortNodes(root);
    return root;
  }, [filteredFiles]);

  const renderTreeNode = (node: TreeNode, depth = 0) => {
    if (node.isDir) {
      const isCollapsed = collapsedDirs[node.path];
      return (
        <div key={node.path} style={{ display: 'flex', flexDirection: 'column' }}>
          <div
            onClick={() => toggleDirectory(node.path)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 8px',
              paddingLeft: `${depth * 14 + 8}px`,
              cursor: 'pointer',
              userSelect: 'none',
              borderRadius: 'var(--radius-sm, 4px)',
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--foreground)',
              transition: 'background-color 0.15s ease',
            }}
            className="file-tree-node dir-node"
          >
            {isCollapsed ? (
              <ChevronRight size={12} color="var(--muted-foreground)" />
            ) : (
              <ChevronDown size={12} color="var(--muted-foreground)" />
            )}
            {isCollapsed ? (
              <Folder size={13} color="#f59e0b" />
            ) : (
              <FolderOpen size={13} color="#f59e0b" />
            )}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {node.name}/
            </span>
            <span style={{ fontSize: '9px', color: 'var(--muted-foreground)', marginLeft: 'auto' }}>
              {node.children.length}
            </span>
          </div>

          {!isCollapsed && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {node.children.map((child) => renderTreeNode(child, depth + 1))}
            </div>
          )}
        </div>
      );
    }

    // It is a file node
    const isSelected = selectedFile === node.path;
    const isCurrentlyAnalyzing = activeAnalyzingFile === node.path;
    const assignedStatus: FileAnalysisStatus =
      isCurrentlyAnalyzing
        ? 'ANALYZING'
        : fileStatuses[node.path] || (node.fileItem?.is_manifest ? 'ANALYZED' : 'PENDING');

    return (
      <div
        key={node.path}
        id={`file-node-${node.path.replace(/[^a-zA-Z0-9_-]/g, '_')}`}
        onClick={() => onSelectFile(node.path)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '4px 8px',
          paddingLeft: `${depth * 14 + 18}px`,
          cursor: 'pointer',
          borderRadius: 'var(--radius-sm, 4px)',
          fontSize: '11px',
          backgroundColor: isSelected
            ? 'var(--accent, #e0f2fe)'
            : isCurrentlyAnalyzing
            ? 'rgba(2, 132, 199, 0.08)'
            : 'transparent',
          borderLeft: isSelected
            ? '2px solid var(--primary, #0284c7)'
            : isCurrentlyAnalyzing
            ? '2px solid var(--warning, #f59e0b)'
            : '2px solid transparent',
          transition: 'all 0.15s ease',
        }}
        className={`file-tree-node file-item ${isSelected ? 'selected' : ''}`}
        title={`Click to inspect agent context for: ${node.path}`}
      >
        {getFileIcon(node.path)}
        <span
          style={{
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            color: isSelected ? 'var(--primary, #0284c7)' : 'inherit',
            fontWeight: isSelected ? 650 : 450,
          }}
        >
          {node.name}
        </span>
        <FileStatusIndicator status={assignedStatus} compact={false} />
      </div>
    );
  };

  const detectedLanguages = useMemo(() => {
    if (!techProfile?.languages) return [];
    return Object.entries(techProfile.languages)
      .sort((a, b) => b[1] - a[1])
      .map(([lang, pct]) => `${lang} ${pct.toFixed(0)}%`);
  }, [techProfile]);

  const detectedFrameworks = techProfile?.frameworks || [];

  return (
    <div
      className="project-explorer-panel"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: 'var(--card, #ffffff)',
        borderRight: '1px solid var(--border)',
        overflow: 'hidden',
      }}
    >
      {/* Header section with job metadata */}
      <div
        className="project-explorer-header"
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--secondary, #f8fafc)',
        }}
      >
        {/* Job selector dropdown */}
        <div style={{ marginBottom: '12px' }}>
          <label
            htmlFor="job-repository-select"
            style={{
              fontSize: '10px',
              textTransform: 'uppercase',
              letterSpacing: '0.6px',
              fontWeight: 700,
              color: 'var(--muted-foreground)',
              display: 'block',
              marginBottom: '5px',
            }}
          >
            Job Repository
          </label>
          <select
            id="job-repository-select"
            className="job-select-control"
            style={{
              width: '100%',
              height: '32px',
              padding: '4px 8px',
              fontSize: '11px',
              fontWeight: 600,
              backgroundColor: 'var(--background)',
              color: 'var(--foreground)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm, 4px)',
              cursor: 'pointer',
              outline: 'none',
              boxShadow: 'var(--shadow-sm)',
            }}
            value={selectedJob?.job_id || ''}
            onChange={(e) => onSelectJob(e.target.value)}
          >
            {jobs.length === 0 ? (
              <option value="">Loading jobs...</option>
            ) : (
              jobs.map((j) => (
                <option key={j.job_id} value={j.job_id}>
                  {j.name} ({j.status})
                </option>
              ))
            )}
          </select>
        </div>

        {/* Title and File count */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
          <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--foreground)' }}>
            Project Explorer
          </span>
          <span className="badge gray" style={{ fontSize: '10px', fontWeight: 650 }}>
            {files.length} Files
          </span>
        </div>

        {/* Repo Name */}
        <div style={{ fontSize: '12px', fontWeight: 650, color: 'var(--primary, #0284c7)', marginBottom: '3px' }}>
          {repoName}
        </div>

        {/* Source Reference & Commit SHA */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '10px',
            color: 'var(--muted-foreground)',
            marginBottom: '8px',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
            <GitBranch size={11} />
            <span>GitHub</span>
          </span>
          <span>·</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
            <GitCommit size={11} />
            <span style={{ fontFamily: 'monospace' }}>main@{shortSha}</span>
          </span>
        </div>

        {/* Converted Modern Modules Status Badge */}
        {(selectedJob?.status === 'CONVERTING' || selectedJob?.status === 'VERIFYING' || selectedJob?.status === 'INTEGRATING' || selectedJob?.status === 'AWAITING_GATE_G4' || selectedJob?.status === 'COMPLETED') && (
          <div style={{ marginTop: '8px', marginBottom: '8px' }}>
            <a
              href="#/modules"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '6px 10px',
                backgroundColor: 'rgba(22, 163, 74, 0.08)',
                border: '1px solid rgba(22, 163, 74, 0.3)',
                borderRadius: '6px',
                textDecoration: 'none',
                color: '#16a34a',
                fontSize: '11px',
                fontWeight: 650,
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <CheckCircle2 size={13} />
                <span>Converted Code & Diffs</span>
              </span>
              <span style={{ fontSize: '10px', opacity: 0.8 }}>View Modules &rarr;</span>
            </a>
          </div>
        )}

        {/* Tech stack tags */}
        {(detectedLanguages.length > 0 || detectedFrameworks.length > 0) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '6px' }}>
            {detectedLanguages.slice(0, 2).map((lang) => (
              <span
                key={lang}
                className="badge blue"
                style={{ fontSize: '9px', padding: '1px 5px', fontWeight: 600 }}
              >
                {lang}
              </span>
            ))}
            {detectedFrameworks.slice(0, 2).map((fw) => (
              <span
                key={fw}
                className="badge purple"
                style={{ fontSize: '9px', padding: '1px 5px', fontWeight: 600 }}
              >
                {fw}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Filter and Search Box */}
      <div
        style={{
          padding: '8px 12px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          backgroundColor: 'var(--background)',
        }}
      >
        <Search size={12} color="var(--muted-foreground)" />
        <input
          type="text"
          placeholder="Filter files..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            border: 'none',
            outline: 'none',
            fontSize: '11px',
            width: '100%',
            backgroundColor: 'transparent',
            color: 'var(--foreground)',
          }}
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            style={{
              padding: '2px',
              background: 'none',
              border: 'none',
              color: 'var(--muted-foreground)',
              cursor: 'pointer',
            }}
          >
            <X size={11} />
          </button>
        )}
      </div>

      {/* File Tree List — Independently scrollable */}
      <div
        className="project-explorer-tree-scroll"
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '8px 6px',
        }}
      >
        {loading ? (
          <div style={{ padding: '28px 16px', textAlign: 'center', color: 'var(--muted-foreground)', fontSize: '11px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
            <Loader2 size={16} className="spin-animation" color="var(--primary, #0284c7)" />
            <span>Loading repository files...</span>
          </div>
        ) : filteredFiles.length === 0 ? (
          <div style={{ padding: '24px 16px', textAlign: 'center', color: 'var(--muted-foreground)', fontSize: '11px' }}>
            {searchQuery ? (
              `No files match "${searchQuery}"`
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
                <span>No files in repository inventory.</span>
                {onRunIntake && (
                  <button
                    type="button"
                    onClick={onRunIntake}
                    disabled={intakeRunning}
                    style={{
                      marginTop: '4px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '5px 10px',
                      fontSize: '11px',
                      fontWeight: 600,
                      backgroundColor: 'var(--primary, #0284c7)',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: 'var(--radius-sm, 4px)',
                      cursor: intakeRunning ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {intakeRunning ? <Loader2 size={12} className="spin-animation" /> : null}
                    <span>{intakeRunning ? 'Running Intake...' : 'Run Repository Intake'}</span>
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
            {fileTree.children.map((child) => renderTreeNode(child, 0))}
          </div>
        )}
      </div>

      {/* Footer count summary */}
      <div
        style={{
          padding: '6px 12px',
          borderTop: '1px solid var(--border)',
          fontSize: '10px',
          color: 'var(--muted-foreground)',
          backgroundColor: 'var(--secondary, #f8fafc)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span>Directories: {directories.length}</span>
        <span>Showing: {filteredFiles.length} / {files.length}</span>
      </div>
    </div>
  );
};
