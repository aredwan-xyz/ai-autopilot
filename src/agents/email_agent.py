"""
EmailAgent — Autonomous inbox triage, categorization, and response drafting.

Capabilities:
  - Fetch unread emails from Gmail
  - Categorize by intent (lead, support, invoice, spam, partnership, etc.)
  - Draft and optionally send replies using LLM
  - Escalate urgent/sensitive emails to Slack
  - Archive/label processed emails
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.agents.base_agent import AgentRun, BaseAgent
from src.integrations.gmail import GmailClient
from src.integrations.slack import SlackClient
from src.utils.llm import LLMClient


class EmailCategory(str, Enum):
    LEAD = "lead"
    SUPPORT = "support"
    INVOICE = "invoice"
    PARTNERSHIP = "partnership"
    NEWSLETTER = "newsletter"
    SPAM = "spam"
    INTERNAL = "internal"
    URGENT = "urgent"
    OTHER = "other"


@dataclass
class ProcessedEmail:
    message_id: str
    sender: str
    subject: str
    snippet: str
    category: EmailCategory
    priority: int  # 1 (highest) to 5 (lowest)
    sentiment: str  # positive | neutral | negative
    draft_reply: str | None
    action_taken: str  # replied | escalated | archived | labelled
    escalate: bool = False


TRIAGE_SYSTEM_PROMPT = """
You are an expert email triage assistant for a B2B AI services company.
Analyze emails and return structured JSON with this exact schema:
{
  "category": one of [lead, support, invoice, partnership, newsletter, spam, internal, urgent, other],
  "priority": integer 1-5 (1=highest urgency),
  "sentiment": one of [positive, neutral, negative],
  "escalate": boolean (true if needs immediate human attention),
  "summary": "one-sentence summary of the email",
  "draft_reply": "complete professional reply or null if no reply needed"
}
Only return valid JSON. No preamble or explanation.
"""


class EmailAgent(BaseAgent):
    name = "email_agent"
    description = (
        "Triages inbound emails, categorizes them, drafts replies, "
        "and escalates urgent messages to the team via Slack."
    )

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.gmail = GmailClient()
        self.slack = SlackClient()
        self.max_emails = self.cfg("max_emails_per_run", 50)
        self.auto_reply = self.cfg("auto_reply", True)
        self.escalation_threshold = self.cfg("escalation_threshold", 0.7)
        self.escalation_channel = self.cfg("escalation_channel", "#autopilot-alerts")

    async def validate(self) -> bool:
        """Ensure Gmail credentials are available."""
        try:
            return await self.gmail.health_check()
        except Exception as e:
            self.log.error("gmail_auth_failed", error=str(e))
            return False

    async def run(self, run: AgentRun) -> AgentRun:
        # 1. Fetch unread emails
        emails = await self.gmail.fetch_unread(limit=self.max_emails)
        run.items_processed = len(emails)
        self.log.info("emails_fetched", count=len(emails))

        processed: list[ProcessedEmail] = []

        for email in emails:
            try:
                result = await self._process_email(email)
                processed.append(result)
                if result.action_taken != "skipped":
                    run.items_actioned += 1
            except Exception as e:
                run.errors.append(f"Failed to process {email.get('id')}: {e}")

        # 2. Summarise results
        categories = {}
        escalations = []
        for p in processed:
            categories[p.category.value] = categories.get(p.category.value, 0) + 1
            if p.escalate:
                escalations.append(p)

        # 3. Send escalation bundle to Slack
        if escalations and not self.dry_run:
            await self._send_escalation_digest(escalations)

        run.output = {
            "total_processed": len(processed),
            "categories": categories,
            "escalations": len(escalations),
            "auto_replies_sent": sum(1 for p in processed if p.action_taken == "replied"),
        }

        return run

    async def _process_email(self, email: dict[str, Any]) -> ProcessedEmail:
        """Triage a single email using LLM classification."""
        message_id = email["id"]
        sender = email.get("from", "unknown")
        subject = email.get("subject", "(no subject)")
        body = email.get("body_text", "")[:3000]  # truncate for token efficiency

        # Build triage prompt
        prompt = (
            f"FROM: {sender}\n"
            f"SUBJECT: {subject}\n"
            f"BODY:\n{body}\n\n"
            "Analyse this email and return the JSON triage object."
        )

        raw = await self.think(prompt=prompt, system=TRIAGE_SYSTEM_PROMPT, max_tokens=800)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: treat as uncategorised
            data = {
                "category": "other",
                "priority": 3,
                "sentiment": "neutral",
                "escalate": False,
                "draft_reply": None,
            }

        category = EmailCategory(data.get("category", "other"))
        priority = int(data.get("priority", 3))
        escalate = bool(data.get("escalate", False))
        draft_reply = data.get("draft_reply")
        action_taken = "labelled"

        # Skip newsletters and spam
        if category in (EmailCategory.NEWSLETTER, EmailCategory.SPAM):
            if not self.dry_run:
                await self.gmail.archive(message_id)
            return ProcessedEmail(
                message_id=message_id,
                sender=sender,
                subject=subject,
                snippet=body[:120],
                category=category,
                priority=priority,
                sentiment=data.get("sentiment", "neutral"),
                draft_reply=None,
                action_taken="archived",
                escalate=False,
            )

        # Send reply if appropriate
        if draft_reply and self.auto_reply and not escalate:
            if not self.dry_run:
                await self.gmail.send_reply(
                    thread_id=email.get("threadId", message_id),
                    to=sender,
                    body=draft_reply,
                )
            action_taken = "replied"

        # Apply label
        if not self.dry_run:
            await self.gmail.apply_label(message_id, f"autopilot/{category.value}")

        if escalate:
            action_taken = "escalated"

        return ProcessedEmail(
            message_id=message_id,
            sender=sender,
            subject=subject,
            snippet=body[:120],
            category=category,
            priority=priority,
            sentiment=data.get("sentiment", "neutral"),
            draft_reply=draft_reply,
            action_taken=action_taken,
            escalate=escalate,
        )

    async def _send_escalation_digest(self, escalations: list[ProcessedEmail]) -> None:
        """Bundle urgent emails into a single Slack alert."""
        lines = [f"🚨 *Email Escalations ({len(escalations)} urgent)*\n"]
        for e in escalations[:10]:
            lines.append(
                f"• *[{e.category.value.upper()}]* P{e.priority} — "
                f"_{e.subject}_ from `{e.sender}`"
            )
        await self.slack.post_message(
            channel=self.escalation_channel,
            text="\n".join(lines),
        )
