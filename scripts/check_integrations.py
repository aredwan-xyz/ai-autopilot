#!/usr/bin/env python3
"""
Integration Health Check — Tests all configured third-party connections.

Usage:
    python scripts/check_integrations.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def check_all():
    from src.config.settings import settings

    results = {}

    # ── Anthropic ──
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        client.models.list()
        results["Anthropic"] = ("✅", "Connected")
    except Exception as e:
        results["Anthropic"] = ("❌", str(e)[:60])

    # ── Gmail ──
    try:
        from src.integrations.gmail import GmailClient
        gmail = GmailClient()
        ok = await gmail.health_check()
        results["Gmail"] = ("✅", "Connected") if ok else ("❌", "Health check failed")
    except Exception as e:
        results["Gmail"] = ("❌", str(e)[:60])

    # ── Slack ──
    try:
        from src.integrations.slack import SlackClient
        slack = SlackClient()
        client = slack._get_client()
        await client.auth_test()
        results["Slack"] = ("✅", "Connected")
    except Exception as e:
        results["Slack"] = ("⚠️ ", "Not configured" if not settings.SLACK_BOT_TOKEN else str(e)[:60])

    # ── Notion ──
    try:
        import httpx
        resp = httpx.get(
            "https://api.notion.com/v1/users/me",
            headers={"Authorization": f"Bearer {settings.NOTION_API_KEY}", "Notion-Version": "2022-06-28"},
        )
        results["Notion"] = ("✅", "Connected") if resp.status_code == 200 else ("❌", f"HTTP {resp.status_code}")
    except Exception as e:
        results["Notion"] = ("⚠️ ", "Not configured" if not settings.NOTION_API_KEY else str(e)[:60])

    # ── HubSpot ──
    try:
        import httpx
        resp = httpx.get(
            "https://api.hubapi.com/crm/v3/objects/contacts?limit=1",
            headers={"Authorization": f"Bearer {settings.HUBSPOT_ACCESS_TOKEN}"},
        )
        results["HubSpot"] = ("✅", "Connected") if resp.status_code == 200 else ("❌", f"HTTP {resp.status_code}")
    except Exception as e:
        results["HubSpot"] = ("⚠️ ", "Not configured" if not settings.HUBSPOT_ACCESS_TOKEN else str(e)[:60])

    # ── Stripe ──
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        stripe.Balance.retrieve()
        results["Stripe"] = ("✅", "Connected")
    except Exception as e:
        results["Stripe"] = ("⚠️ ", "Not configured" if not settings.STRIPE_SECRET_KEY else str(e)[:60])

    # ── Print results ──
    print("\n" + "═" * 50)
    print("  AI Autopilot — Integration Status")
    print("═" * 50)
    for name, (icon, msg) in results.items():
        print(f"  {icon}  {name:<15} {msg}")
    print("═" * 50 + "\n")

    failures = [k for k, (icon, _) in results.items() if icon == "❌"]
    if failures:
        print(f"⚠️  {len(failures)} integration(s) failed. Check your .env configuration.\n")
        return 1
    return 0


if __name__ == "__main__":
    code = asyncio.run(check_all())
    sys.exit(code)
