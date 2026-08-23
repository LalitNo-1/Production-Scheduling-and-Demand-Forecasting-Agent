"""
Pydantic schemas for request validation and API responses.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


# ─── Shared ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str = "0.1.0"


# ─── Sales History ───────────────────────────────────────────────────────────

class SalesPoint(BaseModel):
    date: datetime
    quantity: float
    is_promotional: bool = False


class SalesHistoryResponse(BaseModel):
    sku: str
    data: List[SalesPoint]


# ─── Forecast ────────────────────────────────────────────────────────────────

class ForecastPoint(BaseModel):
    date: datetime
    forecast: float
    lower_bound: float
    upper_bound: float


class ForecastResponse(BaseModel):
    sku: str
    horizon_days: int
    forecast: List[ForecastPoint]
    confidence: Literal["high", "medium", "low"]
    mape_backtest: float = Field(description="MAPE % on last 90-day backtest window")
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ─── Machine Capacity ────────────────────────────────────────────────────────

class ShiftCapacity(BaseModel):
    shift: int
    capacity_hours: float
    utilization_pct: float
    available_hours: float


class MachineCapacityResponse(BaseModel):
    machine_id: str
    machine_name: Optional[str] = None
    shifts: List[ShiftCapacity]
    compatible_skus: List[str] = []
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None


class MachineCreateRequest(BaseModel):
    machine_id: str
    machine_name: str
    shifts: Optional[List[ShiftCapacity]] = None
    capacity_hours: float = 8.0
    compatible_skus: List[str] = []


class MachineUpdateRequest(BaseModel):
    machine_name: Optional[str] = None
    capacity_hours: Optional[float] = None
    compatible_skus: Optional[List[str]] = None


class SKUMetadataOut(BaseModel):
    sku: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    units_per_hour: float = 50.0

    class Config:
        from_attributes = True


class SKUMetadataUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    units_per_hour: Optional[float] = None


class MaintenanceWindowOut(BaseModel):
    machine_id: str
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = None
    is_hard_constraint: bool = True

    class Config:
        from_attributes = True


# ─── Job Orders / Schedule ───────────────────────────────────────────────────

class JobOrderOut(BaseModel):
    job_id: str
    job_name: Optional[str] = None
    sku: str
    quantity: float
    machine_id: str
    start_time: datetime
    end_time: datetime
    committed_delivery_date: Optional[datetime] = None
    has_committed_delivery: bool = False
    status: str
    priority: int = 5
    margin_per_unit: float = 1.0

    class Config:
        from_attributes = True


class JobOrderCreateRequest(BaseModel):
    job_id: Optional[str] = None
    job_name: Optional[str] = None
    sku: str
    quantity: float
    machine_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_hours: Optional[float] = None
    committed_delivery_date: Optional[datetime] = None
    has_committed_delivery: bool = False
    priority: int = 5
    margin_per_unit: float = 1.0


class JobOrderUpdateRequest(BaseModel):
    job_name: Optional[str] = None
    sku: Optional[str] = None
    quantity: Optional[float] = None
    machine_id: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    committed_delivery_date: Optional[datetime] = None
    has_committed_delivery: Optional[bool] = None
    status: Optional[str] = None
    priority: Optional[int] = None


class ScheduleResponse(BaseModel):
    jobs: List[JobOrderOut]
    total_jobs: int
    filters_applied: Dict[str, Any] = {}


# ─── Proposed Changes ────────────────────────────────────────────────────────

class ProposeChangeRequest(BaseModel):
    sku: str
    horizon_days: int = 30
    machine_id: Optional[str] = None
    force: bool = False   # override low-confidence guard (must be explicitly set)


class SimulationResult(BaseModel):
    expected_fulfillment_rate: float   # %
    p10_fulfillment: float             # pessimistic 10th percentile
    p90_fulfillment: float             # optimistic 90th percentile
    at_risk_jobs: List[str]            # job_ids at risk of missing delivery date
    simulation_samples: int = 200


class ProposedChangeResponse(BaseModel):
    change_id: str
    status: str
    sku: str
    rationale: str
    forecast_confidence: Literal["high", "medium", "low"]
    has_delivery_date_warning: bool
    affected_jobs: List[str]
    before_state: List[Dict[str, Any]]
    after_state: List[Dict[str, Any]]
    simulation_result: Optional[SimulationResult] = None
    created_at: datetime
    expires_at: Optional[datetime] = None


class CommitRequest(BaseModel):
    change_id: str
    approved_by: str = Field(..., min_length=1, description="Name/ID of human approver — required")
    notes: Optional[str] = None


class CommitResponse(BaseModel):
    change_id: str
    committed: bool
    audit_id: int
    message: str


class RejectRequest(BaseModel):
    change_id: str
    rejected_by: str
    reason: Optional[str] = None


class RollbackResponse(BaseModel):
    change_id: str
    rolled_back: bool
    jobs_restored: int
    message: str


# ─── Audit Log ───────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id: int
    change_id: str
    timestamp: datetime
    actor: str
    action: str
    sku: Optional[str]
    forecast_confidence: Optional[str]
    has_delivery_date_warning: bool
    approval_status: str
    notes: Optional[str]
    before_state: Optional[List[Dict[str, Any]]]
    after_state: Optional[List[Dict[str, Any]]]

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    entries: List[AuditLogEntry]
    total: int


# ─── Agent ───────────────────────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    sku: str
    horizon_days: int = 30
    machine_id: Optional[str] = None


class AgentRunResponse(BaseModel):
    sku: str
    status: str              # completed, flagged_low_confidence, error
    message: str
    proposed_change_id: Optional[str] = None
    forecast_confidence: Optional[str] = None
    reasoning_steps: List[str] = []
