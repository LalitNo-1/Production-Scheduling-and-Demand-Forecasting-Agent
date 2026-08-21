import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format } from 'date-fns';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/**
 * Gantt chart component — renders job orders as time-scaled bars.
 * Groups by machine, shows maintenance windows in red, delivery-date warnings dashed.
 */
export default function GanttChart({ sku = null, refreshKey = 0 }) {
  const [jobs, setJobs] = useState([]);
  const [maintenance, setMaintenance] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [schedRes, maintRes] = await Promise.all([
          axios.get(`${API}/current-schedule`, { params: sku ? { sku } : {} }),
          axios.get(`${API}/maintenance-windows`),
        ]);
        setJobs(schedRes.data.jobs || []);
        setMaintenance(maintRes.data || []);
      } catch (e) {
        console.error('Gantt fetch error', e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [sku, refreshKey]);

  if (loading) return (
    <div style={{ padding: 20 }}>
      {[1, 2, 3].map(i => (
        <div key={i} style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
          <div className="loading-shimmer" style={{ width: 100, flexShrink: 0 }} />
          <div className="loading-shimmer" style={{ flex: 1 }} />
        </div>
      ))}
    </div>
  );

  if (!jobs.length) return (
    <div className="empty-state">
      <div className="icon">📋</div>
      <div>No scheduled jobs</div>
    </div>
  );

  // Determine time range
  const allTimes = jobs.flatMap(j => [new Date(j.start_time), new Date(j.end_time)]);
  const minTime = new Date(Math.min(...allTimes)).getTime();
  const maxTime = new Date(Math.max(...allTimes)).getTime();
  const totalMs = maxTime - minTime || 1;

  const toPercent = (dt) => Math.max(0, ((new Date(dt).getTime() - minTime) / totalMs) * 100);
  const widthPercent = (start, end) => Math.max(0.5, ((new Date(end).getTime() - new Date(start).getTime()) / totalMs) * 100);

  const machines = [...new Set(jobs.map(j => j.machine_id))].sort();
  const skuClass = (sku) => `sku-${sku.split('-')[1]?.toLowerCase() || 'a'}`;

  // Day tick marks
  const dayMs = 24 * 3600 * 1000;
  const firstDay = new Date(minTime);
  firstDay.setHours(0, 0, 0, 0);
  const ticks = [];
  let t = firstDay.getTime();
  while (t <= maxTime) {
    ticks.push({ pct: toPercent(new Date(t)), label: format(new Date(t), 'MMM d') });
    t += dayMs;
  }

  return (
    <div className="gantt-container">
      {/* Day labels */}
      <div style={{ display: 'flex', marginLeft: 120, position: 'relative', height: 24, borderBottom: '1px solid var(--border)', marginBottom: 2 }}>
        {ticks.slice(0, 12).map((tick, i) => (
          <div key={i} style={{
            position: 'absolute',
            left: `${tick.pct}%`,
            fontSize: 10,
            color: 'var(--text-muted)',
            transform: 'translateX(-50%)',
            whiteSpace: 'nowrap',
          }}>
            {tick.label}
          </div>
        ))}
      </div>

      {/* Rows per machine */}
      {machines.map(mid => {
        const machineJobs = jobs.filter(j => j.machine_id === mid);
        const machineMaints = maintenance.filter(m => m.machine_id === mid);
        return (
          <div key={mid} className="gantt-row">
            <div className="gantt-row-label">{mid}</div>
            <div className="gantt-bar-area">
              {/* Maintenance windows */}
              {machineMaints.map((m, i) => (
                <div key={`maint-${i}`} className="gantt-maint" style={{
                  left: `${toPercent(m.start_time)}%`,
                  width: `${widthPercent(m.start_time, m.end_time)}%`,
                }} title={`Maintenance: ${m.reason}`} />
              ))}
              {/* Job bars */}
              {machineJobs.map(job => (
                <div
                  key={job.job_id}
                  className={`gantt-bar ${skuClass(job.sku)} ${job.has_committed_delivery ? 'delivery-warn' : ''}`}
                  style={{
                    left: `${toPercent(job.start_time)}%`,
                    width: `${widthPercent(job.start_time, job.end_time)}%`,
                  }}
                  onMouseEnter={(e) => setTooltip({ job, x: e.clientX, y: e.clientY })}
                  onMouseLeave={() => setTooltip(null)}
                >
                  {job.sku} {job.has_committed_delivery ? '⚠' : ''}
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x + 12,
          top: tooltip.y - 10,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '10px 14px',
          fontSize: 12,
          zIndex: 1000,
          pointerEvents: 'none',
          minWidth: 200,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          <div style={{ fontWeight: 700, marginBottom: 4, color: 'var(--accent-blue)' }}>{tooltip.job.job_id}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>SKU:</span> {tooltip.job.sku}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>Qty:</span> {tooltip.job.quantity}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>Start:</span> {format(new Date(tooltip.job.start_time), 'MMM d, HH:mm')}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>End:</span> {format(new Date(tooltip.job.end_time), 'MMM d, HH:mm')}</div>
          {tooltip.job.has_committed_delivery && (
            <div style={{ color: 'var(--accent-red)', marginTop: 4 }}>
              ⚠ Committed delivery: {format(new Date(tooltip.job.committed_delivery_date), 'MMM d')}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, marginTop: 12, flexWrap: 'wrap' }}>
        {['SKU-A', 'SKU-B', 'SKU-C'].map(s => (
          <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
            <div style={{ width: 12, height: 12, borderRadius: 2, background: `var(--${s.replace('-', '-').toLowerCase().replace('sku-', 'sku-')})` }} className={skuClass(s)} />
            {s}
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
          <div style={{ width: 12, height: 12, borderRadius: 2, background: 'rgba(252,129,129,0.2)', border: '1px dashed var(--accent-red)' }} />
          Maintenance
        </div>
        <div style={{ fontSize: 11, color: 'var(--accent-red)' }}>⚠ = Committed delivery date</div>
      </div>
    </div>
  );
}
