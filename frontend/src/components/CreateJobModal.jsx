import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { format, addHours } from 'date-fns';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export default function CreateJobModal({ isOpen, onClose, onSuccess, initialMachineId = null }) {
  const [machines, setMachines] = useState([]);
  const [skus, setSkus] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Form fields
  const [sku, setSku] = useState('SKU-A');
  const [machineId, setMachineId] = useState('');
  const [jobName, setJobName] = useState('');
  const [quantity, setQuantity] = useState(150);
  const [priority, setPriority] = useState(5);
  
  // Dates
  const nowStr = format(new Date(), "yyyy-MM-dd'T'HH:mm");
  const [startTime, setStartTime] = useState(nowStr);
  const [durationHours, setDurationHours] = useState(8);
  const [hasCommittedDelivery, setHasCommittedDelivery] = useState(false);
  const [committedDate, setCommittedDate] = useState(format(addHours(new Date(), 48), "yyyy-MM-dd'T'HH:mm"));

  useEffect(() => {
    if (isOpen) {
      setError(null);
      Promise.all([
        axios.get(`${API}/machines`),
        axios.get(`${API}/skus`),
      ]).then(([mRes, sRes]) => {
        setMachines(mRes.data || []);
        setSkus(sRes.data || []);
        if (mRes.data.length > 0 && !machineId) {
          setMachineId(initialMachineId || mRes.data[0].machine_id);
        }
      }).catch(err => {
        console.error('Failed to load modal options', err);
      });
    }
  }, [isOpen, initialMachineId]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const startDt = new Date(startTime);
    const endDt = addHours(startDt, parseFloat(durationHours) || 8);

    const payload = {
      sku,
      machine_id: machineId,
      job_name: jobName.trim() || `${sku} Batch #${Math.floor(Math.random() * 900 + 100)}`,
      quantity: parseFloat(quantity),
      priority: parseInt(priority, 10),
      start_time: startDt.toISOString(),
      end_time: endDt.toISOString(),
      has_committed_delivery: hasCommittedDelivery,
      committed_delivery_date: hasCommittedDelivery ? new Date(committedDate).toISOString() : null,
    };

    try {
      await axios.post(`${API}/job-orders`, payload);
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to schedule job order');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <span>📅</span> Schedule New Production Order
          </div>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        <form onSubmit={handleSubmit}>
          {error && <div className="form-error-banner">{error}</div>}

          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">Product / SKU</label>
              <select
                className="form-select"
                value={sku}
                onChange={e => {
                  setSku(e.target.value);
                  const found = skus.find(s => s.sku === e.target.value);
                  if (found) {
                    setJobName(`${found.display_name || found.sku} Run`);
                  }
                }}
              >
                {skus.map(s => (
                  <option key={s.sku} value={s.sku}>
                    {s.sku} — {s.display_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Target Machine Cell</label>
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

          <div className="form-group" style={{ marginTop: 12 }}>
            <label className="form-label">Job Title / Custom Order Name</label>
            <input
              type="text"
              className="form-input"
              style={{ width: '100%' }}
              placeholder="e.g. Express Assembly Run A"
              value={jobName}
              onChange={e => setJobName(e.target.value)}
            />
          </div>

          <div className="form-grid" style={{ marginTop: 12 }}>
            <div className="form-group">
              <label className="form-label">Production Quantity (Units)</label>
              <input
                type="number"
                className="form-input"
                min="1"
                required
                value={quantity}
                onChange={e => setQuantity(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Priority (1 = Highest, 10 = Normal)</label>
              <select
                className="form-select"
                value={priority}
                onChange={e => setPriority(e.target.value)}
              >
                <option value={1}>1 - Critical / Rush Order</option>
                <option value={3}>3 - High Priority</option>
                <option value={5}>5 - Standard Priority</option>
                <option value={8}>8 - Low Priority</option>
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
              <label className="form-label">Duration (Hours)</label>
              <input
                type="number"
                step="0.5"
                min="0.5"
                className="form-input"
                required
                value={durationHours}
                onChange={e => setDurationHours(e.target.value)}
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
              <span>Enforce Committed Customer Delivery Date</span>
            </label>

            {hasCommittedDelivery && (
              <div className="form-group" style={{ marginTop: 10 }}>
                <label className="form-label">Committed Delivery Deadline</label>
                <input
                  type="datetime-local"
                  className="form-input"
                  value={committedDate}
                  onChange={e => setCommittedDate(e.target.value)}
                />
                <div style={{ fontSize: 11, color: 'var(--accent-yellow)', marginTop: 4 }}>
                  ⚠️ The optimizer and dashboard will flag warnings if machine bottlenecks jeopardize this deadline.
                </div>
              </div>
            )}
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-ghost" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Scheduling…' : '✓ Schedule Order'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
