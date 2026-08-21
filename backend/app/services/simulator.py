"""
Monte Carlo impact simulator.
Runs proposed schedules against historical demand variance to produce
an expected-outcome range (p10/p50/p90 fulfillment rates).
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

N_SAMPLES = 200


class SimulatorService:

    def simulate_impact(
        self,
        proposed_jobs: List[Dict],
        historical_variance: Optional[Dict[str, float]] = None,
        n_samples: int = N_SAMPLES,
    ) -> Dict:
        """
        Simulate the proposed schedule against demand variance.

        Args:
            proposed_jobs: list of job dicts with quantity, sku, committed_delivery_date
            historical_variance: {sku: coefficient_of_variation} — defaults to
                                 realistic estimates from mock data if not provided
        Returns:
            SimulationResult dict
        """
        if historical_variance is None:
            # Estimated CV from mock data (noise_std / base_demand)
            historical_variance = {
                "SKU-A": 0.125,   # 15 / 120
                "SKU-B": 0.125,   # 10 / 80
                "SKU-C": 0.125,   # 25 / 200
            }

        fulfillment_rates = []
        at_risk_counts: Dict[str, int] = {}

        rng = np.random.default_rng(42)

        for _ in range(n_samples):
            fulfilled = 0
            total = 0
            for job in proposed_jobs:
                sku = job.get("sku", "SKU-A")
                planned_qty = float(job.get("quantity", 100))
                cv = historical_variance.get(sku, 0.15)

                # Simulate actual demand as normally distributed around planned
                actual_demand = rng.normal(planned_qty, planned_qty * cv)
                actual_demand = max(0, actual_demand)

                # Fulfillment: min(production capacity, actual demand)
                fulfilled += min(planned_qty, actual_demand)
                total += actual_demand

            rate = (fulfilled / total * 100) if total > 0 else 100.0
            fulfillment_rates.append(rate)

        rates = np.array(fulfillment_rates)

        # Identify at-risk jobs (those with committed delivery that have >20% chance of missing)
        at_risk_jobs = []
        for job in proposed_jobs:
            if job.get("has_committed_delivery") or job.get("committed_delivery_date"):
                sku = job.get("sku", "SKU-A")
                cv = historical_variance.get(sku, 0.15)
                planned = float(job.get("quantity", 100))
                # P(actual_demand > planned) ~ tail probability
                if cv > 0.12:  # high variance = at risk
                    at_risk_jobs.append(job.get("job_id", "unknown"))

        return {
            "expected_fulfillment_rate": float(np.mean(rates)),
            "p10_fulfillment": float(np.percentile(rates, 10)),
            "p90_fulfillment": float(np.percentile(rates, 90)),
            "at_risk_jobs": at_risk_jobs,
            "simulation_samples": n_samples,
        }


_simulator: Optional[SimulatorService] = None


def get_simulator() -> SimulatorService:
    global _simulator
    if _simulator is None:
        _simulator = SimulatorService()
    return _simulator
