# Production Scheduling & Demand Forecasting Agent

A multi-agent system for manufacturing production scheduling that combines time-series
demand forecasting with constraint-based schedule optimization.

## Architecture

```
React Dashboard (port 5173)
       ↓
FastAPI Gateway (port 8000)
  ├── Forecasting Service (Prophet / SARIMA)
  ├── Optimization Service (OR-Tools CP-SAT)
  ├── Agent Orchestration (LangGraph + Claude / Mock)
  └── Data Layer (SQLite)
```

## Quick Start

### 1. Backend Setup

```bash
cd backend

# Create and activate virtualenv
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies (Prophet requires pystan — this may take a few minutes)
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY if you want Claude (optional)
# Leave LLM_MODE=mock to demo without an API key

# Start the API server (auto-seeds DB and trains models on first run)
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### 3. Run Tests

```bash
cd backend
source venv/bin/activate
pytest tests/ -v
```

### 4. Shadow Mode (30-day simulation)

```bash
cd backend
source venv/bin/activate
python shadow_mode/harness.py --days 30 --sku SKU-A,SKU-B,SKU-C
# Outputs: shadow_mode/shadow_report.md
```

## Environment Variables

| Variable          | Default | Description |
|-------------------|---------|-------------|
| `ANTHROPIC_API_KEY` | —     | Anthropic API key for Claude agent |
| `LLM_MODE`        | `mock`  | `mock` = no API key needed; `real` = Claude |
| `DATABASE_URL`    | `sqlite:///./production_scheduler.db` | SQLite path |
| `CORS_ORIGINS`    | `http://localhost:5173` | Allowed frontend origins |

## Mock Data

The system ships with auto-generated mock ERP data:
- **3 SKUs**: SKU-A (Widget Alpha), SKU-B (Widget Beta), SKU-C (Widget Gamma)
- **3 Machines**: MCH-01 (Assembly Alpha), MCH-02 (Assembly Beta), MCH-03 (Finishing Cell)
- **2.5 years** of daily sales with Q4 peaks, Q1 troughs, and promotional spikes
- **15 pre-loaded job orders** with some committed delivery dates
- **5 maintenance windows** scheduled over the next 60 days

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/demand-forecast` | Prophet forecast with confidence |
| GET | `/api/current-schedule` | Current job orders |
| GET | `/api/machine-capacity` | Machine capacity & maintenance |
| POST | `/api/propose-schedule-change` | OR-Tools optimizer (no commit) |
| POST | `/api/commit-schedule` | Human-gated commit + audit log |
| POST | `/api/reject-schedule-change` | Reject a proposal |
| POST | `/api/rollback/{change_id}` | Revert to pre-change state |
| GET | `/api/audit-log` | Filterable audit history |
| POST | `/api/agent/run` | Full agent reasoning cycle |

## Guardrails (Hard-coded, not prompts)

1. `commit_schedule` rejects any call where `approved_by` is empty/null
2. Any proposal touching a committed delivery date → `has_delivery_date_warning=True`
3. Low forecast confidence (MAPE > 20%) → agent flags for human review, no auto-proposal
4. Every commit writes a full before/after audit record before applying changes
5. Rollback uses the audit log to restore prior state exactly

## Confidence Scoring

| MAPE (backtest) | Confidence | Agent Behavior |
|-----------------|------------|----------------|
| < 10% | HIGH | Auto-propose + simulate |
| 10–20% | MEDIUM | Auto-propose + simulate |
| > 20% | LOW | Flag for human review only |

## Test Scenarios

```bash
# Normal: all jobs fit
pytest tests/test_optimizer.py::TestNormalCase -v

# Capacity exceeded: partial solution
pytest tests/test_optimizer.py::TestCapacityExceeded -v

# Maintenance conflict: jobs rescheduled
pytest tests/test_optimizer.py::TestMaintenanceConflict -v

# Guardrail: commit without approver → ValueError
pytest tests/test_agent.py::TestCommitGuardrail -v

# Low confidence blocks proposal
pytest tests/test_agent.py::TestMockAgentWorkflow::test_low_confidence_blocks_proposal -v
```
