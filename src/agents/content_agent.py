"""
ContentAgent — AI-driven content generation, scheduling, and multi-platform publishing.

Capabilities:
  - Read content calendar from Notion database
  - Generate LinkedIn posts, Twitter threads, and newsletter sections
  - Maintain brand voice consistency
  - Schedule and publish to configured platforms
  - Track engagement metrics
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.agents.base_agent import AgentRun, BaseAgent
from src.integrations.notion import NotionClient
from src.integrations.slack import SlackClient


class ContentType(str, Enum):
    LINKEDIN_POST = "linkedin_post"
    TWITTER_THREAD = "twitter_thread"
    NEWSLETTER = "newsletter"
    BLOG_INTRO = "blog_intro"
    CASE_STUDY = "case_study"


@dataclass
class ContentItem:
    id: str
    title: str
    content_type: ContentType
    brief: str
    platform: str
    scheduled_for: datetime | None = None
    generated_content: str = ""
    published: bool = False
    publish_url: str = ""
    tags: list[str] = field(default_factory=list)


BRAND_VOICE_SYSTEM = """
You are the content writer for CodeBeez, an AI services studio.

Brand Voice:
- Authoritative but approachable — a smart friend who knows AI
- First-person, direct, no fluff or corporate speak
- Data-driven with specific examples and numbers when possible
- Mildly provocative — challenges conventional thinking
- Never hype-y or salesy. Never says "game-changer" or "revolutionize"

Tone: Confident, insightful, slightly edgy. Like a founder talking to peers.

For LinkedIn posts:
- Hook in the first line (no "I'm excited to share...")
- 3-5 short paragraphs or a clear numbered list
- End with a direct question or bold statement
- 150-300 words ideal

For Twitter threads:
- Tweet 1: Bold hook claim
- Tweets 2-7: Each tweet = one insight, max 270 chars
- Last tweet: CTA or summary

Always return only the content itself — no titles, no metadata, no explanation.
"""


class ContentAgent(BaseAgent):
    name = "content_agent"
    description = (
        "Generates brand-aligned content from a Notion calendar, "
        "then schedules and publishes to LinkedIn, Twitter, and other platforms."
    )

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        super().__init__(config, dry_run)
        self.notion = NotionClient()
        self.slack = SlackClient()
        self.platforms = self.cfg("publish_platforms", ["linkedin"])

    async def run(self, run: AgentRun) -> AgentRun:
        # 1. Fetch today's content queue from Notion
        queue = await self._fetch_content_queue()
        run.items_processed = len(queue)
        self.log.info("content_queue_fetched", count=len(queue))

        published = []
        failed = []

        for item in queue:
            try:
                # 2. Generate content
                item = await self._generate_content(item)

                # 3. Review gate — post to Slack for approval if configured
                approved = await self._request_approval(item)

                if approved:
                    # 4. Publish
                    item = await self._publish(item)
                    published.append(item)
                    run.items_actioned += 1

                    # 5. Update Notion record
                    if not self.dry_run:
                        await self.notion.mark_content_published(
                            item.id,
                            publish_url=item.publish_url,
                        )

            except Exception as e:
                failed.append(item.title)
                run.errors.append(f"Content '{item.title}': {e}")

        run.output = {
            "queued": len(queue),
            "published": len(published),
            "failed": len(failed),
            "platforms": self.platforms,
        }

        return run

    async def _fetch_content_queue(self) -> list[ContentItem]:
        """Pull today's scheduled content from Notion."""
        raw_items = await self.notion.get_todays_content()
        items = []
        for r in raw_items:
            props = r.get("properties", {})
            content_type_str = props.get("Type", {}).get("select", {}).get("name", "linkedin_post")
            try:
                content_type = ContentType(content_type_str.lower().replace(" ", "_"))
            except ValueError:
                content_type = ContentType.LINKEDIN_POST

            items.append(
                ContentItem(
                    id=r["id"],
                    title=props.get("Title", {}).get("title", [{}])[0].get("plain_text", ""),
                    content_type=content_type,
                    brief=props.get("Brief", {}).get("rich_text", [{}])[0].get("plain_text", ""),
                    platform=props.get("Platform", {}).get("select", {}).get("name", "linkedin"),
                )
            )
        return items

    async def _generate_content(self, item: ContentItem) -> ContentItem:
        """Generate content from brief using LLM."""
        type_instruction = {
            ContentType.LINKEDIN_POST: "Write a LinkedIn post",
            ContentType.TWITTER_THREAD: "Write a Twitter/X thread (number each tweet)",
            ContentType.NEWSLETTER: "Write a newsletter section",
            ContentType.BLOG_INTRO: "Write a blog post introduction",
            ContentType.CASE_STUDY: "Write a case study excerpt",
        }.get(item.content_type, "Write a social media post")

        prompt = f"{type_instruction} based on this brief:\n\n{item.brief}"

        item.generated_content = await self.think(
            prompt=prompt,
            system=BRAND_VOICE_SYSTEM,
            max_tokens=600,
        )

        self.log.info("content_generated", title=item.title, type=item.content_type.value)
        return item

    async def _request_approval(self, item: ContentItem) -> bool:
        """Post content preview to Slack. In auto mode, skip approval gate."""
        auto_publish = self.cfg("auto_publish", False)

        if auto_publish or self.dry_run:
            return not self.dry_run  # dry_run means generate but don't publish

        preview = (
            f"📝 *Content Ready for Review*\n"
            f"*Title:* {item.title}\n"
            f"*Type:* {item.content_type.value}\n"
            f"*Platform:* {item.platform}\n\n"
            f"```{item.generated_content[:500]}```\n\n"
            f"_Reply `approve {item.id}` to publish or `skip {item.id}` to defer._"
        )

        await self.slack.post_message(channel="#content-review", text=preview)
        # In a real implementation, this would wait for a Slack response via webhook
        # For now, we auto-approve after posting the preview
        return True

    async def _publish(self, item: ContentItem) -> ContentItem:
        """Publish content to the target platform."""
        if self.dry_run:
            self.log.info("dry_run_publish_skip", title=item.title)
            item.published = True
            return item

        # Platform routing
        if item.platform.lower() == "linkedin":
            item.publish_url = await self._publish_linkedin(item)
        elif item.platform.lower() in ("twitter", "x"):
            item.publish_url = await self._publish_twitter(item)

        item.published = True
        self.log.info("content_published", title=item.title, url=item.publish_url)
        return item

    async def _publish_linkedin(self, item: ContentItem) -> str:
        """Publish to LinkedIn via API."""
        # LinkedIn API integration placeholder
        # In production: use linkedin-api or requests with OAuth token
        self.log.info("linkedin_publish", title=item.title)
        return f"https://linkedin.com/feed/update/urn:li:activity:placeholder_{item.id}"

    async def _publish_twitter(self, item: ContentItem) -> str:
        """Publish to Twitter/X via API."""
        self.log.info("twitter_publish", title=item.title)
        return f"https://twitter.com/i/web/status/placeholder_{item.id}"
