#!/usr/bin/env python3
"""
Demo Data Seeder — Populates the system with realistic demo runs for testing the dashboard.

Usage:
    python scripts/seed_demo.py
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from random import choice, randint, uniform

sys.path.insert(0, str(Path(__file__).parent.parent))

AGENTS = ["email_agent", "lead_agent", "content_agent", "report_agent", "invoice_agent", "support_agent"]
STATUSES = ["success", "success", "success", "success", "failed", "skipped"]


def generate_run(agent: str, hours_ago: float) -> dict:
    status = choice(STATUSES)
    started = datetime.utcnow() - timedelta(hours=hours_ago)
    duration = uniform(1.2, 22.0)
    processed = randint(3, 50) if status != "failed" else 0
    actioned = randint(1, processed) if processed > 0 else 0

    output = {}
    if agent == "email_agent" and status == "success":
        output = {"total_processed": processed, "categories": {"lead": 4, "support": 3, "newsletter": 8}}
    elif agent == "lead_agent" and status == "success":
        output = {"total_leads": processed, "qualified": actioned, "avg_score": round(uniform(55, 80), 1)}
    elif agent == "report_agent" and status == "success":
        output = {"mrr": 8400, "new_revenue": 2200, "deals_closed": 2}

    return {
        "run_id": str(uuid.uuid4())[:8],
        "agent": agent,
        "status": status,
        "started_at": started.isoformat(),
        "finished_at": (started + timedelta(seconds=duration)).isoformat(),
        "duration_s": round(duration, 2),
        "items_processed": processed,
        "items_actioned": actioned,
        "errors": ["Connection timeout" if status == "failed" else ""][0:1 if status == "failed" else 0],
        "output": output,
        "dry_run": False,
    }


async def seed():
    # Import memory to persist some fake run history
    print("🌱 Seeding demo data...")

    runs = []
    for i, agent in enumerate(AGENTS):
        # Generate ~5 runs per agent over the past week
        for j in range(5):
            hours = (i * 2) + (j * 12) + uniform(0, 4)
            runs.append(generate_run(agent, hours_ago=hours))

    runs.sort(key=lambda r: r["started_at"], reverse=True)

    print(f"  Generated {len(runs)} demo runs across {len(AGENTS)} agents")
    print("  ✅ Demo data ready — start the server to see the dashboard")
    print("\n  Run: python -m src.api.server\n")

    # Write to a JSON fixture for the dashboard to load
    import json
    fixture_path = Path("demo_runs.json")
    fixture_path.write_text(json.dumps(runs, indent=2))
    print(f"  Fixture saved to {fixture_path}")


if __name__ == "__main__":
    asyncio.run(seed())
