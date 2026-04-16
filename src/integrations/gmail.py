"""
Gmail Integration — Google Gmail API client.
"""

from __future__ import annotations

import base64
import email
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger("gmail")


class GmailClient:
    """Async-compatible Gmail API wrapper."""

    def __init__(self):
        self.log = logger
        self._service = None

    def _get_service(self):
        """Lazy-load the Gmail API service."""
        if self._service:
            return self._service

        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from src.config.settings import settings

        creds_path = Path(settings.GOOGLE_CREDENTIALS_FILE)
        if creds_path.exists():
            creds = Credentials.from_authorized_user_file(str(creds_path))
        else:
            raise RuntimeError(
                f"Google credentials not found at {creds_path}. "
                "Run `python scripts/setup_gmail.py` to authenticate."
            )

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    async def health_check(self) -> bool:
        try:
            svc = self._get_service()
            svc.users().getProfile(userId="me").execute()
            return True
        except Exception as e:
            self.log.error("gmail_health_check_failed", error=str(e))
            return False

    async def fetch_unread(self, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch unread emails from inbox."""
        svc = self._get_service()

        results = svc.users().messages().list(
            userId="me",
            q="is:unread in:inbox",
            maxResults=limit,
        ).execute()

        messages = results.get("messages", [])
        full_messages = []

        for msg_stub in messages:
            try:
                msg = svc.users().messages().get(
                    userId="me",
                    id=msg_stub["id"],
                    format="full",
                ).execute()
                full_messages.append(self._parse_message(msg))
            except Exception as e:
                self.log.warning("message_fetch_failed", id=msg_stub["id"], error=str(e))

        return full_messages

    def _parse_message(self, msg: dict) -> dict[str, Any]:
        """Extract useful fields from a raw Gmail message."""
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        # Extract body text
        body = self._extract_body(msg.get("payload", {}))

        return {
            "id": msg["id"],
            "threadId": msg.get("threadId", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", "(no subject)"),
            "date": headers.get("date", ""),
            "body_text": body,
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: dict, depth: int = 0) -> str:
        """Recursively extract text body from MIME parts."""
        if depth > 5:
            return ""

        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data", "")

        if body_data and mime_type == "text/plain":
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            result = self._extract_body(part, depth + 1)
            if result:
                return result

        return ""

    async def send_reply(self, thread_id: str, to: str, body: str) -> None:
        """Send a reply to a Gmail thread."""
        svc = self._get_service()
        message = MIMEText(body)
        message["to"] = to
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        svc.users().messages().send(
            userId="me",
            body={"raw": raw, "threadId": thread_id},
        ).execute()

    async def apply_label(self, message_id: str, label_name: str) -> None:
        """Apply a label to an email (creates label if it doesn't exist)."""
        svc = self._get_service()
        try:
            label_id = self._get_or_create_label(svc, label_name)
            svc.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id], "removeLabelIds": ["UNREAD"]},
            ).execute()
        except Exception as e:
            self.log.warning("label_apply_failed", message_id=message_id, error=str(e))

    async def archive(self, message_id: str) -> None:
        """Remove from inbox (archive)."""
        svc = self._get_service()
        svc.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["INBOX", "UNREAD"]},
        ).execute()

    def _get_or_create_label(self, svc, name: str) -> str:
        """Get label ID, creating it if needed."""
        labels = svc.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label["name"].lower() == name.lower():
                return label["id"]

        new_label = svc.users().labels().create(
            userId="me",
            body={"name": name, "labelListVisibility": "labelShow"},
        ).execute()
        return new_label["id"]
