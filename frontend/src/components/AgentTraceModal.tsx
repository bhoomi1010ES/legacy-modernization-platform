import React from 'react';
import type { AgentRun } from '../types/domain';
import { Bot, X, Terminal, Cpu, Clock, IndianRupee } from 'lucide-react';
import { StatusBadge } from './StatusBadge';

interface AgentTraceModalProps {
  agent: AgentRun;
  onClose: () => void;
}

export const AgentTraceModal: React.FC<AgentTraceModalProps> = ({ agent, onClose }) => {
  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-box" style={{ width: 'min(760px, 100%)' }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--purple-surface)',
                color: 'var(--purple)',
                display: 'grid',
                placeItems: 'center',
              }}
            >
              <Bot size={18} />
            </div>
            <div>
              <h2>{agent.agent_name} Agent Execution Trace</h2>
              <small style={{ color: 'var(--muted-foreground)' }}>
                Run ID: {agent.run_id} · Job: {agent.job_id}
              </small>
            </div>
          </div>
          <button onClick={onClose} style={{ padding: '6px' }}>
            <X size={18} />
          </button>
        </div>

        {/* Stats Row */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '12px',
            marginBottom: '20px',
          }}
        >
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', marginBottom: '4px' }}>Status</div>
            <StatusBadge status={agent.status} />
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Cpu size={12} /> Tokens
            </div>
            <strong style={{ fontSize: '13px' }}>{(agent.input_tokens + agent.output_tokens).toLocaleString()}</strong>
            <small style={{ display: 'block', fontSize: '9px', color: 'var(--muted-foreground)' }}>
              In: {agent.input_tokens} / Out: {agent.output_tokens}
            </small>
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <IndianRupee size={12} /> Cost Spend
            </div>
            <strong style={{ fontSize: '13px' }}>₹{agent.cost_usd.toFixed(2)}</strong>
            <small style={{ display: 'block', fontSize: '9px', color: 'var(--muted-foreground)' }}>Budget tracked</small>
          </div>
          <div style={{ padding: '10px 12px', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
            <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={12} /> Started
            </div>
            <strong style={{ fontSize: '11px' }}>{new Date(agent.started_at).toLocaleTimeString()}</strong>
            <small style={{ display: 'block', fontSize: '9px', color: 'var(--muted-foreground)' }}>
              {agent.completed_at ? 'Finished' : 'Running'}
            </small>
          </div>
        </div>

        {/* Role & Tooling */}
        <div style={{ marginBottom: '16px', fontSize: '12px' }}>
          <strong>Specialist Role: </strong>
          <span style={{ color: 'var(--muted-foreground)' }}>{agent.role_description}</span>
        </div>
        <div style={{ marginBottom: '20px', fontSize: '12px' }}>
          <strong>Configured Tools & Isolation: </strong>
          <code style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--primary)' }}>
            {agent.tooling}
          </code>
        </div>

        {/* Trace Stream Log */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 650, marginBottom: '8px' }}>
            <Terminal size={14} /> Agent Step-by-Step Execution Log:
          </div>
          <div className="code-panel" style={{ maxHeight: '220px', overflowY: 'auto' }}>
{`[${agent.started_at}] [AGENT_INIT] Initializing specialist ${agent.agent_name} with contract version 1.0.0
[${agent.started_at}] [SANDBOX_ACQUIRE] Isolated gVisor rootless container allocated with no external network
[${agent.started_at}] [CORRELATION_ID] corr_018f92b4-7a11-7392-a1b0-918237c09182
[${agent.started_at}] [TOOL_EXEC] git rev-parse HEAD -> 8d41f96b27a3c20e4b88df1a774169c3a0b
[${agent.started_at}] [TOOL_EXEC] tree-sitter parse src/main/java/**/*.java --format=ast-json
[${agent.started_at}] [EMIT_ARTIFACT] Generated schema-validated artifact -> RepoInventory v1
[${agent.started_at}] [BUDGET_CHECK] Token consumption: ${agent.input_tokens} input, ${agent.output_tokens} output (Cost: ₹${agent.cost_usd.toFixed(2)})
${agent.completed_at ? `[${agent.completed_at}] [AGENT_COMPLETE] Checkpoint saved to PostgreSQL. Transitioning job state.` : '[RUNNING] Awaiting next outer-loop coordinator instruction...'}`}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '20px' }}>
          <button className="button button-secondary" onClick={onClose}>
            Close Trace
          </button>
        </div>
      </div>
    </div>
  );
};
