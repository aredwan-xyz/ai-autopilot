"""
Content Calendar Workflow — Weekly content planning and batch generation.

Runs once per week to:
  1. Analyse recent performance data (optional)
  2. Generate a full week of content briefs
  3. Populate Notion content calendar
  4. Notify team for review
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import structlog

from src.integrations.notion import NotionClient
from src.integrations.slack import SlackClient
from src.utils.llm import LLMClient

logger = structlog.get_logger("content_calendar")


@dataclass
class ContentBrief:
    day: str               # Monday, Tuesday, etc.
    platform: str          # linkedin, twitter, newsletter
    content_type: str
    topic: str
    brief: str
    hook: str
    tags: list[str] = field(default_factory=list)


CALENDAR_GENERATION_PROMPT = """
You are a B2B content strategist for CodeBeez, an AI services studio targeting
founders and operations leaders who want to automate their businesses.

Generate a week of content briefs. Return a JSON array of 5 items (Mon-Fri):
[
  {
    "day": "Monday",
    "platform": "linkedin",
    "content_type": "linkedin_post",
    "topic": "short topic title",
    "brief": "2-3 sentence brief explaining what the post should cover",
    "hook": "opening line that grabs attention",
    "tags": ["tag1", "tag2"]
  }
]

Content pillars to rotate through:
1. AI automation case studies / results (specific numbers)
2. Founder productivity & ops insights
3. Behind-the-scenes: how we build AI systems
4. Industry hot takes / contrarian views
5. Educational: AI concepts explained simply

Vary platforms: 3x LinkedIn posts, 1x Twitter thread, 1x newsletter section.
Return only the JSON array.
"""


class ContentCalendarWorkflow:
    """Generates and populates a weekly content calendar in Notion."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.llm = LLMClient()
        self.notion = NotionClient()
        self.slack = SlackClient()
        self.log = logger

    async def run(self, week_start: datetime | None = None) -> list[ContentBrief]:
        if not week_start:
            # Start from next Monday
            today = datetime.utcnow()
            days_ahead = (7 - today.weekday()) % 7 or 7
            week_start = today + timedelta(days=days_ahead)

        self.log.info("calendar_generation_start", week=week_start.strftime("%Y-W%W"))

        # 1. Generate content briefs
        briefs = await self._generate_briefs(week_start)
        self.log.info("briefs_generated", count=len(briefs))

        # 2. Populate Notion calendar
        if not self.dry_run:
            await self._populate_notion(briefs, week_start)

        # 3. Notify team
        if not self.dry_run:
            await self._notify_team(briefs, week_start)

        return briefs

    async def _generate_briefs(self, week_start: datetime) -> list[ContentBrief]:
        """Use LLM to generate a week of content briefs."""
        context = (
            f"Week starting: {week_start.strftime('%B %d, %Y')}\n"
            f"Generate varied, high-quality briefs for this week."
        )

        raw = await self.llm.complete(
            prompt=context,
            system=CALENDAR_GENERATION_PROMPT,
            max_tokens=1200,
        )

        # Strip markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        briefs = []
        try:
            data = json.loads(raw)
            for item in data:
                briefs.append(ContentBrief(
                    day=item.get("day", ""),
                    platform=item.get("platform", "linkedin"),
                    content_type=item.get("content_type", "linkedin_post"),
                    topic=item.get("topic", ""),
                    brief=item.get("brief", ""),
                    hook=item.get("hook", ""),
                    tags=item.get("tags", []),
                ))
        except (json.JSONDecodeError, KeyError) as e:
            self.log.error("calendar_parse_error", error=str(e))

        return briefs

    async def _populate_notion(self, briefs: list[ContentBrief], week_start: datetime) -> None:
        """Create Notion database pages for each content brief."""
        days_map = {"Monday": 0, "Tuesday": 1, "Wednesday": 2,
                    "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}

        for brief in briefs:
            offset = days_map.get(brief.day, 0)
            scheduled_date = (week_start + timedelta(days=offset)).strftime("%Y-%m-%d")

            try:
                await self.notion.create_content_brief(
                    title=brief.topic,
                    content_type=brief.content_type,
                    platform=brief.platform,
                    brief=brief.brief,
                    hook=brief.hook,
                    scheduled_date=scheduled_date,
                    tags=brief.tags,
                )
                self.log.info("notion_brief_created", topic=brief.topic, day=brief.day)
            except Exception as e:
                self.log.error("notion_brief_failed", topic=brief.topic, error=str(e))

    async def _notify_team(self, briefs: list[ContentBrief], week_start: datetime) -> None:
        """Post a preview of the week's content plan to Slack."""
        platform_icons = {"linkedin": "💼", "twitter": "🐦", "newsletter": "📧"}

        lines = [
            f"📅 *Content Calendar Generated — Week of {week_start.strftime('%b %d')}*\n",
            "_Review and approve in Notion before scheduling._\n",
        ]

        for brief in briefs:
            icon = platform_icons.get(brief.platform, "📝")
            lines.append(f"{icon} *{brief.day}* — {brief.topic}")
            lines.append(f"   _{brief.hook[:80]}..._\n")

        await self.slack.post_message(channel="#content-review", text="\n".join(lines))
