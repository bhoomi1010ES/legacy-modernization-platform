import React from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  note?: string;
  noteType?: 'normal' | 'warn' | 'success';
  icon?: React.ReactNode;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  note,
  noteType = 'normal',
  icon,
}) => {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        {icon}
      </div>
      <div className="stat-value">{value}</div>
      {note && (
        <div className={`stat-note ${noteType === 'warn' ? 'warn' : ''}`}>
          {noteType === 'success' ? <em>{note}</em> : note}
        </div>
      )}
    </div>
  );
};
