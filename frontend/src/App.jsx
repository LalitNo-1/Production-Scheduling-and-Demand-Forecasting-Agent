import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import GanttChart from './components/GanttChart';
import ForecastChart from './components/ForecastChart';
import ProposedChanges from './components/ProposedChanges';
import AuditLog from './components/AuditLog';
import './index.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const NAV_ITEMS = [
  { id: 'schedule', label: '📅 Schedule', section: null },
  { id: 'forecast', label: '📈 Forecast', section: null },
  { id: 'proposals', label: '🤖 Agent Proposals', section: null },
  { id: 'audit', label: '📝 Audit Log', section: null },
];

function useAgentStatus() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    axios.get(`${API}/agent/status`).then(r => setStatus(r.data)).catch(() => {});
  }, []);
  return status;
}

function useStats(refreshKey) {
  const [stats, setStats] = useState({ jobs: 0, pending: 0, audits: 0 });
  const fetch = useCallback(async () => {
    try {
      const [sched, changes, audit] = await Promise.all([
        axios.get(`${API}/current-schedule`),
        axios.get(`${API}/proposed-changes`, { params: { status: 'pending' } }),
        axios.get(`${API}/audit-log`, { params: { limit: 1 } }),
      ]);
      setStats({
        jobs: sched.data.total_jobs,
        pending: (changes.data || []).length,
        audits: audit.data.total,
      });
    } catch (e) { /* silent */ }
  }, [refreshKey]);
  useEffect(() => { fetch(); }, [fetch]);
  return stats;
}

export default function App() {
  const [activeTab, setActiveTab] = useState('schedule');
  const [selectedSku, setSelectedSku] = useState('SKU-A');
  const [refreshKey, setRefreshKey] = useState(0);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentResult, setAgentResult] = useState(null);
  const agentStatus = useAgentStatus();
  const stats = useStats(refreshKey);

  const refresh = () => setRefreshKey(k => k + 1);

  const runAgent = async () => {
    setAgentLoading(true);
    setAgentResult(null);
    try {
      const res = await axios.post(`${API}/agent/run`, {
        sku: selectedSku,
        horizon_days: 30,
      });
      setAgentResult(res.data);
      if (res.data.proposed_change_id) {
        setActiveTab('proposals');
        refresh();
      }
    } catch (e) {
      setAgentResult({ status: 'error', message: e.response?.data?.detail || 'Agent run failed' });
    } finally {
      setAgentLoading(false);
    }
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'schedule':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
              <h1 className="section-title">Production Schedule</h1>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Filter SKU:</label>
                <select id="schedule-sku-filter" className="form-select" value={selectedSku} onChange={e => setSelectedSku(e.target.value)}>
                  <option value="">All SKUs</option>
                  <option value="SKU-A">SKU-A</option>
                  <option value="SKU-B">SKU-B</option>
                  <option value="SKU-C">SKU-C</option>
                </select>
                <button className="btn btn-ghost btn-sm" onClick={refresh}>↻ Refresh</button>
              </div>
            </div>
            <div className="card" style={{ marginBottom: 20 }}>
              <div className="card-header">
                <span className="card-title">🏭 Gantt View — Machine Cells</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Dashed = committed delivery date</span>
              </div>
              <GanttChart sku={selectedSku || null} refreshKey={refreshKey} />
            </div>
          </div>
        );

      case 'forecast':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
              <div>
                <h1 className="section-title">Demand Forecast</h1>
                <p className="section-sub">Prophet model with 90-day backtest MAPE and confidence bands</p>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                <select id="forecast-sku-select" className="form-select" value={selectedSku} onChange={e => setSelectedSku(e.target.value)}>
                  <option value="SKU-A">SKU-A</option>
                  <option value="SKU-B">SKU-B</option>
                  <option value="SKU-C">SKU-C</option>
                </select>
              </div>
            </div>
            <div className="page-grid-2" style={{ marginBottom: 20 }}>
              {['SKU-A', 'SKU-B', 'SKU-C'].map(s => (
                <div key={s} className="card" style={{ cursor: 'pointer', border: s === selectedSku ? '1px solid var(--accent-blue)' : undefined }}
                  onClick={() => setSelectedSku(s)}>
                  <div className="card-header">
                    <span className="card-title">📈 {s}</span>
                  </div>
                  <ForecastChart sku={s} horizon={30} refreshKey={refreshKey} />
                </div>
              ))}
            </div>
          </div>
        );

      case 'proposals':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
              <div>
                <h1 className="section-title">Agent Proposals</h1>
                <p className="section-sub">Review and approve or reject AI-generated schedule changes</p>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select id="agent-sku-select" className="form-select" value={selectedSku} onChange={e => setSelectedSku(e.target.value)}>
                  <option value="SKU-A">SKU-A</option>
                  <option value="SKU-B">SKU-B</option>
                  <option value="SKU-C">SKU-C</option>
                </select>
                <button
                  id="run-agent-btn"
                  className="btn btn-primary"
                  onClick={runAgent}
                  disabled={agentLoading}
                >
                  {agentLoading ? '⏳ Agent Running…' : '🤖 Run Agent'}
                </button>
              </div>
            </div>

            {/* Agent reasoning output */}
            {agentResult && (
              <div className="card" style={{ marginBottom: 20 }}>
                <div className="card-header">
                  <span className="card-title">
                    {agentResult.status === 'completed' ? '✅' :
                     agentResult.status === 'flagged_low_confidence' ? '⚠️' : '❌'} Agent Output
                  </span>
                  {agentResult.forecast_confidence && (
                    <span className={`badge badge-${agentResult.forecast_confidence}`}>
                      {agentResult.forecast_confidence?.toUpperCase()} CONFIDENCE
                    </span>
                  )}
                </div>
                <div className="agent-output">
                  {agentResult.message}
                  {agentResult.reasoning_steps?.length > 0 && (
                    <>
                      {'\n\n--- Reasoning Steps ---\n'}
                      {agentResult.reasoning_steps.map((s, i) => {
                        const cls = s.includes('[Tool]') ? 'step-tool' :
                                    s.includes('[Observation]') ? 'step-obs' :
                                    s.includes('[Decision]') ? 'step-dec' : '';
                        return <span key={i} className={cls}>{s}{'\n'}</span>;
                      })}
                    </>
                  )}
                </div>
              </div>
            )}

            <div className="card">
              <div className="card-header">
                <span className="card-title">📋 Pending Proposals</span>
                <span className="badge badge-warn" style={{ display: stats.pending > 0 ? 'inline-flex' : 'none' }}>
                  {stats.pending} pending
                </span>
              </div>
              <ProposedChanges
                onApprove={refresh}
                onReject={refresh}
                refreshKey={refreshKey}
              />
            </div>
          </div>
        );

      case 'audit':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
              <div>
                <h1 className="section-title">Audit Log</h1>
                <p className="section-sub">Append-only record of all committed schedule changes</p>
              </div>
              <button className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto' }} onClick={refresh}>↻ Refresh</button>
            </div>
            <div className="card">
              <AuditLog refreshKey={refreshKey} />
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="app-shell">
      {/* Topbar */}
      <header className="topbar">
        <div className="topbar-logo">
          ⚙ ProductionAI <span>Scheduler</span>
        </div>
        <div className="topbar-divider" />
        {agentStatus && (
          <span className={`badge ${agentStatus.llm_mode === 'real_claude' ? 'badge-live' : 'badge-mock'}`}>
            {agentStatus.llm_mode === 'real_claude' ? '🟢 Claude Live' : '🟡 Mock Agent'}
          </span>
        )}
      </header>

      {/* Sidebar */}
      <nav className="sidebar">
        <div className="nav-section">Navigation</div>
        {NAV_ITEMS.map(item => (
          <div
            key={item.id}
            id={`nav-${item.id}`}
            className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
            onClick={() => setActiveTab(item.id)}
          >
            {item.label}
          </div>
        ))}

        {/* Stats in sidebar */}
        <div className="nav-section" style={{ marginTop: 24 }}>Stats</div>
        <div style={{ padding: '4px 20px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Active Jobs</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{stats.jobs}</div>
        </div>
        <div style={{ padding: '8px 20px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Pending Proposals</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: stats.pending > 0 ? 'var(--accent-orange)' : 'var(--text-primary)' }}>
            {stats.pending}
          </div>
        </div>
        <div style={{ padding: '8px 20px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Audit Records</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{stats.audits}</div>
        </div>
      </nav>

      {/* Main content */}
      <main className="main-content">
        {renderContent()}
      </main>
    </div>
  );
}
