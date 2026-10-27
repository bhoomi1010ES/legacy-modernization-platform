import React, { useState } from 'react';
import {
  Activity, AlertTriangle, CheckCircle2, ChevronDown, Circle,
  Clock3, Database, Fingerprint, Gauge, RotateCcw, XCircle,
} from 'lucide-react';
import type { WorkflowEvent, WorkflowPhase, WorkflowState } from '../types/domain';

const iconFor = (phase: WorkflowPhase) => {
  if (phase.status === 'SUCCEEDED') return <CheckCircle2 size={16} />;
  if (phase.status === 'FAILED' || phase.status === 'CANCELLED') return <XCircle size={16} />;
  if (phase.status === 'BLOCKED') return <AlertTriangle size={16} />;
  if (phase.status === 'RUNNING') return <Clock3 size={16} />;
  return <Circle size={15} />;
};

const eventLabel = (event: WorkflowEvent) => event.event_type.toLowerCase().split('_').map((part) => part[0]?.toUpperCase() + part.slice(1)).join(' ');

export const WorkflowProgress: React.FC<{ workflow: WorkflowState; events?: WorkflowEvent[] }> = ({ workflow, events = [] }) => {
  const [showEvents, setShowEvents] = useState(false);
  const ratio = workflow.budget_limit > 0 ? Math.min(100, workflow.budget_used / workflow.budget_limit * 100) : 0;
  return <section className="workflow-card" aria-label="Durable workflow progress">
    <header className="workflow-card-head">
      <div><div className="eyebrow"><Database size={12} /> Phase 3 · durable supervisor</div><h2>Workflow checkpoint timeline</h2><p>Every critical transition is checkpointed before and after execution.</p></div>
      <div className="workflow-head-meta"><span><Fingerprint size={12} /> Sequence {workflow.checkpoint_sequence}</span><span>Graph v{workflow.workflow_version}</span><span>Updated {new Date(workflow.updated_at).toLocaleTimeString()}</span></div>
    </header>

    {workflow.blocking_reason && <div className="workflow-blocker"><AlertTriangle size={18} /><div><strong>Workflow is waiting</strong><span>{workflow.blocking_reason}</span></div></div>}

    <div className="workflow-budget"><div><Gauge size={15} /><span>Per-job budget</span><strong>{workflow.budget_used.toFixed(2)} / {workflow.budget_limit.toFixed(2)}</strong>{workflow.budget_warning && <em>80% threshold reached</em>}</div><div className="workflow-budget-track"><span style={{ width: `${ratio}%` }} /></div></div>

    <div className="workflow-timeline">
      {workflow.phases.map((phase, index) => <div key={phase.node} className={`workflow-phase phase-${phase.status.toLowerCase()}`}>
        <div className="workflow-phase-rail">{index > 0 && <span className="rail-before" />}{iconFor(phase)}{index < workflow.phases.length - 1 && <span className="rail-after" />}</div>
        <div><strong>{phase.label}</strong><span>{phase.status.replace('_', ' ')}</span></div>
      </div>)}
    </div>

    <button className="workflow-events-toggle" onClick={() => setShowEvents((value) => !value)} aria-expanded={showEvents}><Activity size={14} /> Recent durable events <span>{events.length}</span><ChevronDown size={14} className={showEvents ? 'rotated' : ''} /></button>
    {showEvents && <div className="workflow-events">{events.length ? events.slice(0, 8).map((event) => <div key={event.event_id}><span className="event-marker" /><div><strong>{eventLabel(event)}</strong><small>{event.actor_type} · {event.actor_id} · {new Date(event.created_at).toLocaleString()}</small></div>{event.event_type.includes('RECOVER') && <RotateCcw size={13} />}</div>) : <div className="empty-inline">No workflow events have been recorded.</div>}</div>}
  </section>;
};
