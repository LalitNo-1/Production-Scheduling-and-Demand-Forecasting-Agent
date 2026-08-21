import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts';
import { format, parseISO } from 'date-fns';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const confidenceColor = { high: '#68d391', medium: '#f6ad55', low: '#fc8181' };

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '10px 14px', fontSize: 12,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ color: p.color }}>
          {p.name}: {Number(p.value).toFixed(1)}
        </div>
      ))}
    </div>
  );
};

export default function ForecastChart({ sku = 'SKU-A', horizon = 30, refreshKey = 0 }) {
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
        setError('Failed to load forecast');
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, [sku, horizon, refreshKey]);

  if (loading) return (
    <div>
      <div className="loading-shimmer" style={{ height: 260 }} />
    </div>
  );
  if (error || !data) return <div style={{ color: 'var(--accent-red)', padding: 20 }}>{error}</div>;

  const chartData = data.forecast.map(p => ({
    date: format(parseISO(p.date), 'MMM d'),
    forecast: +p.forecast.toFixed(1),
    lower: +p.lower_bound.toFixed(1),
    upper: +p.upper_bound.toFixed(1),
    range: [+p.lower_bound.toFixed(1), +p.upper_bound.toFixed(1)],
  }));

  const conf = data.confidence;
  const color = confidenceColor[conf] || '#63b3ed';

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          MAPE: <strong style={{ color: 'var(--text-primary)' }}>{data.mape_backtest.toFixed(1)}%</strong>
        </span>
        <span className={`badge badge-${conf}`}>{conf.toUpperCase()} CONFIDENCE</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {horizon}-day horizon
        </span>
      </div>

      <div className="forecast-chart-wrap">
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id="gradForecast" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.25} />
                <stop offset="95%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="gradBand" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.12} />
                <stop offset="95%" stopColor={color} stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,45,74,0.8)" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#4a5568', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--border)' }}
              interval={Math.floor(chartData.length / 6)}
            />
            <YAxis
              tick={{ fill: '#4a5568', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => v.toFixed(0)}
            />
            <Tooltip content={<CustomTooltip />} />
            {/* Confidence band */}
            <Area
              type="monotone"
              dataKey="upper"
              stroke="none"
              fill="url(#gradBand)"
              fillOpacity={1}
              name="Upper bound"
            />
            <Area
              type="monotone"
              dataKey="lower"
              stroke="none"
              fill="var(--bg-primary)"
              fillOpacity={1}
              name="Lower bound"
            />
            {/* Main forecast line */}
            <Area
              type="monotone"
              dataKey="forecast"
              stroke={color}
              strokeWidth={2}
              fill="url(#gradForecast)"
              dot={false}
              activeDot={{ r: 4, fill: color }}
              name="Forecast"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
