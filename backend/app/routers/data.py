"""
Data / ERP endpoints — exposes mock ERP data from SQLite.
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.db import get_db, SalesHistory, MachineCapacity, MaintenanceWindow, SKUMetadata
from app.models.schemas import (
    SalesHistoryResponse, SalesPoint, MachineCapacityResponse, ShiftCapacity, MaintenanceWindowOut,
    MachineCreateRequest, MachineUpdateRequest, SKUMetadataOut, SKUMetadataUpdateRequest
)
from fastapi import HTTPException

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
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    windows = db.query(MaintenanceWindow).filter(
        MaintenanceWindow.machine_id == machine_id
    ).all()
    return MachineCapacityResponse(
        machine_id=machine_id,
        machine_name=rows[0].machine_name or machine_id,
        shifts=[
            ShiftCapacity(
                shift=r.shift,
                capacity_hours=r.capacity_hours,
                utilization_pct=r.utilization_pct,
                available_hours=r.capacity_hours * (1 - r.utilization_pct / 100),
            )
            for r in rows
        ],
        compatible_skus=rows[0].compatible_skus or ["SKU-A", "SKU-B", "SKU-C"],
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
    """List all machines with names and shift details."""
    rows = db.query(MachineCapacity).all()
    # Group by machine_id
    res = {}
    for r in rows:
        if r.machine_id not in res:
            res[r.machine_id] = {
                "machine_id": r.machine_id,
                "machine_name": r.machine_name or r.machine_id,
                "capacity_hours": r.capacity_hours,
                "utilization_pct": r.utilization_pct,
                "compatible_skus": r.compatible_skus or [],
                "shifts_count": 0,
            }
        res[r.machine_id]["shifts_count"] += 1
    return list(res.values())


@router.post("/machines")
def create_machine(req: MachineCreateRequest, db: Session = Depends(get_db)):
    """Add a new machine with shift capacities."""
    existing = db.query(MachineCapacity).filter(MachineCapacity.machine_id == req.machine_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Machine {req.machine_id} already exists")

    # Create shifts 1, 2, 3
    for s in [1, 2, 3]:
        mc = MachineCapacity(
            machine_id=req.machine_id,
            machine_name=req.machine_name,
            shift=s,
            capacity_hours=req.capacity_hours,
            utilization_pct=0.0,
            compatible_skus=req.compatible_skus or ["SKU-A", "SKU-B", "SKU-C"],
        )
        db.add(mc)
    db.commit()
    return {"status": "created", "machine_id": req.machine_id, "machine_name": req.machine_name}


@router.put("/machines/{machine_id}")
def update_machine(machine_id: str, req: MachineUpdateRequest, db: Session = Depends(get_db)):
    """Rename or update capacity of an existing machine."""
    rows = db.query(MachineCapacity).filter(MachineCapacity.machine_id == machine_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")

    for r in rows:
        if req.machine_name is not None:
            r.machine_name = req.machine_name
        if req.capacity_hours is not None:
            r.capacity_hours = req.capacity_hours
        if req.compatible_skus is not None:
            r.compatible_skus = req.compatible_skus
    db.commit()
    return {"status": "updated", "machine_id": machine_id, "machine_name": rows[0].machine_name}


@router.delete("/machines/{machine_id}")
def delete_machine(machine_id: str, db: Session = Depends(get_db)):
    """Delete a machine from capacity registry."""
    rows = db.query(MachineCapacity).filter(MachineCapacity.machine_id == machine_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    for r in rows:
        db.delete(r)
    db.commit()
    return {"status": "deleted", "machine_id": machine_id}


@router.get("/skus")
def list_skus(db: Session = Depends(get_db)):
    """List all known SKUs with custom metadata/display names."""
    # Find all distinct SKUs in sales history
    sales_skus = [r[0] for r in db.query(SalesHistory.sku).distinct().all()]
    if not sales_skus:
        sales_skus = ["SKU-A", "SKU-B", "SKU-C"]

    # Ensure default metadata rows exist
    for sku in sales_skus:
        meta = db.query(SKUMetadata).filter(SKUMetadata.sku == sku).first()
        if not meta:
            default_names = {
                "SKU-A": ("Widget Alpha", "Primary precision housing assembly", 60.0),
                "SKU-B": ("Widget Beta", "Secondary sensor bracket component", 45.0),
                "SKU-C": ("Widget Gamma", "High-durability fastener module", 75.0),
            }
            name, desc, rate = default_names.get(sku, (sku, "Custom product line", 50.0))
            meta = SKUMetadata(sku=sku, display_name=name, description=desc, units_per_hour=rate)
            db.add(meta)
    db.commit()

    all_meta = db.query(SKUMetadata).all()
    return [
        {
            "sku": m.sku,
            "display_name": m.display_name or m.sku,
            "description": m.description or "",
            "units_per_hour": m.units_per_hour or 50.0,
        }
        for m in all_meta
    ]


@router.put("/skus/{sku}")
def update_sku(sku: str, req: SKUMetadataUpdateRequest, db: Session = Depends(get_db)):
    """Rename or update product SKU metadata."""
    meta = db.query(SKUMetadata).filter(SKUMetadata.sku == sku).first()
    if not meta:
        meta = SKUMetadata(sku=sku)
        db.add(meta)

    if req.display_name is not None:
        meta.display_name = req.display_name
    if req.description is not None:
        meta.description = req.description
    if req.units_per_hour is not None:
        meta.units_per_hour = req.units_per_hour
    db.commit()
    return {
        "status": "updated",
        "sku": meta.sku,
        "display_name": meta.display_name,
        "description": meta.description,
        "units_per_hour": meta.units_per_hour,
    }
