"""
Unit and integration tests for new CRUD & Renaming features:
- Machine addition, renaming, and deletion
- SKU metadata renaming and run rate updating
- Job Order manual creation, updating, and cancellation
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.models.db import SessionLocal, JobOrder, MachineCapacity, SKUMetadata

client = TestClient(app)


def test_create_and_rename_machine():
    # 1. Create Machine
    res = client.post("/api/machines", json={
        "machine_id": "MCH-TEST-01",
        "machine_name": "Test Laser Mill",
        "capacity_hours": 10.0,
        "compatible_skus": ["SKU-A", "SKU-B"]
    })
    assert res.status_code == 200
    assert res.json()["machine_id"] == "MCH-TEST-01"

    # 2. Verify machine capacity retrieval
    cap_res = client.get("/api/machine-capacity?machine_id=MCH-TEST-01")
    assert cap_res.status_code == 200
    assert cap_res.json()["machine_name"] == "Test Laser Mill"

    # 3. Rename Machine
    put_res = client.put("/api/machines/MCH-TEST-01", json={
        "machine_name": "Renamed Laser Cell",
        "capacity_hours": 12.0
    })
    assert put_res.status_code == 200
    assert put_res.json()["machine_name"] == "Renamed Laser Cell"

    # 4. Clean up / Delete Machine
    del_res = client.delete("/api/machines/MCH-TEST-01")
    assert del_res.status_code == 200


def test_rename_and_update_sku():
    # 1. Update SKU-A
    res = client.put("/api/skus/SKU-A", json={
        "display_name": "Titanium Rotor Assembly",
        "description": "High tolerance aerospace rotor",
        "units_per_hour": 65.0
    })
    assert res.status_code == 200
    data = res.json()
    assert data["display_name"] == "Titanium Rotor Assembly"
    assert data["units_per_hour"] == 65.0

    # 2. Verify SKU in list
    skus_res = client.get("/api/skus")
    assert skus_res.status_code == 200
    sku_a = next((s for s in skus_res.json() if s["sku"] == "SKU-A"), None)
    assert sku_a is not None
    assert sku_a["display_name"] == "Titanium Rotor Assembly"


def test_create_and_edit_job_order():
    start = (datetime.now() + timedelta(days=2)).isoformat()
    committed = (datetime.now() + timedelta(days=5)).isoformat()

    # 1. Create Job Order
    res = client.post("/api/job-orders", json={
        "sku": "SKU-A",
        "job_name": "Custom Urgent Batch #999",
        "machine_id": "MCH-01",
        "quantity": 200,
        "priority": 1,
        "start_time": start,
        "duration_hours": 4.0,
        "has_committed_delivery": True,
        "committed_delivery_date": committed
    })
    assert res.status_code == 200
    created = res.json()
    job_id = created["job_id"]
    assert created["job_name"] == "Custom Urgent Batch #999"
    assert created["has_committed_delivery"] is True

    # 2. Rename and update quantity
    edit_res = client.put(f"/api/job-orders/{job_id}", json={
        "job_name": "Renamed Super Batch #999",
        "quantity": 250,
        "priority": 2
    })
    assert edit_res.status_code == 200
    assert edit_res.json()["job_name"] == "Renamed Super Batch #999"
    assert edit_res.json()["quantity"] == 250

    # 3. Verify in current schedule
    sched_res = client.get("/api/current-schedule")
    assert sched_res.status_code == 200
    found = next((j for j in sched_res.json()["jobs"] if j["job_id"] == job_id), None)
    assert found is not None
    assert found["job_name"] == "Renamed Super Batch #999"

    # 4. Delete Job Order
    del_res = client.delete(f"/api/job-orders/{job_id}")
    assert del_res.status_code == 200
