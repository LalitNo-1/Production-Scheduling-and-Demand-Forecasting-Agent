import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export default function ManageMachinesModal({ isOpen, onClose, onUpdated }) {
  const [machines, setMachines] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // New machine form
  const [newMachineId, setNewMachineId] = useState('');
  const [newMachineName, setNewMachineName] = useState('');
  const [newCapacityHours, setNewCapacityHours] = useState(8);

  // Editing map: { [machine_id]: string }
  const [editingNames, setEditingNames] = useState({});

  const fetchMachines = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/machines`);
      setMachines(res.data || []);
      const initNames = {};
      (res.data || []).forEach(m => {
        initNames[m.machine_id] = m.machine_name || '';
      });
      setEditingNames(initNames);
    } catch (err) {
      setError('Failed to fetch machines');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setError(null);
      setSuccessMsg(null);
      fetchMachines();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleAddMachine = async (e) => {
    e.preventDefault();
    if (!newMachineId.trim()) return;

    setLoading(true);
    setError(null);
    try {
      await axios.post(`${API}/machines`, {
        machine_id: newMachineId.trim().toUpperCase(),
        machine_name: newMachineName.trim() || newMachineId.trim().toUpperCase(),
        capacity_hours: parseFloat(newCapacityHours) || 8,
        compatible_skus: ['SKU-A', 'SKU-B', 'SKU-C'],
      });
      setSuccessMsg(`Added ${newMachineId.toUpperCase()} successfully`);
      setNewMachineId('');
      setNewMachineName('');
      await fetchMachines();
      onUpdated?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to add machine');
    } finally {
      setLoading(false);
    }
  };

  const handleRenameMachine = async (machineId) => {
    const updatedName = editingNames[machineId];
    setLoading(true);
    setError(null);
    try {
      await axios.put(`${API}/machines/${machineId}`, {
        machine_name: updatedName,
      });
      setSuccessMsg(`Updated ${machineId} name to "${updatedName}"`);
      await fetchMachines();
      onUpdated?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to rename machine');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteMachine = async (machineId) => {
    if (!window.confirm(`Are you sure you want to remove machine ${machineId}?`)) return;

    setLoading(true);
    setError(null);
    try {
      await axios.delete(`${API}/machines/${machineId}`);
      setSuccessMsg(`Removed ${machineId}`);
      await fetchMachines();
      onUpdated?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete machine');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: 640 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <span>⚙️</span> Manage & Rename Factory Machines
          </div>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        {error && <div className="form-error-banner">{error}</div>}
        {successMsg && <div className="form-success-banner">{successMsg}</div>}

        {/* Existing Machines Table */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>
            Active Production Machines
          </div>
          
          <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
            <table className="audit-table">
              <thead>
                <tr>
                  <th style={{ width: 100 }}>Machine ID</th>
                  <th>Display Name / Label</th>
                  <th style={{ width: 90 }}>Capacity</th>
                  <th style={{ width: 110, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {machines.map(m => (
                  <tr key={m.machine_id}>
                    <td style={{ fontWeight: 700, color: 'var(--accent-blue)', fontFamily: 'JetBrains Mono, monospace' }}>
                      {m.machine_id}
                    </td>
                    <td>
                      <input
                        type="text"
                        className="form-input"
                        style={{ width: '100%', padding: '4px 8px', fontSize: 12 }}
                        value={editingNames[m.machine_id] || ''}
                        onChange={e => setEditingNames({ ...editingNames, [m.machine_id]: e.target.value })}
                        placeholder="Machine name..."
                      />
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {m.capacity_hours}h / shift
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button
                          className="btn btn-ghost btn-sm"
                          style={{ padding: '3px 8px', fontSize: 11 }}
                          onClick={() => handleRenameMachine(m.machine_id)}
                          title="Save Name"
                        >
                          💾 Save
                        </button>
                        <button
                          className="btn btn-danger btn-sm"
                          style={{ padding: '3px 8px', fontSize: 11 }}
                          onClick={() => handleDeleteMachine(m.machine_id)}
                          title="Delete Machine"
                        >
                          🗑
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Add Machine Section */}
        <div style={{ background: 'rgba(99,179,237,0.04)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>➕</span> Add New Machine Cell
          </div>

          <form onSubmit={handleAddMachine}>
            <div className="form-grid-3">
              <div className="form-group">
                <label className="form-label">Machine ID</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. MCH-04"
                  required
                  value={newMachineId}
                  onChange={e => setNewMachineId(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Display Name</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="e.g. Laser CNC Mill D"
                  value={newMachineName}
                  onChange={e => setNewMachineName(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Hours / Shift</label>
                <input
                  type="number"
                  step="0.5"
                  min="1"
                  max="24"
                  className="form-input"
                  value={newCapacityHours}
                  onChange={e => setNewCapacityHours(e.target.value)}
                />
              </div>
            </div>

            <div style={{ marginTop: 14, display: 'flex', justifyContent: 'flex-end' }}>
              <button type="submit" className="btn btn-primary btn-sm" disabled={loading}>
                + Add Machine to Floor
              </button>
            </div>
          </form>
        </div>

        <div className="modal-footer" style={{ marginTop: 20 }}>
          <button className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
