"""
Mock ERP data generator.
Produces 2.5 years of realistic sales history with:
  - Weekly seasonality (lower on weekends)
  - Annual seasonality (Q4 peak, Q1 trough)
  - One promotional spike per SKU per year (trade-show weeks)
  - Additive white noise

Run: python -m app.data.seed
"""

import json
import math
import random
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2026, 6, 30)   # ~2.5 years

SKUS = {
    "SKU-A": {"base_demand": 120, "annual_growth": 0.08, "noise_std": 15, "margin_per_unit": 45.0},
    "SKU-B": {"base_demand": 80,  "annual_growth": 0.05, "noise_std": 10, "margin_per_unit": 62.0},
    "SKU-C": {"base_demand": 200, "annual_growth": 0.03, "noise_std": 25, "margin_per_unit": 28.0},
}

MACHINES = [
    {
        "machine_id": "MCH-01",
        "machine_name": "Assembly Line Alpha",
        "compatible_skus": ["SKU-A", "SKU-B"],
        "shifts": [
            {"shift": 1, "capacity_hours": 8.0, "utilization_pct": 72},
            {"shift": 2, "capacity_hours": 8.0, "utilization_pct": 65},
        ],
    },
    {
        "machine_id": "MCH-02",
        "machine_name": "Assembly Line Beta",
        "compatible_skus": ["SKU-B", "SKU-C"],
        "shifts": [
            {"shift": 1, "capacity_hours": 8.0, "utilization_pct": 80},
            {"shift": 2, "capacity_hours": 8.0, "utilization_pct": 55},
        ],
    },
    {
        "machine_id": "MCH-03",
        "machine_name": "Finishing Cell Gamma",
        "compatible_skus": ["SKU-A", "SKU-C"],
        "shifts": [
            {"shift": 1, "capacity_hours": 6.0, "utilization_pct": 90},
            {"shift": 2, "capacity_hours": 6.0, "utilization_pct": 40},
        ],
    },
]

# Promotional spike weeks (month, week_of_month) per SKU
PROMO_WEEKS = {
    "SKU-A": [(3, 2), (3, 2 + 52)],   # March trade show, repeated next year
    "SKU-B": [(9, 3), (9, 3 + 52)],   # September industry expo
    "SKU-C": [(6, 2), (6, 2 + 52)],   # June mid-year sale
}

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _annual_seasonality(day_of_year: int) -> float:
    """Q4 peak (+30%), Q1 trough (-20%). Cosine curve."""
    angle = 2 * math.pi * (day_of_year - 1) / 365
    return 0.05 - 0.25 * math.cos(angle)


def _weekly_seasonality(weekday: int) -> float:
    """Mon–Fri full production; Sat/Sun reduced."""
    return {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 0.9, 5: 0.4, 6: 0.2}[weekday]


def _is_promo(date: datetime, sku: str) -> bool:
    week_num = (date - START_DATE).days // 7
    for month, week_offset in PROMO_WEEKS.get(sku, []):
        promo_week = (datetime(date.year, month, 1) - START_DATE).days // 7 + week_offset % 52
        if abs(week_num - promo_week) <= 1:
            return True
    return False


def generate_sales_history() -> pd.DataFrame:
    rows = []
    current = START_DATE
    while current <= END_DATE:
        years_elapsed = (current - START_DATE).days / 365
        for sku, cfg in SKUS.items():
            base = cfg["base_demand"]
            growth = (1 + cfg["annual_growth"]) ** years_elapsed
            seasonal = 1 + _annual_seasonality(current.timetuple().tm_yday)
            weekly = _weekly_seasonality(current.weekday())
            is_promo = _is_promo(current, sku)
            promo_boost = 1.8 if is_promo else 1.0
            noise = np.random.normal(0, cfg["noise_std"])
            quantity = max(0, base * growth * seasonal * weekly * promo_boost + noise)
            rows.append({
                "sku": sku,
                "date": current.strftime("%Y-%m-%d"),
                "quantity": round(quantity, 1),
                "is_promotional": is_promo,
                "region": "default",
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


def generate_current_schedule(reference_date: datetime) -> list:
    """Generate 15 job orders covering the next 60 days."""
    jobs = []
    job_counter = 1
    skus_machines = [
        ("SKU-A", "MCH-01"), ("SKU-A", "MCH-03"),
        ("SKU-B", "MCH-01"), ("SKU-B", "MCH-02"),
        ("SKU-C", "MCH-02"), ("SKU-C", "MCH-03"),
    ]
    for i in range(15):
        sku, machine = skus_machines[i % len(skus_machines)]
        day_offset = random.randint(1, 55)
        start = reference_date + timedelta(days=day_offset, hours=random.choice([6, 14]))
        duration_hours = random.uniform(4, 14)
        end = start + timedelta(hours=duration_hours)
        has_delivery = random.random() < 0.5
        delivery_date = (end + timedelta(days=random.randint(1, 5))) if has_delivery else None
        jobs.append({
            "job_id": f"JOB-{job_counter:04d}",
            "sku": sku,
            "quantity": round(random.uniform(50, 300), 0),
            "machine_id": machine,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "committed_delivery_date": delivery_date.isoformat() if delivery_date else None,
            "has_committed_delivery": has_delivery,
            "status": "scheduled",
            "priority": random.randint(1, 8),
            "margin_per_unit": SKUS[sku]["margin_per_unit"],
        })
        job_counter += 1
    return jobs


def generate_maintenance_calendar(reference_date: datetime) -> list:
    windows = [
        {"machine_id": "MCH-01", "offset_days": 10, "duration_hours": 8,  "reason": "Scheduled lubrication & belt inspection"},
        {"machine_id": "MCH-02", "offset_days": 18, "duration_hours": 16, "reason": "Full preventive maintenance — quarterly"},
        {"machine_id": "MCH-03", "offset_days": 7,  "duration_hours": 4,  "reason": "Calibration check"},
        {"machine_id": "MCH-01", "offset_days": 35, "duration_hours": 12, "reason": "Conveyor belt replacement"},
        {"machine_id": "MCH-02", "offset_days": 50, "duration_hours": 8,  "reason": "Software update & sensor calibration"},
    ]
    result = []
    for w in windows:
        start = reference_date + timedelta(days=w["offset_days"])
        end = start + timedelta(hours=w["duration_hours"])
        result.append({
            "machine_id": w["machine_id"],
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "reason": w["reason"],
            "is_hard_constraint": True,
        })
    return result


def save_fixtures(reference_date: datetime):
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating sales history (2.5 years)...")
    df = generate_sales_history()
    df.to_csv(FIXTURES_DIR / "sales_history.csv", index=False)
    print(f"  ✓ {len(df)} rows → sales_history.csv")

    print("Generating machine capacity...")
    with open(FIXTURES_DIR / "machine_capacity.json", "w") as f:
        json.dump(MACHINES, f, indent=2)
    print(f"  ✓ {len(MACHINES)} machines → machine_capacity.json")

    print("Generating current schedule...")
    schedule = generate_current_schedule(reference_date)
    with open(FIXTURES_DIR / "current_schedule.json", "w") as f:
        json.dump(schedule, f, indent=2)
    print(f"  ✓ {len(schedule)} jobs → current_schedule.json")

    print("Generating maintenance calendar...")
    maintenance = generate_maintenance_calendar(reference_date)
    with open(FIXTURES_DIR / "maintenance_calendar.json", "w") as f:
        json.dump(maintenance, f, indent=2)
    print(f"  ✓ {len(maintenance)} windows → maintenance_calendar.json")


def seed_database(reference_date: datetime):
    """Load fixtures into SQLite."""
    sys.path.insert(0, str(Path(__file__).parents[3]))
    from app.models.db import (
        create_all_tables, SessionLocal,
        SalesHistory, MachineCapacity, JobOrder, MaintenanceWindow
    )

    create_all_tables()
    db = SessionLocal()

    try:
        # Clear existing data
        db.query(SalesHistory).delete()
        db.query(MachineCapacity).delete()
        db.query(JobOrder).delete()
        db.query(MaintenanceWindow).delete()
        db.commit()

        # Sales history
        df = pd.read_csv(FIXTURES_DIR / "sales_history.csv")
        df["date"] = pd.to_datetime(df["date"])
        records = [
            SalesHistory(
                sku=row["sku"],
                date=row["date"].to_pydatetime(),
                quantity=float(row["quantity"]),
                is_promotional=bool(row["is_promotional"]),
                region=str(row.get("region", "default")),
            )
            for _, row in df.iterrows()
        ]
        db.add_all(records)
        db.commit()
        print(f"  ✓ Loaded {len(df)} sales history records")

        # Machine capacity
        with open(FIXTURES_DIR / "machine_capacity.json") as f:
            machines = json.load(f)
        for m in machines:
            for shift in m["shifts"]:
                db.add(MachineCapacity(
                    machine_id=m["machine_id"],
                    machine_name=m["machine_name"],
                    shift=shift["shift"],
                    capacity_hours=shift["capacity_hours"],
                    utilization_pct=shift["utilization_pct"],
                    compatible_skus=m["compatible_skus"],
                ))
        db.commit()
        print(f"  ✓ Loaded machine capacity for {len(machines)} machines")

        # Job orders
        with open(FIXTURES_DIR / "current_schedule.json") as f:
            jobs = json.load(f)
        for j in jobs:
            j["start_time"] = datetime.fromisoformat(j["start_time"])
            j["end_time"] = datetime.fromisoformat(j["end_time"])
            if j["committed_delivery_date"]:
                j["committed_delivery_date"] = datetime.fromisoformat(j["committed_delivery_date"])
            db.add(JobOrder(**j))
        db.commit()
        print(f"  ✓ Loaded {len(jobs)} job orders")

        # Maintenance windows
        with open(FIXTURES_DIR / "maintenance_calendar.json") as f:
            windows = json.load(f)
        for w in windows:
            w["start_time"] = datetime.fromisoformat(w["start_time"])
            w["end_time"] = datetime.fromisoformat(w["end_time"])
            db.add(MaintenanceWindow(**w))
        db.commit()
        print(f"  ✓ Loaded {len(windows)} maintenance windows")

    finally:
        db.close()


if __name__ == "__main__":
    ref = datetime.now()
    print("=== Generating fixtures ===")
    save_fixtures(ref)
    print("\n=== Seeding database ===")
    seed_database(ref)
    print("\n✅ Done! Database seeded successfully.")
