import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format } from 'date-fns';
import EditJobModal from './EditJobModal';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/**
 * Gantt chart component — renders job orders as time-scaled bars.
 * Groups by machine, shows maintenance windows in red, delivery-date warnings dashed.
 */
export default function GanttChart({ sku = null, refreshKey = 0, onRefresh = null }) {
  const [jobs, setJobs] = useState([]);
  const [maintenance, setMaintenance] = useState([]);
  const [machinesList, setMachinesList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [isEditOpen, setIsEditOpen] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [schedRes, maintRes, machRes] = await Promise.all([
          axios.get(`${API}/current-schedule`, { params: sku ? { sku } : {} }),
          axios.get(`${API}/maintenance-windows`),
          axios.get(`${API}/machines`),
        ]);
        setJobs(schedRes.data.jobs || []);
        setMaintenance(maintRes.data || []);
        setMachinesList(machRes.data || []);
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
          <div className="loading-shimmer" style={{ width: 140, flexShrink: 0 }} />
          <div className="loading-shimmer" style={{ flex: 1 }} />
        </div>
      ))}
    </div>
  );

  if (!jobs.length && !machinesList.length) return (
    <div className="empty-state">
      <div className="icon">📋</div>
      <div>No scheduled jobs or machines found</div>
    </div>
  );

  // Map machine_id -> machine_name
  const machineNameMap = {};
  machinesList.forEach(m => {
    machineNameMap[m.machine_id] = m.machine_name || m.machine_id;
  });

  // Determine time range (at least 7 days from now if empty)
  const now = new Date();
  const allTimes = jobs.length > 0
    ? jobs.flatMap(j => [new Date(j.start_time), new Date(j.end_time)])
    : [now, new Date(now.getTime() + 7 * 24 * 3600 * 1000)];

  const minTime = new Date(Math.min(...allTimes)).getTime();
  const maxTime = new Date(Math.max(...allTimes)).getTime();
  const totalMs = Math.max(maxTime - minTime, 3600 * 1000);

  const toPercent = (dt) => Math.max(0, ((new Date(dt).getTime() - minTime) / totalMs) * 100);
  const widthPercent = (start, end) => Math.max(1.2, ((new Date(end).getTime() - new Date(start).getTime()) / totalMs) * 100);

  // Collect all machine IDs from registry + jobs
  const distinctMachineIds = [...new Set([
    ...machinesList.map(m => m.machine_id),
    ...jobs.map(j => j.machine_id)
  ])].sort();

  const skuClass = (skuCode) => `sku-${skuCode.split('-')[1]?.toLowerCase() || 'a'}`;

  // Day tick marks
  const dayMs = 24 * 3600 * 1000;
  const firstDay = new Date(minTime);
  firstDay.setHours(0, 0, 0, 0);
  const ticks = [];
  let t = firstDay.getTime();
  while (t <= maxTime + dayMs) {
    ticks.push({ pct: toPercent(new Date(t)), label: format(new Date(t), 'MMM d') });
    t += dayMs;
  }

  const handleJobClick = (job) => {
    setSelectedJob(job);
    setIsEditOpen(true);
  };

  return (
    <div className="gantt-container">
      {/* Day labels */}
      <div style={{ display: 'flex', marginLeft: 160, position: 'relative', height: 24, borderBottom: '1px solid var(--border)', marginBottom: 2 }}>
        {ticks.slice(0, 14).map((tick, i) => (
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
      {distinctMachineIds.map(mid => {
        const machineJobs = jobs.filter(j => j.machine_id === mid);
        const machineMaints = maintenance.filter(m => m.machine_id === mid);
        const displayName = machineNameMap[mid] || mid;

        return (
          <div key={mid} className="gantt-row">
            <div className="gantt-row-label" style={{ width: 160, minWidth: 160 }}>
              <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: 12 }}>{mid}</div>
              <div style={{ fontSize: 10, color: 'var(--accent-blue)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }} title={displayName}>
                {displayName}
              </div>
            </div>
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
                  onClick={() => handleJobClick(job)}
                  onMouseEnter={(e) => setTooltip({ job, x: e.clientX, y: e.clientY })}
                  onMouseLeave={() => setTooltip(null)}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {job.job_name || `${job.sku} (${job.quantity})`} {job.has_committed_delivery ? '⚠' : ''}
                  </span>
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
          left: tooltip.x + 14,
          top: tooltip.y - 10,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '10px 14px',
          fontSize: 12,
          zIndex: 1000,
          pointerEvents: 'none',
          minWidth: 220,
          boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
        }}>
          <div style={{ fontWeight: 700, marginBottom: 4, color: 'var(--accent-blue)' }}>
            {tooltip.job.job_name || tooltip.job.job_id}
          </div>
          <div><span style={{ color: 'var(--text-muted)' }}>Job ID:</span> {tooltip.job.job_id}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>SKU:</span> {tooltip.job.sku}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>Qty:</span> {tooltip.job.quantity} units</div>
          <div><span style={{ color: 'var(--text-muted)' }}>Start:</span> {format(new Date(tooltip.job.start_time), 'MMM d, HH:mm')}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>End:</span> {format(new Date(tooltip.job.end_time), 'MMM d, HH:mm')}</div>
          {tooltip.job.has_committed_delivery && (
            <div style={{ color: 'var(--accent-red)', marginTop: 4, fontWeight: 600 }}>
              ⚠ Committed: {tooltip.job.committed_delivery_date ? format(new Date(tooltip.job.committed_delivery_date), 'MMM d, HH:mm') : 'Required'}
            </div>
          )}
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6, fontStyle: 'italic' }}>
            Click bar to edit or rename
          </div>
        </div>
      )}

      {/* Legend & Controls */}
      <div style={{ display: 'flex', gap: 16, marginTop: 14, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          {['SKU-A', 'SKU-B', 'SKU-C'].map(s => (
            <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
              <div style={{ width: 12, height: 12, borderRadius: 2 }} className={`gantt-bar ${skuClass(s)}`} />
              {s}
            </div>
          ))}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
            <div style={{ width: 12, height: 12, borderRadius: 2, background: 'rgba(252,129,129,0.2)', border: '1px dashed var(--accent-red)' }} />
            Maintenance Window
          </div>
          <div style={{ fontSize: 11, color: 'var(--accent-red)', fontWeight: 600 }}>
            ⚠ = Committed delivery deadline
          </div>
        </div>

        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          💡 <em>Tip: Click any job bar to rename, reschedule, or delete it.</em>
        </div>
      </div>

      {/* Edit Job Modal */}
      <EditJobModal
        job={selectedJob}
        isOpen={isEditOpen}
        onClose={() => {
          setIsEditOpen(false);
          setSelectedJob(null);
        }}
        onSuccess={() => {
          onRefresh?.();
        }}
      />
    </div>
  );
}
