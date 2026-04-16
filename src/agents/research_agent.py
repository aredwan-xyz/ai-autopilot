"""
ResearchAgent — Deep AI-powered research and competitive intelligence.

Capabilities:
  - Accept a research topic or company target
  - Scrape and synthesize multiple sources
  - Generate structured briefing documents
  - Output to Notion, Slack, or email
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.agents.base_agent import AgentRun, BaseAgent
from src.integrations.notion import NotionClient
from src.integrations.slack import SlackClient


@dataclass
class ResearchBrief:
    topic: str
    summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    opportunities: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)


RESEARCH_SYNTHESIS_PROMPT = """
You are a senior business research analyst. Given raw information about a topic,
produce a structured JSON briefing:
{
  "summary": "3-4 sentence executive summary",
  "key_findings": ["finding 1", "finding 2", ...],
  "opportunities": ["opportunity 1", ...],
  "risks": ["risk 1", ...],
  "recommended_actions": ["action 1", ...]
}

Be specific. Focus on actionable intelligence. Return only valid JSON.
"""


class ResearchAgent(BaseAgent):
    name = "research_agent"
    description = (
        "Conducts deep research on topics, competitors, or markets "
        "and delivers structured intelligence briefs."
    )

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.notion = NotionClient()
        self.slack = SlackClient()
        self.max_sources = self.cfg("max_sources", 10)
        self.output_format = self.cfg("output_format", "slack")

    async def run(self, run: AgentRun, topic: str = "") -> AgentRun:
        if not topic:
            topic = self.cfg("default_topic", "AI automation industry trends 2025")

        self.log.info("research_start", topic=topic)

        # 1. Gather raw information
        raw_data = await self._gather_information(topic)

        # 2. Synthesize into brief
        brief = await self._synthesize(topic, raw_data)

        # 3. Deliver output
        if not self.dry_run:
            await self._deliver(brief)

        run.items_processed = len(raw_data)
        run.items_actioned = 1
        run.output = {
            "topic": topic,
            "sources_used": len(raw_data),
            "findings": len(brief.key_findings),
            "opportunities": len(brief.opportunities),
        }

        return run

    async def _gather_information(self, topic: str) -> list[str]:
        """
        Gather raw text from multiple sources.
        In production, this integrates with Playwright for scraping
        or a search API like Serper/Tavily.
        """
        # Placeholder: returns structured prompt for LLM to simulate research
        # In production: use playwright to scrape SERPs, news, LinkedIn, etc.
        self.log.info("gathering_sources", topic=topic)
        return [f"Source data for: {topic} (placeholder — integrate Serper/Tavily API here)"]

    async def _synthesize(self, topic: str, raw_data: list[str]) -> ResearchBrief:
        """Use LLM to synthesize raw data into a structured brief."""
        combined = "\n\n---\n\n".join(raw_data[:self.max_sources])
        prompt = f"RESEARCH TOPIC: {topic}\n\nRAW INFORMATION:\n{combined}\n\nSynthesize this into a briefing."

        raw = await self.think(prompt=prompt, system=RESEARCH_SYNTHESIS_PROMPT, max_tokens=1200)

        try:
            data = json.loads(raw)
            return ResearchBrief(
                topic=topic,
                summary=data.get("summary", ""),
                key_findings=data.get("key_findings", []),
                opportunities=data.get("opportunities", []),
                risks=data.get("risks", []),
                recommended_actions=data.get("recommended_actions", []),
                sources=raw_data[:self.max_sources],
            )
        except json.JSONDecodeError:
            return ResearchBrief(topic=topic, summary=raw)

    async def _deliver(self, brief: ResearchBrief) -> None:
        """Deliver the research brief to the configured output."""
        if self.output_format == "slack":
            await self._post_to_slack(brief)
        elif self.output_format == "notion":
            await self._save_to_notion(brief)

    async def _post_to_slack(self, brief: ResearchBrief) -> None:
        lines = [
            f"🔬 *Research Brief: {brief.topic}*\n",
            f"_{brief.summary}_\n",
            "*Key Findings:*",
            *[f"• {f}" for f in brief.key_findings],
            "\n*Opportunities:*",
            *[f"• {o}" for o in brief.opportunities],
            "\n*Recommended Actions:*",
            *[f"• {a}" for a in brief.recommended_actions],
        ]
        await self.slack.post_message(channel="#autopilot-research", text="\n".join(lines))

    async def _save_to_notion(self, brief: ResearchBrief) -> None:
        self.log.info("notion_research_save", topic=brief.topic)
        # Implementation: create a Notion page with structured content blocks
