import React, { useEffect, useState } from 'react';
import type { AgentRun, AgentTrace } from '../types/domain';
import { api } from '../services/api';
import {
  Bot, Check, Clock, Copy, Cpu, DollarSign, ExternalLink,
  FileJson, LockKeyhole, Terminal, Wrench, X,
} from 'lucide-react';
import { StatusBadge } from './StatusBadge';

interface AgentTraceModalProps { agent: AgentRun; onClose: () => void }
type TraceTab = 'trace' | 'tools' | 'evidence';

const MarkdownEvidence: React.FC<{ value: string }> = ({ value }) => {
  const nodes: React.ReactNode[] = [];
  let code: string[] = [];
  let inCode = false;
  value.split('\n').forEach((line, index) => {
    if (line.trim().startsWith('```')) {
      if (inCode) { nodes.push(<pre key={`code-${index}`} className="code-panel evidence-code">{code.join('\n')}</pre>); code = []; }
      inCode = !inCode;
      return;
    }
    if (inCode) { code.push(line); return; }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) nodes.push(React.createElement(`h${heading[1].length + 2}`, { key: index }, heading[2]));
    else if (/^[-*]\s+/.test(line)) nodes.push(<div key={index} className="markdown-list-item">• {line.replace(/^[-*]\s+/, '')}</div>);
    else nodes.push(<p key={index}>{line || '\u00a0'}</p>);
  });
  if (code.length) nodes.push(<pre key="code-final" className="code-panel evidence-code">{code.join('\n')}</pre>);
  return <div className="markdown-evidence">{nodes}</div>;
};

const EvidenceView: React.FC<{ evidence?: Record<string, unknown> }> = ({ evidence }) => {
  const [copied, setCopied] = useState(false);
  if (!evidence) return <div className="empty-inline"><FileJson size={18} /> No structured output evidence was produced.</div>;
  const markdown = typeof evidence.markdown === 'string' ? evidence.markdown : undefined;
  const raw = JSON.stringify(evidence, null, 2);
  return <div className="evidence-panel">
    <div className="evidence-panel-head"><span>{markdown ? 'Rendered Markdown' : 'Validated JSON output'}</span><button className="button button-secondary button-sm" onClick={async () => { await navigator.clipboard?.writeText(markdown || raw); setCopied(true); window.setTimeout(() => setCopied(false), 1200); }}>{copied ? <Check size={12} /> : <Copy size={12} />} {copied ? 'Copied' : 'Copy'}</button></div>
    {markdown ? <MarkdownEvidence value={markdown} /> : <pre className="code-panel evidence-code">{raw}</pre>}
  </div>;
};

export const AgentTraceModal: React.FC<AgentTraceModalProps> = ({ agent, onClose }) => {
  const [trace, setTrace] = useState<AgentTrace | null>(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState<TraceTab>('trace');

  useEffect(() => {
    let active = true;
    setTrace(null); setError('');
    api.getAgentTrace(agent.run_id).then((value) => active && setTrace(value)).catch((err) => active && setError(err.message));
    return () => { active = false; };
  }, [agent.run_id]);

  return <div className="dialog-overlay" onClick={onClose} role="presentation">
    <div className="dialog-box trace-dialog" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label={`${agent.agent_name} execution trace`}>
      <div className="dialog-header trace-dialog-header">
        <div className="agent-identity"><div className="agent-icon"><Bot size={19} /></div><div><h2>{agent.agent_name} run</h2><code>{agent.run_id} · {agent.job_id}</code></div></div>
        <button className="icon-button" onClick={onClose} aria-label="Close trace"><X size={18} /></button>
      </div>

      <div className="trace-summary-grid">
        <div><span>Status</span><StatusBadge status={agent.status} /></div>
        <div><span><Cpu size={12} /> Tokens</span><strong>{(trace?.total_tokens ?? agent.input_tokens + agent.output_tokens).toLocaleString()}</strong></div>
        <div><span><DollarSign size={12} /> Cost</span><strong>${(trace?.cost_usd ?? agent.cost_usd).toFixed(4)}</strong></div>
        <div><span><Clock size={12} /> Duration</span><strong>{(trace?.duration_seconds ?? agent.duration_seconds ?? 0).toFixed(2)}s</strong></div>
      </div>

      <div className="redaction-note"><LockKeyhole size={13} /><span>This authorized view is redacted. Secrets, credentials, environment values, and unsafe model output are removed server-side.</span></div>
      {error && <div className="safe-error"><Terminal size={15} /><div><strong>Unable to load trace</strong><span>{error}</span></div></div>}
      {!trace && !error && <div className="empty-inline"><span className="loading-dot" /> Loading redacted execution trace…</div>}

      {trace && <>
        {trace.error_message && <div className="safe-error"><Terminal size={15} /><div><strong>{trace.failure_classification || 'Safe failure'}</strong><span>{trace.error_message}</span></div></div>}
        <div className="trace-tabs" role="tablist">
          <button className={tab === 'trace' ? 'active' : ''} onClick={() => setTab('trace')}><Terminal size={13} /> Trace <span>{trace.steps.length}</span></button>
          <button className={tab === 'tools' ? 'active' : ''} onClick={() => setTab('tools')}><Wrench size={13} /> Tool calls <span>{trace.tool_calls.length}</span></button>
          <button className={tab === 'evidence' ? 'active' : ''} onClick={() => setTab('evidence')}><FileJson size={13} /> Evidence <span>{trace.evidence_artifacts.length}</span></button>
        </div>

        {tab === 'trace' && <div className="trace-step-list">
          {trace.steps.length ? trace.steps.map((step) => <article key={step.step_number} className="trace-step">
            <div className="trace-step-index">{step.step_number}</div><div><div className="trace-step-head"><strong>{step.step_type.replace('_', ' ')}</strong><span>{step.duration_ms.toFixed(1)}ms · {new Date(step.timestamp).toLocaleTimeString()}</span></div><pre>{typeof step.content === 'string' ? step.content : JSON.stringify(step.content, null, 2)}</pre></div>
          </article>) : <div className="empty-inline">No trace steps recorded.</div>}
        </div>}

        {tab === 'tools' && <div className="tool-call-list">
          {trace.tool_calls.length ? trace.tool_calls.map((call, index) => <details key={call.call_id} className="tool-call-card" open={index === 0}>
            <summary><div><Wrench size={14} /><strong>{call.tool_name}</strong><span className={`capability-tag ${call.is_read_only ? 'read-only' : 'write-execute'}`}>{call.is_read_only ? 'Read only' : 'Write / execute'}</span></div><div><span>{call.duration_ms.toFixed(1)}ms</span><StatusBadge status={call.ok ? 'SUCCEEDED' : 'FAILED'} /></div></summary>
            <div className="tool-call-body"><div><label>Validated arguments</label><pre>{JSON.stringify(call.arguments_summary, null, 2)}</pre></div><div><label>Safe output summary</label><pre>{call.error || call.output_summary || 'No output returned.'}</pre></div></div>
          </details>) : <div className="empty-inline">No tools were called during this run.</div>}
        </div>}

        {tab === 'evidence' && <div>
          <EvidenceView evidence={trace.output_evidence} />
          <div className="artifact-link-list"><h3>Persisted artifact references</h3>{trace.evidence_artifacts.length ? trace.evidence_artifacts.map((id) => <a key={id} href="#/artifacts"><FileJson size={13} /> {id}<ExternalLink size={11} /></a>) : <div className="empty-inline">No artifact references were attached.</div>}</div>
        </div>}
      </>}
    </div>
  </div>;
};
