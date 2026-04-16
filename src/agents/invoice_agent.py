"""
InvoiceAgent — Monitor overdue invoices and send automated follow-ups.

Capabilities:
  - Pull open invoices from Stripe
  - Categorize by overdue severity (due soon / overdue / critical)
  - Generate personalised follow-up emails via LLM
  - Send follow-ups (or queue for review)
  - Alert on critical accounts via Slack
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from src.agents.base_agent import AgentRun, BaseAgent
from src.integrations.slack import SlackClient
from src.integrations.stripe import StripeClient


class InvoiceStatus(str, Enum):
    DUE_SOON = "due_soon"       # Due in < 3 days
    OVERDUE = "overdue"         # 1–14 days past due
    CRITICAL = "critical"       # 14+ days past due or high value


@dataclass
class Invoice:
    id: str
    client_name: str
    client_email: str
    amount: float
    currency: str
    due_date: datetime
    days_overdue: int
    status: InvoiceStatus
    follow_up_draft: str = ""
    action_taken: str = ""


FOLLOWUP_PROMPT = """
You are a professional accounts receivable specialist writing a polite but firm invoice follow-up.

Guidelines:
- Warm but direct tone — assume it's an oversight, not malice
- Reference the specific invoice amount and due date
- For first follow-up (1-7 days): gentle reminder
- For second follow-up (8-14 days): firmer, mention potential disruption to services
- For critical (14+ days): urgent, request immediate response or payment plan
- Always end with a clear CTA: payment link or reply to arrange payment
- Keep it under 120 words
- No subject line, just the email body

Return only the email body text.
"""


class InvoiceAgent(BaseAgent):
    name = "invoice_agent"
    description = (
        "Monitors overdue invoices via Stripe, generates personalised follow-up emails, "
        "and escalates critical accounts to Slack."
    )

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.stripe = StripeClient()
        self.slack = SlackClient()
        self.overdue_days = self.cfg("overdue_days", 14)
        self.critical_amount = self.cfg("critical_amount", 5000)

    async def run(self, run: AgentRun) -> AgentRun:
        # 1. Fetch open invoices from Stripe
        open_invoices = await self._fetch_open_invoices()
        run.items_processed = len(open_invoices)
        self.log.info("open_invoices_fetched", count=len(open_invoices))

        critical = []
        actioned = []

        for inv in open_invoices:
            inv = await self._generate_followup(inv)

            if inv.status == InvoiceStatus.CRITICAL:
                critical.append(inv)

            if not self.dry_run and inv.days_overdue > 0:
                # In production: send email via SendGrid / Gmail
                self.log.info(
                    "followup_queued",
                    invoice_id=inv.id,
                    client=inv.client_name,
                    days_overdue=inv.days_overdue,
                    amount=inv.amount,
                )
                inv.action_taken = "follow_up_sent"
                actioned.append(inv)
                run.items_actioned += 1

        # 2. Alert critical accounts in Slack
        if critical and not self.dry_run:
            await self._send_critical_alert(critical)

        run.output = {
            "open_invoices": len(open_invoices),
            "actioned": len(actioned),
            "critical": len(critical),
            "total_outstanding": sum(i.amount for i in open_invoices),
            "critical_value": sum(i.amount for i in critical),
        }

        return run

    async def _fetch_open_invoices(self) -> list[Invoice]:
        """Pull open invoices and classify by overdue status."""
        now = datetime.utcnow()
        invoices = []

        try:
            import stripe as stripe_lib
            stripe_lib.api_key = self.cfg("stripe_key", "")

            raw = stripe_lib.Invoice.list(status="open", limit=100)
            for r in raw.data:
                due_date = datetime.fromtimestamp(r.due_date) if r.due_date else now
                days_overdue = max(0, (now - due_date).days)
                amount = r.amount_due / 100

                if days_overdue == 0 and (due_date - now).days <= 3:
                    status = InvoiceStatus.DUE_SOON
                elif days_overdue >= self.overdue_days or amount >= self.critical_amount:
                    status = InvoiceStatus.CRITICAL
                elif days_overdue > 0:
                    status = InvoiceStatus.OVERDUE
                else:
                    continue  # Not yet due, skip

                invoices.append(Invoice(
                    id=r.id,
                    client_name=r.customer_name or "Client",
                    client_email=r.customer_email or "",
                    amount=amount,
                    currency=r.currency.upper(),
                    due_date=due_date,
                    days_overdue=days_overdue,
                    status=status,
                ))
        except Exception as e:
            self.log.warning("stripe_invoice_fetch_failed", error=str(e))
            # Return sample data for dry-run/demo
            if self.dry_run:
                invoices = self._demo_invoices(now)

        return invoices

    def _demo_invoices(self, now: datetime) -> list[Invoice]:
        return [
            Invoice(
                id="inv_demo_001",
                client_name="Acme Corp",
                client_email="billing@acme.com",
                amount=3500.00,
                currency="USD",
                due_date=now - timedelta(days=5),
                days_overdue=5,
                status=InvoiceStatus.OVERDUE,
            ),
            Invoice(
                id="inv_demo_002",
                client_name="TechFlow Inc",
                client_email="accounts@techflow.io",
                amount=8200.00,
                currency="USD",
                due_date=now - timedelta(days=18),
                days_overdue=18,
                status=InvoiceStatus.CRITICAL,
            ),
        ]

    async def _generate_followup(self, inv: Invoice) -> Invoice:
        """Draft a personalised follow-up email for the invoice."""
        urgency = {
            InvoiceStatus.DUE_SOON: "gentle reminder, due in 1-3 days",
            InvoiceStatus.OVERDUE: f"first follow-up, {inv.days_overdue} days overdue",
            InvoiceStatus.CRITICAL: f"urgent follow-up, {inv.days_overdue} days overdue — critical",
        }[inv.status]

        prompt = (
            f"Client: {inv.client_name}\n"
            f"Amount: {inv.currency} {inv.amount:,.2f}\n"
            f"Due Date: {inv.due_date.strftime('%B %d, %Y')}\n"
            f"Situation: {urgency}\n\n"
            "Write the follow-up email body."
        )

        inv.follow_up_draft = await self.think(
            prompt=prompt,
            system=FOLLOWUP_PROMPT,
            max_tokens=300,
        )
        return inv

    async def _send_critical_alert(self, critical: list[Invoice]) -> None:
        """Notify team of critical overdue invoices via Slack."""
        total = sum(i.amount for i in critical)
        lines = [f"🔴 *Critical Invoice Alert — ${total:,.0f} at risk*\n"]
        for inv in critical:
            lines.append(
                f"• *{inv.client_name}* — ${inv.amount:,.0f} {inv.currency} "
                f"| {inv.days_overdue} days overdue | `{inv.id}`"
            )
        await self.slack.post_message(channel="#autopilot-alerts", text="\n".join(lines))
