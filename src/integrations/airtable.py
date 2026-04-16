"""Airtable Integration"""
from __future__ import annotations
from typing import Any
import httpx
import structlog
from src.config.settings import settings

logger = structlog.get_logger("airtable")


class AirtableClient:
    BASE_URL = "https://api.airtable.com/v0"

    def __init__(self):
        self.api_key = settings.AIRTABLE_API_KEY
        self.base_id = settings.AIRTABLE_BASE_ID
        self.log = logger

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def get_unprocessed_leads(self, table: str = "Leads") -> list[dict]:
        if not self.api_key or not self.base_id:
            self.log.warning("airtable_not_configured")
            return []
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/{self.base_id}/{table}",
                headers=self._headers(),
                params={"filterByFormula": "NOT({Processed})", "maxRecords": 100},
            )
            if resp.status_code != 200:
                self.log.error("airtable_fetch_failed", status=resp.status_code)
                return []
            records = resp.json().get("records", [])
            return [{"id": r["id"], **r.get("fields", {})} for r in records]

    async def mark_processed(self, record_id: str, score: int, qualified: bool) -> None:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{self.BASE_URL}/{self.base_id}/Leads/{record_id}",
                headers=self._headers(),
                json={"fields": {"Processed": True, "Score": score, "Qualified": qualified}},
            )

    async def create_qualified_lead(self, data: dict[str, Any]) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/{self.base_id}/Qualified Leads",
                headers=self._headers(),
                json={"fields": data},
            )
            resp.raise_for_status()
            return resp.json()
