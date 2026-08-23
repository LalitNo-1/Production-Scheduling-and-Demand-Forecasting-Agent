"""
Schedule endpoints — CRUD for job orders, propose, commit, rollback, audit log.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.models.db import get_db, JobOrder, ProposedChange, AuditLog, SKUMetadata
from app.models.schemas import (
    ScheduleResponse, JobOrderOut, JobOrderCreateRequest, JobOrderUpdateRequest,
    ProposeChangeRequest, ProposedChangeResponse, SimulationResult,
    CommitRequest, CommitResponse,
    RejectRequest,
    RollbackResponse,
    AuditLogResponse, AuditLogEntry,
)
from app.services.agent import AgentTools

router = APIRouter()


@router.get("/current-schedule", response_model=ScheduleResponse)
def get_current_schedule(
    sku: Optional[str] = Query(None),
    machine_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(JobOrder)
    filters = {}
    if sku:
        q = q.filter(JobOrder.sku == sku)
        filters["sku"] = sku
    if machine_id:
        q = q.filter(JobOrder.machine_id == machine_id)
        filters["machine_id"] = machine_id
    if status:
        q = q.filter(JobOrder.status == status)
        filters["status"] = status
    else:
        q = q.filter(JobOrder.status.in_(["scheduled", "in_progress"]))
    jobs = q.order_by(JobOrder.start_time).all()
    return ScheduleResponse(
        jobs=[JobOrderOut.model_validate(j) for j in jobs],
        total_jobs=len(jobs),
        filters_applied=filters,
    )


@router.post("/job-orders", response_model=JobOrderOut)
def create_job_order(req: JobOrderCreateRequest, db: Session = Depends(get_db)):
    """Directly schedule a new production job order."""
    # Generate job_id if not provided
    job_id = req.job_id
    if not job_id:
        count = db.query(JobOrder).count() + 1
        job_id = f"JOB-{count:03d}"

    # Calculate end_time if missing
    start_time = req.start_time
    end_time = req.end_time
    if not end_time:
        # Check SKU run rate
        sku_meta = db.query(SKUMetadata).filter(SKUMetadata.sku == req.sku).first()
        rate = sku_meta.units_per_hour if sku_meta and sku_meta.units_per_hour else 50.0
        duration_hrs = req.duration_hours or (req.quantity / rate)
        end_time = start_time + timedelta(hours=duration_hrs)

    job = JobOrder(
        job_id=job_id,
        job_name=req.job_name or f"{req.sku} Production Run",
        sku=req.sku,
        quantity=req.quantity,
        machine_id=req.machine_id,
        start_time=start_time,
        end_time=end_time,
        committed_delivery_date=req.committed_delivery_date,
        has_committed_delivery=req.has_committed_delivery or (req.committed_delivery_date is not None),
        status="scheduled",
        priority=req.priority,
        margin_per_unit=req.margin_per_unit,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return JobOrderOut.model_validate(job)


@router.put("/job-orders/{job_id}", response_model=JobOrderOut)
def update_job_order(job_id: str, req: JobOrderUpdateRequest, db: Session = Depends(get_db)):
    """Rename or update timing/machine/quantity of a job order."""
    job = db.query(JobOrder).filter(JobOrder.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if req.job_name is not None:
        job.job_name = req.job_name
    if req.sku is not None:
        job.sku = req.sku
    if req.quantity is not None:
        job.quantity = req.quantity
    if req.machine_id is not None:
        job.machine_id = req.machine_id
    if req.start_time is not None:
        job.start_time = req.start_time
    if req.end_time is not None:
        job.end_time = req.end_time
    if req.committed_delivery_date is not None:
        job.committed_delivery_date = req.committed_delivery_date
    if req.has_committed_delivery is not None:
        job.has_committed_delivery = req.has_committed_delivery
    if req.status is not None:
        job.status = req.status
    if req.priority is not None:
        job.priority = req.priority

    db.commit()
    db.refresh(job)
    return JobOrderOut.model_validate(job)


@router.delete("/job-orders/{job_id}")
def delete_job_order(job_id: str, db: Session = Depends(get_db)):
    """Cancel / delete a job order."""
    job = db.query(JobOrder).filter(JobOrder.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    db.delete(job)
    db.commit()
    return {"status": "deleted", "job_id": job_id}


@router.post("/propose-schedule-change", response_model=ProposedChangeResponse)
def propose_schedule_change(
    req: ProposeChangeRequest,
    db: Session = Depends(get_db),
):
    """
    Calls the OR-Tools optimizer and returns a proposed diff — does NOT commit.
    Returns 400 if forecast confidence is LOW and force=False.
    """
    from app.services.forecasting import get_forecasting_service
    svc = get_forecasting_service(db)
    _, mape, confidence = svc.forecast(req.sku, req.horizon_days)

    if confidence == "low" and not req.force:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Forecast confidence is LOW (MAPE={mape:.1f}%) for {req.sku}. "
                "A proposed schedule change requires human review. "
                "Set force=true to override (not recommended)."
            ),
        )

    tools = AgentTools(db)
    result = tools.propose_schedule_change(req.sku, req.horizon_days, req.machine_id)
    change_id = result["change_id"]

    proposed = db.query(ProposedChange).filter(ProposedChange.change_id == change_id).first()

    sim_result = None
    if proposed and proposed.simulation_result:
        sim_result = SimulationResult(**proposed.simulation_result)

    return ProposedChangeResponse(
        change_id=change_id,
        status=proposed.status if proposed else "pending",
        sku=req.sku,
        rationale=proposed.rationale if proposed else "",
        forecast_confidence=confidence,
        has_delivery_date_warning=result.get("has_delivery_date_warning", False),
        affected_jobs=proposed.affected_jobs if proposed else [],
        before_state=proposed.before_state if proposed else [],
        after_state=proposed.after_state if proposed else [],
        simulation_result=sim_result,
        created_at=proposed.created_at if proposed else datetime.utcnow(),
        expires_at=proposed.expires_at if proposed else None,
    )


@router.get("/proposed-changes")
def list_proposed_changes(
    status: Optional[str] = Query("pending"),
    db: Session = Depends(get_db),
):
    q = db.query(ProposedChange)
    if status:
        q = q.filter(ProposedChange.status == status)
    changes = q.order_by(ProposedChange.created_at.desc()).all()
    return [
        {
            "change_id": c.change_id,
            "sku": c.sku,
            "status": c.status,
            "rationale": c.rationale,
            "forecast_confidence": c.forecast_confidence,
            "has_delivery_date_warning": c.has_delivery_date_warning,
            "affected_jobs": c.affected_jobs,
            "simulation_result": c.simulation_result,
            "created_at": c.created_at.isoformat(),
            "before_state": c.before_state,
            "after_state": c.after_state,
        }
        for c in changes
    ]


@router.post("/commit-schedule", response_model=CommitResponse)
def commit_schedule(req: CommitRequest, db: Session = Depends(get_db)):
    """
    Commit a proposed schedule change. Requires approved_by (hardcoded guardrail).
    Writes full audit record before applying changes.
    """
    if not req.approved_by or not req.approved_by.strip():
        raise HTTPException(
            status_code=400,
            detail="approved_by is required — this endpoint cannot be called without a human approver.",
        )
    tools = AgentTools(db)
    try:
        result = tools.commit_schedule(req.change_id, req.approved_by, req.notes or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return CommitResponse(**result)


@router.post("/reject-schedule-change")
def reject_schedule_change(req: RejectRequest, db: Session = Depends(get_db)):
    proposed = db.query(ProposedChange).filter(ProposedChange.change_id == req.change_id).first()
    if not proposed:
        raise HTTPException(status_code=404, detail=f"Change {req.change_id} not found")
    if proposed.status != "pending":
        raise HTTPException(status_code=400, detail=f"Change is not pending (status: {proposed.status})")

    proposed.status = "rejected"
    proposed.rejected_by = req.rejected_by
    proposed.rejected_at = datetime.utcnow()
    proposed.rejection_reason = req.reason

    # Write audit record
    audit = AuditLog(
        change_id=req.change_id,
        timestamp=datetime.utcnow(),
        actor=req.rejected_by,
        action="reject",
        before_state=proposed.before_state,
        after_state=None,
        sku=proposed.sku,
        forecast_confidence=proposed.forecast_confidence,
        has_delivery_date_warning=proposed.has_delivery_date_warning,
        approval_status="rejected",
        notes=req.reason,
    )
    db.add(audit)
    db.commit()

    return {"change_id": req.change_id, "rejected": True, "message": "Change rejected and logged."}


@router.post("/rollback/{change_id}", response_model=RollbackResponse)
def rollback_schedule_change(
    change_id: str,
    rolled_back_by: str = Query(..., description="Name of person performing rollback"),
    db: Session = Depends(get_db),
):
    """Revert a committed change to its pre-change state using the audit log."""
    tools = AgentTools(db)
    try:
        result = tools.rollback_schedule_change(change_id, rolled_back_by)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return RollbackResponse(**result)


@router.get("/audit-log", response_model=AuditLogResponse)
def get_audit_log(
    sku: Optional[str] = Query(None),
    machine_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if sku:
        q = q.filter(AuditLog.sku == sku)
    if action:
        q = q.filter(AuditLog.action == action)
    if start_date:
        q = q.filter(AuditLog.timestamp >= datetime.fromisoformat(start_date))
    if end_date:
        q = q.filter(AuditLog.timestamp <= datetime.fromisoformat(end_date))
    entries = q.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    total = db.query(AuditLog).count()
    return AuditLogResponse(
        entries=[AuditLogEntry.model_validate(e) for e in entries],
        total=total,
    )
