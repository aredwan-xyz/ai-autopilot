"""
SupportAgent — Tier-1 support ticket handling and intelligent escalation.

Capabilities:
  - Ingest support tickets from email/form/Slack
  - Classify by type, urgency, and sentiment
  - Generate accurate first-response drafts
  - Escalate complex or angry tickets to humans
  - Track resolution status in Notion
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from src.agents.base_agent import AgentRun, BaseAgent
from src.integrations.notion import NotionClient
from src.integrations.slack import SlackClient


class TicketType(str, Enum):
    BUG = "bug"
    BILLING = "billing"
    ONBOARDING = "onboarding"
    FEATURE_REQUEST = "feature_request"
    ACCESS = "access"
    GENERAL = "general"
    COMPLAINT = "complaint"


class TicketUrgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SupportTicket:
    id: str
    sender: str
    subject: str
    body: str
    ticket_type: TicketType = TicketType.GENERAL
    urgency: TicketUrgency = TicketUrgency.MEDIUM
    sentiment_score: float = 0.0   # -1 (very negative) to 1 (very positive)
    escalate: bool = False
    draft_response: str = ""
    action_taken: str = ""
    confidence: float = 0.0


SUPPORT_TRIAGE_PROMPT = """
You are a support specialist for an AI services company. Analyse this support ticket
and return a JSON triage object:
{
  "ticket_type": one of [bug, billing, onboarding, feature_request, access, general, complaint],
  "urgency": one of [low, medium, high, critical],
  "sentiment_score": float -1 to 1,
  "escalate": boolean (true if: angry customer, legal threat, data loss, production down),
  "confidence": float 0-1 (how confident you are in your response),
  "draft_response": "complete, empathetic support response. Address their issue directly.",
  "internal_note": "1-sentence note for the human support team if escalated"
}
Return only valid JSON.
"""


class SupportAgent(BaseAgent):
    name = "support_agent"
    description = (
        "Handles tier-1 support tickets automatically, drafts responses, "
        "and escalates complex cases to humans via Slack."
    )

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.notion = NotionClient()
        self.slack = SlackClient()
        self.auto_respond = self.cfg("auto_respond", True)
        self.escalation_threshold = self.cfg("escalation_threshold", 0.6)

    async def run(self, run: AgentRun) -> AgentRun:
        # Fetch unresolved tickets (placeholder — in production pulls from email/Intercom/Zendesk)
        tickets = await self._fetch_tickets()
        run.items_processed = len(tickets)

        escalations = []

        for ticket in tickets:
            ticket = await self._triage(ticket)

            if ticket.escalate:
                escalations.append(ticket)
                ticket.action_taken = "escalated"
            elif self.auto_respond and ticket.confidence >= self.escalation_threshold:
                if not self.dry_run:
                    await self._send_response(ticket)
                ticket.action_taken = "responded"
                run.items_actioned += 1
            else:
                ticket.action_taken = "queued_for_review"

            if not self.dry_run:
                await self._log_to_notion(ticket)

        if escalations and not self.dry_run:
            await self._send_escalation_bundle(escalations)

        run.output = {
            "total": len(tickets),
            "auto_responded": sum(1 for t in tickets if t.action_taken == "responded"),
            "escalated": len(escalations),
            "queued": sum(1 for t in tickets if t.action_taken == "queued_for_review"),
        }

        return run

    async def _fetch_tickets(self) -> list[SupportTicket]:
        """Fetch open support tickets. In production: pull from email/helpdesk."""
        # Demo tickets for dry-run
        if self.dry_run:
            return [
                SupportTicket(
                    id="tkt_001",
                    sender="client@company.com",
                    subject="Can't access the dashboard",
                    body="Hi, I've been trying to log in since this morning but keep getting a 403 error. This is urgent, I have a presentation in 2 hours.",
                ),
                SupportTicket(
                    id="tkt_002",
                    sender="billing@acme.com",
                    subject="Invoice discrepancy",
                    body="I noticed I was charged twice for March. Invoice #1042 and #1043 both show the same services. Please refund the duplicate.",
                ),
            ]
        return []

    async def _triage(self, ticket: SupportTicket) -> SupportTicket:
        prompt = (
            f"FROM: {ticket.sender}\n"
            f"SUBJECT: {ticket.subject}\n"
            f"BODY:\n{ticket.body}\n\n"
            "Triage this support ticket."
        )

        raw = await self.think(prompt=prompt, system=SUPPORT_TRIAGE_PROMPT, max_tokens=600)

        try:
            data = json.loads(raw)
            ticket.ticket_type = TicketType(data.get("ticket_type", "general"))
            ticket.urgency = TicketUrgency(data.get("urgency", "medium"))
            ticket.sentiment_score = float(data.get("sentiment_score", 0))
            ticket.escalate = bool(data.get("escalate", False))
            ticket.confidence = float(data.get("confidence", 0.5))
            ticket.draft_response = data.get("draft_response", "")
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.log.warning("support_triage_parse_error", id=ticket.id, error=str(e))

        self.log.info(
            "ticket_triaged",
            id=ticket.id,
            type=ticket.ticket_type.value,
            urgency=ticket.urgency.value,
            escalate=ticket.escalate,
        )
        return ticket

    async def _send_response(self, ticket: SupportTicket) -> None:
        self.log.info("support_response_sent", id=ticket.id, to=ticket.sender)

    async def _log_to_notion(self, ticket: SupportTicket) -> None:
        self.log.info("ticket_logged_notion", id=ticket.id)

    async def _send_escalation_bundle(self, tickets: list[SupportTicket]) -> None:
        lines = [f"🎫 *Support Escalations ({len(tickets)} tickets)*\n"]
        for t in tickets:
            urgency_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            lines.append(
                f"{urgency_emoji.get(t.urgency.value, '⚪')} *[{t.ticket_type.value.upper()}]* "
                f"_{t.subject}_ from `{t.sender}`"
            )
        await self.slack.post_message(channel="#support-escalations", text="\n".join(lines))
