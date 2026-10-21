import React, { useState, useEffect } from 'react';
import type { AuditEvent } from '../types/domain';
import { api } from '../services/api';
import { History, Shield, Bot, User, Download, Search, CheckCircle, RefreshCw } from 'lucide-react';

export const Audit: React.FC = () => {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'ALL' | 'USER' | 'AGENT'>('ALL');
  const [search, setSearch] = useState('');

  const fetchAuditEvents = async () => {
    try {
      setLoading(true);
      const res = await api.getAuditLogs(undefined, 100, 0);
      setEvents(res.items || []);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditEvents();
  }, []);

  const filtered = events.filter((e) => {
    if (filter === 'USER' && e.actor_type !== 'USER' && e.actor_type !== 'HUMAN') return false;
    if (filter === 'AGENT' && e.actor_type !== 'AGENT') return false;
    if (
      search &&
      !e.action?.toLowerCase().includes(search.toLowerCase()) &&
      !e.actor_id?.toLowerCase().includes(search.toLowerCase()) &&
      !e.event_type?.toLowerCase().includes(search.toLowerCase()) &&
      !(e.job_id && e.job_id.toLowerCase().includes(search.toLowerCase()))
    ) {
      return false;
    }
    return true;
  });

  const exportJSON = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(events, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `rebase_audit_trail_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Immutable Cryptographic Audit Trail</h1>
          <p className="subtitle">
            Append-only tamper-evident event log recording all human architectural decisions and autonomous agent actions.
          </p>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary button-sm" onClick={fetchAuditEvents} title="Refresh log">
            <RefreshCw size={13} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>
          <button className="button button-secondary button-sm" onClick={exportJSON} disabled={events.length === 0}>
            <Download size={13} />
            <span>Export Full JSON Log</span>
          </button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className={`button button-sm ${filter === 'ALL' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setFilter('ALL')}
          >
            All Events ({events.length})
          </button>
          <button
            className={`button button-sm ${filter === 'USER' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setFilter('USER')}
          >
            User Actions
          </button>
          <button
            className={`button button-sm ${filter === 'AGENT' ? 'button-primary' : 'button-secondary'}`}
            onClick={() => setFilter('AGENT')}
          >
            Agent Executions
          </button>
        </div>

        <div style={{ width: '260px' }}>
          <input
            type="text"
            className="field"
            placeholder="Search action, actor, or type..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--muted-foreground)', fontSize: '13px' }}>
          Loading cryptographic audit trail from PostgreSQL...
        </div>
      ) : filtered.length === 0 ? (
        <div
          style={{
            padding: '48px 24px',
            textAlign: 'center',
            backgroundColor: 'var(--card-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <History size={36} color="var(--muted-foreground)" style={{ margin: '0 auto 12px' }} />
          <h3 style={{ fontSize: '15px', fontWeight: 650, marginBottom: '6px' }}>No Audit Events Found</h3>
          <p style={{ fontSize: '12px', color: 'var(--muted-foreground)', maxWidth: '400px', margin: '0 auto' }}>
            {search
              ? 'No events match your search criteria. Try clearing the search term.'
              : 'Audit events are automatically and immutably appended to PostgreSQL when actions (login, register, job creation, gate approvals) occur.'}
          </p>
        </div>
      ) : (
        /* Audit Log Table */
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Job Identifier</th>
                <th>Event Type</th>
                <th>Correlation ID</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((evt) => (
                <tr key={evt.event_id}>
                  <td style={{ color: 'var(--muted-foreground)', fontSize: '11px', whiteSpace: 'nowrap' }}>
                    {new Date(evt.created_at).toLocaleString()}
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {evt.actor_type === 'USER' || evt.actor_type === 'HUMAN' ? (
                        <User size={14} color="var(--primary)" />
                      ) : (
                        <Bot size={14} color="var(--purple)" />
                      )}
                      <strong>{evt.actor_id}</strong>
                    </div>
                  </td>
                  <td>
                    <span style={{ fontWeight: 500 }}>{evt.action || `${evt.event_type} executed`}</span>
                  </td>
                  <td>
                    {evt.job_id ? (
                      <span className="badge gray">{evt.job_id.slice(0, 8)}</span>
                    ) : (
                      <span style={{ color: 'var(--muted-foreground)', fontSize: '11px' }}>Global / Auth</span>
                    )}
                  </td>
                  <td>
                    <span className="stack-label">{evt.event_type}</span>
                  </td>
                  <td>
                    <code style={{ fontSize: '10px', fontFamily: 'var(--font-mono)' }}>
                      {evt.correlation_id || '—'}
                    </code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
