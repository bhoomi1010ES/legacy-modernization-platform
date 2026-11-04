import React, { useState } from 'react';
import {
  CheckCircle2,
  Clock,
  Loader2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronRight,
  FileCode,
  Users,
  RotateCcw,
  Sparkles,
  ExternalLink,
} from 'lucide-react';

export type AgentExecutionStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'BLOCKED'
  | 'ACTION_REQUIRED';

export interface SpecializedWorker {
  name: string;
  type: string;
  status: 'Pending' | 'Running' | 'Completed' | 'Failed' | 'Partial';
  currentFile?: string;
  summary?: string;
}

export interface AgentCardData {
  id: string;
  name: string;
  phaseNumber: number;
  status: AgentExecutionStatus;
  shortDescription: string;
  currentActivity?: string;
  currentFile?: string;
  fileLines?: string;
  elapsedTime?: string;
  progressPercent?: number;
  completedWorkers?: number;
  totalWorkers?: number;
  lastOperation?: string;
  resultSummary?: string[];
  errorMessage?: string;
  failedFile?: string;
  workers?: SpecializedWorker[];
  isGate?: boolean;
  gateType?: 'G1' | 'G2' | 'G3' | 'G4';
  onActionRequired?: () => void;
  onRetry?: () => void;
}

interface AgentCardProps {
  agent: AgentCardData;
  defaultExpanded?: boolean;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, defaultExpanded = false }) => {
  const [expanded, setExpanded] = useState<boolean>(
    defaultExpanded || agent.status === 'RUNNING' || agent.status === 'ACTION_REQUIRED' || agent.status === 'BLOCKED' || agent.status === 'FAILED'
  );

  const getStatusBadge = () => {
    switch (agent.status) {
      case 'RUNNING':
        return (
          <span
            className="badge blue"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '10px',
              fontWeight: 700,
            }}
          >
            <Loader2 size={11} className="spin-animation" />
            <span>Running</span>
          </span>
        );
      case 'COMPLETED':
        return (
          <span
            className="badge green"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '10px',
              fontWeight: 700,
            }}
          >
            <CheckCircle2 size={11} />
            <span>Completed</span>
          </span>
        );
      case 'ACTION_REQUIRED':
        return (
          <span
            className="badge orange"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '10px',
              fontWeight: 700,
              backgroundColor: 'var(--warning-surface, #fffbeb)',
              color: 'var(--warning, #b45309)',
              border: '1px solid var(--warning, #f59e0b)',
            }}
          >
            <AlertTriangle size={11} />
            <span>ACTION REQUIRED</span>
          </span>
        );
      case 'FAILED':
        return (
          <span
            className="badge red"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '10px',
              fontWeight: 700,
            }}
          >
            <XCircle size={11} />
            <span>Failed</span>
          </span>
        );
      case 'BLOCKED':
        return (
          <span className="badge orange" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '10px', fontWeight: 700 }}>
            <AlertTriangle size={11} />
            <span>Blocked</span>
          </span>
        );
      case 'PENDING':
      default:
        return (
          <span
            className="badge gray"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '10px',
              fontWeight: 600,
              opacity: 0.7,
            }}
          >
            <Clock size={10} />
            <span>Pending</span>
          </span>
        );
    }
  };

  const isPending = agent.status === 'PENDING';

  return (
    <div
      className={`agent-card agent-card-${agent.status.toLowerCase()} ${isPending ? 'agent-card-dimmed' : ''}`}
      style={{
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md, 6px)',
        backgroundColor: 'var(--card, #ffffff)',
        boxShadow: agent.status === 'RUNNING' ? '0 2px 8px rgba(2, 132, 199, 0.12)' : 'var(--shadow-sm)',
        marginBottom: '10px',
        overflow: 'hidden',
        transition: 'all 0.2s ease',
        opacity: isPending ? 0.75 : 1,
      }}
    >
      {/* Header bar */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          cursor: 'pointer',
          backgroundColor:
            agent.status === 'RUNNING'
              ? 'rgba(2, 132, 199, 0.04)'
              : agent.status === 'ACTION_REQUIRED' || agent.status === 'BLOCKED'
              ? 'rgba(245, 158, 11, 0.05)'
              : 'transparent',
          borderBottom: expanded ? '1px solid var(--border)' : 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ color: 'var(--muted-foreground)' }}>
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--foreground)' }}>
                {agent.name}
              </span>
              {agent.isGate && (
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 700,
                    padding: '1px 5px',
                    borderRadius: '3px',
                    backgroundColor: 'var(--secondary, #f1f5f9)',
                    color: 'var(--muted-foreground)',
                  }}
                >
                  GATE {agent.gateType}
                </span>
              )}
            </div>

            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
              {agent.shortDescription}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {agent.elapsedTime && (
            <span style={{ fontSize: '11px', color: 'var(--muted-foreground)', display: 'flex', alignItems: 'center', gap: '3px' }}>
              <Clock size={11} />
              <span>{agent.elapsedTime}</span>
            </span>
          )}
          {getStatusBadge()}
        </div>
      </div>

      {/* Expanded Details Body */}
      {expanded && (
        <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {/* Prominent Current Activity Section (for running or active agents) */}
          {agent.currentActivity && (
            <div
              style={{
                border: '1px solid rgba(2, 132, 199, 0.25)',
                backgroundColor: 'rgba(2, 132, 199, 0.04)',
                borderRadius: 'var(--radius-sm, 4px)',
                padding: '10px 12px',
              }}
            >
              <div
                style={{
                  fontSize: '10px',
                  textTransform: 'uppercase',
                  fontWeight: 700,
                  letterSpacing: '0.5px',
                  color: 'var(--primary, #0284c7)',
                  marginBottom: '4px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                }}
              >
                <Loader2 size={11} className="spin-animation" />
                <span>Current Activity</span>
              </div>
              <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--foreground)' }}>
                {agent.currentActivity}
              </div>
              {agent.currentFile && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    marginTop: '4px',
                    fontSize: '11px',
                    color: 'var(--muted-foreground)',
                  }}
                >
                  <FileCode size={12} color="var(--primary)" />
                  <span style={{ fontFamily: 'monospace' }}>{agent.currentFile}</span>
                  {agent.fileLines && <span className="badge gray" style={{ fontSize: '9px' }}>{agent.fileLines}</span>}
                </div>
              )}
            </div>
          )}

          {/* Action Required Gate Review Button */}
          {agent.status === 'ACTION_REQUIRED' && (
            <div
              style={{
                border: '1px solid var(--warning, #f59e0b)',
                backgroundColor: 'rgba(245, 158, 11, 0.08)',
                borderRadius: 'var(--radius-sm, 4px)',
                padding: '12px 14px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--warning, #b45309)' }}>
                  Human Review & Approval Required
                </div>
                <div style={{ fontSize: '11px', color: 'var(--foreground)', marginTop: '2px' }}>
                  Critical architectural checkpoints and feasibility criteria require human verification before advancing.
                </div>
              </div>
              {agent.onActionRequired && (
                <button
                  className="button button-primary button-sm"
                  onClick={agent.onActionRequired}
                  style={{ whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '5px' }}
                >
                  <Sparkles size={12} />
                  <span>Review & Decide</span>
                </button>
              )}
            </div>
          )}

          {/* Error State */}
          {agent.status === 'FAILED' && (
            <div
              style={{
                border: '1px solid var(--destructive, #dc2626)',
                backgroundColor: 'rgba(220, 38, 38, 0.05)',
                borderRadius: 'var(--radius-sm, 4px)',
                padding: '12px 14px',
              }}
            >
              <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--destructive, #dc2626)', marginBottom: '4px' }}>
                Agent Execution Error
              </div>
              {agent.failedFile && (
                <div style={{ fontSize: '11px', color: 'var(--foreground)', marginBottom: '4px' }}>
                  <strong>Unable to analyze:</strong>{' '}
                  <span style={{ fontFamily: 'monospace' }}>{agent.failedFile}</span>
                </div>
              )}
              <div style={{ fontSize: '11px', color: 'var(--foreground)', marginBottom: '10px' }}>
                <strong>Reason:</strong> {agent.errorMessage || 'Execution timeout or worker failure'}
              </div>
              {agent.onRetry && (
                <button
                  className="button button-secondary button-sm"
                  onClick={agent.onRetry}
                  style={{ display: 'flex', alignItems: 'center', gap: '5px' }}
                >
                  <RotateCcw size={12} />
                  <span>Retry Agent</span>
                </button>
              )}
            </div>
          )}

          {agent.status === 'BLOCKED' && (
            <div style={{ border: '1px solid var(--warning, #f59e0b)', backgroundColor: 'rgba(245, 158, 11, 0.08)', borderRadius: 'var(--radius-sm, 4px)', padding: '12px 14px' }}>
              <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--warning, #b45309)', marginBottom: '4px' }}>Agent Blocked</div>
              <div style={{ fontSize: '11px', color: 'var(--foreground)' }}>
                {agent.errorMessage || 'Required runtime or evidence is unavailable; this agent did not complete its work.'}
              </div>
            </div>
          )}

          {/* Worker List Section (e.g. for Analysis Coordinator) */}
          {agent.workers && agent.workers.length > 0 && (
            <div style={{ marginTop: '2px' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '8px',
                }}
              >
                <span
                  style={{
                    fontSize: '10px',
                    textTransform: 'uppercase',
                    fontWeight: 700,
                    letterSpacing: '0.5px',
                    color: 'var(--muted-foreground)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <Users size={11} />
                  <span>Specialized Workers</span>
                </span>
                <span style={{ fontSize: '10px', fontWeight: 600, color: 'var(--muted-foreground)' }}>
                  {agent.completedWorkers ?? agent.workers.filter((w) => w.status === 'Completed').length} / {agent.workers.length} completed
                </span>
              </div>

              {/* Progress bar */}
              <div
                style={{
                  height: '4px',
                  backgroundColor: 'var(--secondary, #f1f5f9)',
                  borderRadius: '2px',
                  overflow: 'hidden',
                  marginBottom: '10px',
                }}
              >
                <div
                  style={{
                    height: '100%',
                    backgroundColor: 'var(--primary, #0284c7)',
                    width: `${
                      ((agent.completedWorkers ?? agent.workers.filter((w) => w.status === 'Completed').length) /
                        agent.workers.length) *
                      100
                    }%`,
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>

              {/* Workers Grid / List */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '6px' }}>
                {agent.workers.map((worker) => {
                  let statusColor = 'var(--muted-foreground)';
                  let statusBg = 'var(--secondary, #f8fafc)';
                  if (worker.status === 'Completed') {
                    statusColor = 'var(--success, #16a34a)';
                    statusBg = 'rgba(22, 163, 74, 0.08)';
                  } else if (worker.status === 'Running') {
                    statusColor = 'var(--primary, #0284c7)';
                    statusBg = 'rgba(2, 132, 199, 0.08)';
                  } else if (worker.status === 'Failed') {
                    statusColor = 'var(--destructive, #dc2626)';
                    statusBg = 'rgba(220, 38, 38, 0.08)';
                  }

                  return (
                    <div
                      key={worker.name}
                      style={{
                        padding: '6px 8px',
                        borderRadius: 'var(--radius-sm, 4px)',
                        border: '1px solid var(--border)',
                        backgroundColor: statusBg,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '11px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                        {worker.status === 'Completed' ? (
                          <CheckCircle2 size={12} color="var(--success, #16a34a)" />
                        ) : worker.status === 'Running' ? (
                          <Loader2 size={12} className="spin-animation" color="var(--primary, #0284c7)" />
                        ) : worker.status === 'Failed' ? (
                          <XCircle size={12} color="var(--destructive, #dc2626)" />
                        ) : (
                          <Clock size={11} color="var(--muted-foreground)" />
                        )}
                        <span style={{ fontWeight: 600 }}>{worker.name}</span>
                      </div>
                      <span style={{ fontSize: '9px', fontWeight: 650, color: statusColor }}>
                        {worker.status}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Completed Agent Summary Results */}
          {agent.status === 'COMPLETED' && agent.resultSummary && agent.resultSummary.length > 0 && (
            <div
              style={{
                padding: '10px 12px',
                borderRadius: 'var(--radius-sm, 4px)',
                backgroundColor: 'rgba(22, 163, 74, 0.04)',
                border: '1px solid rgba(22, 163, 74, 0.2)',
                fontSize: '11px',
                color: 'var(--foreground)',
              }}
            >
              <div style={{ fontWeight: 700, color: 'var(--success, #16a34a)', marginBottom: '4px' }}>
                Key Findings & Verified Deliverables
              </div>
              <ul style={{ margin: 0, paddingLeft: '16px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                {agent.resultSummary.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Last completed operation */}
          {agent.lastOperation && (
            <div style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
              <strong>Last Operation:</strong> {agent.lastOperation}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
