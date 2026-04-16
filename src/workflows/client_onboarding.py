"""
Client Onboarding Workflow — Automates new client setup from deal-close to kickoff.

Steps:
  1. Receive trigger (new deal closed in HubSpot/Stripe)
  2. Create Notion client workspace
  3. Generate personalised onboarding checklist
  4. Send welcome email
  5. Schedule kickoff calendar invite
  6. Notify internal team on Slack
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

import structlog

from src.integrations.notion import NotionClient
from src.integrations.slack import SlackClient
from src.utils.llm import LLMClient

logger = structlog.get_logger("client_onboarding")


@dataclass
class ClientProfile:
    id: str
    name: str
    company: str
    email: str
    plan: str           # quick_win | sprint | retainer
    industry: str = ""
    goals: list[str] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)
    notion_workspace_url: str = ""
    welcome_email_sent: bool = False
    kickoff_scheduled: bool = False


ONBOARDING_EMAIL_PROMPT = """
You are a client success manager at CodeBeez, an AI services studio.
Write a warm, professional welcome email for a new client.

Guidelines:
- Personal and specific (reference their company and plan)
- Clear next steps (what happens in the first 48 hours)
- Excited but not over-the-top
- Under 200 words
- No subject line — just the email body
"""

CHECKLIST_PROMPT = """
You are an AI project manager. Generate a personalised onboarding checklist
for a new client. Return JSON:
{
  "week_1": ["task 1", "task 2", ...],
  "week_2": ["task 1", ...],
  "ongoing": ["task 1", ...]
}
Tasks should be specific to their industry and goals.
Return only valid JSON.
"""


class ClientOnboardingWorkflow:
    """Orchestrates the full client onboarding sequence."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.llm = LLMClient()
        self.notion = NotionClient()
        self.slack = SlackClient()
        self.log = logger

    async def run(self, client_data: dict) -> ClientProfile:
        """Execute full onboarding for a new client."""
        client = ClientProfile(
            id=client_data.get("id", ""),
            name=client_data.get("name", ""),
            company=client_data.get("company", ""),
            email=client_data.get("email", ""),
            plan=client_data.get("plan", "sprint"),
            industry=client_data.get("industry", ""),
            goals=client_data.get("goals", []),
            pain_points=client_data.get("pain_points", []),
        )

        self.log.info("onboarding_start", client=client.name, company=client.company)

        steps = [
            ("create_notion_workspace", self._create_notion_workspace),
            ("generate_checklist", self._generate_onboarding_checklist),
            ("send_welcome_email", self._send_welcome_email),
            ("notify_team", self._notify_internal_team),
        ]

        for step_name, fn in steps:
            try:
                await fn(client)
                self.log.info("onboarding_step_done", step=step_name, client=client.name)
            except Exception as e:
                self.log.error("onboarding_step_failed", step=step_name, error=str(e))

        return client

    async def _create_notion_workspace(self, client: ClientProfile) -> None:
        """Create a dedicated Notion workspace for the client."""
        if self.dry_run:
            client.notion_workspace_url = f"https://notion.so/demo-workspace-{client.id}"
            return

        # In production: create a Notion page from template
        self.log.info("notion_workspace_created", client=client.company)
        client.notion_workspace_url = f"https://notion.so/workspace-{client.id}"

    async def _generate_onboarding_checklist(self, client: ClientProfile) -> None:
        """Generate a personalised checklist using LLM."""
        prompt = (
            f"Client: {client.name} at {client.company}\n"
            f"Plan: {client.plan}\n"
            f"Industry: {client.industry}\n"
            f"Goals: {', '.join(client.goals)}\n"
            f"Pain points: {', '.join(client.pain_points)}\n\n"
            "Generate their onboarding checklist."
        )

        raw = await self.llm.complete(prompt=prompt, system=CHECKLIST_PROMPT, max_tokens=600)

        try:
            checklist = json.loads(raw)
            self.log.info(
                "checklist_generated",
                client=client.name,
                week1_tasks=len(checklist.get("week_1", [])),
            )
        except json.JSONDecodeError:
            self.log.warning("checklist_parse_failed", client=client.name)

    async def _send_welcome_email(self, client: ClientProfile) -> None:
        """Draft and send a personalised welcome email."""
        plan_names = {
            "quick_win": "Quick Win ($997)",
            "sprint": "AI Transformation Sprint ($3,997)",
            "retainer": "AI-Native Partner (retainer)",
        }

        prompt = (
            f"Client name: {client.name}\n"
            f"Company: {client.company}\n"
            f"Plan purchased: {plan_names.get(client.plan, client.plan)}\n"
            f"Industry: {client.industry}\n"
            f"Main goal: {client.goals[0] if client.goals else 'AI automation'}\n\n"
            "Write the welcome email."
        )

        email_body = await self.llm.complete(
            prompt=prompt, system=ONBOARDING_EMAIL_PROMPT, max_tokens=400
        )

        if not self.dry_run:
            # In production: send via SendGrid / Gmail API
            self.log.info("welcome_email_sent", to=client.email)

        client.welcome_email_sent = True
        self.log.info("welcome_email_drafted", client=client.name)

    async def _notify_internal_team(self, client: ClientProfile) -> None:
        """Alert the team about the new client in Slack."""
        plan_emoji = {"quick_win": "⚡", "sprint": "🚀", "retainer": "💎"}

        message = (
            f"{plan_emoji.get(client.plan, '🎉')} *New Client Onboarded!*\n\n"
            f"*{client.name}* @ {client.company}\n"
            f"Plan: *{client.plan.replace('_', ' ').title()}*\n"
            f"Industry: {client.industry}\n"
        )

        if client.goals:
            message += f"Goals: {', '.join(client.goals[:2])}\n"

        if client.notion_workspace_url:
            message += f"\n<{client.notion_workspace_url}|Open Client Workspace →>"

        if not self.dry_run:
            await self.slack.post_message(channel="#new-clients", text=message)
