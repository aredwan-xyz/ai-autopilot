"""HubSpot CRM Integration"""
from __future__ import annotations
from datetime import datetime
from typing import Any
import httpx
import structlog
from src.config.settings import settings

logger = structlog.get_logger("hubspot")


class HubSpotClient:
    BASE_URL = "https://api.hubapi.com"

    def __init__(self):
        self.token = settings.HUBSPOT_ACCESS_TOKEN
        self.log = logger

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def create_contact(self, data: dict[str, Any]) -> dict:
        payload = {
            "properties": {
                "firstname": data.get("name", "").split()[0],
                "lastname": " ".join(data.get("name", "").split()[1:]),
                "email": data.get("email", ""),
                "company": data.get("company", ""),
                "jobtitle": data.get("role", ""),
                "hs_lead_status": "NEW",
                "lead_score": str(data.get("lead_score", 0)),
                "lead_source": data.get("source", "autopilot"),
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/crm/v3/objects/contacts",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pipeline_metrics(self, start: datetime, end: datetime) -> dict:
        # Simplified — real implementation would query HubSpot analytics APIs
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/crm/v3/objects/contacts",
                headers=self._headers(),
                params={"limit": 100, "properties": "hs_lead_status,createdate"},
            )
            if resp.status_code != 200:
                return {}
            contacts = resp.json().get("results", [])
            return {
                "new_leads": len(contacts),
                "qualified": sum(1 for c in contacts if c.get("properties", {}).get("hs_lead_status") == "QUALIFIED"),
                "proposals": 0,
                "closed_won": 0,
                "pipeline_value": 0,
                "avg_deal_size": 0,
            }
