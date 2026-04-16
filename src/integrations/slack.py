"""
Slack Integration
"""
from __future__ import annotations
from pathlib import Path
import structlog
from src.config.settings import settings

logger = structlog.get_logger("slack")


class SlackClient:
    def __init__(self):
        self.token = settings.SLACK_BOT_TOKEN
        self.log = logger
        self._client = None

    def _get_client(self):
        if self._client:
            return self._client
        from slack_sdk.web.async_client import AsyncWebClient
        self._client = AsyncWebClient(token=self.token)
        return self._client

    async def post_message(self, channel: str, text: str) -> None:
        if not self.token:
            self.log.warning("slack_token_missing")
            return
        client = self._get_client()
        await client.chat_postMessage(channel=channel, text=text)

    async def post_file(self, channel: str, message: str, file_path: str, filename: str) -> None:
        if not self.token:
            return
        client = self._get_client()
        with open(file_path, "rb") as f:
            await client.files_upload_v2(
                channel=channel,
                initial_comment=message,
                filename=filename,
                content=f.read(),
            )
