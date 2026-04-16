"""
LeadAgent — Autonomous lead scoring, enrichment, and CRM routing.

Capabilities:
  - Pull new leads from Airtable intake form or webhook queue
  - Score leads (0-100) based on ICP fit criteria
  - Enrich lead data via web research
  - Route qualified leads to HubSpot/Notion CRM
  - Send intro personalised outreach draft to Slack for review
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.agents.base_agent import AgentRun, BaseAgent
from src.integrations.airtable import AirtableClient
from src.integrations.hubspot import HubSpotClient
from src.integrations.notion import NotionClient
from src.integrations.slack import SlackClient


@dataclass
class Lead:
    id: str
    name: str
    company: str
    email: str
    role: str = ""
    industry: str = ""
    company_size: str = ""
    source: str = ""
    notes: str = ""
    score: int = 0
    score_breakdown: dict = field(default_factory=dict)
    enrichment: dict = field(default_factory=dict)
    outreach_draft: str = ""
    qualified: bool = False


ICP_SCORING_PROMPT = """
You are a B2B lead qualification specialist for an AI services agency.

Our Ideal Customer Profile (ICP):
- Company size: 10-500 employees
- Industry: Professional services, SaaS, e-commerce, healthcare, finance
- Role: Founder, CEO, CTO, COO, VP Operations, Head of Growth
- Pain: Wants to automate operations, scale without hiring, reduce manual workflows
- Geography: USA, UK, Canada, Australia
- Budget signal: Funded startup or established SMB

Score this lead from 0-100 and return JSON:
{
  "score": integer 0-100,
  "breakdown": {
    "role_fit": 0-25,
    "industry_fit": 0-20,
    "company_size_fit": 0-20,
    "geography_fit": 0-15,
    "intent_signals": 0-20
  },
  "qualified": boolean (score >= 65),
  "reasoning": "2-sentence explanation",
  "outreach_angle": "personalised opening line for cold outreach"
}
Return only valid JSON.
"""


class LeadAgent(BaseAgent):
    name = "lead_agent"
    description = (
        "Scores inbound leads against ICP criteria, enriches their profiles, "
        "and routes qualified leads to the CRM with a personalised outreach draft."
    )

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.airtable = AirtableClient()
        self.hubspot = HubSpotClient()
        self.notion = NotionClient()
        self.slack = SlackClient()
        self.min_score = self.cfg("min_score_to_route", 65)
        self.crm_target = self.cfg("crm_target", "hubspot")

    async def run(self, run: AgentRun) -> AgentRun:
        # 1. Pull unprocessed leads from Airtable
        raw_leads = await self.airtable.get_unprocessed_leads()
        run.items_processed = len(raw_leads)
        self.log.info("leads_fetched", count=len(raw_leads))

        qualified_leads: list[Lead] = []

        for raw in raw_leads:
            lead = Lead(
                id=raw["id"],
                name=raw.get("Name", ""),
                company=raw.get("Company", ""),
                email=raw.get("Email", ""),
                role=raw.get("Role", ""),
                industry=raw.get("Industry", ""),
                company_size=raw.get("Company Size", ""),
                source=raw.get("Source", ""),
                notes=raw.get("Notes", ""),
            )

            # 2. Score the lead
            lead = await self._score_lead(lead)

            # 3. Route if qualified
            if lead.qualified:
                qualified_leads.append(lead)
                await self._route_to_crm(lead)
                run.items_actioned += 1

            # 4. Mark as processed in Airtable
            if not self.dry_run:
                await self.airtable.mark_processed(
                    lead.id,
                    score=lead.score,
                    qualified=lead.qualified,
                )

        # 5. Post qualified leads digest to Slack
        if qualified_leads and not self.dry_run:
            await self._post_qualified_digest(qualified_leads)

        run.output = {
            "total_leads": len(raw_leads),
            "qualified": len(qualified_leads),
            "avg_score": (
                sum(l.score for l in [Lead(id="", name="", company="", email="")] + qualified_leads)
                / max(len(raw_leads), 1)
            ),
            "routed_to": self.crm_target,
        }

        return run

    async def _score_lead(self, lead: Lead) -> Lead:
        """Score a lead against ICP using LLM."""
        prompt = (
            f"Name: {lead.name}\n"
            f"Company: {lead.company}\n"
            f"Role: {lead.role}\n"
            f"Industry: {lead.industry}\n"
            f"Company Size: {lead.company_size}\n"
            f"Source: {lead.source}\n"
            f"Notes: {lead.notes}\n\n"
            "Score this lead."
        )

        raw = await self.think(prompt=prompt, system=ICP_SCORING_PROMPT, max_tokens=512)

        try:
            data = json.loads(raw)
            lead.score = int(data.get("score", 0))
            lead.score_breakdown = data.get("breakdown", {})
            lead.qualified = bool(data.get("qualified", False)) and lead.score >= self.min_score
            lead.outreach_draft = data.get("outreach_angle", "")
        except (json.JSONDecodeError, ValueError) as e:
            self.log.warning("lead_scoring_parse_error", lead_id=lead.id, error=str(e))
            lead.score = 0
            lead.qualified = False

        self.log.info(
            "lead_scored",
            lead=lead.name,
            company=lead.company,
            score=lead.score,
            qualified=lead.qualified,
        )
        return lead

    async def _route_to_crm(self, lead: Lead) -> None:
        """Push a qualified lead to the configured CRM."""
        if self.dry_run:
            self.log.info("dry_run_crm_skip", lead=lead.name, target=self.crm_target)
            return

        payload = {
            "name": lead.name,
            "email": lead.email,
            "company": lead.company,
            "role": lead.role,
            "lead_score": lead.score,
            "source": lead.source,
            "outreach_draft": lead.outreach_draft,
        }

        if self.crm_target == "hubspot":
            await self.hubspot.create_contact(payload)
        elif self.crm_target == "notion":
            await self.notion.create_lead_record(payload)
        elif self.crm_target == "airtable":
            await self.airtable.create_qualified_lead(payload)

    async def _post_qualified_digest(self, leads: list[Lead]) -> None:
        """Post a digest of new qualified leads to Slack."""
        lines = [f"🎯 *{len(leads)} New Qualified Lead(s) Routed to {self.crm_target.title()}*\n"]
        for lead in leads[:8]:
            lines.append(
                f"• *{lead.name}* @ {lead.company} ({lead.role}) — "
                f"Score: *{lead.score}/100*\n"
                f"  _{lead.outreach_draft}_"
            )
        await self.slack.post_message(channel="#autopilot-leads", text="\n".join(lines))
