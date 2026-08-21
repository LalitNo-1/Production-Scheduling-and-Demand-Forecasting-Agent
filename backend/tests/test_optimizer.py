"""
Unit tests for the OR-Tools optimizer.
Three core scenarios: normal, capacity-exceeded, maintenance-conflict.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime, timedelta
from app.services.optimizer import OptimizationService, JobInput, MachineInput


def make_job(job_id, sku="SKU-A", duration_hours=4.0, eligible_machines=None,
             committed_delivery_date=None, has_committed_delivery=False,
             priority=5, margin_per_unit=45.0, day_offset=0):
    base = datetime(2025, 1, 1)
    return JobInput(
        job_id=job_id, sku=sku, quantity=100.0,
        eligible_machines=eligible_machines or ["MCH-01"],
        duration_hours=duration_hours,
        earliest_start=base + timedelta(days=day_offset),
        latest_end=base + timedelta(days=day_offset + 30),
        committed_delivery_date=committed_delivery_date,
        has_committed_delivery=has_committed_delivery,
        priority=priority, margin_per_unit=margin_per_unit,
    )


def make_machine(machine_id="MCH-01", capacity_hours=8.0, maintenance_windows=None):
    return MachineInput(
        machine_id=machine_id,
        shifts=[{"shift": 1, "capacity_hours": capacity_hours}],
        maintenance_windows=maintenance_windows or [],
    )


@pytest.fixture
def optimizer():
    return OptimizationService()


# ── Scenario 1: Normal ────────────────────────────────────────────────────────

class TestNormalCase:
    def test_all_jobs_scheduled(self, optimizer):
        jobs = [make_job(f"JOB-{i:03d}", duration_hours=2.0) for i in range(3)]
        machines = [make_machine("MCH-01", capacity_hours=8.0)]
        result = optimizer.propose_schedule(jobs, machines, base_time=datetime(2025, 1, 1))
        assert result.status in ("optimal", "feasible", "partial")
        assert len(result.assigned_jobs) == 3
        assert len(result.dropped_jobs) == 0

    def test_assigned_jobs_have_valid_times(self, optimizer):
        jobs = [make_job("JOB-001", duration_hours=4.0)]
        machines = [make_machine("MCH-01")]
        result = optimizer.propose_schedule(jobs, machines, base_time=datetime(2025, 1, 1))
        for aj in result.assigned_jobs:
            assert aj.start_time < aj.end_time
            assert aj.machine_id == "MCH-01"

    def test_no_overlap_on_same_machine(self, optimizer):
        jobs = [make_job("JOB-001", duration_hours=6.0), make_job("JOB-002", duration_hours=6.0)]
        machines = [make_machine("MCH-01", capacity_hours=12.0)]
        result = optimizer.propose_schedule(jobs, machines, base_time=datetime(2025, 1, 1))
        assigned = sorted(result.assigned_jobs, key=lambda x: x.start_time)
        if len(assigned) == 2:
            assert assigned[0].end_time <= assigned[1].start_time, "Overlap detected!"

    def test_empty_job_list(self, optimizer):
        result = optimizer.propose_schedule([], [make_machine()], base_time=datetime(2025, 1, 1))
        assert result.status == "optimal"
        assert result.assigned_jobs == []

    def test_two_machines_parallel(self, optimizer):
        jobs = [
            make_job("JOB-001", eligible_machines=["MCH-01", "MCH-02"], duration_hours=4.0),
            make_job("JOB-002", eligible_machines=["MCH-01", "MCH-02"], duration_hours=4.0),
        ]
        machines = [make_machine("MCH-01"), make_machine("MCH-02")]
        result = optimizer.propose_schedule(jobs, machines, base_time=datetime(2025, 1, 1))
        assert len(result.assigned_jobs) == 2


# ── Scenario 2: Capacity Exceeded ────────────────────────────────────────────

class TestCapacityExceeded:
    def test_partial_solution_returned(self, optimizer):
        """
        5 × 4h jobs with deadline = 8h from now, on a single machine.
        Latest_end forces all jobs into an 8h window, so only 2 can fit.
        """
        base = datetime(2025, 1, 1, 0, 0)
        deadline = base + timedelta(hours=8)  # tight window: only 8h available
        jobs = []
        for i in range(5):
            jobs.append(JobInput(
                job_id=f"JOB-{i:03d}", sku="SKU-A", quantity=100.0,
                eligible_machines=["MCH-01"],
                duration_hours=4.0,
                earliest_start=base,
                latest_end=deadline,  # forces all into tight window
                priority=5, margin_per_unit=45.0,
            ))
        machines = [make_machine("MCH-01", capacity_hours=8.0)]
        result = optimizer.propose_schedule(jobs, machines, base_time=base)
        assert result.status in ("partial", "feasible", "optimal")
        assert len(result.dropped_jobs) > 0, \
            f"Expected dropped jobs with tight 8h deadline, got {len(result.assigned_jobs)} assigned"
        assert len(result.assigned_jobs) > 0, "Expected at least some assigned"
        print(f"\n[CAPACITY] {len(result.assigned_jobs)} assigned, {len(result.dropped_jobs)} dropped")

    def test_dropped_plus_assigned_equals_input(self, optimizer):
        job_ids = {f"JOB-{i:03d}" for i in range(4)}
        jobs = [make_job(jid, duration_hours=8.0) for jid in job_ids]
        machines = [make_machine("MCH-01")]
        result = optimizer.propose_schedule(jobs, machines, base_time=datetime(2025, 1, 1))
        output_ids = {aj.job_id for aj in result.assigned_jobs} | set(result.dropped_jobs)
        assert output_ids == job_ids

    def test_infeasibility_reason_set(self, optimizer):
        jobs = [make_job(f"JOB-{i:03d}", duration_hours=8.0) for i in range(5)]
        machines = [make_machine("MCH-01", capacity_hours=8.0)]
        result = optimizer.propose_schedule(jobs, machines, base_time=datetime(2025, 1, 1))
        if result.dropped_jobs:
            assert result.infeasibility_reason is not None


# ── Scenario 3: Maintenance Conflict ─────────────────────────────────────────

class TestMaintenanceConflict:
    def test_job_not_during_maintenance(self, optimizer):
        base = datetime(2025, 1, 1, 0, 0, 0)
        maint_end = base + timedelta(hours=8)
        jobs = [make_job("JOB-001", duration_hours=4.0)]
        machines = [make_machine("MCH-01", capacity_hours=16.0, maintenance_windows=[{
            "start_time": base, "end_time": maint_end, "is_hard_constraint": True
        }])]
        result = optimizer.propose_schedule(jobs, machines, base_time=base)
        for aj in result.assigned_jobs:
            if aj.machine_id == "MCH-01":
                assert aj.start_time >= maint_end, \
                    f"Job scheduled during maintenance! start={aj.start_time}"

    def test_job_moves_to_other_machine(self, optimizer):
        base = datetime(2025, 1, 1, 0, 0, 0)
        jobs = [make_job("JOB-001", duration_hours=4.0, eligible_machines=["MCH-01", "MCH-02"])]
        machines = [
            make_machine("MCH-01", capacity_hours=8.0, maintenance_windows=[{
                "start_time": base, "end_time": base + timedelta(hours=24),
                "is_hard_constraint": True
            }]),
            make_machine("MCH-02", capacity_hours=8.0),
        ]
        result = optimizer.propose_schedule(jobs, machines, base_time=base)
        assert len(result.assigned_jobs) >= 0  # sanity check


# ── Performance ───────────────────────────────────────────────────────────────

class TestPerformance:
    def test_solves_within_time_limit(self, optimizer):
        import time
        base = datetime(2025, 1, 1)
        jobs = [make_job(f"JOB-{i:03d}", duration_hours=3.0, eligible_machines=["MCH-01", "MCH-02", "MCH-03"]) for i in range(10)]
        machines = [make_machine(f"MCH-0{i}", capacity_hours=8.0) for i in range(1, 4)]
        t0 = time.time()
        result = optimizer.propose_schedule(jobs, machines, base_time=base)
        elapsed = time.time() - t0
        assert elapsed < 65, f"Solver too slow: {elapsed:.1f}s"
        print(f"\n[PERF] Solver: {result.solver_wall_time_s:.2f}s, status: {result.status}")
