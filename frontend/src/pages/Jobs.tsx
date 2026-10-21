import React, { useState } from 'react';
import type { Job } from '../types/domain';
import { StatusBadge } from '../components/StatusBadge';
import { Search, Plus, GitBranch, ArrowRight, Filter } from 'lucide-react';

interface JobsProps {
  jobs: Job[];
  onNavigate: (path: string) => void;
}

export const Jobs: React.FC<JobsProps> = ({ jobs, onNavigate }) => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  const filtered = jobs.filter((j) => {
    const matchesSearch =
      j.name.toLowerCase().includes(search.toLowerCase()) ||
      j.job_id.toLowerCase().includes(search.toLowerCase()) ||
      j.source_repository.toLowerCase().includes(search.toLowerCase());

    if (!matchesSearch) return false;
    if (statusFilter === 'ALL') return true;
    if (statusFilter === 'AWAITING' && j.status.includes('AWAITING')) return true;
    if (statusFilter === 'ACTIVE' && (j.status === 'CONVERTING' || j.status === 'VERIFYING' || j.status === 'PLANNING')) return true;
    if (statusFilter === 'COMPLETED' && j.status === 'COMPLETED') return true;
    return j.status === statusFilter;
  });

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Modernization Jobs</h1>
          <p className="subtitle">
            Catalog of all legacy code migration jobs across repositories and branch targets.
          </p>
        </div>
        <div className="heading-actions">
          <button className="button button-primary" onClick={() => onNavigate('/jobs/new')}>
            <Plus size={14} />
            <span>New Modernization</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          marginBottom: '20px',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            className={`button button-sm ${statusFilter === 'ALL' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setStatusFilter('ALL')}
          >
            All ({jobs.length})
          </button>
          <button
            className={`button button-sm ${statusFilter === 'ACTIVE' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setStatusFilter('ACTIVE')}
          >
            Active Conversions
          </button>
          <button
            className={`button button-sm ${statusFilter === 'AWAITING' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setStatusFilter('AWAITING')}
          >
            Awaiting Gate
          </button>
          <button
            className={`button button-sm ${statusFilter === 'COMPLETED' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setStatusFilter('COMPLETED')}
          >
            Completed
          </button>
        </div>

        <div style={{ position: 'relative', width: '280px' }}>
          <Search
            size={14}
            style={{
              position: 'absolute',
              left: '10px',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'var(--muted-foreground)',
            }}
          />
          <input
            type="text"
            className="field"
            placeholder="Search by job ID, repo, or name..."
            style={{ paddingLeft: '32px' }}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Jobs Table */}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Job Identifier</th>
              <th>Source & Target Stack</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Cost Spend</th>
              <th>Owner</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: '40px', color: 'var(--muted-foreground)' }}>
                  No modernization jobs found matching criteria.
                </td>
              </tr>
            ) : (
              filtered.map((job) => (
                <tr key={job.job_id} style={{ cursor: 'pointer' }} onClick={() => onNavigate(`/jobs/${job.job_id}`)}>
                  <td>
                    <span className="job-name">{job.name}</span>
                    <span className="job-repo">
                      <GitBranch size={11} />
                      {job.job_id} · {job.source_repository.replace('https://github.com/', '')}
                    </span>
                  </td>
                  <td>
                    <div className="stack-cell">
                      <span className="stack-label">{job.source_stack}</span>
                      <ArrowRight size={10} color="var(--muted-foreground)" />
                      <span className="stack-label" style={{ backgroundColor: 'var(--accent)', color: 'var(--primary)' }}>
                        {job.target_stack}
                      </span>
                    </div>
                  </td>
                  <td>
                    <StatusBadge status={job.status} />
                  </td>
                  <td>
                    <div className="progress-row">
                      <div className="progress-track">
                        <div
                          className={`progress-fill ${job.status.includes('AWAITING') ? 'amber' : ''}`}
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                      <span>{job.progress}%</span>
                    </div>
                  </td>
                  <td>
                    <span style={{ fontWeight: 600 }}>${job.cost.toFixed(2)}</span>
                    <span style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}> / ${job.budget.toFixed(2)}</span>
                  </td>
                  <td>
                    <span style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>{job.owner}</span>
                  </td>
                  <td>
                    <button
                      className="button button-secondary button-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigate(`/jobs/${job.job_id}`);
                      }}
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
