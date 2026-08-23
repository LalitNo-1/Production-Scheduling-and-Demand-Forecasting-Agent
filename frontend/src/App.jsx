import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import GanttChart from './components/GanttChart';
import ForecastChart from './components/ForecastChart';
import ProposedChanges from './components/ProposedChanges';
import AuditLog from './components/AuditLog';
import CreateJobModal from './components/CreateJobModal';
import ManageMachinesModal from './components/ManageMachinesModal';
import ManageSKUsModal from './components/ManageSKUsModal';
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
  const [forecastHorizon, setForecastHorizon] = useState(30);
  const [allSkus, setAllSkus] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentResult, setAgentResult] = useState(null);
  
  // Modals state
  const [isCreateJobOpen, setIsCreateJobOpen] = useState(false);
  const [isManageMachinesOpen, setIsManageMachinesOpen] = useState(false);
  const [isManageSKUsOpen, setIsManageSKUsOpen] = useState(false);

  const agentStatus = useAgentStatus();
  const stats = useStats(refreshKey);

  const refresh = () => setRefreshKey(k => k + 1);

  // Fetch SKU list
  useEffect(() => {
    axios.get(`${API}/skus`).then(r => {
      setAllSkus(r.data || []);
      if (r.data.length > 0 && !selectedSku) {
        setSelectedSku(r.data[0].sku);
      }
    }).catch(() => {});
  }, [refreshKey]);

  const runAgent = async () => {
    setAgentLoading(true);
    setAgentResult(null);
    try {
      const res = await axios.post(`${API}/agent/run`, {
        sku: selectedSku,
        horizon_days: forecastHorizon,
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

  const currentSkuObj = allSkus.find(s => s.sku === selectedSku) || {
    sku: selectedSku,
    display_name: selectedSku,
    description: '',
    units_per_hour: 50
  };

  const renderContent = () => {
    switch (activeTab) {
      case 'schedule':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
              <div>
                <h1 className="section-title">Production Schedule</h1>
                <p className="section-sub">Machine cell timeline and active job order allocation</p>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => setIsCreateJobOpen(true)}
                  id="schedule-new-job-btn"
                >
                  ➕ Schedule Order
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => setIsManageMachinesOpen(true)}
                  title="Add, rename or edit machines"
                >
                  🏭 Machines
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => setIsManageSKUsOpen(true)}
                  title="Rename product lines and rates"
                >
                  📦 Products
                </button>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginLeft: 6 }}>
                  <label style={{ fontSize: 12, color: 'var(--text-secondary)' }}>SKU:</label>
                  <select
                    id="schedule-sku-filter"
                    className="form-select"
                    value={selectedSku}
                    onChange={e => setSelectedSku(e.target.value)}
                  >
                    <option value="">All SKUs</option>
                    {allSkus.map(s => (
                      <option key={s.sku} value={s.sku}>
                        {s.sku} ({s.display_name})
                      </option>
                    ))}
                  </select>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={refresh}>↻</button>
              </div>
            </div>

            <div className="card" style={{ marginBottom: 20 }}>
              <div className="card-header">
                <span className="card-title">🏭 Interactive Gantt Timeline — Machine Cells</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Click any job bar to rename or edit</span>
              </div>
              <GanttChart sku={selectedSku || null} refreshKey={refreshKey} onRefresh={refresh} />
            </div>
          </div>
        );

      case 'forecast':
        return (
          <div>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
              <div>
                <h1 className="section-title">Demand Forecasting & Capacity Planning</h1>
                <p className="section-sub">Time-series forecasting with uncertainty envelopes and statistical confidence gating</p>
              </div>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <button className="btn btn-ghost btn-sm" onClick={() => setIsManageSKUsOpen(true)}>
                  📦 Rename Product Lines
                </button>
                <div style={{ display: 'flex', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: 2 }}>
                  {[14, 30, 60].map(h => (
                    <button
                      key={h}
                      className="btn btn-sm"
                      style={{
                        background: forecastHorizon === h ? 'var(--accent-blue)' : 'transparent',
                        color: forecastHorizon === h ? '#0a0e1a' : 'var(--text-secondary)',
                        padding: '4px 10px',
                        fontSize: 11,
                      }}
                      onClick={() => setForecastHorizon(h)}
                    >
                      {h} Days
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Product Selector Pills */}
            <div style={{ display: 'flex', gap: 10, marginBottom: 20, overflowX: 'auto', paddingBottom: 4 }}>
              {allSkus.map(s => {
                const isSelected = s.sku === selectedSku;
                return (
                  <div
                    key={s.sku}
                    onClick={() => setSelectedSku(s.sku)}
                    style={{
                      background: isSelected ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                      border: isSelected ? '1.5px solid var(--accent-blue)' : '1px solid var(--border)',
                      boxShadow: isSelected ? '0 0 16px rgba(99,179,237,0.2)' : 'none',
                      borderRadius: 'var(--radius-md)',
                      padding: '10px 16px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      minWidth: 200,
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <span className={`badge sku-${s.sku.split('-')[1]?.toLowerCase() || 'a'}`} style={{ fontSize: 11 }}>
                      {s.sku}
                    </span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 13, color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                        {s.display_name}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                        ⚡ {s.units_per_hour} units/hr
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Primary Hero Forecast Card */}
            <div className="card" style={{ marginBottom: 24 }}>
              <div className="card-header" style={{ borderBottom: '1px solid var(--border)', paddingBottom: 12 }}>
                <div>
                  <span className="card-title" style={{ fontSize: 16 }}>
                    📈 {selectedSku} — {currentSkuObj.display_name}
                  </span>
                  {currentSkuObj.description && (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                      {currentSkuObj.description}
                    </div>
                  )}
                </div>
                <button className="btn btn-ghost btn-sm" onClick={refresh}>↻ Refresh</button>
              </div>

              <ForecastChart
                sku={selectedSku}
                horizon={forecastHorizon}
                refreshKey={refreshKey}
                isCompact={false}
              />
            </div>

            {/* Cross-Product Comparison */}
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 12, letterSpacing: '0.8px' }}>
                Multi-Product Comparison ({forecastHorizon}-Day Outlook)
              </div>
              <div className="page-grid-3">
                {allSkus.map(s => (
                  <div
                    key={s.sku}
                    className="card"
                    style={{
                      cursor: 'pointer',
                      border: s.sku === selectedSku ? '1px solid var(--accent-blue)' : undefined,
                      padding: 14,
                    }}
                    onClick={() => setSelectedSku(s.sku)}
                  >
                    <div className="card-header" style={{ marginBottom: 8 }}>
                      <span className="card-title" style={{ fontSize: 12 }}>
                        {s.sku} — {s.display_name}
                      </span>
                    </div>
                    <ForecastChart sku={s.sku} horizon={forecastHorizon} refreshKey={refreshKey} isCompact={true} />
                  </div>
                ))}
              </div>
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

      {/* Modals */}
      <CreateJobModal
        isOpen={isCreateJobOpen}
        onClose={() => setIsCreateJobOpen(false)}
        onSuccess={refresh}
      />

      <ManageMachinesModal
        isOpen={isManageMachinesOpen}
        onClose={() => setIsManageMachinesOpen(false)}
        onUpdated={refresh}
      />

      <ManageSKUsModal
        isOpen={isManageSKUsOpen}
        onClose={() => setIsManageSKUsOpen(false)}
        onUpdated={refresh}
      />
    </div>
  );
}
