import React, { useState } from 'react';
import type { AgentRun } from '../types/domain';
import { StatusBadge } from '../components/StatusBadge';
import { AgentTraceModal } from '../components/AgentTraceModal';
import { Bot, Terminal, Cpu, IndianRupee, Activity, CheckCircle2, ShieldCheck } from 'lucide-react';

interface AgentWorkspaceProps {
  agents: AgentRun[];
}

export const AgentWorkspace: React.FC<AgentWorkspaceProps> = ({ agents }) => {
  const [selectedAgent, setSelectedAgent] = useState<AgentRun | null>(null);

  const displayList = agents;
  const totalTokens = displayList.reduce((acc, a) => acc + (a.input_tokens || 0) + (a.output_tokens || 0), 0);
  const totalCost = displayList.reduce((acc, a) => acc + (a.cost_usd || 0), 0);

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>11 Specialist Multi-Agent Workspace</h1>
          <p className="subtitle">
            Autonomous agent coordination with specialized contracts, isolated tool execution, and token budget governance.
          </p>
        </div>
        <div className="heading-actions">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: 'var(--muted-foreground)' }}>
            <Cpu size={14} />
            <span>Total Tokens: <strong>{totalTokens.toLocaleString()}</strong></span>
            <span>•</span>
            <IndianRupee size={14} />
            <span>Spend: <strong>₹{totalCost.toFixed(2)}</strong></span>
          </div>
        </div>
      </div>

      {displayList.length === 0 ? (
        <div style={{ padding: '60px 20px', textAlign: 'center', backgroundColor: 'var(--card)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
          <Terminal size={36} color="var(--primary)" style={{ margin: '0 auto 12px' }} />
          <div style={{ fontSize: '14px', fontWeight: 650, color: 'var(--foreground)' }}>No Specialist Agent Runs Active</div>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', marginTop: '4px', maxWidth: '420px', margin: '4px auto 0' }}>
            Agent execution traces and token metrics stream live from PostgreSQL when modernization jobs undergo intake, characterization, and conversion.
          </p>
        </div>
      ) : (
        /* Agents Grid */
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '16px' }}>
          {displayList.map((agent) => (
            <div
              key={agent.run_id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '20px',
                backgroundColor: 'var(--card)',
                boxShadow: 'var(--shadow-soft)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
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
                      <Bot size={16} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 650, fontSize: '13px' }}>{agent.agent_name}</div>
                      <small style={{ color: 'var(--muted-foreground)', fontSize: '10px' }}>ID: {agent.run_id.slice(0, 8)}</small>
                    </div>
                  </div>
                  <StatusBadge status={agent.status} />
                </div>

                <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', lineHeight: 1.5, marginBottom: '12px' }}>
                  {agent.role_description}
                </p>

                <div style={{ fontSize: '11px', color: 'var(--muted-foreground)', marginBottom: '14px' }}>
                  <span style={{ fontWeight: 600 }}>Tools: </span>
                  <span>{agent.tooling}</span>
                </div>
              </div>

              <div style={{ borderTop: '1px solid var(--border)', paddingTop: '12px', marginTop: 'auto' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '8px' }}>
                  <span style={{ color: 'var(--muted-foreground)' }}>Tokens (In / Out):</span>
                  <span style={{ fontWeight: 600 }}>
                    {(agent.input_tokens || 0).toLocaleString()} / {(agent.output_tokens || 0).toLocaleString()}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '12px' }}>
                  <span style={{ color: 'var(--muted-foreground)' }}>Spend:</span>
                  <span style={{ fontWeight: 600, color: 'var(--primary)' }}>₹{(agent.cost_usd || 0).toFixed(2)}</span>
                </div>

                <button
                  className="button button-secondary button-sm"
                  style={{ width: '100%' }}
                  onClick={() => setSelectedAgent(agent)}
                >
                  <Terminal size={12} />
                  <span>Inspect Execution Trace</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Trace Inspector Modal */}
      {selectedAgent && (
        <AgentTraceModal
          agent={selectedAgent}
          onClose={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
};
