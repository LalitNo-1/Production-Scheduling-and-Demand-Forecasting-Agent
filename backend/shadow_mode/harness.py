"""
Shadow mode harness — runs the agent daily for N simulated days.
Logs what it WOULD have proposed without committing anything.
Produces shadow_report.md with proposal stats and forecast accuracy.

Usage:
    cd backend
    python shadow_mode/harness.py --days 30 --sku SKU-A
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

LOG_FILE = Path(__file__).parent / "shadow_log.jsonl"
REPORT_FILE = Path(__file__).parent / "shadow_report.md"


def run_shadow_day(
    sku: str,
    sim_date: datetime,
    db,
    dry_run: bool = True,
) -> dict:
    """
    Run the agent for one simulated day.
    Returns the agent result without committing.
    """
    from app.services.agent import MockProductionAgent

    agent = MockProductionAgent(db)
    result = agent.run(sku, horizon_days=30)

    entry = {
        "simulated_date": sim_date.isoformat(),
        "sku": sku,
        "status": result["status"],
        "proposed_change_id": result.get("proposed_change_id"),
        "forecast_confidence": result.get("forecast_confidence"),
        "message_preview": result.get("message", "")[:200],
        "reasoning_steps_count": len(result.get("reasoning_steps", [])),
        "dry_run": dry_run,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Append to JSONL log
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info(
        f"Day {sim_date.date()} | {sku} | status={result['status']} | "
        f"confidence={result.get('forecast_confidence')} | "
        f"proposal={result.get('proposed_change_id')}"
    )
    return entry


def generate_report(days: int, skus: list, entries: list) -> str:
    """Generate shadow_report.md."""
    total = len(entries)
    proposed = [e for e in entries if e.get("proposed_change_id")]
    flagged = [e for e in entries if e["status"] == "flagged_low_confidence"]
    errors = [e for e in entries if e["status"] == "error"]

    by_sku = {}
    for sku in skus:
        sku_entries = [e for e in entries if e["sku"] == sku]
        by_sku[sku] = {
            "total": len(sku_entries),
            "proposed": len([e for e in sku_entries if e.get("proposed_change_id")]),
            "flagged_low_confidence": len([e for e in sku_entries if e["status"] == "flagged_low_confidence"]),
        }

    lines = [
        "# Shadow Mode Report",
        f"\n**Generated**: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Simulated Period**: {days} days",
        f"**SKUs monitored**: {', '.join(skus)}",
        "\n---\n",
        "## Summary",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total agent runs | {total} |",
        f"| Proposals generated | {len(proposed)} ({len(proposed)/max(total,1)*100:.0f}%) |",
        f"| Flagged (low confidence) | {len(flagged)} ({len(flagged)/max(total,1)*100:.0f}%) |",
        f"| Errors | {len(errors)} |",
        "\n## Per-SKU Breakdown",
        "| SKU | Runs | Proposals | Flagged |",
        "|-----|------|-----------|---------|",
    ]
    for sku, stats in by_sku.items():
        lines.append(f"| {sku} | {stats['total']} | {stats['proposed']} | {stats['flagged_low_confidence']} |")

    lines += [
        "\n## What Would Have Happened",
        "\n### Always-Accept Scenario",
        f"If a human always approved every proposal: **{len(proposed)} schedule changes** would have been committed over {days} days.",
        "\n### Always-Reject Scenario",
        f"If a human always rejected: **0 schedule changes** committed. The original schedule would remain unchanged.",
        "\n### Recommended Strategy",
        "- Review proposals flagged with delivery-date warnings manually",
        "- Auto-queue HIGH-confidence proposals for expedited human review",
        "- Treat LOW-confidence days as forecast review triggers",
        "\n## Trust Indicators",
        f"- **Proposal rate**: {len(proposed)/max(days,1)*100:.0f}% of days generated proposals",
        f"- **Flag rate**: {len(flagged)/max(days,1)*100:.0f}% of days triggered low-confidence flags",
        f"- **Stability**: {'HIGH' if len(proposed)/max(days,1) < 0.5 else 'MODERATE'} "
        f"(fewer daily proposals = more stable baseline schedule)",
        "\n> **Note**: This report covers shadow mode only. No changes were committed to the production schedule.",
    ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Production Scheduling Shadow Mode Harness")
    parser.add_argument("--days", type=int, default=30, help="Number of days to simulate")
    parser.add_argument("--sku", type=str, default="SKU-A,SKU-B,SKU-C", help="Comma-separated SKUs")
    parser.add_argument("--start-date", type=str, default=None, help="Simulation start date (YYYY-MM-DD)")
    args = parser.parse_args()

    skus = [s.strip() for s in args.sku.split(",")]
    start = (
        datetime.fromisoformat(args.start_date)
        if args.start_date
        else datetime.now()
    )

    logger.info(f"=== Shadow Mode Harness ===")
    logger.info(f"Simulating {args.days} days for SKUs: {skus}")
    logger.info(f"Starting from: {start.date()}")
    logger.info(f"Log file: {LOG_FILE}")

    # Ensure DB is seeded
    from app.models.db import create_all_tables, SessionLocal, SalesHistory
    create_all_tables()
    db = SessionLocal()

    count = db.query(SalesHistory).count()
    if count == 0:
        logger.info("DB empty — seeding...")
        from app.data.seed import save_fixtures, seed_database
        save_fixtures(start)
        seed_database(start)

    # Clear old log
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    entries = []
    for day_offset in range(args.days):
        sim_date = start + timedelta(days=day_offset)
        for sku in skus:
            try:
                entry = run_shadow_day(sku, sim_date, db, dry_run=True)
                entries.append(entry)
            except Exception as e:
                logger.error(f"Error on day {sim_date.date()} for {sku}: {e}")
                entries.append({
                    "simulated_date": sim_date.isoformat(),
                    "sku": sku, "status": "error",
                    "error": str(e),
                })

    db.close()

    # Generate report
    report = generate_report(args.days, skus, entries)
    with open(REPORT_FILE, "w") as f:
        f.write(report)

    logger.info(f"\n=== Shadow Run Complete ===")
    logger.info(f"Report: {REPORT_FILE}")
    logger.info(f"Log entries: {LOG_FILE}")
    print("\n" + report)


if __name__ == "__main__":
    main()
