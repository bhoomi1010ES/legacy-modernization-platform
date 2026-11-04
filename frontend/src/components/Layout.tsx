import React from 'react';
import {
  Layers,
  LayoutDashboard,
  CheckCircle,
  FileCode,
  FolderArchive,
  Terminal,
  Activity,
  FileSpreadsheet,
  History,
  BookOpen,
  Settings,
  Plus,
  Search,
  ExternalLink,
  LogOut,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import type { User, Job } from '../types/domain';

interface LayoutProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  user: User | null;
  pendingGatesCount: number;
  activeJob?: Job | null;
  onLogout?: () => void;
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({
  currentPath,
  onNavigate,
  user,
  pendingGatesCount,
  activeJob,
  onLogout,
  children,
}) => {
  const getBreadcrumbs = () => {
    switch (currentPath) {
      case '/dashboard':
        return ['Platform', 'Modernization Command Center'];
      case '/jobs':
        return ['Platform', 'Modernization Jobs'];
      case '/jobs/new':
        return ['Jobs', 'New Modernization Wizard'];
      case '/approvals':
        return ['Governance', 'Approval Gates (G1–G4)'];
      case '/agents':
        return ['Multi-Agent Systems', '11 Specialist Agents'];
      case '/artifacts':
        return ['Storage', 'Versioned Artifact Lineage'];
      case '/verification':
        return ['Quality Assurance', 'Dual-Harness Equivalence'];
      case '/characterization':
        return ['Quality Assurance', 'Characterization & Schema Review'];
      case '/modules':
        return ['Modernization', 'Module Execution & Repair'];
      case '/reports':
        return ['Delivery', 'Readiness & Cutover Packages'];
      case '/audit':
        return ['Compliance', 'Append-Only Audit Trail'];
      case '/catalog':
        return ['Architecture', 'Modernization Pattern Catalog'];
      case '/settings':
        return ['Platform', 'Workspace & Security Policies'];
      case '/code':
        return ['IDE', 'Multi-Pane Agent Code Workspace'];
      default:
        if (currentPath.startsWith('/jobs/')) {
          return ['Jobs', currentPath.replace('/jobs/', '')];
        }
        return ['Platform', 'Overview'];
    }
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <div className="workspace">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand" onClick={() => onNavigate('/dashboard')} style={{ cursor: 'pointer' }}>
          <Layers className="brand-mark" />
          <span>Rebase<span className="brand-dot">.</span></span>
        </div>

        <div className="workspace-selector">
          <div className="workspace-icon">
            <ShieldCheck size={14} />
          </div>
          <div style={{ overflow: 'hidden' }}>
            <div style={{ fontSize: '11px', fontWeight: 650, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '170px' }}>
              {activeJob?.name || (user?.full_name ? `${user.full_name}'s Workspace` : 'Modernization Platform')}
            </div>
            <div style={{ fontSize: '9px', color: 'var(--muted-foreground)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '170px' }}>
              {activeJob?.source_stack && activeJob?.target_stack
                ? `${activeJob.source_stack} → ${activeJob.target_stack}`
                : activeJob?.job_id
                ? `Job #${activeJob.job_id.slice(0, 8)} · ${activeJob.status}`
                : 'Enterprise Multi-Agent Workspace'}
            </div>
          </div>
        </div>

        {/* Section 1: Core Modernization */}
        <div className="nav-label">Modernization</div>
        <a
          href="#/dashboard"
          className={`nav-item ${currentPath === '/dashboard' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/dashboard'); }}
        >
          <LayoutDashboard size={15} />
          <span>Dashboard</span>
        </a>
        <a
          href="#/jobs"
          className={`nav-item ${currentPath === '/jobs' || currentPath.startsWith('/jobs/') ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/jobs'); }}
        >
          <Layers size={15} />
          <span>Modernization Jobs</span>
        </a>
        <a
          href="#/approvals"
          className={`nav-item ${currentPath === '/approvals' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/approvals'); }}
        >
          <CheckCircle size={15} />
          <span>Approval Gates</span>
          {pendingGatesCount > 0 && <span className="nav-count">{pendingGatesCount}</span>}
        </a>
        <a
          href="#/agents"
          className={`nav-item ${currentPath === '/agents' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/agents'); }}
        >
          <Terminal size={15} />
          <span>Agent Workspace</span>
        </a>
        <a
          href="#/artifacts"
          className={`nav-item ${currentPath === '/artifacts' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/artifacts'); }}
        >
          <FolderArchive size={15} />
          <span>Artifact Lineage</span>
        </a>
        <a
          href="#/code"
          className={`nav-item ${currentPath === '/code' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/code'); }}
        >
          <FileCode size={15} />
          <span>Code Workspace</span>
        </a>

        {/* Section 2: Quality & Assurance */}
        <a href="#/modules" className={`nav-item ${currentPath === '/modules' ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); onNavigate('/modules'); }}>
          <FileCode size={15} /><span>Module Execution &amp; Repair</span>
        </a>
        <div className="nav-label">Governance & QA</div>
        <a href="#/characterization" className={`nav-item ${currentPath === '/characterization' ? 'active' : ''}`} onClick={(e) => { e.preventDefault(); onNavigate('/characterization'); }}>
          <ShieldCheck size={15} /><span>Characterization &amp; Schema</span>
        </a>
        <a
          href="#/verification"
          className={`nav-item ${currentPath === '/verification' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/verification'); }}
        >
          <Activity size={15} />
          <span>Verification & Drift</span>
        </a>
        <a
          href="#/reports"
          className={`nav-item ${currentPath === '/reports' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/reports'); }}
        >
          <FileSpreadsheet size={15} />
          <span>Delivery Reports</span>
        </a>
        <a
          href="#/audit"
          className={`nav-item ${currentPath === '/audit' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/audit'); }}
        >
          <History size={15} />
          <span>Audit Trail</span>
        </a>

        {/* Section 3: Platform */}
        <div className="nav-label">Platform</div>
        <a
          href="#/catalog"
          className={`nav-item ${currentPath === '/catalog' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/catalog'); }}
        >
          <BookOpen size={15} />
          <span>Pattern Catalog</span>
        </a>
        <a
          href="#/settings"
          className={`nav-item ${currentPath === '/settings' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('/settings'); }}
        >
          <Settings size={15} />
          <span>Policy & Budgets</span>
        </a>

        {/* Sidebar Footer */}
        <div className="sidebar-bottom">
          <div className="system-health">
            <span className="dot" />
            <span>Platform v1.0.0 · Healthy</span>
          </div>

          <div className="profile">
            <div className="avatar">
              {user ? user.full_name.substring(0, 2).toUpperCase() : 'AU'}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 650, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {user ? user.full_name : 'Authorized User'}
              </div>
              <small>Signed in</small>
            </div>
            <button
              onClick={() => {
                if (onLogout) {
                  onLogout();
                } else {
                  onNavigate('/login');
                }
              }}
              title="Logout / Switch User"
              style={{ padding: '4px', color: 'var(--muted-foreground)', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Column */}
      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            <span>{breadcrumbs[0]}</span>
            <ChevronRight size={13} />
            <strong>{breadcrumbs[1]}</strong>
          </div>

          <div className="topbar-tools">
            <div className="search-trigger">
              <Search size={13} />
              <span>Search jobs, hashes...</span>
              <kbd>Ctrl K</kbd>
            </div>

            <button
              className="button button-primary button-sm"
              onClick={() => onNavigate('/jobs/new')}
            >
              <Plus size={14} />
              <span>New Job</span>
            </button>
          </div>
        </header>

        <section className={`content ${currentPath === '/code' ? 'content-workspace-flush' : ''}`}>
          {children}
        </section>
      </main>
    </div>
  );
};
