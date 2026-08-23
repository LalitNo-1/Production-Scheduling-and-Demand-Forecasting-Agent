import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend
} from 'recharts';
import { format, parseISO } from 'date-fns';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const CONFIDENCE_META = {
  high: { label: 'High Confidence', color: '#68d391', bg: 'rgba(104, 211, 145, 0.12)', border: 'rgba(104, 211, 145, 0.3)' },
  medium: { label: 'Medium Confidence', color: '#f6ad55', bg: 'rgba(246, 173, 85, 0.12)', border: 'rgba(246, 173, 85, 0.3)' },
  low: { label: 'Low Confidence', color: '#fc8181', bg: 'rgba(252, 129, 129, 0.12)', border: 'rgba(252, 129, 129, 0.3)' },
};

const SKU_COLORS = {
  'SKU-A': '#63b3ed',
  'SKU-B': '#b794f4',
  'SKU-C': '#4fd1c5',
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const forecastItem = payload.find(p => p.dataKey === 'forecast');
  const upperItem = payload.find(p => p.dataKey === 'upper');
  const lowerItem = payload.find(p => p.dataKey === 'lower');

  return (
    <div style={{
      background: 'rgba(17, 24, 39, 0.95)',
      backdropFilter: 'blur(8px)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)',
      padding: '12px 16px',
      fontSize: 12,
      boxShadow: '0 10px 25px rgba(0,0,0,0.6)',
      minWidth: 170,
    }}>
      <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)', borderBottom: '1px solid var(--border)', paddingBottom: 4 }}>
        📅 {label}
      </div>
      {forecastItem && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 4 }}>
          <span style={{ color: 'var(--text-secondary)' }}>Projected:</span>
          <strong style={{ color: forecastItem.color || 'var(--accent-blue)', fontSize: 13 }}>
            {Number(forecastItem.value).toFixed(1)} units
          </strong>
        </div>
      )}
      {upperItem && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 11 }}>
          <span style={{ color: 'var(--text-muted)' }}>Upper Bound:</span>
          <span style={{ color: 'var(--text-secondary)' }}>{Number(upperItem.value).toFixed(1)}</span>
        </div>
      )}
      {lowerItem && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 11 }}>
          <span style={{ color: 'var(--text-muted)' }}>Lower Bound:</span>
          <span style={{ color: 'var(--text-secondary)' }}>{Number(lowerItem.value).toFixed(1)}</span>
        </div>
      )}
    </div>
  );
};

export default function ForecastChart({ sku = 'SKU-A', horizon = 30, refreshKey = 0, isCompact = false }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await axios.get(`${API}/demand-forecast`, { params: { sku, horizon } });
        setData(res.data);
      } catch (e) {
        setError('Failed to load forecast data');
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [sku, horizon, refreshKey]);

  if (loading) {
    return (
      <div style={{ padding: isCompact ? 10 : 20 }}>
        <div className="loading-shimmer" style={{ height: isCompact ? 180 : 300 }} />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ color: 'var(--accent-red)', padding: 20, textAlign: 'center' }}>
        {error || 'No forecast data available'}
      </div>
    );
  }

  const chartData = data.forecast.map(p => ({
    date: format(parseISO(p.date), 'MMM d'),
    fullDate: format(parseISO(p.date), 'EEE, MMM d, yyyy'),
    forecast: +p.forecast.toFixed(1),
    lower: +Math.max(0, p.lower_bound).toFixed(1),
    upper: +p.upper_bound.toFixed(1),
  }));

  const totalDemand = chartData.reduce((acc, c) => acc + c.forecast, 0);
  const avgDaily = chartData.length ? totalDemand / chartData.length : 0;
  const peakDay = chartData.reduce((max, c) => (c.forecast > max.forecast ? c : max), chartData[0] || { forecast: 0 });

  const confMeta = CONFIDENCE_META[data.confidence] || CONFIDENCE_META.medium;
  const themeColor = SKU_COLORS[sku] || '#63b3ed';
  const gradId = `gradForecast_${sku.replace(/[^a-zA-Z0-9]/g, '_')}`;

  return (
    <div>
      {/* Stat Tiles (in full view) */}
      {!isCompact && (
        <div className="stat-grid" style={{ marginBottom: 20 }}>
          <div className="stat-tile">
            <div className="stat-label">Total {horizon}-Day Demand</div>
            <div className="stat-value" style={{ color: themeColor }}>
              {Math.round(totalDemand).toLocaleString()} <span style={{ fontSize: 13, fontWeight: 400 }}>units</span>
            </div>
            <div className="stat-sub">Across next {horizon} production days</div>
          </div>

          <div className="stat-tile">
            <div className="stat-label">Avg Daily Requirement</div>
            <div className="stat-value">
              {Math.round(avgDaily)} <span style={{ fontSize: 13, fontWeight: 400 }}>units/day</span>
            </div>
            <div className="stat-sub">Baseline daily run rate</div>
          </div>

          <div className="stat-tile">
            <div className="stat-label">Peak Demand Spike</div>
            <div className="stat-value" style={{ color: 'var(--accent-orange)' }}>
              {Math.round(peakDay.forecast)} <span style={{ fontSize: 13, fontWeight: 400 }}>units</span>
            </div>
            <div className="stat-sub">Expected on {peakDay.date}</div>
          </div>

          <div className="stat-tile" style={{ borderLeft: `3px solid ${confMeta.color}` }}>
            <div className="stat-label">Model Confidence</div>
            <div className="stat-value" style={{ color: confMeta.color, fontSize: 20, display: 'flex', alignItems: 'center', gap: 6 }}>
              {confMeta.label}
            </div>
            <div className="stat-sub">Backtest MAPE: <strong>{data.mape_backtest.toFixed(1)}%</strong></div>
          </div>
        </div>
      )}

      {/* Main Chart */}
      <div style={{ width: '100%', height: isCompact ? 190 : 320 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 12, left: -10, bottom: 5 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={themeColor} stopOpacity={0.4} />
                <stop offset="95%" stopColor={themeColor} stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="bandGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.15} />
                <stop offset="95%" stopColor="#94a3b8" stopOpacity={0.02} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="rgba(30, 45, 74, 0.6)" vertical={false} />

            <XAxis
              dataKey="date"
              tick={{ fill: 'var(--text-secondary)', fontSize: isCompact ? 10 : 11 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
              interval={isCompact ? 6 : Math.floor(chartData.length / 8)}
            />

            <YAxis
              tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => `${v}`}
              domain={['auto', 'auto']}
            />

            <Tooltip content={<CustomTooltip />} />

            <ReferenceLine
              y={avgDaily}
              stroke="rgba(246, 224, 94, 0.5)"
              strokeDasharray="4 4"
              label={!isCompact ? { value: `Avg: ${Math.round(avgDaily)}`, fill: '#f6e05e', fontSize: 10, position: 'insideTopRight' } : undefined}
            />

            {/* Upper uncertainty bound */}
            <Area
              type="monotone"
              dataKey="upper"
              stroke="rgba(148, 163, 184, 0.4)"
              strokeDasharray="3 3"
              fill="url(#bandGrad)"
              name="Upper Bound (80%)"
            />

            {/* Forecast trajectory */}
            <Area
              type="monotone"
              dataKey="forecast"
              stroke={themeColor}
              strokeWidth={2.5}
              fill={`url(#${gradId})`}
              dot={false}
              activeDot={{ r: 5, fill: themeColor, stroke: '#fff', strokeWidth: 1.5 }}
              name="Predicted Demand"
            />

            {/* Lower uncertainty bound */}
            <Area
              type="monotone"
              dataKey="lower"
              stroke="rgba(148, 163, 184, 0.3)"
              strokeDasharray="3 3"
              fill="none"
              name="Lower Bound"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* 7-Day Table Breakdown for high clarity */}
      {!isCompact && chartData.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10, letterSpacing: '0.6px' }}>
            📅 Upcoming 7-Day Production Run Breakdown
          </div>
          <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Predicted Demand</th>
                  <th>Expected Range (80% Confidence)</th>
                  <th>Shift Load Status</th>
                </tr>
              </thead>
              <tbody>
                {chartData.slice(0, 7).map((row, idx) => {
                  const isHigh = row.forecast > avgDaily * 1.15;
                  const isLow = row.forecast < avgDaily * 0.85;
                  return (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {row.fullDate}
                      </td>
                      <td>
                        <strong style={{ color: themeColor, fontSize: 14 }}>
                          {row.forecast}
                        </strong> <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>units</span>
                      </td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                        {row.lower} – {row.upper} units
                      </td>
                      <td>
                        {isHigh ? (
                          <span className="badge badge-warn" style={{ fontSize: 10 }}>⚡ Peak Load</span>
                        ) : isLow ? (
                          <span className="badge badge-mock" style={{ fontSize: 10 }}>📉 Light Demand</span>
                        ) : (
                          <span className="badge badge-live" style={{ fontSize: 10 }}>✓ Normal Shift</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
