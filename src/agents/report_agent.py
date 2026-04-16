"""
ReportAgent — Automated KPI aggregation and PDF report generation.

Capabilities:
  - Pull metrics from HubSpot, Stripe, Airtable, and manual sources
  - Generate narrative summaries of business performance
  - Produce branded PDF reports
  - Email and Slack delivery to stakeholders
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from src.agents.base_agent import AgentRun, BaseAgent
from src.integrations.hubspot import HubSpotClient
from src.integrations.slack import SlackClient
from src.integrations.stripe import StripeClient
from src.utils.pdf_generator import PDFGenerator


@dataclass
class BusinessMetrics:
    period_start: datetime
    period_end: datetime
    # Revenue
    mrr: float = 0.0
    new_revenue: float = 0.0
    collected_revenue: float = 0.0
    outstanding_invoices: float = 0.0
    # Sales
    new_leads: int = 0
    qualified_leads: int = 0
    proposals_sent: int = 0
    deals_closed: int = 0
    pipeline_value: float = 0.0
    # Operations
    emails_processed: int = 0
    content_published: int = 0
    support_tickets: int = 0
    avg_response_time_h: float = 0.0
    # Growth
    lead_to_close_rate: float = 0.0
    avg_deal_size: float = 0.0
    notes: list[str] = field(default_factory=list)


NARRATIVE_PROMPT = """
You are a business analyst writing the executive summary for a weekly business report.

Write a 3-paragraph narrative based on the metrics provided:
1. Overall performance summary (positive framing with honest assessment)
2. Top wins and concerning trends to watch
3. Recommended focus areas for next week

Be specific. Reference numbers from the data. Keep it under 250 words total.
Write in second person ("Your business showed...").
"""


class ReportAgent(BaseAgent):
    name = "report_agent"
    description = (
        "Aggregates KPIs from all connected systems, generates an executive narrative, "
        "and delivers a PDF report via email and Slack."
    )

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.hubspot = HubSpotClient()
        self.stripe = StripeClient()
        self.slack = SlackClient()
        self.pdf_gen = PDFGenerator()
        self.output_dir = Path(self.cfg("output_dir", "./reports"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.recipients = self.cfg("recipients", [])

    async def run(self, run: AgentRun) -> AgentRun:
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=7)

        self.log.info("report_generation_start", period=f"{period_start.date()} → {period_end.date()}")

        # 1. Aggregate metrics
        metrics = await self._gather_metrics(period_start, period_end)

        # 2. Generate narrative
        narrative = await self._generate_narrative(metrics)

        # 3. Build PDF
        report_path = await self._build_pdf(metrics, narrative, period_start, period_end)

        # 4. Deliver
        if not self.dry_run:
            await self._deliver_report(report_path, metrics, narrative)

        run.items_processed = 1
        run.items_actioned = 1
        run.output = {
            "report_file": str(report_path),
            "period": f"{period_start.date()} to {period_end.date()}",
            "mrr": metrics.mrr,
            "new_revenue": metrics.new_revenue,
            "new_leads": metrics.new_leads,
            "deals_closed": metrics.deals_closed,
        }

        return run

    async def _gather_metrics(
        self, period_start: datetime, period_end: datetime
    ) -> BusinessMetrics:
        """Pull metrics from all integrations."""
        metrics = BusinessMetrics(period_start=period_start, period_end=period_end)

        # Revenue from Stripe
        try:
            stripe_data = await self.stripe.get_period_revenue(period_start, period_end)
            metrics.mrr = stripe_data.get("mrr", 0)
            metrics.new_revenue = stripe_data.get("new_revenue", 0)
            metrics.collected_revenue = stripe_data.get("collected", 0)
            metrics.outstanding_invoices = stripe_data.get("outstanding", 0)
        except Exception as e:
            self.log.warning("stripe_metrics_failed", error=str(e))
            metrics.notes.append("⚠️ Stripe data unavailable this period")

        # Sales pipeline from HubSpot
        try:
            hs_data = await self.hubspot.get_pipeline_metrics(period_start, period_end)
            metrics.new_leads = hs_data.get("new_leads", 0)
            metrics.qualified_leads = hs_data.get("qualified", 0)
            metrics.proposals_sent = hs_data.get("proposals", 0)
            metrics.deals_closed = hs_data.get("closed_won", 0)
            metrics.pipeline_value = hs_data.get("pipeline_value", 0)
            metrics.avg_deal_size = hs_data.get("avg_deal_size", 0)
        except Exception as e:
            self.log.warning("hubspot_metrics_failed", error=str(e))

        # Compute derived
        if metrics.new_leads > 0:
            metrics.lead_to_close_rate = metrics.deals_closed / metrics.new_leads * 100

        return metrics

    async def _generate_narrative(self, metrics: BusinessMetrics) -> str:
        """Use LLM to write the executive summary."""
        metrics_summary = (
            f"Period: {metrics.period_start.date()} to {metrics.period_end.date()}\n"
            f"MRR: ${metrics.mrr:,.0f}\n"
            f"New Revenue: ${metrics.new_revenue:,.0f}\n"
            f"Outstanding Invoices: ${metrics.outstanding_invoices:,.0f}\n"
            f"New Leads: {metrics.new_leads}\n"
            f"Qualified Leads: {metrics.qualified_leads}\n"
            f"Proposals Sent: {metrics.proposals_sent}\n"
            f"Deals Closed: {metrics.deals_closed}\n"
            f"Pipeline Value: ${metrics.pipeline_value:,.0f}\n"
            f"Lead-to-Close Rate: {metrics.lead_to_close_rate:.1f}%\n"
            f"Avg Deal Size: ${metrics.avg_deal_size:,.0f}\n"
            f"Content Published: {metrics.content_published}\n"
        )

        return await self.think(
            prompt=metrics_summary,
            system=NARRATIVE_PROMPT,
            max_tokens=400,
        )

    async def _build_pdf(
        self,
        metrics: BusinessMetrics,
        narrative: str,
        period_start: datetime,
        period_end: datetime,
    ) -> Path:
        """Generate the PDF report file."""
        filename = f"report_{period_start.strftime('%Y-%m-%d')}.pdf"
        output_path = self.output_dir / filename

        await self.pdf_gen.generate_business_report(
            output_path=output_path,
            metrics=metrics,
            narrative=narrative,
            period_start=period_start,
            period_end=period_end,
        )

        self.log.info("pdf_generated", path=str(output_path))
        return output_path

    async def _deliver_report(
        self, report_path: Path, metrics: BusinessMetrics, narrative: str
    ) -> None:
        """Deliver report via Slack (and optionally email)."""
        slack_summary = (
            f"📊 *Weekly Business Report Ready*\n"
            f"Period: {metrics.period_start.strftime('%b %d')} — {metrics.period_end.strftime('%b %d, %Y')}\n\n"
            f"*Revenue:* ${metrics.new_revenue:,.0f} new | ${metrics.mrr:,.0f} MRR\n"
            f"*Leads:* {metrics.new_leads} new | {metrics.deals_closed} closed\n"
            f"*Pipeline:* ${metrics.pipeline_value:,.0f}\n\n"
            f"_{narrative[:280].strip()}..._\n\n"
            f"Full PDF report attached ↑"
        )

        await self.slack.post_file(
            channel="#autopilot-reports",
            message=slack_summary,
            file_path=str(report_path),
            filename=report_path.name,
        )
