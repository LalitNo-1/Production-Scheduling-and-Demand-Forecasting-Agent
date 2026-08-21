"""
Agent orchestration layer using LangGraph with Claude (Anthropic).
Supports a mock LLM mode (LLM_MODE=mock) for demos without an API key.

Workflow:
1. get_demand_forecast  →  check confidence
2a. LOW confidence     →  flag for human, stop
2b. MED/HIGH           →  propose_schedule_change → simulate_schedule_impact
3. Return human-readable summary for approve/reject
"""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)

LLM_MODE = os.getenv("LLM_MODE", "mock").lower()


# ── Tool definitions (called by both real and mock agents) ───────────────────

class AgentTools:
    """Thin wrappers around the service layer — these are what the LLM calls."""

    def __init__(self, db):
        self.db = db

    def get_demand_forecast(self, sku: str, horizon: int = 30) -> Dict:
        from app.services.forecasting import get_forecasting_service
        svc = get_forecasting_service(self.db)
        points, mape, confidence = svc.forecast(sku, horizon)
        return {
            "sku": sku,
            "horizon_days": horizon,
            "confidence": confidence,
            "mape_backtest": mape,
            "total_forecast_qty": sum(p["forecast"] for p in points),
            "avg_daily_demand": sum(p["forecast"] for p in points) / max(1, len(points)),
            "forecast_points": [
                {
                    "date": p["date"].isoformat(),
                    "forecast": round(p["forecast"], 1),
                    "lower": round(p["lower_bound"], 1),
                    "upper": round(p["upper_bound"], 1),
                }
                for p in points[:7]  # first 7 days in tool response (full data in API)
            ],
        }

    def get_machine_capacity(self, machine_id: str, date_range: Optional[str] = None) -> Dict:
        from app.models.db import MachineCapacity, MaintenanceWindow
        rows = self.db.query(MachineCapacity).filter(
            MachineCapacity.machine_id == machine_id
        ).all()
        windows = self.db.query(MaintenanceWindow).filter(
            MaintenanceWindow.machine_id == machine_id
        ).all()
        return {
            "machine_id": machine_id,
            "shifts": [
                {
                    "shift": r.shift,
                    "capacity_hours": r.capacity_hours,
                    "available_hours": r.capacity_hours * (1 - r.utilization_pct / 100),
                    "utilization_pct": r.utilization_pct,
                }
                for r in rows
            ],
            "maintenance_windows": [
                {"start": w.start_time.isoformat(), "end": w.end_time.isoformat(), "reason": w.reason}
                for w in windows
            ],
        }

    def get_current_schedule(self, sku: Optional[str] = None, machine_id: Optional[str] = None) -> Dict:
        from app.models.db import JobOrder
        q = self.db.query(JobOrder).filter(JobOrder.status.in_(["scheduled", "in_progress"]))
        if sku:
            q = q.filter(JobOrder.sku == sku)
        if machine_id:
            q = q.filter(JobOrder.machine_id == machine_id)
        jobs = q.all()
        return {
            "total_jobs": len(jobs),
            "jobs": [
                {
                    "job_id": j.job_id,
                    "sku": j.sku,
                    "quantity": j.quantity,
                    "machine_id": j.machine_id,
                    "start_time": j.start_time.isoformat(),
                    "end_time": j.end_time.isoformat(),
                    "has_committed_delivery": j.has_committed_delivery,
                    "committed_delivery_date": j.committed_delivery_date.isoformat() if j.committed_delivery_date else None,
                    "status": j.status,
                }
                for j in jobs
            ],
        }

    def propose_schedule_change(
        self,
        sku: str,
        horizon_days: int = 30,
        machine_id: Optional[str] = None,
    ) -> Dict:
        """Runs optimizer → stores ProposedChange in DB → returns change_id + diff."""
        from app.models.db import JobOrder, MachineCapacity, MaintenanceWindow, ProposedChange
        from app.services.optimizer import get_optimizer, JobInput, MachineInput
        from app.services.forecasting import get_forecasting_service

        # Get forecast
        svc = get_forecasting_service(self.db)
        points, mape, confidence = svc.forecast(sku, horizon_days)
        total_demand = sum(p["forecast"] for p in points)

        # Build job inputs from current schedule
        jobs_db = self.db.query(JobOrder).filter(
            JobOrder.status == "scheduled",
            JobOrder.sku == sku,
        ).all()
        if machine_id:
            jobs_db = [j for j in jobs_db if j.machine_id == machine_id]

        now = datetime.utcnow()
        job_inputs = []
        for j in jobs_db:
            machines_db = self.db.query(MachineCapacity).filter(
                MachineCapacity.compatible_skus.contains(j.sku)
            ).all()
            eligible = list({m.machine_id for m in machines_db})
            hours = max(1.0, (j.end_time - j.start_time).total_seconds() / 3600)
            job_inputs.append(JobInput(
                job_id=j.job_id,
                sku=j.sku,
                quantity=j.quantity,
                eligible_machines=eligible or [j.machine_id],
                duration_hours=hours,
                earliest_start=now,
                latest_end=j.committed_delivery_date or (now + timedelta(days=horizon_days)),
                committed_delivery_date=j.committed_delivery_date,
                has_committed_delivery=j.has_committed_delivery,
                priority=j.priority,
                margin_per_unit=j.margin_per_unit,
            ))

        # Build machine inputs
        all_machines = self.db.query(MachineCapacity).all()
        machine_dict: Dict[str, MachineInput] = {}
        for m in all_machines:
            if m.machine_id not in machine_dict:
                windows = self.db.query(MaintenanceWindow).filter(
                    MaintenanceWindow.machine_id == m.machine_id
                ).all()
                machine_dict[m.machine_id] = MachineInput(
                    machine_id=m.machine_id,
                    shifts=[{"shift": m.shift, "capacity_hours": m.capacity_hours}],
                    maintenance_windows=[
                        {"start_time": w.start_time, "end_time": w.end_time,
                         "is_hard_constraint": w.is_hard_constraint}
                        for w in windows
                    ],
                )

        result = get_optimizer().propose_schedule(
            job_inputs, list(machine_dict.values()), base_time=now
        )

        # Build before/after state
        before_state = [
            {
                "job_id": j.job_id, "sku": j.sku,
                "machine_id": j.machine_id,
                "start_time": j.start_time.isoformat(),
                "end_time": j.end_time.isoformat(),
                "quantity": j.quantity,
                "has_committed_delivery": j.has_committed_delivery,
                "committed_delivery_date": j.committed_delivery_date.isoformat() if j.committed_delivery_date else None,
            }
            for j in jobs_db
        ]
        after_state = [
            {
                "job_id": aj.job_id, "sku": aj.sku,
                "machine_id": aj.machine_id,
                "start_time": aj.start_time.isoformat(),
                "end_time": aj.end_time.isoformat(),
                "quantity": aj.quantity,
                "has_committed_delivery": aj.has_committed_delivery,
                "committed_delivery_date": aj.committed_delivery_date.isoformat() if aj.committed_delivery_date else None,
            }
            for aj in result.assigned_jobs
        ]

        has_delivery_warning = any(
            j.has_committed_delivery for j in jobs_db
        ) or bool(result.dropped_jobs)

        affected_jobs = [j.job_id for j in jobs_db]

        change_id = f"CHG-{uuid.uuid4().hex[:8].upper()}"
        proposed = ProposedChange(
            change_id=change_id,
            sku=sku,
            status="pending",
            before_state=before_state,
            after_state=after_state,
            rationale=(
                f"Optimizer re-scheduled {len(result.assigned_jobs)} jobs for {sku} "
                f"over {horizon_days}-day horizon. Status: {result.status}. "
                f"Dropped: {len(result.dropped_jobs)} jobs. "
                f"Forecast demand: {total_demand:.0f} units. "
                f"Confidence: {confidence}."
            ),
            forecast_confidence=confidence,
            has_delivery_date_warning=has_delivery_warning,
            affected_jobs=affected_jobs,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        self.db.add(proposed)
        self.db.commit()
        self.db.refresh(proposed)

        return {
            "change_id": change_id,
            "status": result.status,
            "assigned_count": len(result.assigned_jobs),
            "dropped_jobs": result.dropped_jobs,
            "has_delivery_date_warning": has_delivery_warning,
            "forecast_confidence": confidence,
            "solver_time_s": result.solver_wall_time_s,
        }

    def simulate_schedule_impact(self, change_id: str) -> Dict:
        from app.models.db import ProposedChange
        from app.services.simulator import get_simulator

        proposed = self.db.query(ProposedChange).filter(
            ProposedChange.change_id == change_id
        ).first()
        if not proposed:
            return {"error": f"Change {change_id} not found"}

        result = get_simulator().simulate_impact(proposed.after_state or [])

        # Persist simulation result
        proposed.simulation_result = result
        self.db.commit()

        return result

    def commit_schedule(self, change_id: str, approved_by: str, notes: str = "") -> Dict:
        """
        HARDCODED GUARDRAIL: approved_by must be non-empty.
        Writes full audit record before applying changes.
        """
        # ── Guardrail 1: approved_by required ────────────────────────────────
        if not approved_by or not approved_by.strip():
            raise ValueError(
                "commit_schedule REJECTED: approved_by is required. "
                "This change cannot be auto-committed — a human approver must be specified."
            )

        from app.models.db import ProposedChange, JobOrder, AuditLog

        proposed = self.db.query(ProposedChange).filter(
            ProposedChange.change_id == change_id
        ).first()
        if not proposed:
            raise ValueError(f"Change {change_id} not found")
        if proposed.status != "pending":
            raise ValueError(f"Change {change_id} is not in pending status (current: {proposed.status})")

        # ── Guardrail 2: delivery date warning must be preserved in audit ─────
        # (already set on proposed object — just ensure it flows through)

        # Write audit record FIRST (append-only, never deleted)
        audit = AuditLog(
            change_id=change_id,
            timestamp=datetime.utcnow(),
            actor=approved_by.strip(),
            action="commit",
            before_state=proposed.before_state,
            after_state=proposed.after_state,
            sku=proposed.sku,
            forecast_confidence=proposed.forecast_confidence,
            has_delivery_date_warning=proposed.has_delivery_date_warning,
            approval_status="approved",
            notes=notes,
        )
        self.db.add(audit)
        self.db.flush()

        # Apply the schedule change — update job orders
        if proposed.after_state:
            for job_data in proposed.after_state:
                job = self.db.query(JobOrder).filter(
                    JobOrder.job_id == job_data["job_id"]
                ).first()
                if job:
                    job.machine_id = job_data["machine_id"]
                    job.start_time = datetime.fromisoformat(job_data["start_time"])
                    job.end_time = datetime.fromisoformat(job_data["end_time"])
                    job.updated_at = datetime.utcnow()

        proposed.status = "approved"
        proposed.approved_by = approved_by.strip()
        proposed.approved_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(audit)

        return {
            "change_id": change_id,
            "committed": True,
            "audit_id": audit.id,
            "message": f"Schedule committed by {approved_by}. Audit record #{audit.id} created.",
        }

    def rollback_schedule_change(self, change_id: str, rolled_back_by: str) -> Dict:
        """Reverts to pre-change state using audit log."""
        from app.models.db import AuditLog, JobOrder, ProposedChange

        audit = self.db.query(AuditLog).filter(
            AuditLog.change_id == change_id,
            AuditLog.action == "commit",
        ).order_by(AuditLog.timestamp.desc()).first()

        if not audit:
            raise ValueError(f"No committed audit record found for change {change_id}")

        before_state = audit.before_state or []
        restored = 0
        for job_data in before_state:
            job = self.db.query(JobOrder).filter(
                JobOrder.job_id == job_data["job_id"]
            ).first()
            if job:
                job.machine_id = job_data["machine_id"]
                job.start_time = datetime.fromisoformat(job_data["start_time"])
                job.end_time = datetime.fromisoformat(job_data["end_time"])
                job.updated_at = datetime.utcnow()
                restored += 1

        # Write rollback audit record
        rollback_audit = AuditLog(
            change_id=change_id,
            timestamp=datetime.utcnow(),
            actor=rolled_back_by,
            action="rollback",
            before_state=audit.after_state,
            after_state=audit.before_state,
            sku=audit.sku,
            forecast_confidence=audit.forecast_confidence,
            has_delivery_date_warning=audit.has_delivery_date_warning,
            approval_status="rolled_back",
            notes=f"Rollback of commit by {audit.actor}",
        )
        self.db.add(rollback_audit)

        # Update proposed change status
        proposed = self.db.query(ProposedChange).filter(
            ProposedChange.change_id == change_id
        ).first()
        if proposed:
            proposed.status = "rolled_back"

        self.db.commit()

        return {
            "change_id": change_id,
            "rolled_back": True,
            "jobs_restored": restored,
            "message": f"Rolled back {restored} jobs to pre-change state.",
        }


# ── Mock Agent (no API key required) ─────────────────────────────────────────

class MockProductionAgent:
    """
    Deterministic mock agent that follows the full workflow without Claude.
    Used when LLM_MODE=mock or no ANTHROPIC_API_KEY is set.
    """

    def __init__(self, db):
        self.tools = AgentTools(db)

    def run(self, sku: str, horizon_days: int = 30, machine_id: Optional[str] = None) -> Dict:
        steps = []

        # Step 1: Get forecast
        steps.append(f"[Tool] get_demand_forecast(sku={sku}, horizon={horizon_days})")
        forecast_result = self.tools.get_demand_forecast(sku, horizon_days)
        confidence = forecast_result["confidence"]
        mape = forecast_result["mape_backtest"]
        steps.append(
            f"[Observation] Forecast confidence={confidence}, MAPE={mape:.1f}%, "
            f"avg_daily_demand={forecast_result['avg_daily_demand']:.1f} units"
        )

        # Step 2: Low confidence guard
        if confidence == "low":
            steps.append(
                "[Decision] Confidence is LOW. Flagging for human review. "
                "NOT auto-proposing any schedule change."
            )
            return {
                "sku": sku,
                "status": "flagged_low_confidence",
                "message": (
                    f"⚠️ Forecast confidence is LOW (MAPE={mape:.1f}%) for {sku}. "
                    "A human planner must review before any schedule change is proposed. "
                    "No proposal has been generated."
                ),
                "proposed_change_id": None,
                "forecast_confidence": confidence,
                "reasoning_steps": steps,
            }

        # Step 3: Get machine capacity
        machines = ["MCH-01", "MCH-02", "MCH-03"]
        for mid in machines:
            steps.append(f"[Tool] get_machine_capacity(machine_id={mid})")
            cap = self.tools.get_machine_capacity(mid)
            available = sum(s["available_hours"] for s in cap["shifts"])
            steps.append(f"[Observation] {mid}: {available:.1f} available hours, {len(cap['maintenance_windows'])} maintenance windows")

        # Step 4: Get current schedule
        steps.append(f"[Tool] get_current_schedule(sku={sku})")
        schedule = self.tools.get_current_schedule(sku=sku)
        steps.append(f"[Observation] Found {schedule['total_jobs']} scheduled jobs for {sku}")

        # Step 5: Propose schedule change
        steps.append(f"[Tool] propose_schedule_change(sku={sku}, horizon={horizon_days})")
        proposal = self.tools.propose_schedule_change(sku, horizon_days, machine_id)
        change_id = proposal["change_id"]
        steps.append(
            f"[Observation] Proposed change {change_id}: "
            f"{proposal['assigned_count']} jobs assigned, "
            f"{len(proposal.get('dropped_jobs', []))} dropped. "
            f"Delivery date warning: {proposal['has_delivery_date_warning']}"
        )

        # Step 6: Simulate impact
        steps.append(f"[Tool] simulate_schedule_impact(change_id={change_id})")
        impact = self.tools.simulate_schedule_impact(change_id)
        steps.append(
            f"[Observation] Expected fulfillment: {impact['expected_fulfillment_rate']:.1f}% "
            f"(p10={impact['p10_fulfillment']:.1f}%, p90={impact['p90_fulfillment']:.1f}%). "
            f"At-risk jobs: {len(impact.get('at_risk_jobs', []))}"
        )

        # Step 7: Generate human-readable summary
        dropped = proposal.get("dropped_jobs", [])
        warning_text = ""
        if proposal["has_delivery_date_warning"]:
            warning_text = "\n⚠️ **DELIVERY DATE WARNING**: This change affects jobs with committed delivery dates."

        summary = (
            f"## Schedule Change Proposal: {change_id}\n\n"
            f"**SKU**: {sku} | **Horizon**: {horizon_days} days | "
            f"**Forecast confidence**: {confidence.upper()} (MAPE={mape:.1f}%)\n\n"
            f"### What's Changing\n"
            f"- {proposal['assigned_count']} jobs re-optimized by CP-SAT solver\n"
            f"- {len(dropped)} jobs dropped (capacity constraint): {', '.join(dropped) or 'none'}\n"
            f"- Avg daily demand forecast: {forecast_result['avg_daily_demand']:.1f} units\n\n"
            f"### Expected Impact\n"
            f"- Fulfillment rate: **{impact['expected_fulfillment_rate']:.1f}%** "
            f"(range: {impact['p10_fulfillment']:.1f}%–{impact['p90_fulfillment']:.1f}%)\n"
            f"- At-risk jobs: {', '.join(impact.get('at_risk_jobs', [])) or 'none'}\n"
            f"{warning_text}\n\n"
            f"**Action required**: Approve or reject this proposal in the dashboard."
        )

        steps.append(f"[Summary generated] Awaiting human approval for change {change_id}")

        return {
            "sku": sku,
            "status": "completed",
            "message": summary,
            "proposed_change_id": change_id,
            "forecast_confidence": confidence,
            "reasoning_steps": steps,
        }


# ── Real LangGraph Agent (requires ANTHROPIC_API_KEY) ────────────────────────

class LangGraphProductionAgent:
    """Real agent using LangGraph + Claude. Requires ANTHROPIC_API_KEY."""

    def __init__(self, db):
        self.db = db
        self._build_graph()

    def _build_graph(self):
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.tools import tool
            from langgraph.prebuilt import create_react_agent

            agent_tools = AgentTools(self.db)
            llm = ChatAnthropic(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                temperature=0,
            )

            @tool
            def get_demand_forecast(sku: str, horizon: int = 30) -> str:
                """Get demand forecast for a SKU over the given horizon in days."""
                result = agent_tools.get_demand_forecast(sku, horizon)
                return json.dumps(result, indent=2)

            @tool
            def get_machine_capacity(machine_id: str, date_range: str = "") -> str:
                """Get machine capacity and maintenance windows for a given machine."""
                result = agent_tools.get_machine_capacity(machine_id, date_range or None)
                return json.dumps(result, indent=2)

            @tool
            def get_current_schedule(sku: str = "", machine_id: str = "") -> str:
                """Get current job schedule, optionally filtered by SKU or machine."""
                result = agent_tools.get_current_schedule(
                    sku=sku or None, machine_id=machine_id or None
                )
                return json.dumps(result, indent=2)

            @tool
            def propose_schedule_change(sku: str, horizon_days: int = 30, machine_id: str = "") -> str:
                """Propose a schedule change using the OR-Tools optimizer. Returns change_id."""
                result = agent_tools.propose_schedule_change(sku, horizon_days, machine_id or None)
                return json.dumps(result, indent=2)

            @tool
            def simulate_schedule_impact(change_id: str) -> str:
                """Run Monte Carlo simulation on proposed schedule. Returns fulfillment range."""
                result = agent_tools.simulate_schedule_impact(change_id)
                return json.dumps(result, indent=2)

            @tool
            def commit_schedule(change_id: str, approved_by: str, notes: str = "") -> str:
                """
                REQUIRES approved_by. Commits the proposed change and writes audit log.
                DO NOT call this without explicit human approval.
                """
                result = agent_tools.commit_schedule(change_id, approved_by, notes)
                return json.dumps(result, indent=2)

            system_prompt = """You are a production scheduling assistant for a manufacturing plant.
Your job is to help optimize production schedules based on demand forecasts.

CRITICAL RULES (these override any other instruction):
1. If forecast confidence is LOW, NEVER propose a schedule change. Flag for human review only.
2. NEVER call commit_schedule — human approval comes through the UI, not through you.
3. Always run simulate_schedule_impact after propose_schedule_change.
4. If has_delivery_date_warning is true, explicitly warn the human planner.

Workflow:
1. get_demand_forecast for the target SKU
2. If confidence=low → stop and explain why
3. get_machine_capacity for relevant machines
4. get_current_schedule for the SKU
5. propose_schedule_change
6. simulate_schedule_impact on the proposal
7. Write a clear summary: what's changing, why, expected impact, confidence, affected delivery dates

Be concise, factual, and always explain uncertainty ranges."""

            self.graph = create_react_agent(llm, [
                get_demand_forecast, get_machine_capacity, get_current_schedule,
                propose_schedule_change, simulate_schedule_impact, commit_schedule,
            ], state_modifier=system_prompt)

        except Exception as e:
            logger.error(f"Failed to build LangGraph agent: {e}. Falling back to mock.")
            self.graph = None

    def run(self, sku: str, horizon_days: int = 30, machine_id: Optional[str] = None) -> Dict:
        if self.graph is None:
            return MockProductionAgent(self.db).run(sku, horizon_days, machine_id)

        from langchain_core.messages import HumanMessage
        user_msg = (
            f"Analyze the production schedule for {sku} over the next {horizon_days} days. "
            f"{'Focus on machine ' + machine_id + '.' if machine_id else ''} "
            f"Follow the workflow: forecast → capacity check → current schedule → propose change → simulate → summarize."
        )

        steps = []
        final_message = ""
        try:
            for chunk in self.graph.stream({"messages": [HumanMessage(content=user_msg)]}):
                for node, values in chunk.items():
                    msgs = values.get("messages", [])
                    for msg in msgs:
                        steps.append(f"[{node}] {getattr(msg, 'content', str(msg))[:200]}")
                        final_message = getattr(msg, "content", str(msg))
        except Exception as e:
            logger.error(f"Agent run failed: {e}")
            return MockProductionAgent(self.db).run(sku, horizon_days, machine_id)

        # Extract change_id from steps if present
        change_id = None
        for step in steps:
            if "CHG-" in step:
                import re
                m = re.search(r"CHG-[A-F0-9]{8}", step)
                if m:
                    change_id = m.group(0)
                    break

        return {
            "sku": sku,
            "status": "completed",
            "message": final_message,
            "proposed_change_id": change_id,
            "forecast_confidence": None,
            "reasoning_steps": steps,
        }


# ── Factory ───────────────────────────────────────────────────────────────────

def get_agent(db) -> Any:
    """Return the appropriate agent based on LLM_MODE env var."""
    mode = os.getenv("LLM_MODE", "mock").lower()
    has_key = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())

    if mode == "mock" or not has_key:
        logger.info("Using MockProductionAgent (LLM_MODE=mock or no API key)")
        return MockProductionAgent(db)
    else:
        logger.info("Using LangGraphProductionAgent (Claude)")
        return LangGraphProductionAgent(db)
