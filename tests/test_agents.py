"""Tests for BaseAgent and EmailAgent."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base_agent import AgentRun, AgentStatus, BaseAgent
from src.agents.email_agent import EmailAgent, EmailCategory


# ------------------------------------------------------------------
# Concrete subclass for testing BaseAgent
# ------------------------------------------------------------------

class EchoAgent(BaseAgent):
    name = "echo_agent"

    async def run(self, run: AgentRun) -> AgentRun:
        run.items_processed = 3
        run.items_actioned = 2
        return run


class FailingAgent(BaseAgent):
    name = "failing_agent"

    async def run(self, run: AgentRun) -> AgentRun:
        raise RuntimeError("Deliberate test failure")


# ------------------------------------------------------------------
# BaseAgent tests
# ------------------------------------------------------------------

class TestBaseAgent:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        agent = EchoAgent(dry_run=True)
        run = await agent.execute()

        assert run.status == AgentStatus.SUCCESS
        assert run.items_processed == 3
        assert run.items_actioned == 2
        assert run.started_at is not None
        assert run.finished_at is not None
        assert run.duration_seconds is not None
        assert run.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_failed_execution_captured(self):
        agent = FailingAgent(dry_run=True)
        run = await agent.execute()

        assert run.status == AgentStatus.FAILED
        assert len(run.errors) == 1
        assert "Deliberate test failure" in run.errors[0]

    @pytest.mark.asyncio
    async def test_validation_skip(self):
        class SkippingAgent(BaseAgent):
            name = "skipping_agent"

            async def validate(self):
                return False

            async def run(self, run):
                return run

        agent = SkippingAgent(dry_run=True)
        run = await agent.execute()
        assert run.status == AgentStatus.SKIPPED

    def test_config_accessor(self):
        agent = EchoAgent(config={"max_items": 42}, dry_run=True)
        assert agent.cfg("max_items") == 42
        assert agent.cfg("missing_key", "default") == "default"

    def test_run_to_dict(self):
        run = AgentRun(agent_name="test_agent", items_processed=5)
        d = run.to_dict()
        assert d["agent"] == "test_agent"
        assert d["items_processed"] == 5
        assert "run_id" in d


# ------------------------------------------------------------------
# EmailAgent tests
# ------------------------------------------------------------------

class TestEmailAgent:
    def _make_agent(self):
        agent = EmailAgent(
            config={"auto_reply": True, "max_emails_per_run": 10},
            dry_run=True,
        )
        # Mock integrations
        agent.gmail = AsyncMock()
        agent.gmail.health_check = AsyncMock(return_value=True)
        agent.gmail.fetch_unread = AsyncMock(return_value=[
            {
                "id": "msg_001",
                "threadId": "thread_001",
                "from": "prospect@startup.com",
                "subject": "Interested in AI automation for our team",
                "body_text": "Hi, I saw your work on AI automation. We're a 50-person SaaS company looking to automate our operations. Do you have time for a call?",
                "snippet": "Hi, I saw your work...",
            },
            {
                "id": "msg_002",
                "threadId": "thread_002",
                "from": "newsletter@spamco.com",
                "subject": "This week in growth hacking!!",
                "body_text": "Subscribe to our newsletter for the best growth tips...",
                "snippet": "Subscribe to our newsletter...",
            },
        ])
        agent.gmail.apply_label = AsyncMock()
        agent.gmail.archive = AsyncMock()
        agent.gmail.send_reply = AsyncMock()
        agent.slack = AsyncMock()
        agent.slack.post_message = AsyncMock()
        return agent

    @pytest.mark.asyncio
    async def test_email_triage_runs(self):
        agent = self._make_agent()

        # Mock LLM responses
        agent.llm = AsyncMock()
        agent.llm.complete = AsyncMock(side_effect=[
            # Response for first email (lead)
            '{"category":"lead","priority":1,"sentiment":"positive","escalate":false,"summary":"Prospect interested in AI automation","draft_reply":"Hi! Thanks for reaching out. I would love to connect for a call. When works for you?"}',
            # Response for second email (newsletter)
            '{"category":"newsletter","priority":5,"sentiment":"neutral","escalate":false,"summary":"Newsletter spam","draft_reply":null}',
        ])

        run = await agent.execute()

        assert run.status == AgentStatus.SUCCESS
        assert run.items_processed == 2

    @pytest.mark.asyncio
    async def test_malformed_llm_response_handled(self):
        """Agent should handle invalid JSON from LLM gracefully."""
        agent = self._make_agent()
        agent.llm = AsyncMock()
        agent.llm.complete = AsyncMock(return_value="This is not valid JSON at all!")

        run = await agent.execute()
        # Should not crash — falls back to default categorisation
        assert run.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_dry_run_skips_send(self):
        agent = self._make_agent()
        agent.dry_run = True
        agent.llm = AsyncMock()
        agent.llm.complete = AsyncMock(return_value=(
            '{"category":"lead","priority":1,"sentiment":"positive",'
            '"escalate":false,"summary":"Test","draft_reply":"Hello!"}'
        ))

        await agent.execute()

        # In dry_run, should NOT call send_reply or apply_label
        agent.gmail.send_reply.assert_not_called()
        agent.gmail.apply_label.assert_not_called()

    def test_email_category_values(self):
        assert EmailCategory.LEAD == "lead"
        assert EmailCategory.SPAM == "spam"
        assert EmailCategory.URGENT == "urgent"
