import React, { useState } from 'react';
import type { ConversionPlan, ConversionPlanWave, ModulePlanningUnit, PlanningTask } from '../../types/phase4';
import {
  GitCommit,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  ArrowRight,
  ShieldAlert,
  Boxes,
  FileCheck,
  Split,
} from 'lucide-react';

interface ConversionPlanViewProps {
  plan: ConversionPlan | null;
  onRevisionRequested?: (reason: string) => Promise<void>;
}

export const ConversionPlanView: React.FC<ConversionPlanViewProps> = ({
  plan,
  onRevisionRequested,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'waves' | 'modules' | 'dag' | 'g3'>('waves');
  const [selectedWave, setSelectedWave] = useState<number | null>(null);

  if (!plan) {
    return (
      <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
        <p>No conversion plan generated yet for this job.</p>
        <small>The Planner Coordinator and parallel Module Planners generate and aggregate the plan after G1 approval.</small>
      </div>
    );
  }

  const validation = plan.validation_status;
  const waves = plan.waves || [];
  const modules = plan.modules || [];
  const tasks = plan.tasks || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* DAG Validation Status Banner */}
      <div
        style={{
          border: `1px solid ${validation.is_valid_dag ? 'var(--success, #22c55e)' : 'var(--destructive, #ef4444)'}`,
          borderRadius: 'var(--radius-md)',
          padding: '16px 20px',
          backgroundColor: validation.is_valid_dag ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {validation.is_valid_dag ? (
            <CheckCircle2 size={24} color="var(--success, #22c55e)" />
          ) : (
            <ShieldAlert size={24} color="var(--destructive, #ef4444)" />
          )}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <strong style={{ fontSize: '14px' }}>
                {validation.is_valid_dag
                  ? 'Conversion Plan DAG Formally Validated'
                  : 'DAG Validation Errors Detected'}
              </strong>
              <span className={`badge ${validation.is_valid_dag ? 'green' : 'red'}`}>
                {validation.is_valid_dag ? 'CYCLE FREE' : 'INVALID DAG'}
              </span>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
              Plan v{plan.version} (Blueprint v{plan.blueprint_version}) · {plan.estimates.total_hours.toFixed(1)} hrs total effort across {tasks.length} tasks
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <span className="badge blue">{modules.length} Modules</span>
          <span className="badge purple">{waves.length} Topological Waves</span>
        </div>
      </div>

      {/* Cycle / Validation Warning Details if any */}
      {!validation.is_valid_dag && (
        <div style={{ border: '1px solid var(--destructive)', borderRadius: 'var(--radius-md)', padding: '16px', backgroundColor: 'var(--card)' }}>
          <strong style={{ fontSize: '13px', color: 'var(--destructive)' }}>Validation Diagnostics:</strong>
          <ul style={{ fontSize: '12px', paddingLeft: '16px', marginTop: '6px' }}>
            {validation.has_cycles && (
              <li>Cycles detected in module dependencies: {JSON.stringify(validation.cycle_nodes)}</li>
            )}
            {validation.missing_dependencies.map((dep, idx) => (
              <li key={idx}>Missing dependency: {dep}</li>
            ))}
            {validation.duplicate_ids.map((dup, idx) => (
              <li key={idx}>Duplicate ID: {dup}</li>
            ))}
            {validation.missing_acceptance_criteria_tasks.map((task, idx) => (
              <li key={idx}>Missing acceptance criteria: {task}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Subtabs */}
      <div className="tabs" style={{ marginBottom: 0 }}>
        <button
          className={`tab ${activeSubTab === 'waves' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('waves')}
        >
          Topological Execution Waves ({waves.length})
        </button>
        <button
          className={`tab ${activeSubTab === 'modules' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('modules')}
        >
          Planned Modules & Tasks ({modules.length})
        </button>
        <button
          className={`tab ${activeSubTab === 'dag' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('dag')}
        >
          Dependency Graph & Interfaces
        </button>
        <button
          className={`tab ${activeSubTab === 'g3' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('g3')}
        >
          Gate G3 Readiness Package
        </button>
      </div>

      {/* View 1: Waves */}
      {activeSubTab === 'waves' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {waves.map((wave) => (
            <div
              key={wave.wave_number}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '18px',
                backgroundColor: 'var(--card)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Layers size={18} color="var(--primary)" />
                  <strong style={{ fontSize: '14px' }}>Wave {wave.wave_number}: {wave.name}</strong>
                </div>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <span className="badge blue">{wave.module_ids.length} Modules</span>
                  <span className="badge green">{wave.task_ids.length} Implementation Tasks</span>
                </div>
              </div>

              <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', margin: '6px 0 12px 0' }}>
                {wave.rationale}
              </p>

              <div style={{ fontSize: '11px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ color: 'var(--muted-foreground)' }}>Scheduled Modules:</span>
                {wave.module_ids.map((modId) => (
                  <code key={modId} style={{ fontFamily: 'var(--font-mono)', padding: '2px 6px', background: 'var(--secondary)', borderRadius: '4px' }}>
                    {modId}
                  </code>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* View 2: Planned Modules & Tasks */}
      {activeSubTab === 'modules' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {modules.map((mod) => (
            <div
              key={mod.module_id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '16px',
                backgroundColor: 'var(--card)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <strong style={{ fontSize: '14px' }}>{mod.module_id}</strong>
                    <span className={`badge ${mod.risk === 'HIGH' || mod.risk === 'CRITICAL' ? 'red' : 'amber'}`}>
                      {mod.risk} Risk
                    </span>
                    <span className="badge blue">{mod.estimate_hours} hrs</span>
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', margin: '4px 0' }}>
                    {mod.responsibility}
                  </p>
                </div>
              </div>

              {/* Acceptance Criteria Checklist */}
              <div style={{ marginTop: '12px', background: 'var(--background)', padding: '12px', borderRadius: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 600, marginBottom: '6px' }}>
                  <FileCheck size={14} color="var(--primary)" />
                  <span>Mandatory Acceptance Criteria:</span>
                </div>
                <ul style={{ fontSize: '11px', margin: 0, paddingLeft: '16px', lineHeight: 1.6 }}>
                  {mod.acceptance_criteria.map((crit, idx) => (
                    <li key={idx}>{crit}</li>
                  ))}
                </ul>
              </div>

              {/* Implementation Tasks */}
              <div style={{ marginTop: '12px' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, display: 'block', marginBottom: '6px' }}>
                  Granular Implementation Tasks ({mod.implementation_tasks.length}):
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {mod.implementation_tasks.map((task) => (
                    <div
                      key={task.task_id}
                      style={{
                        fontSize: '11px',
                        padding: '8px 12px',
                        borderRadius: '4px',
                        border: '1px solid var(--border)',
                        background: 'var(--secondary)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <div>
                        <strong>{task.title}</strong>
                        <div style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>
                          ID: {task.task_id} · Deps: {task.dependencies.length > 0 ? task.dependencies.join(', ') : 'None'}
                        </div>
                      </div>
                      <span className="badge purple">{task.estimate_hours}h</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* View 3: Dependency Graph & Interfaces */}
      {activeSubTab === 'dag' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '20px', backgroundColor: 'var(--card)' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 650, marginBottom: '12px' }}>Inter-Module Dependencies & Edges</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--secondary)', textAlign: 'left' }}>
                <th style={{ padding: '8px 12px' }}>Source Module</th>
                <th style={{ padding: '8px 12px' }}>Edge Type</th>
                <th style={{ padding: '8px 12px' }}>Target Module</th>
                <th style={{ padding: '8px 12px' }}>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {plan.dependencies.length > 0 ? (
                plan.dependencies.map((dep, idx) => (
                  <tr key={idx} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)' }}>{dep.source}</td>
                    <td style={{ padding: '8px 12px' }}>
                      <span className="badge blue" style={{ fontSize: '9px' }}>{dep.dependency_type}</span>
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)' }}>{dep.target}</td>
                    <td style={{ padding: '8px 12px' }}>{dep.confidence}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} style={{ padding: '20px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
                    No inter-module dependencies (all modules independent).
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* View 4: Gate G3 Readiness Package */}
      {activeSubTab === 'g3' && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '24px', backgroundColor: 'var(--card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <ShieldAlert size={20} color="var(--primary)" />
            <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>Gate G3 Review Readiness Package</h3>
          </div>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginBottom: '16px' }}>
            Phase 4 prepares the system for Gate G3 human review. Gate approval itself remains an independent human review decision.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px', fontSize: '12px' }}>
            <div style={{ padding: '12px', border: '1px solid var(--border)', borderRadius: '6px', background: 'var(--background)' }}>
              <span style={{ color: 'var(--muted-foreground)' }}>Conversion Plan Version:</span>
              <div style={{ fontWeight: 650, fontSize: '14px', marginTop: '2px' }}>v{plan.version}</div>
            </div>
            <div style={{ padding: '12px', border: '1px solid var(--border)', borderRadius: '6px', background: 'var(--background)' }}>
              <span style={{ color: 'var(--muted-foreground)' }}>Target Blueprint Version:</span>
              <div style={{ fontWeight: 650, fontSize: '14px', marginTop: '2px' }}>v{plan.blueprint_version}</div>
            </div>
            <div style={{ padding: '12px', border: '1px solid var(--border)', borderRadius: '6px', background: 'var(--background)' }}>
              <span style={{ color: 'var(--muted-foreground)' }}>Total Planned Effort:</span>
              <div style={{ fontWeight: 650, fontSize: '14px', marginTop: '2px' }}>{plan.estimates.total_hours.toFixed(1)} hrs</div>
            </div>
          </div>

          <div style={{ marginTop: '20px', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
            <div style={{ fontSize: '12px', fontWeight: 650, marginBottom: '8px' }}>Mandatory Phase 4 Boundaries:</div>
            <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
              ✓ No CodeWriter has been invoked during Phase 4 analysis & planning.<br />
              ✓ All module planning units contain explicit acceptance criteria.<br />
              ✓ Module dependency graph is cycle-free and topological waves are computed.<br />
              ✓ Ready for G3 human review before Phase 5 code generation begins.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
