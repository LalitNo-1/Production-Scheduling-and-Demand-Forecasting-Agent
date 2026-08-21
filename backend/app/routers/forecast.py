"""
Forecast endpoints — wraps the ForecastingService.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models.db import get_db
from app.models.schemas import ForecastResponse, ForecastPoint
from app.services.forecasting import get_forecasting_service

router = APIRouter()


@router.get("/demand-forecast", response_model=ForecastResponse)
def demand_forecast(
    sku: str = Query(..., description="SKU to forecast, e.g. SKU-A"),
    horizon: int = Query(30, ge=1, le=365, description="Forecast horizon in days"),
    db: Session = Depends(get_db),
):
    """
    Returns demand forecast for a SKU with confidence bands and backtest MAPE.
    Confidence level is HIGH (<10% MAPE), MEDIUM (10-20%), or LOW (>20%).
    """
    svc = get_forecasting_service(db)
    points, mape, confidence = svc.forecast(sku, horizon)

    return ForecastResponse(
        sku=sku,
        horizon_days=horizon,
        forecast=[
            ForecastPoint(
                date=p["date"],
                forecast=p["forecast"],
                lower_bound=p["lower_bound"],
                upper_bound=p["upper_bound"],
            )
            for p in points
        ],
        confidence=confidence,
        mape_backtest=mape,
    )


@router.get("/forecast-backtest")
def forecast_backtest(
    sku: str = Query(...),
    window_days: int = Query(90, ge=30, le=180),
    db: Session = Depends(get_db),
):
    """Run walk-forward backtest and return MAPE for the SKU."""
    svc = get_forecasting_service(db)
    mape = svc.backtest(sku, window_days=window_days)
    from app.services.forecasting import CONFIDENCE_THRESHOLDS
    if mape < CONFIDENCE_THRESHOLDS["high"]:
        confidence = "high"
    elif mape < CONFIDENCE_THRESHOLDS["medium"]:
        confidence = "medium"
    else:
        confidence = "low"
    return {"sku": sku, "window_days": window_days, "mape_pct": round(mape, 2), "confidence": confidence}


@router.post("/train-models")
def train_models(
    force: bool = Query(False, description="Force retrain even if cached"),
    db: Session = Depends(get_db),
):
    """Trigger model training for all SKUs."""
    svc = get_forecasting_service(db)
    results = svc.train_all(force=force)
    return {"trained": results}
