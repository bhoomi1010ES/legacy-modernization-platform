import React from 'react';
import { Loader2, CheckCircle2, Clock, AlertTriangle, XCircle } from 'lucide-react';

export type FileAnalysisStatus = 'PENDING' | 'ANALYZING' | 'ANALYZED' | 'WARNING' | 'ERROR';

interface FileStatusIndicatorProps {
  status: FileAnalysisStatus;
  compact?: boolean;
}

export const FileStatusIndicator: React.FC<FileStatusIndicatorProps> = ({ status, compact = false }) => {
  switch (status) {
    case 'ANALYZING':
      return (
        <span
          className="file-status-badge analyzing"
          title="Currently being analyzed by agent worker"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            color: 'var(--primary, #0284c7)',
            fontSize: '10px',
            fontWeight: 600,
          }}
        >
          <Loader2 size={11} className="spin-animation" />
          {!compact && <span>Analyzing</span>}
        </span>
      );
    case 'ANALYZED':
      return (
        <span
          className="file-status-badge analyzed"
          title="Analysis completed and verified"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '3px',
            color: 'var(--success, #16a34a)',
            fontSize: '10px',
            fontWeight: 600,
          }}
        >
          <CheckCircle2 size={11} />
          {!compact && <span>Analyzed</span>}
        </span>
      );
    case 'WARNING':
      return (
        <span
          className="file-status-badge warning"
          title="Analysis detected potential gaps or warnings"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '3px',
            color: 'var(--warning, #d97706)',
            fontSize: '10px',
            fontWeight: 600,
          }}
        >
          <AlertTriangle size={11} />
          {!compact && <span>Warning</span>}
        </span>
      );
    case 'ERROR':
      return (
        <span
          className="file-status-badge error"
          title="Analysis parser timeout or error"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '3px',
            color: 'var(--destructive, #dc2626)',
            fontSize: '10px',
            fontWeight: 600,
          }}
        >
          <XCircle size={11} />
          {!compact && <span>Error</span>}
        </span>
      );
    case 'PENDING':
    default:
      return (
        <span
          className="file-status-badge pending"
          title="Queued for analysis"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '3px',
            color: 'var(--muted-foreground, #64748b)',
            fontSize: '10px',
            opacity: 0.7,
          }}
        >
          <Clock size={10} />
          {!compact && <span>Pending</span>}
        </span>
      );
  }
};
