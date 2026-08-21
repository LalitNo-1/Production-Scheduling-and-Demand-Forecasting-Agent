"""
Integration tests for the agent orchestration layer.
Uses mock DB session to test the tool-calling flow.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta


def make_mock_db():
    """Create a mock DB session for testing."""
    db = MagicMock()
    
    # Mock SalesHistory
    from app.models.db import SalesHistory, MachineCapacity, JobOrder, MaintenanceWindow, ProposedChange
    
    mock_job = MagicMock(spec=JobOrder)
    mock_job.job_id = "JOB-0001"
    mock_job.sku = "SKU-A"
    mock_job.quantity = 100.0
    mock_job.machine_id = "MCH-01"
    mock_job.start_time = datetime(2025, 6, 1, 8, 0)
    mock_job.end_time = datetime(2025, 6, 1, 16, 0)
    mock_job.committed_delivery_date = datetime(2025, 6, 5)
    mock_job.has_committed_delivery = True
    mock_job.status = "scheduled"
    mock_job.priority = 3
    mock_job.margin_per_unit = 45.0
    
    mock_machine = MagicMock(spec=MachineCapacity)
    mock_machine.machine_id = "MCH-01"
    mock_machine.machine_name = "Assembly Line Alpha"
    mock_machine.shift = 1
    mock_machine.capacity_hours = 8.0
    mock_machine.utilization_pct = 72.0
    mock_machine.compatible_skus = ["SKU-A", "SKU-B"]
    
    mock_maint = MagicMock(spec=MaintenanceWindow)
    mock_maint.machine_id = "MCH-01"
    mock_maint.start_time = datetime(2025, 6, 10, 0, 0)
    mock_maint.end_time = datetime(2025, 6, 10, 8, 0)
    mock_maint.reason = "Scheduled maintenance"
    
    def mock_query(model):
        q = MagicMock()
        if model == JobOrder:
            q.filter.return_value = q
            q.filter_by.return_value = q
            q.all.return_value = [mock_job]
            q.first.return_value = mock_job
        elif model == MachineCapacity:
            q.filter.return_value = q
            q.all.return_value = [mock_machine]
        elif model == MaintenanceWindow:
            q.filter.return_value = q
            q.all.return_value = [mock_maint]
        elif model == ProposedChange:
            mock_proposed = MagicMock(spec=ProposedChange)
            mock_proposed.change_id = "CHG-ABCD1234"
            mock_proposed.status = "pending"
            mock_proposed.sku = "SKU-A"
            mock_proposed.before_state = []
            mock_proposed.after_state = []
            mock_proposed.rationale = "Test rationale"
            mock_proposed.forecast_confidence = "high"
            mock_proposed.has_delivery_date_warning = True
            mock_proposed.affected_jobs = ["JOB-0001"]
            mock_proposed.simulation_result = None
            mock_proposed.created_at = datetime.utcnow()
            mock_proposed.expires_at = None
            q.filter.return_value = q
            q.all.return_value = [mock_proposed]
            q.first.return_value = mock_proposed
        else:
            q.filter.return_value = q
            q.all.return_value = []
            q.first.return_value = None
        return q
    
    db.query = mock_query
    db.add = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.refresh = MagicMock()
    
    return db


class TestCommitGuardrail:
    """Test the hardcoded commit_schedule guardrails."""

    def test_commit_requires_approved_by(self):
        """commit_schedule must reject calls with empty approved_by."""
        from app.services.agent import AgentTools
        db = make_mock_db()
        tools = AgentTools(db)

        with pytest.raises(ValueError, match="approved_by is required"):
            tools.commit_schedule("CHG-001", approved_by="")

    def test_commit_requires_non_whitespace_approved_by(self):
        from app.services.agent import AgentTools
        db = make_mock_db()
        tools = AgentTools(db)

        with pytest.raises(ValueError, match="approved_by is required"):
            tools.commit_schedule("CHG-001", approved_by="   ")

    def test_commit_with_valid_approver_proceeds(self):
        """A valid approved_by should proceed past the guardrail check."""
        from app.services.agent import AgentTools
        db = make_mock_db()
        tools = AgentTools(db)

        # Should not raise ValueError for non-empty approved_by
        # (will fail at DB lookup, which is fine for this unit test)
        try:
            tools.commit_schedule("CHG-ABCD1234", approved_by="Jane Smith")
        except ValueError as e:
            if "approved_by is required" in str(e):
                pytest.fail("Guardrail incorrectly blocked valid approver")


class TestMockAgentWorkflow:
    """Test the mock agent's full workflow."""

    def test_mock_agent_runs_without_api_key(self):
        """MockProductionAgent should work with no API key."""
        from app.services.agent import MockProductionAgent
        db = make_mock_db()

        with patch("app.services.agent.AgentTools.get_demand_forecast") as mock_forecast, \
             patch("app.services.agent.AgentTools.get_machine_capacity") as mock_cap, \
             patch("app.services.agent.AgentTools.get_current_schedule") as mock_sched, \
             patch("app.services.agent.AgentTools.propose_schedule_change") as mock_propose, \
             patch("app.services.agent.AgentTools.simulate_schedule_impact") as mock_sim:

            mock_forecast.return_value = {
                "sku": "SKU-A", "confidence": "high", "mape_backtest": 8.0,
                "avg_daily_demand": 120.0, "total_forecast_qty": 3600.0,
                "forecast_points": []
            }
            mock_cap.return_value = {"machine_id": "MCH-01", "shifts": [], "maintenance_windows": []}
            mock_sched.return_value = {"total_jobs": 3, "jobs": []}
            mock_propose.return_value = {
                "change_id": "CHG-TEST0001", "status": "feasible",
                "assigned_count": 3, "dropped_jobs": [],
                "has_delivery_date_warning": False,
                "forecast_confidence": "high", "solver_time_s": 0.5
            }
            mock_sim.return_value = {
                "expected_fulfillment_rate": 95.0,
                "p10_fulfillment": 88.0, "p90_fulfillment": 99.0,
                "at_risk_jobs": [], "simulation_samples": 200
            }

            agent = MockProductionAgent(db)
            result = agent.run("SKU-A", horizon_days=30)

        assert result["status"] == "completed"
        assert result["proposed_change_id"] == "CHG-TEST0001"
        assert result["forecast_confidence"] == "high"
        assert len(result["reasoning_steps"]) > 0

    def test_low_confidence_blocks_proposal(self):
        """Agent must flag for human review when confidence=low."""
        from app.services.agent import MockProductionAgent
        db = make_mock_db()

        with patch("app.services.agent.AgentTools.get_demand_forecast") as mock_forecast, \
             patch("app.services.agent.AgentTools.propose_schedule_change") as mock_propose:

            mock_forecast.return_value = {
                "sku": "SKU-A", "confidence": "low", "mape_backtest": 35.0,
                "avg_daily_demand": 100.0, "total_forecast_qty": 3000.0,
                "forecast_points": []
            }

            agent = MockProductionAgent(db)
            result = agent.run("SKU-A")

        assert result["status"] == "flagged_low_confidence"
        assert result["proposed_change_id"] is None
        mock_propose.assert_not_called()


class TestSimulator:
    def test_simulation_returns_valid_percentiles(self):
        from app.services.simulator import SimulatorService
        svc = SimulatorService()

        jobs = [
            {"job_id": "JOB-001", "sku": "SKU-A", "quantity": 100.0, "has_committed_delivery": True},
            {"job_id": "JOB-002", "sku": "SKU-B", "quantity": 80.0, "has_committed_delivery": False},
        ]
        result = svc.simulate_impact(jobs, n_samples=50)

        assert 0 <= result["p10_fulfillment"] <= result["expected_fulfillment_rate"]
        assert result["expected_fulfillment_rate"] <= result["p90_fulfillment"]
        assert result["simulation_samples"] == 50

    def test_empty_jobs_gives_100_percent(self):
        from app.services.simulator import SimulatorService
        svc = SimulatorService()
        result = svc.simulate_impact([], n_samples=10)
        assert result["expected_fulfillment_rate"] == pytest.approx(100.0)
