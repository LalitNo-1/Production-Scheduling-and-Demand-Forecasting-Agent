import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, parseISO } from 'date-fns';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

function ImpactBar({ result }) {
  if (!result) return null;
  return (
    <div className="impact-bar">
      <div className="impact-metric">
        <div className="val">{result.expected_fulfillment_rate.toFixed(1)}%</div>
        <div className="lbl">Expected Fulfillment</div>
      </div>
      <div className="impact-divider" />
      <div className="impact-metric">
        <div className="val" style={{ color: 'var(--accent-orange)' }}>{result.p10_fulfillment.toFixed(1)}%</div>
        <div className="lbl">Pessimistic (P10)</div>
      </div>
      <div className="impact-divider" />
      <div className="impact-metric">
        <div className="val" style={{ color: 'var(--accent-cyan)' }}>{result.p90_fulfillment.toFixed(1)}%</div>
        <div className="lbl">Optimistic (P90)</div>
      </div>
      {result.at_risk_jobs?.length > 0 && (
        <>
          <div className="impact-divider" />
          <div className="impact-metric">
            <div className="val" style={{ color: 'var(--accent-red)' }}>{result.at_risk_jobs.length}</div>
            <div className="lbl">At-Risk Jobs</div>
          </div>
        </>
      )}
    </div>
  );
}

export default function ProposedChanges({ onApprove, onReject, refreshKey = 0 }) {
  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [approverName, setApproverName] = useState('');
  const [actionLoading, setActionLoading] = useState({});
  const [expandedDiff, setExpandedDiff] = useState(null);

  const fetchChanges = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/proposed-changes`, { params: { status: 'pending' } });
      setChanges(res.data || []);
    } catch (e) {
      console.error('Fetch changes error', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchChanges(); }, [refreshKey]);

  const handleApprove = async (changeId) => {
    if (!approverName.trim()) {
      alert('Please enter your name to approve.');
      return;
    }
    setActionLoading(prev => ({ ...prev, [changeId]: 'approving' }));
    try {
      await axios.post(`${API}/commit-schedule`, {
        change_id: changeId,
        approved_by: approverName.trim(),
        notes: 'Approved via dashboard',
      });
      await fetchChanges();
      onApprove?.();
    } catch (e) {
      alert(e.response?.data?.detail || 'Approval failed');
    } finally {
      setActionLoading(prev => ({ ...prev, [changeId]: null }));
    }
  };

  const handleReject = async (changeId) => {
    const reason = prompt('Reason for rejection (optional):') ?? '';
    setActionLoading(prev => ({ ...prev, [changeId]: 'rejecting' }));
    try {
      await axios.post(`${API}/reject-schedule-change`, {
        change_id: changeId,
        rejected_by: approverName.trim() || 'Planner',
        reason,
      });
      await fetchChanges();
      onReject?.();
    } catch (e) {
      alert(e.response?.data?.detail || 'Rejection failed');
    } finally {
      setActionLoading(prev => ({ ...prev, [changeId]: null }));
    }
  };

  if (loading) return (
    <div>
      {[1, 2].map(i => <div key={i} className="loading-shimmer" style={{ height: 140, marginBottom: 12, borderRadius: 10 }} />)}
    </div>
  );

  if (!changes.length) return (
    <div className="empty-state">
      <div className="icon">✅</div>
      <div style={{ marginBottom: 4 }}>No pending proposals</div>
      <div style={{ fontSize: 12 }}>Run the agent to generate a schedule proposal</div>
    </div>
  );

  return (
    <div>
      {/* Approver name input */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Your name:</span>
        <input
          id="approver-name"
          className="form-input"
          placeholder="e.g. Jane Smith"
          value={approverName}
          onChange={e => setApproverName(e.target.value)}
          style={{ width: 180 }}
        />
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Required to approve</span>
      </div>

      {changes.map(change => (
        <div
          key={change.change_id}
          className={`change-card ${change.has_delivery_date_warning ? 'warn-delivery' : ''}`}
        >
          <div className="change-card-header">
            <span className="change-id">{change.change_id}</span>
            <span className={`badge badge-${change.forecast_confidence}`}>
              {change.forecast_confidence?.toUpperCase()} CONFIDENCE
            </span>
            {change.has_delivery_date_warning && (
              <span className="badge badge-warn">⚠ DELIVERY DATE AFFECTED</span>
            )}
            <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>
              {change.created_at ? format(parseISO(change.created_at), 'MMM d, HH:mm') : ''}
            </span>
          </div>

          <div className="change-rationale">{change.rationale}</div>

          <ImpactBar result={change.simulation_result} />

          {/* Diff toggle */}
          <div style={{ marginBottom: 12 }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setExpandedDiff(expandedDiff === change.change_id ? null : change.change_id)}
            >
              {expandedDiff === change.change_id ? '▲ Hide' : '▼ Show'} Schedule Diff
              ({change.affected_jobs?.length || 0} jobs affected)
            </button>
            {expandedDiff === change.change_id && (
              <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>BEFORE</div>
                  <pre style={{ fontSize: 10, background: 'var(--bg-secondary)', padding: 10, borderRadius: 6, overflow: 'auto', maxHeight: 180, color: 'var(--accent-red)' }}>
                    {JSON.stringify(change.before_state?.slice(0, 3), null, 2)}
                  </pre>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>AFTER</div>
                  <pre style={{ fontSize: 10, background: 'var(--bg-secondary)', padding: 10, borderRadius: 6, overflow: 'auto', maxHeight: 180, color: 'var(--accent-green)' }}>
                    {JSON.stringify(change.after_state?.slice(0, 3), null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>

          <div className="action-row">
            <button
              id={`approve-${change.change_id}`}
              className="btn btn-success"
              onClick={() => handleApprove(change.change_id)}
              disabled={!approverName.trim() || actionLoading[change.change_id]}
            >
              {actionLoading[change.change_id] === 'approving' ? '⏳ Approving…' : '✓ Approve'}
            </button>
            <button
              id={`reject-${change.change_id}`}
              className="btn btn-danger"
              onClick={() => handleReject(change.change_id)}
              disabled={actionLoading[change.change_id]}
            >
              {actionLoading[change.change_id] === 'rejecting' ? '⏳ Rejecting…' : '✗ Reject'}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
