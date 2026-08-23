import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format } from 'date-fns';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export default function EditJobModal({ job, isOpen, onClose, onSuccess }) {
  const [machines, setMachines] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Form fields
  const [jobName, setJobName] = useState('');
  const [machineId, setMachineId] = useState('');
  const [quantity, setQuantity] = useState(100);
  const [priority, setPriority] = useState(5);
  const [status, setStatus] = useState('scheduled');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [hasCommittedDelivery, setHasCommittedDelivery] = useState(false);
  const [committedDate, setCommittedDate] = useState('');

  useEffect(() => {
    if (isOpen && job) {
      setError(null);
      setJobName(job.job_name || job.job_id || '');
      setMachineId(job.machine_id || '');
      setQuantity(job.quantity || 100);
      setPriority(job.priority || 5);
      setStatus(job.status || 'scheduled');
      
      try {
        setStartTime(format(new Date(job.start_time), "yyyy-MM-dd'T'HH:mm"));
        setEndTime(format(new Date(job.end_time), "yyyy-MM-dd'T'HH:mm"));
      } catch (e) {
        setStartTime('');
        setEndTime('');
      }

      setHasCommittedDelivery(!!job.has_committed_delivery);
      if (job.committed_delivery_date) {
        try {
          setCommittedDate(format(new Date(job.committed_delivery_date), "yyyy-MM-dd'T'HH:mm"));
        } catch (e) {
          setCommittedDate('');
        }
      } else {
        setCommittedDate('');
      }

      // Fetch machines
      axios.get(`${API}/machines`).then(r => setMachines(r.data || [])).catch(() => {});
    }
  }, [isOpen, job]);

  if (!isOpen || !job) return null;

  const handleSave = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const payload = {
      job_name: jobName.trim(),
      machine_id: machineId,
      quantity: parseFloat(quantity),
      priority: parseInt(priority, 10),
      status,
      start_time: new Date(startTime).toISOString(),
      end_time: new Date(endTime).toISOString(),
      has_committed_delivery: hasCommittedDelivery,
      committed_delivery_date: hasCommittedDelivery && committedDate ? new Date(committedDate).toISOString() : null,
    };

    try {
      await axios.put(`${API}/job-orders/${job.job_id}`, payload);
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update job order');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Are you sure you want to cancel and remove ${job.job_id}?`)) return;
    setLoading(true);
    try {
      await axios.delete(`${API}/job-orders/${job.job_id}`);
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete job order');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <span>✏️</span> Edit Job Order <code style={{ color: 'var(--accent-blue)', marginLeft: 6 }}>{job.job_id}</code>
          </div>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSave}>
          {error && <div className="form-error-banner">{error}</div>}

          <div className="form-group" style={{ marginBottom: 12 }}>
            <label className="form-label">Job Title / Custom Order Name</label>
            <input
              type="text"
              className="form-input"
              style={{ width: '100%' }}
              value={jobName}
              onChange={e => setJobName(e.target.value)}
              placeholder="e.g. Batch #104"
            />
          </div>

          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">Product / SKU</label>
              <input
                type="text"
                className="form-input"
                value={job.sku}
                disabled
                style={{ opacity: 0.7, cursor: 'not-allowed' }}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Assigned Machine</label>
              <select
                className="form-select"
                value={machineId}
                onChange={e => setMachineId(e.target.value)}
                required
              >
                {machines.map(m => (
                  <option key={m.machine_id} value={m.machine_id}>
                    {m.machine_id} — {m.machine_name || 'Machine'}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-grid" style={{ marginTop: 12 }}>
            <div className="form-group">
              <label className="form-label">Quantity (Units)</label>
              <input
                type="number"
                min="1"
                required
                className="form-input"
                value={quantity}
                onChange={e => setQuantity(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Order Status</label>
              <select
                className="form-select"
                value={status}
                onChange={e => setStatus(e.target.value)}
              >
                <option value="scheduled">Scheduled</option>
                <option value="in_progress">In Progress</option>
                <option value="completed">Completed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
          </div>

          <div className="form-grid" style={{ marginTop: 12 }}>
            <div className="form-group">
              <label className="form-label">Start Time</label>
              <input
                type="datetime-local"
                className="form-input"
                required
                value={startTime}
                onChange={e => setStartTime(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">End Time</label>
              <input
                type="datetime-local"
                className="form-input"
                required
                value={endTime}
                onChange={e => setEndTime(e.target.value)}
              />
            </div>
          </div>

          <div style={{ marginTop: 16, padding: '12px 14px', background: 'rgba(99,179,237,0.05)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={hasCommittedDelivery}
                onChange={e => setHasCommittedDelivery(e.target.checked)}
                style={{ width: 16, height: 16, accentColor: 'var(--accent-blue)' }}
              />
              <span>Committed Delivery Deadline</span>
            </label>

            {hasCommittedDelivery && (
              <div className="form-group" style={{ marginTop: 10 }}>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={committedDate}
                  onChange={e => setCommittedDate(e.target.value)}
                />
              </div>
            )}
          </div>

          <div className="modal-footer" style={{ justifyContent: 'space-between', marginTop: 20 }}>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={handleDelete}
              disabled={loading}
            >
              🗑 Delete Job
            </button>

            <div style={{ display: 'flex', gap: 8 }}>
              <button type="button" className="btn btn-ghost" onClick={onClose} disabled={loading}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? 'Saving…' : '✓ Save Changes'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
