import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { format, parseISO } from 'date-fns';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export default function AuditLog({ refreshKey = 0 }) {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ sku: '', action: '', start_date: '', end_date: '' });
  const [expandedRow, setExpandedRow] = useState(null);
  const [rollbackLoading, setRollbackLoading] = useState({});

  const fetchLog = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 50 };
      if (filters.sku) params.sku = filters.sku;
      if (filters.action) params.action = filters.action;
      if (filters.start_date) params.start_date = filters.start_date;
      if (filters.end_date) params.end_date = filters.end_date;
      const res = await axios.get(`${API}/audit-log`, { params });
      setEntries(res.data.entries || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      console.error('Audit log fetch error', e);
    } finally {
      setLoading(false);
    }
  }, [filters, refreshKey]);

  useEffect(() => { fetchLog(); }, [fetchLog, refreshKey]);

  const handleRollback = async (changeId) => {
    const who = prompt('Your name (for rollback audit record):');
    if (!who?.trim()) return;
    setRollbackLoading(prev => ({ ...prev, [changeId]: true }));
    try {
      await axios.post(`${API}/rollback/${changeId}`, null, {
        params: { rolled_back_by: who.trim() }
      });
      await fetchLog();
    } catch (e) {
      alert(e.response?.data?.detail || 'Rollback failed');
    } finally {
      setRollbackLoading(prev => ({ ...prev, [changeId]: false }));
    }
  };

  const actionColor = { commit: 'var(--accent-green)', rollback: 'var(--accent-orange)', reject: 'var(--accent-red)' };

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <select id="audit-filter-sku" className="form-select" value={filters.sku} onChange={e => setFilters(f => ({ ...f, sku: e.target.value }))}>
          <option value="">All SKUs</option>
          <option value="SKU-A">SKU-A</option>
          <option value="SKU-B">SKU-B</option>
          <option value="SKU-C">SKU-C</option>
        </select>
        <select id="audit-filter-action" className="form-select" value={filters.action} onChange={e => setFilters(f => ({ ...f, action: e.target.value }))}>
          <option value="">All Actions</option>
          <option value="commit">Commit</option>
          <option value="rollback">Rollback</option>
          <option value="reject">Reject</option>
        </select>
        <input
          className="form-input"
          type="date"
          value={filters.start_date}
          onChange={e => setFilters(f => ({ ...f, start_date: e.target.value }))}
          title="Start date"
        />
        <input
          className="form-input"
          type="date"
          value={filters.end_date}
          onChange={e => setFilters(f => ({ ...f, end_date: e.target.value }))}
          title="End date"
        />
        <button className="btn btn-ghost btn-sm" onClick={() => setFilters({ sku: '', action: '', start_date: '', end_date: '' })}>
          Clear
        </button>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
          {total} total records
        </span>
      </div>

      {loading ? (
        <div>
          {[1, 2, 3].map(i => <div key={i} className="loading-shimmer" style={{ height: 40, marginBottom: 8 }} />)}
        </div>
      ) : entries.length === 0 ? (
        <div className="empty-state">
          <div className="icon">📝</div>
          <div>No audit records yet</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>Approved schedule changes will appear here</div>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Change ID</th>
                <th>Action</th>
                <th>Actor</th>
                <th>SKU</th>
                <th>Confidence</th>
                <th>Delivery Warn</th>
                <th>Status</th>
                <th>Notes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {entries.map(entry => (
                <React.Fragment key={entry.id}>
                  <tr
                    onClick={() => setExpandedRow(expandedRow === entry.id ? null : entry.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ whiteSpace: 'nowrap', color: 'var(--text-secondary)', fontSize: 11 }}>
                      {entry.timestamp ? format(parseISO(entry.timestamp), 'MMM d, HH:mm') : '—'}
                    </td>
                    <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: 'var(--accent-blue)' }}>
                      {entry.change_id}
                    </td>
                    <td>
                      <span className={`audit-action ${entry.action}`}>
                        {entry.action?.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ color: 'var(--text-primary)' }}>{entry.actor}</td>
                    <td>{entry.sku || '—'}</td>
                    <td>
                      {entry.forecast_confidence ? (
                        <span className={`badge badge-${entry.forecast_confidence}`}>
                          {entry.forecast_confidence}
                        </span>
                      ) : '—'}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      {entry.has_delivery_date_warning ? (
                        <span style={{ color: 'var(--accent-red)' }}>⚠</span>
                      ) : '—'}
                    </td>
                    <td>
                      <span style={{ color: actionColor[entry.action] || 'var(--text-secondary)', fontSize: 11 }}>
                        {entry.approval_status}
                      </span>
                    </td>
                    <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)', fontSize: 11 }}>
                      {entry.notes || '—'}
                    </td>
                    <td>
                      {entry.action === 'commit' && (
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={(e) => { e.stopPropagation(); handleRollback(entry.change_id); }}
                          disabled={rollbackLoading[entry.change_id]}
                          title="Rollback this change"
                          id={`rollback-${entry.change_id}`}
                        >
                          {rollbackLoading[entry.change_id] ? '⏳' : '↩ Rollback'}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedRow === entry.id && (
                    <tr>
                      <td colSpan={10} style={{ padding: '12px 16px', background: 'var(--bg-secondary)' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                          <div>
                            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>BEFORE STATE</div>
                            <pre style={{ fontSize: 10, color: 'var(--accent-red)', overflow: 'auto', maxHeight: 160 }}>
                              {JSON.stringify(entry.before_state?.slice(0, 3), null, 2) || '{}'}
                            </pre>
                          </div>
                          <div>
                            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>AFTER STATE</div>
                            <pre style={{ fontSize: 10, color: 'var(--accent-green)', overflow: 'auto', maxHeight: 160 }}>
                              {JSON.stringify(entry.after_state?.slice(0, 3), null, 2) || '{}'}
                            </pre>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
