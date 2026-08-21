"""
Data / ERP endpoints — exposes mock ERP data from SQLite.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.db import get_db, SalesHistory, MachineCapacity, MaintenanceWindow
from app.models.schemas import SalesHistoryResponse, SalesPoint, MachineCapacityResponse, ShiftCapacity, MaintenanceWindowOut

router = APIRouter()


@router.get("/sales-history", response_model=SalesHistoryResponse)
def get_sales_history(
    sku: str = Query(..., description="SKU identifier, e.g. SKU-A"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(SalesHistory).filter(SalesHistory.sku == sku)
    if start_date:
        q = q.filter(SalesHistory.date >= datetime.fromisoformat(start_date))
    if end_date:
        q = q.filter(SalesHistory.date <= datetime.fromisoformat(end_date))
    rows = q.order_by(SalesHistory.date).all()
    return SalesHistoryResponse(
        sku=sku,
        data=[SalesPoint(date=r.date, quantity=r.quantity, is_promotional=r.is_promotional) for r in rows],
    )


@router.get("/machine-capacity", response_model=MachineCapacityResponse)
def get_machine_capacity(
    machine_id: str = Query(..., description="Machine ID, e.g. MCH-01"),
    db: Session = Depends(get_db),
):
    rows = db.query(MachineCapacity).filter(MachineCapacity.machine_id == machine_id).all()
    if not rows:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    windows = db.query(MaintenanceWindow).filter(
        MaintenanceWindow.machine_id == machine_id
    ).all()
    return MachineCapacityResponse(
        machine_id=machine_id,
        machine_name=rows[0].machine_name,
        shifts=[
            ShiftCapacity(
                shift=r.shift,
                capacity_hours=r.capacity_hours,
                utilization_pct=r.utilization_pct,
                available_hours=r.capacity_hours * (1 - r.utilization_pct / 100),
            )
            for r in rows
        ],
        compatible_skus=rows[0].compatible_skus,
    )


@router.get("/maintenance-windows")
def get_maintenance_windows(
    machine_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(MaintenanceWindow)
    if machine_id:
        q = q.filter(MaintenanceWindow.machine_id == machine_id)
    windows = q.all()
    return [MaintenanceWindowOut.model_validate(w) for w in windows]


@router.get("/machines")
def list_machines(db: Session = Depends(get_db)):
    """List all machine IDs."""
    rows = db.query(MachineCapacity.machine_id, MachineCapacity.machine_name).distinct().all()
    return [{"machine_id": r.machine_id, "machine_name": r.machine_name} for r in rows]


@router.get("/skus")
def list_skus(db: Session = Depends(get_db)):
    """List all known SKUs."""
    rows = db.query(SalesHistory.sku).distinct().all()
    return [r.sku for r in rows]
