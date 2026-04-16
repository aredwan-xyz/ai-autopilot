"""Notion Integration"""
from __future__ import annotations
from datetime import datetime, date
from typing import Any
import httpx
import structlog
from src.config.settings import settings

logger = structlog.get_logger("notion")


class NotionClient:
    BASE_URL = "https://api.notion.com/v1"

    def __init__(self):
        self.api_key = settings.NOTION_API_KEY
        self.log = logger

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    async def get_todays_content(self) -> list[dict]:
        db_id = settings.NOTION_DATABASE_ID_CONTENT
        if not db_id:
            return []

        today = date.today().isoformat()
        payload = {
            "filter": {
                "and": [
                    {"property": "Scheduled Date", "date": {"equals": today}},
                    {"property": "Status", "select": {"equals": "Ready"}},
                ]
            }
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/databases/{db_id}/query",
                headers=self._headers(),
                json=payload,
            )
            if resp.status_code != 200:
                self.log.warning("notion_content_fetch_failed", status=resp.status_code)
                return []
            return resp.json().get("results", [])

    async def mark_content_published(self, page_id: str, publish_url: str) -> None:
        async with httpx.AsyncClient() as client:
            await client.patch(
                f"{self.BASE_URL}/pages/{page_id}",
                headers=self._headers(),
                json={
                    "properties": {
                        "Status": {"select": {"name": "Published"}},
                        "Publish URL": {"url": publish_url},
                    }
                },
            )

    async def create_lead_record(self, data: dict[str, Any]) -> dict:
        db_id = settings.NOTION_DATABASE_ID_LEADS
        if not db_id:
            return {}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/pages",
                headers=self._headers(),
                json={
                    "parent": {"database_id": db_id},
                    "properties": {
                        "Name": {"title": [{"text": {"content": data.get("name", "")}}]},
                        "Company": {"rich_text": [{"text": {"content": data.get("company", "")}}]},
                        "Email": {"email": data.get("email", "")},
                        "Score": {"number": data.get("lead_score", 0)},
                        "Status": {"select": {"name": "New"}},
                    },
                },
            )
            resp.raise_for_status()
            return resp.json()
