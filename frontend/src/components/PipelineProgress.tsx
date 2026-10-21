import React from 'react';
import type { JobStatus } from '../types/domain';

interface PipelineProgressProps {
  status: JobStatus;
}

interface StepInfo {
  number: string;
  name: string;
  gate?: string;
  subtext: string;
  statuses: JobStatus[];
}

const STAGES: StepInfo[] = [
  {
    number: '01',
    name: 'Intake & Discovery',
    subtext: 'Repository clone & cloc',
    statuses: ['INTAKE'],
  },
  {
    number: '02',
    name: 'Legacy Analysis',
    subtext: 'Dependency & capability graph',
    statuses: ['ANALYZING'],
  },
  {
    number: '03',
    name: 'Stack Feasibility',
    gate: 'G1',
    subtext: 'Capability gaps & sign-off',
    statuses: ['AWAITING_GATE_G1'],
  },
  {
    number: '04',
    name: 'Characterization',
    gate: 'G2',
    subtext: 'Frozen test generation',
    statuses: ['CHARACTERIZING', 'AWAITING_GATE_G2'],
  },
  {
    number: '05',
    name: 'Wave Planning',
    gate: 'G3',
    subtext: 'Dependency DAG blueprint',
    statuses: ['PLANNING', 'AWAITING_GATE_G3'],
  },
  {
    number: '06',
    name: 'Conversion & Repair',
    subtext: 'Sandboxed multi-worker TDD',
    statuses: ['CONVERTING', 'VERIFYING'],
  },
  {
    number: '07',
    name: 'Delivery Readiness',
    gate: 'G4',
    subtext: 'Verification package & PR',
    statuses: ['INTEGRATING', 'AWAITING_GATE_G4', 'COMPLETED'],
  },
];

export const PipelineProgress: React.FC<PipelineProgressProps> = ({ status }) => {
  const getStageState = (index: number) => {
    const stageOrder: JobStatus[] = [
      'CREATED',
      'INTAKE',
      'ANALYZING',
      'AWAITING_GATE_G1',
      'CHARACTERIZING',
      'AWAITING_GATE_G2',
      'PLANNING',
      'AWAITING_GATE_G3',
      'CONVERTING',
      'VERIFYING',
      'INTEGRATING',
      'AWAITING_GATE_G4',
      'COMPLETED',
    ];

    const currentStatusIndex = stageOrder.indexOf(status);
    const stage = STAGES[index];

    // Find the max index corresponding to this stage
    const stageMaxIndex = Math.max(...stage.statuses.map((s) => stageOrder.indexOf(s)));
    const stageMinIndex = Math.min(...stage.statuses.map((s) => stageOrder.indexOf(s)));

    if (currentStatusIndex > stageMaxIndex || status === 'COMPLETED') {
      return 'done';
    }
    if (currentStatusIndex >= stageMinIndex && currentStatusIndex <= stageMaxIndex) {
      return 'current';
    }
    return 'pending';
  };

  return (
    <div className="pipeline">
      {STAGES.map((st, i) => {
        const state = getStageState(i);
        return (
          <div key={st.number} className={`pipeline-step ${state}`}>
            <span style={{ fontSize: '10px', color: 'var(--muted-foreground)', fontWeight: 700 }}>
              {st.number} {st.gate && `· Gate ${st.gate}`}
            </span>
            <strong>{st.name}</strong>
            <small>{st.subtext}</small>
          </div>
        );
      })}
    </div>
  );
};
