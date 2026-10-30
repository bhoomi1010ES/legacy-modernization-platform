from pathlib import Path
import re

# 1. Patch frontend/src/components/Layout.tsx
layout_file = Path("frontend/src/components/Layout.tsx")
content = layout_file.read_text(encoding="utf-8")

content = content.replace(
    "import type { User } from '../types/domain';",
    "import type { User, Job } from '../types/domain';"
)

content = content.replace(
    """interface LayoutProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  user: User | null;
  pendingGatesCount: number;
  onLogout?: () => void;
  children: React.ReactNode;
}""",
    """interface LayoutProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  user: User | null;
  pendingGatesCount: number;
  activeJob?: Job | null;
  onLogout?: () => void;
  children: React.ReactNode;
}"""
)

content = content.replace(
    """export const Layout: React.FC<LayoutProps> = ({
  currentPath,
  onNavigate,
  user,
  pendingGatesCount,
  onLogout,
  children,
}) => {""",
    """export const Layout: React.FC<LayoutProps> = ({
  currentPath,
  onNavigate,
  user,
  pendingGatesCount,
  activeJob,
  onLogout,
  children,
}) => {"""
)

old_workspace_selector = """        <div className="workspace-selector">
          <div className="workspace-icon">
            <ShieldCheck size={14} />
          </div>
          <div>
            <div style={{ fontSize: '11px', fontWeight: 650 }}>Acme Corp Enterprise</div>
            <div style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>Java → TypeScript Slice</div>
          </div>
        </div>"""

new_workspace_selector = """        <div className="workspace-selector">
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
        </div>"""

if old_workspace_selector in content:
    content = content.replace(old_workspace_selector, new_workspace_selector)
    print("Replaced Acme Corp Enterprise in Layout.tsx")
else:
    print("Warning: old_workspace_selector not found in Layout.tsx")

content = content.replace(
    "{user ? user.full_name : 'Alex Morgan'}",
    "{user ? user.full_name : 'Authorized User'}"
)
content = content.replace(
    "{user ? user.full_name.substring(0, 2).toUpperCase() : 'AM'}",
    "{user ? user.full_name.substring(0, 2).toUpperCase() : 'AU'}"
)

layout_file.write_text(content, encoding="utf-8")
print("Saved Layout.tsx")

# 2. Patch frontend/src/App.tsx
app_file = Path("frontend/src/App.tsx")
content = app_file.read_text(encoding="utf-8")

content = content.replace(
    "return <Verification onNavigate={navigate} />;",
    "return <Verification jobs={jobs} onNavigate={navigate} />;"
)

old_layout_call = """  return (
    <Layout
      currentPath={currentPath}
      onNavigate={navigate}
      user={user}
      pendingGatesCount={pendingGatesCount}
      onLogout={handleLogout}
    >
      {renderContent()}
    </Layout>
  );"""

new_layout_call = """  const activeJobId = typeof localStorage !== 'undefined' ? localStorage.getItem('rebase_active_job_id') : null;
  const activeJob = jobs.find((j) => j.job_id === activeJobId) || jobs[0] || null;

  return (
    <Layout
      currentPath={currentPath}
      onNavigate={navigate}
      user={user}
      pendingGatesCount={pendingGatesCount}
      activeJob={activeJob}
      onLogout={handleLogout}
    >
      {renderContent()}
    </Layout>
  );"""

if old_layout_call in content:
    content = content.replace(old_layout_call, new_layout_call)
    print("Updated Layout call in App.tsx with activeJob")
else:
    print("Warning: old_layout_call not found in App.tsx")

app_file.write_text(content, encoding="utf-8")
print("Saved App.tsx")

# 3. Patch frontend/src/pages/Verification.tsx
verif_file = Path("frontend/src/pages/Verification.tsx")
content = verif_file.read_text(encoding="utf-8")

content = content.replace(
    "import type { VerificationReportResponse } from '../types/api';",
    "import type { VerificationReportResponse } from '../types/api';\nimport type { Job } from '../types/domain';"
)

content = content.replace(
    """interface VerificationProps {
  onNavigate: (path: string) => void;
}""",
    """interface VerificationProps {
  jobs?: Job[];
  onNavigate: (path: string) => void;
}"""
)

content = content.replace(
    """export const Verification: React.FC<VerificationProps> = ({ onNavigate }) => {
  const [report, setReport] = useState<VerificationReportResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadReport();
  }, []);

  const loadReport = async () => {
    try {
      setLoading(true);
      const data = await api.getVerificationReport('JOB-0248');
      setReport(data);
    } finally {
      setLoading(false);
    }
  };""",
    """export const Verification: React.FC<VerificationProps> = ({ jobs = [], onNavigate }) => {
  const getInitialJobId = () => {
    try {
      const saved = localStorage.getItem('rebase_active_job_id');
      if (saved && jobs.some(j => j.job_id === saved)) return saved;
    } catch {}
    return jobs[0]?.job_id || '';
  };
  const [selectedJobId, setSelectedJobId] = useState(getInitialJobId);
  const [report, setReport] = useState<VerificationReportResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const activeJob = jobs.find(j => j.job_id === selectedJobId) || jobs[0] || null;

  useEffect(() => {
    if (selectedJobId) {
      loadReport(selectedJobId);
    }
  }, [selectedJobId]);

  const loadReport = async (jobId: string) => {
    try {
      setLoading(true);
      const data = await api.getVerificationReport(jobId);
      setReport(data);
    } catch {
      setReport(null);
    } finally {
      setLoading(false);
    }
  };"""
)

content = content.replace(
    "Parallel replay of frozen characterization vectors across legacy Java and converted TypeScript services.",
    "{`Parallel replay of frozen characterization vectors across legacy ${activeJob?.source_stack || 'source'} and modern ${activeJob?.target_stack || 'target'} implementations.`}"
)

verif_file.write_text(content, encoding="utf-8")
print("Saved Verification.tsx")

# 4. Patch frontend/src/components/GateReviewModal.tsx
modal_file = Path("frontend/src/components/GateReviewModal.tsx")
content = modal_file.read_text(encoding="utf-8")

content = content.replace(
    "by <strong>{gate.reviewer || 'Alex Morgan (Lead Architect)'}</strong>",
    "by <strong>{gate.reviewer || 'Recorded Reviewer'}</strong>"
)

content = content.replace(
    "<small>Signed with your corporate identity Alex Morgan (Lead Architect).</small>",
    "<small>Signed with your corporate identity {activeJob?.owner || 'Authorized Lead Reviewer'}.</small>"
)

modal_file.write_text(content, encoding="utf-8")
print("Saved GateReviewModal.tsx")

