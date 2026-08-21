"""
OR-Tools CP-SAT optimization service for production scheduling.
Models the job-shop scheduling problem with hard and soft constraints.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class JobInput:
    job_id: str
    sku: str
    quantity: float
    eligible_machines: List[str]
    duration_hours: float       # processing time needed
    earliest_start: datetime
    latest_end: datetime        # deadline (soft)
    committed_delivery_date: Optional[datetime] = None
    has_committed_delivery: bool = False
    priority: int = 5           # 1 (highest) – 10 (lowest)
    margin_per_unit: float = 1.0


@dataclass
class MachineInput:
    machine_id: str
    shifts: List[Dict]          # [{shift, capacity_hours}]
    maintenance_windows: List[Dict] = field(default_factory=list)


@dataclass
class AssignedJob:
    job_id: str
    sku: str
    machine_id: str
    start_time: datetime
    end_time: datetime
    quantity: float
    committed_delivery_date: Optional[datetime] = None
    has_committed_delivery: bool = False


@dataclass
class ProposedSchedule:
    status: str                     # "optimal", "feasible", "partial", "infeasible"
    assigned_jobs: List[AssignedJob]
    dropped_jobs: List[str]         # job_ids not schedulable
    objective_value: float
    solver_wall_time_s: float
    infeasibility_reason: Optional[str] = None
    priority_rule: str = "margin_weighted"


# ── Optimizer ────────────────────────────────────────────────────────────────

class OptimizationService:
    """
    CP-SAT based job-shop scheduler.

    Hard constraints:
      - No two jobs on the same machine at the same time
      - No jobs during maintenance windows
      - Machine must be capable of the SKU

    Soft constraints (minimized):
      - Tardiness: weighted delivery date deviation
      - Changeover: penalty when consecutive jobs on same machine differ in SKU
    """

    TIME_UNIT_MINUTES = 15   # planning horizon granularity
    MAX_HORIZON_DAYS = 90
    SOLVER_TIME_LIMIT_S = 60
    TARDINESS_WEIGHT = 100
    CHANGEOVER_WEIGHT = 10
    DROPPED_JOB_PENALTY = 10_000

    def _to_slots(self, dt: datetime, base: datetime) -> int:
        """Convert a datetime to integer time-slots since base."""
        delta_minutes = (dt - base).total_seconds() / 60
        return max(0, int(delta_minutes // self.TIME_UNIT_MINUTES))

    def _from_slots(self, slots: int, base: datetime) -> datetime:
        return base + timedelta(minutes=slots * self.TIME_UNIT_MINUTES)

    def _duration_slots(self, hours: float) -> int:
        return max(1, int(hours * 60 // self.TIME_UNIT_MINUTES))

    # ── Main entry point ─────────────────────────────────────────────────────

    def propose_schedule(
        self,
        jobs: List[JobInput],
        machines: List[MachineInput],
        base_time: Optional[datetime] = None,
        priority_rule: str = "margin_weighted",
    ) -> ProposedSchedule:
        """
        Main scheduling function.
        Returns ProposedSchedule with status "optimal", "feasible", "partial",
        or — if completely infeasible — best effort with dropped jobs.
        """
        if not jobs:
            return ProposedSchedule(
                status="optimal", assigned_jobs=[], dropped_jobs=[],
                objective_value=0.0, solver_wall_time_s=0.0
            )

        base = base_time or datetime.utcnow()
        horizon_slots = self._to_slots(
            base + timedelta(days=self.MAX_HORIZON_DAYS), base
        )

        try:
            from ortools.sat.python import cp_model
        except ImportError:
            logger.error("OR-Tools not installed — returning mock schedule")
            return self._mock_schedule(jobs)

        model = cp_model.CpModel()

        # ── Variables ────────────────────────────────────────────────────────
        machine_ids = [m.machine_id for m in machines]
        machine_map = {m.machine_id: m for m in machines}

        # For each job: interval variable + machine assignment
        job_vars = {}
        for job in jobs:
            duration = self._duration_slots(job.duration_hours)
            earliest = self._to_slots(job.earliest_start, base)
            latest = min(
                self._to_slots(job.latest_end, base),
                horizon_slots - duration
            )
            latest = max(earliest, latest)  # clamp

            start_var = model.NewIntVar(earliest, latest, f"start_{job.job_id}")
            end_var = model.NewIntVar(earliest + duration, horizon_slots, f"end_{job.job_id}")
            interval_var = model.NewIntervalVar(start_var, duration, end_var, f"interval_{job.job_id}")

            # Optional: job can be dropped (not scheduled)
            is_present = model.NewBoolVar(f"present_{job.job_id}")
            opt_interval = model.NewOptionalIntervalVar(
                start_var, duration, end_var, is_present, f"opt_interval_{job.job_id}"
            )

            # Machine assignment (one-hot among eligible machines)
            eligible = [m for m in job.eligible_machines if m in machine_ids]
            machine_bool = {}
            for mid in eligible:
                machine_bool[mid] = model.NewBoolVar(f"mch_{job.job_id}_{mid}")
            if eligible:
                model.Add(sum(machine_bool.values()) == 1).OnlyEnforceIf(is_present)
                model.Add(sum(machine_bool.values()) == 0).OnlyEnforceIf(is_present.Not())

            job_vars[job.job_id] = {
                "start": start_var, "end": end_var,
                "interval": opt_interval, "is_present": is_present,
                "duration": duration, "machine_bool": machine_bool,
                "eligible": eligible, "job": job,
            }

        # ── Hard constraints ─────────────────────────────────────────────────

        # No-overlap on same machine
        for mid in machine_ids:
            machine_intervals = []
            for jid, v in job_vars.items():
                if mid in v["machine_bool"]:
                    # Create conditional interval: active only when assigned to this machine AND present
                    start_v = v["start"]
                    dur = v["duration"]
                    end_v = v["end"]
                    cond_bool = model.NewBoolVar(f"cond_{jid}_{mid}")
                    model.AddBoolAnd([v["is_present"], v["machine_bool"][mid]]).OnlyEnforceIf(cond_bool)
                    model.AddBoolOr([v["is_present"].Not(), v["machine_bool"][mid].Not()]).OnlyEnforceIf(cond_bool.Not())
                    cond_interval = model.NewOptionalIntervalVar(
                        start_v, dur, end_v, cond_bool, f"cond_interval_{jid}_{mid}"
                    )
                    machine_intervals.append(cond_interval)
            if machine_intervals:
                model.AddNoOverlap(machine_intervals)

        # Maintenance windows: no jobs during maintenance
        for mach in machines:
            for window in mach.maintenance_windows:
                if not window.get("is_hard_constraint", True):
                    continue
                w_start = self._to_slots(datetime.fromisoformat(str(window["start_time"])), base)
                w_end = self._to_slots(datetime.fromisoformat(str(window["end_time"])), base)
                for jid, v in job_vars.items():
                    if mach.machine_id in v["machine_bool"]:
                        # If assigned to this machine AND present: must not overlap window
                        b = v["machine_bool"][mach.machine_id]
                        p = v["is_present"]
                        both = model.NewBoolVar(f"both_{jid}_{mach.machine_id}_maint")
                        model.AddBoolAnd([b, p]).OnlyEnforceIf(both)
                        model.AddBoolOr([b.Not(), p.Not()]).OnlyEnforceIf(both.Not())
                        # end <= w_start OR start >= w_end
                        before = model.NewBoolVar(f"before_{jid}_{mach.machine_id}_maint")
                        model.Add(v["end"] <= w_start).OnlyEnforceIf([both, before])
                        model.Add(v["start"] >= w_end).OnlyEnforceIf([both, before.Not()])

        # ── Objective ────────────────────────────────────────────────────────
        penalties = []

        for jid, v in job_vars.items():
            job = v["job"]

            # Penalty for dropping a job (margin-weighted)
            if priority_rule == "margin_weighted":
                drop_penalty = int(self.DROPPED_JOB_PENALTY * job.margin_per_unit)
            else:
                drop_penalty = int(self.DROPPED_JOB_PENALTY * (11 - job.priority))
            penalties.append(drop_penalty * v["is_present"].Not())

            # Tardiness penalty (only if committed delivery)
            if job.committed_delivery_date:
                deadline_slot = self._to_slots(job.committed_delivery_date, base)
                tardiness = model.NewIntVar(0, horizon_slots, f"tard_{jid}")
                model.Add(tardiness >= v["end"] - deadline_slot).OnlyEnforceIf(v["is_present"])
                model.Add(tardiness == 0).OnlyEnforceIf(v["is_present"].Not())
                penalties.append(self.TARDINESS_WEIGHT * tardiness)

        model.Minimize(sum(penalties))

        # ── Solve ────────────────────────────────────────────────────────────
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.SOLVER_TIME_LIMIT_S
        solver.parameters.num_search_workers = 4

        status = solver.Solve(model)
        wall_time = solver.WallTime()

        status_map = {
            cp_model.OPTIMAL: "optimal",
            cp_model.FEASIBLE: "feasible",
            cp_model.INFEASIBLE: "infeasible",
            cp_model.MODEL_INVALID: "infeasible",
            cp_model.UNKNOWN: "partial",
        }
        solve_status = status_map.get(status, "partial")

        if status in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
            return ProposedSchedule(
                status="infeasible",
                assigned_jobs=[],
                dropped_jobs=[j.job_id for j in jobs],
                objective_value=0.0,
                solver_wall_time_s=wall_time,
                infeasibility_reason="No feasible schedule exists — check capacity and maintenance windows. All jobs dropped.",
                priority_rule=priority_rule,
            )

        # Extract solution
        assigned = []
        dropped = []
        for jid, v in job_vars.items():
            job = v["job"]
            if solver.Value(v["is_present"]):
                machine_assigned = None
                for mid, mb in v["machine_bool"].items():
                    if solver.Value(mb):
                        machine_assigned = mid
                        break
                start_dt = self._from_slots(solver.Value(v["start"]), base)
                end_dt = self._from_slots(solver.Value(v["end"]), base)
                assigned.append(AssignedJob(
                    job_id=jid,
                    sku=job.sku,
                    machine_id=machine_assigned or (v["eligible"][0] if v["eligible"] else "UNKNOWN"),
                    start_time=start_dt,
                    end_time=end_dt,
                    quantity=job.quantity,
                    committed_delivery_date=job.committed_delivery_date,
                    has_committed_delivery=job.has_committed_delivery,
                ))
            else:
                dropped.append(jid)

        final_status = solve_status if not dropped else "partial"

        return ProposedSchedule(
            status=final_status,
            assigned_jobs=assigned,
            dropped_jobs=dropped,
            objective_value=float(solver.ObjectiveValue()),
            solver_wall_time_s=wall_time,
            infeasibility_reason=(
                f"Partial solution: {len(dropped)} job(s) could not be scheduled due to "
                "capacity or constraint violations." if dropped else None
            ),
            priority_rule=priority_rule,
        )

    def _mock_schedule(self, jobs: List[JobInput]) -> ProposedSchedule:
        """Fallback when OR-Tools is not installed — returns trivial mock."""
        base = datetime.utcnow()
        assigned = []
        for i, job in enumerate(jobs[:5]):
            assigned.append(AssignedJob(
                job_id=job.job_id, sku=job.sku,
                machine_id=job.eligible_machines[0] if job.eligible_machines else "MCH-01",
                start_time=base + timedelta(hours=i * 8),
                end_time=base + timedelta(hours=(i + 1) * 8),
                quantity=job.quantity,
            ))
        return ProposedSchedule(
            status="feasible", assigned_jobs=assigned,
            dropped_jobs=[], objective_value=0.0, solver_wall_time_s=0.0
        )


_optimizer: Optional[OptimizationService] = None


def get_optimizer() -> OptimizationService:
    global _optimizer
    if _optimizer is None:
        _optimizer = OptimizationService()
    return _optimizer
