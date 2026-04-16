"""
Lead Pipeline Workflow — Multi-step orchestration from raw lead to booked call.

Steps:
  1. Intake → Validate lead data
  2. Enrich → Research company + person
  3. Score → ICP fit scoring
  4. Route → Push to CRM
  5. Outreach → Draft and queue personalised email
  6. Notify → Alert sales team on Slack
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

from src.agents.lead_agent import Lead, LeadAgent
from src.integrations.slack import SlackClient
from src.utils.llm import LLMClient

logger = structlog.get_logger("lead_pipeline")


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PipelineStep:
    name: str
    status: StepStatus = StepStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: Any = None
    error: str | None = None


@dataclass
class PipelineRun:
    lead_id: str
    steps: list[PipelineStep] = field(default_factory=list)
    lead: Lead | None = None
    completed: bool = False
    failed: bool = False


ENRICHMENT_PROMPT = """
You are a B2B researcher. Given a company name and person's role,
produce a JSON enrichment object:
{
  "company_description": "1-sentence description of what the company does",
  "company_stage": "startup | smb | mid-market | enterprise",
  "likely_pain_points": ["pain 1", "pain 2"],
  "relevant_ai_use_cases": ["use case 1", "use case 2"],
  "conversation_starter": "one specific, personalised conversation opener"
}
Return only valid JSON.
"""


class LeadPipeline:
    """
    Orchestrates the full lead journey from raw intake to qualified outreach.
    Designed to run as a triggered workflow (not on a schedule).
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.llm = LLMClient()
        self.slack = SlackClient()
        self.lead_agent = LeadAgent(dry_run=dry_run)
        self.log = logger

    async def run(self, raw_lead: dict[str, Any]) -> PipelineRun:
        """Execute the full pipeline for a single lead."""
        pipeline = PipelineRun(lead_id=raw_lead.get("id", "unknown"))

        steps = [
            ("validate", self._validate),
            ("enrich", self._enrich),
            ("score", self._score),
            ("route", self._route),
            ("notify", self._notify),
        ]

        for step_name, step_fn in steps:
            step = PipelineStep(name=step_name)
            pipeline.steps.append(step)

            step.status = StepStatus.RUNNING
            step.started_at = datetime.utcnow()

            try:
                result = await step_fn(pipeline, raw_lead)
                step.output = result
                step.status = StepStatus.DONE
                self.log.info("pipeline_step_done", lead=pipeline.lead_id, step=step_name)
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)
                pipeline.failed = True
                self.log.error("pipeline_step_failed", step=step_name, error=str(e))
                break
            finally:
                step.finished_at = datetime.utcnow()

        pipeline.completed = not pipeline.failed
        return pipeline

    async def _validate(self, pipeline: PipelineRun, raw: dict) -> dict:
        required = ["name", "email", "company"]
        missing = [f for f in required if not raw.get(f)]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        pipeline.lead = Lead(
            id=raw.get("id", ""),
            name=raw["name"],
            company=raw["company"],
            email=raw["email"],
            role=raw.get("role", ""),
            industry=raw.get("industry", ""),
            company_size=raw.get("company_size", ""),
            source=raw.get("source", ""),
            notes=raw.get("notes", ""),
        )
        return {"valid": True}

    async def _enrich(self, pipeline: PipelineRun, raw: dict) -> dict:
        lead = pipeline.lead
        if not lead:
            raise ValueError("No lead to enrich")

        prompt = (
            f"Company: {lead.company}\n"
            f"Person Role: {lead.role}\n"
            f"Industry: {lead.industry}\n"
            f"Company Size: {lead.company_size}"
        )

        import json
        raw_response = await self.llm.complete(
            prompt=prompt,
            system=ENRICHMENT_PROMPT,
            max_tokens=512,
        )

        try:
            enrichment = json.loads(raw_response)
        except json.JSONDecodeError:
            enrichment = {"conversation_starter": raw_response[:200]}

        lead.enrichment = enrichment
        return enrichment

    async def _score(self, pipeline: PipelineRun, raw: dict) -> dict:
        lead = pipeline.lead
        if not lead:
            raise ValueError("No lead to score")

        lead = await self.lead_agent._score_lead(lead)
        pipeline.lead = lead
        return {"score": lead.score, "qualified": lead.qualified}

    async def _route(self, pipeline: PipelineRun, raw: dict) -> dict:
        lead = pipeline.lead
        if not lead or not lead.qualified:
            return {"routed": False, "reason": "not_qualified"}

        await self.lead_agent._route_to_crm(lead)
        return {"routed": True, "crm": self.lead_agent.crm_target}

    async def _notify(self, pipeline: PipelineRun, raw: dict) -> dict:
        lead = pipeline.lead
        if not lead:
            return {}

        enrichment = lead.enrichment or {}
        status_emoji = "🎯" if lead.qualified else "📋"

        message = (
            f"{status_emoji} *New Lead Processed: {lead.name} @ {lead.company}*\n"
            f"Score: *{lead.score}/100* | Qualified: *{'Yes' if lead.qualified else 'No'}*\n"
            f"Role: {lead.role} | Source: {lead.source}\n"
        )

        if enrichment.get("conversation_starter"):
            message += f"\n_Opening line:_ \"{enrichment['conversation_starter']}\""

        if not self.dry_run:
            await self.slack.post_message(
                channel="#autopilot-leads",
                text=message,
            )

        return {"notified": True}
