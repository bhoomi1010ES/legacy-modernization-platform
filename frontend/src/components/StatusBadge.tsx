import React from 'react';
import type { JobStatus } from '../types/domain';

interface StatusBadgeProps {
  status: JobStatus | 'PENDING' | 'APPROVED' | 'REJECTED' | 'Active' | 'Idle' | 'Completed' | 'Failed' | string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  let color = 'gray';

  switch (status) {
    case 'COMPLETED':
    case 'APPROVED':
    case 'Completed':
    case 'SUCCEEDED':
    case 'VERIFIED':
    case 'REPAIRED':
      color = 'green';
      break;
    case 'CONVERTING':
    case 'VERIFYING':
    case 'Active':
    case 'PLANNING':
    case 'CHARACTERIZING':
    case 'ANALYZING':
    case 'INTAKE':
    case 'RUNNING':
    case 'LEASED':
      color = 'blue';
      break;
    case 'AWAITING_GATE_G1':
    case 'AWAITING_GATE_G2':
    case 'AWAITING_GATE_G3':
    case 'AWAITING_GATE_G4':
    case 'PENDING':
    case 'PAUSED':
    case 'QUEUED':
    case 'BLOCKED':
    case 'REPAIR_REQUIRED':
      color = 'amber';
      break;
    case 'FAILED':
    case 'REJECTED':
    case 'NEEDS_CHANGES':
    case 'INVALIDATED':
    case 'TIMED_OUT':
    case 'CANCELLED':
    case 'ESCALATED':
      color = 'red';
      break;
    default:
      color = 'gray';
  }

  // Format label: remove prefixes, replace underscores with spaces
  const label = status.replace(/AWAITING_GATE_/, 'Awaiting ').replace(/_/g, ' ');

  return (
    <span className={`badge ${color} ${className}`}>
      <span className="dot" />
      {label}
    </span>
  );
};
