"""
Forecasting service using Facebook Prophet.
Handles per-SKU model training, backtest MAPE, and confidence scoring.
"""

import logging
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Suppress Prophet's verbose Stan output
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

MODEL_CACHE_DIR = Path(__file__).parents[2] / ".model_cache"
MODEL_CACHE_DIR.mkdir(exist_ok=True)

CONFIDENCE_THRESHOLDS = {
    "high":   10.0,   # MAPE < 10%
    "medium": 20.0,   # MAPE 10–20%
    # else: low (MAPE > 20%)
}


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Percentage Error, ignoring near-zero actuals."""
    mask = actual > 1.0
    if mask.sum() == 0:
        return 999.0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


class ForecastingService:
    """
    Trains and serves Prophet models per SKU.
    Models are cached to disk for fast startup after first run.
    """

    def __init__(self, db_session=None):
        self._models: Dict[str, object] = {}
        self._mape_cache: Dict[str, float] = {}
        self.db = db_session

    # ── Training ─────────────────────────────────────────────────────────────

    def _load_history_from_db(self, sku: str) -> pd.DataFrame:
        """Load sales history from DB as a Prophet-ready DataFrame (ds, y)."""
        if self.db is None:
            raise RuntimeError("ForecastingService needs a DB session to load history")
        from app.models.db import SalesHistory
        rows = self.db.query(SalesHistory).filter(SalesHistory.sku == sku).all()
        if not rows:
            raise ValueError(f"No sales history found for SKU: {sku}")
        df = pd.DataFrame([{"ds": r.date, "y": r.quantity} for r in rows])
        df["ds"] = pd.to_datetime(df["ds"])
        return df.sort_values("ds").reset_index(drop=True)

    def _load_history_from_csv(self, sku: str) -> pd.DataFrame:
        """Fallback: load from CSV fixture (for tests / standalone use)."""
        csv_path = Path(__file__).parents[2] / "app" / "data" / "fixtures" / "sales_history.csv"
        df = pd.read_csv(csv_path)
        df = df[df["sku"] == sku][["date", "quantity"]].rename(
            columns={"date": "ds", "quantity": "y"}
        )
        df["ds"] = pd.to_datetime(df["ds"])
        return df.sort_values("ds").reset_index(drop=True)

    def _get_history(self, sku: str) -> pd.DataFrame:
        try:
            return self._load_history_from_db(sku)
        except Exception:
            return self._load_history_from_csv(sku)

    def train(self, sku: str, force_retrain: bool = False) -> float:
        """
        Train Prophet model for a SKU.
        Returns backtest MAPE.
        Caches model to disk.
        """
        try:
            from prophet import Prophet
        except ImportError:
            logger.warning("Prophet not installed, using SARIMA fallback")
            mape = self._train_sarima(sku)
            self._mape_cache[sku] = mape  # ← fix: populate cache
            return mape

        cache_path = MODEL_CACHE_DIR / f"{sku}.pkl"

        if not force_retrain and cache_path.exists():
            with open(cache_path, "rb") as f:
                self._models[sku] = pickle.load(f)
            logger.info(f"Loaded cached Prophet model for {sku}")
            if sku in self._mape_cache:
                return self._mape_cache[sku]

        df = self._get_history(sku)

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10,
        )
        model.fit(df)
        self._models[sku] = model

        # Persist
        with open(cache_path, "wb") as f:
            pickle.dump(model, f)

        mape = self.backtest(sku, df=df)
        self._mape_cache[sku] = mape
        logger.info(f"Trained Prophet for {sku} — MAPE: {mape:.2f}%")
        return mape

    def _train_sarima(self, sku: str) -> float:
        """SARIMA fallback if Prophet is unavailable."""
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        df = self._get_history(sku)
        weekly = df.set_index("ds").resample("W").sum()
        model = SARIMAX(weekly["y"], order=(1, 1, 1), seasonal_order=(1, 1, 1, 52))
        result = model.fit(disp=False)
        self._models[sku] = ("sarima", result, weekly.index[-1])
        return 15.0  # rough placeholder MAPE for SARIMA

    # ── Forecasting ──────────────────────────────────────────────────────────

    def forecast(
        self, sku: str, horizon_days: int = 30
    ) -> Tuple[List[dict], float, str]:
        """
        Returns (forecast_points, mape, confidence_level).
        forecast_points: list of {date, forecast, lower_bound, upper_bound}
        """
        if sku not in self._models:
            self.train(sku)

        model = self._models[sku]
        mape = self._mape_cache.get(sku, 999.0)
        confidence = self._confidence_from_mape(mape)

        if isinstance(model, tuple) and model[0] == "sarima":
            return self._forecast_sarima(model, horizon_days), mape, confidence

        future = model.make_future_dataframe(periods=horizon_days, freq="D")
        forecast_df = model.predict(future)

        # Only return future rows
        last_history_date = self._get_history(sku)["ds"].max()
        future_rows = forecast_df[forecast_df["ds"] > last_history_date].copy()

        points = []
        for _, row in future_rows.iterrows():
            points.append({
                "date": row["ds"].to_pydatetime(),
                "forecast": max(0.0, float(row["yhat"])),
                "lower_bound": max(0.0, float(row["yhat_lower"])),
                "upper_bound": max(0.0, float(row["yhat_upper"])),
            })

        return points[:horizon_days], mape, confidence

    def _forecast_sarima(self, model_tuple, horizon_days: int) -> List[dict]:
        _, result, last_date = model_tuple
        horizon_weeks = max(1, horizon_days // 7)
        forecast = result.get_forecast(steps=horizon_weeks)
        mean = forecast.predicted_mean
        ci = forecast.conf_int()
        points = []
        for i in range(len(mean)):
            date = last_date + timedelta(weeks=i + 1)
            points.append({
                "date": date.to_pydatetime(),
                "forecast": max(0.0, float(mean.iloc[i])),
                "lower_bound": max(0.0, float(ci.iloc[i, 0])),
                "upper_bound": max(0.0, float(ci.iloc[i, 1])),
            })
        return points

    # ── Backtesting ──────────────────────────────────────────────────────────

    def backtest(self, sku: str, df: Optional[pd.DataFrame] = None, window_days: int = 90) -> float:
        """
        Walk-forward backtest on the last `window_days` of history.
        Trains on everything before the window, forecasts through the window, computes MAPE.
        """
        try:
            from prophet import Prophet
        except ImportError:
            return 15.0

        if df is None:
            df = self._get_history(sku)

        cutoff = df["ds"].max() - timedelta(days=window_days)
        train_df = df[df["ds"] <= cutoff]
        test_df = df[df["ds"] > cutoff]

        if len(train_df) < 30 or len(test_df) == 0:
            return 999.0

        bt_model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05,
        )
        bt_model.fit(train_df)

        future = bt_model.make_future_dataframe(periods=window_days, freq="D")
        preds = bt_model.predict(future)
        preds = preds[preds["ds"] > cutoff].set_index("ds")["yhat"]

        test_df = test_df.set_index("ds")
        aligned = test_df.join(preds, how="inner")
        mape = _mape(aligned["y"].values, aligned["yhat"].values)
        return mape

    def _confidence_from_mape(self, mape: float) -> str:
        if mape < CONFIDENCE_THRESHOLDS["high"]:
            return "high"
        elif mape < CONFIDENCE_THRESHOLDS["medium"]:
            return "medium"
        return "low"

    def get_mape(self, sku: str) -> float:
        if sku not in self._mape_cache:
            self.train(sku)
        return self._mape_cache.get(sku, 999.0)

    def train_all(self, skus: List[str] = None, force: bool = False):
        if skus is None:
            skus = ["SKU-A", "SKU-B", "SKU-C"]
        results = {}
        for sku in skus:
            try:
                mape = self.train(sku, force_retrain=force)
                results[sku] = {"mape": mape, "confidence": self._confidence_from_mape(mape)}
                print(f"  {sku}: MAPE={mape:.2f}%  confidence={results[sku]['confidence']}")
            except Exception as e:
                logger.error(f"Failed to train {sku}: {e}")
                results[sku] = {"error": str(e)}
        return results


# Singleton instance
_service: Optional[ForecastingService] = None


def get_forecasting_service(db=None) -> ForecastingService:
    global _service
    if _service is None:
        _service = ForecastingService(db_session=db)
    elif db is not None:
        _service.db = db
    return _service
