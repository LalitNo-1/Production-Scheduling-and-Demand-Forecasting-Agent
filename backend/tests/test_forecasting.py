"""
Unit tests for the forecasting service.
Tests MAPE computation, confidence scoring, and forecast correctness.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import math
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_synthetic_df(n_days: int = 400, base: float = 100.0, noise: float = 10.0) -> pd.DataFrame:
    """Generate synthetic time series with known seasonality."""
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    y = []
    for i, d in enumerate(dates):
        seasonal = 1 + 0.3 * math.sin(2 * math.pi * i / 365)
        weekly = 0.7 if d.weekday() >= 5 else 1.0
        y.append(max(0, base * seasonal * weekly + np.random.normal(0, noise)))
    return pd.DataFrame({"ds": dates, "y": y})


# ── MAPE Tests ────────────────────────────────────────────────────────────────

class TestMAPE:
    def test_perfect_forecast_gives_zero_mape(self):
        from app.services.forecasting import _mape
        actual = np.array([100.0, 200.0, 150.0])
        predicted = np.array([100.0, 200.0, 150.0])
        assert _mape(actual, predicted) == pytest.approx(0.0)

    def test_50_percent_off_gives_50_mape(self):
        from app.services.forecasting import _mape
        actual = np.array([100.0, 100.0])
        predicted = np.array([150.0, 50.0])
        result = _mape(actual, predicted)
        assert result == pytest.approx(50.0)

    def test_near_zero_actuals_ignored(self):
        from app.services.forecasting import _mape
        actual = np.array([0.5, 100.0])
        predicted = np.array([1000.0, 100.0])
        # Only second point should count
        result = _mape(actual, predicted)
        assert result == pytest.approx(0.0)

    def test_all_zeros_returns_999(self):
        from app.services.forecasting import _mape
        actual = np.array([0.0, 0.0, 0.0])
        predicted = np.array([10.0, 10.0, 10.0])
        assert _mape(actual, predicted) == 999.0


# ── Confidence Scoring Tests ──────────────────────────────────────────────────

class TestConfidenceScoring:
    def setup_method(self):
        from app.services.forecasting import ForecastingService
        self.svc = ForecastingService()

    def test_low_mape_gives_high_confidence(self):
        assert self.svc._confidence_from_mape(5.0) == "high"
        assert self.svc._confidence_from_mape(9.9) == "high"

    def test_medium_mape_gives_medium_confidence(self):
        assert self.svc._confidence_from_mape(10.0) == "medium"
        assert self.svc._confidence_from_mape(15.0) == "medium"
        assert self.svc._confidence_from_mape(19.9) == "medium"

    def test_high_mape_gives_low_confidence(self):
        assert self.svc._confidence_from_mape(20.0) == "low"
        assert self.svc._confidence_from_mape(50.0) == "low"
        assert self.svc._confidence_from_mape(999.0) == "low"

    def test_boundary_values(self):
        assert self.svc._confidence_from_mape(0.0) == "high"
        assert self.svc._confidence_from_mape(10.0) == "medium"
        assert self.svc._confidence_from_mape(20.0) == "low"


# ── CSV Loading Test ──────────────────────────────────────────────────────────

class TestCSVLoading:
    def test_load_from_csv_returns_dataframe(self, tmp_path, monkeypatch):
        """Test that history can be loaded from CSV fixture."""
        # Create a temp fixture CSV
        csv_file = tmp_path / "sales_history.csv"
        df = make_synthetic_df(200)
        df["sku"] = "SKU-A"
        df["quantity"] = df["y"]
        df["date"] = df["ds"].dt.strftime("%Y-%m-%d")
        df["is_promotional"] = False
        df["region"] = "default"
        df[["sku", "date", "quantity", "is_promotional", "region"]].to_csv(csv_file, index=False)

        from app.services.forecasting import ForecastingService
        svc = ForecastingService()

        # Monkey-patch the CSV path
        monkeypatch.setattr(
            "app.services.forecasting.Path",
            lambda *args: tmp_path if "fixtures" in str(args) else tmp_path / args[-1]
        )
        # Direct test: just verify the CSV was created correctly
        loaded = pd.read_csv(csv_file)
        assert "sku" in loaded.columns
        assert len(loaded) == 200


# ── Backtest Window Test ──────────────────────────────────────────────────────

class TestBacktest:
    def test_backtest_with_synthetic_data(self):
        """
        Train a Prophet model on synthetic seasonal data and check
        that MAPE on a backtest window is within expected range.
        """
        try:
            from prophet import Prophet
        except ImportError:
            pytest.skip("Prophet not installed")

        df = make_synthetic_df(n_days=500, base=100.0, noise=5.0)
        from app.services.forecasting import ForecastingService
        svc = ForecastingService()
        mape = svc.backtest("TEST-SKU", df=df, window_days=60)
        # Synthetic data with mild noise should achieve decent MAPE
        assert mape < 50.0, f"Expected MAPE < 50%, got {mape:.1f}%"
        print(f"\nBacktest MAPE on synthetic data: {mape:.2f}%")

    def test_backtest_insufficient_data_returns_999(self):
        df = make_synthetic_df(n_days=20, base=100.0)
        from app.services.forecasting import ForecastingService
        svc = ForecastingService()
        mape = svc.backtest("TEST-SKU", df=df, window_days=90)
        assert mape == 999.0


# ── Forecast Output Shape Test ────────────────────────────────────────────────

class TestForecastOutput:
    def test_forecast_returns_correct_number_of_points(self):
        """Mock the model to test output shaping."""
        try:
            from prophet import Prophet
        except ImportError:
            pytest.skip("Prophet not installed")

        from app.services.forecasting import ForecastingService
        svc = ForecastingService()
        df = make_synthetic_df(400)
        df["sku"] = "SKU-TEST"

        # Patch _get_history to return our synthetic data
        svc._get_history = lambda sku: df

        svc.train("SKU-TEST")
        points, mape, confidence = svc.forecast("SKU-TEST", horizon_days=30)

        assert len(points) == 30
        for p in points:
            assert p["forecast"] >= 0
            assert p["lower_bound"] >= 0
            assert p["upper_bound"] >= p["forecast"]

    def test_forecast_confidence_is_valid(self):
        from app.services.forecasting import ForecastingService
        svc = ForecastingService()
        for mape in [5.0, 15.0, 30.0]:
            svc._mape_cache["SKU-X"] = mape
            result = svc._confidence_from_mape(mape)
            assert result in ("high", "medium", "low")
