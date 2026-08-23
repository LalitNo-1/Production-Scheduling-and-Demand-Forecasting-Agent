import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export default function ManageSKUsModal({ isOpen, onClose, onUpdated }) {
  const [skus, setSkus] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Form states per SKU
  const [editMap, setEditMap] = useState({});

  const fetchSKUs = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/skus`);
      setSkus(res.data || []);
      const map = {};
      (res.data || []).forEach(s => {
        map[s.sku] = {
          display_name: s.display_name || s.sku,
          description: s.description || '',
          units_per_hour: s.units_per_hour || 50,
        };
      });
      setEditMap(map);
    } catch (err) {
      setError('Failed to fetch SKUs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setError(null);
      setSuccessMsg(null);
      fetchSKUs();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSaveSKU = async (skuCode) => {
    const data = editMap[skuCode];
    if (!data) return;

    setLoading(true);
    setError(null);
    try {
      await axios.put(`${API}/skus/${skuCode}`, {
        display_name: data.display_name,
        description: data.description,
        units_per_hour: parseFloat(data.units_per_hour) || 50,
      });
      setSuccessMsg(`Updated ${skuCode} (${data.display_name})`);
      await fetchSKUs();
      onUpdated?.();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update SKU');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: 680 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <span>📦</span> Manage & Rename Product Lines (SKUs)
          </div>
          <button className="modal-close-btn" onClick={onClose}>✕</button>
        </div>

        {error && <div className="form-error-banner">{error}</div>}
        {successMsg && <div className="form-success-banner">{successMsg}</div>}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {skus.map(s => {
            const current = editMap[s.sku] || {};
            return (
              <div
                key={s.sku}
                style={{
                  background: 'var(--bg-secondary)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  padding: 16,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className={`badge sku-${s.sku.split('-')[1]?.toLowerCase() || 'a'}`} style={{ fontSize: 12 }}>
                      {s.sku}
                    </span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {s.display_name}
                    </span>
                  </div>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleSaveSKU(s.sku)}
                    disabled={loading}
                  >
                    💾 Save Changes
                  </button>
                </div>

                <div className="form-grid-3">
                  <div className="form-group">
                    <label className="form-label">Product Display Name</label>
                    <input
                      type="text"
                      className="form-input"
                      value={current.display_name || ''}
                      onChange={e => setEditMap({
                        ...editMap,
                        [s.sku]: { ...current, display_name: e.target.value }
                      })}
                      placeholder="e.g. Widget Alpha"
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Run Rate (Units / Hour)</label>
                    <input
                      type="number"
                      step="5"
                      min="1"
                      className="form-input"
                      value={current.units_per_hour || 50}
                      onChange={e => setEditMap({
                        ...editMap,
                        [s.sku]: { ...current, units_per_hour: e.target.value }
                      })}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label">Description / Spec</label>
                    <input
                      type="text"
                      className="form-input"
                      value={current.description || ''}
                      onChange={e => setEditMap({
                        ...editMap,
                        [s.sku]: { ...current, description: e.target.value }
                      })}
                      placeholder="Short spec or notes..."
                    />
                  </div>
                </div>
              </div>
            );
          })}
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
