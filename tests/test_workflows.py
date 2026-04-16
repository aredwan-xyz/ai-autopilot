"""Tests for LeadPipeline workflow."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


class TestLeadPipeline:
    def _make_valid_lead(self):
        return {
            "id": "lead_001",
            "name": "Sarah Chen",
            "email": "sarah@techcorp.io",
            "company": "TechCorp",
            "role": "COO",
            "industry": "SaaS",
            "company_size": "80 employees",
            "source": "LinkedIn",
            "notes": "Mentioned they want to automate reporting",
        }

    @pytest.mark.asyncio
    async def test_full_pipeline_qualified_lead(self):
        from src.workflows.lead_pipeline import LeadPipeline

        pipeline = LeadPipeline(dry_run=True)

        # Mock LLM calls
        pipeline.llm = AsyncMock()
        pipeline.llm.complete = AsyncMock(side_effect=[
            # enrichment
            '{"company_description":"B2B SaaS company","company_stage":"smb","likely_pain_points":["manual reporting"],"relevant_ai_use_cases":["automated reporting"],"conversation_starter":"I noticed TechCorp is scaling fast — are manual ops starting to slow you down?"}',
            # scoring (called within lead_agent)
            '{"score":82,"breakdown":{"role_fit":22,"industry_fit":18,"company_size_fit":18,"geography_fit":12,"intent_signals":12},"qualified":true,"reasoning":"COO at 80-person SaaS is a strong ICP fit.","outreach_angle":"I noticed TechCorp is scaling fast."}',
        ])

        # Mock integrations
        pipeline.slack.post_message = AsyncMock()
        pipeline.lead_agent.hubspot = AsyncMock()
        pipeline.lead_agent.hubspot.create_contact = AsyncMock(return_value={"id": "hs_001"})
        pipeline.lead_agent.airtable = AsyncMock()

        result = await pipeline.run(self._make_valid_lead())

        assert result.completed is True
        assert result.failed is False
        assert result.lead is not None
        assert result.lead.name == "Sarah Chen"

    @pytest.mark.asyncio
    async def test_pipeline_fails_on_missing_email(self):
        from src.workflows.lead_pipeline import LeadPipeline

        pipeline = LeadPipeline(dry_run=True)

        bad_lead = {"id": "bad_001", "name": "John Doe", "company": "ACME"}  # no email

        result = await pipeline.run(bad_lead)

        assert result.failed is True
        validate_step = next(s for s in result.steps if s.name == "validate")
        assert validate_step.error is not None
        assert "email" in validate_step.error

    @pytest.mark.asyncio
    async def test_unqualified_lead_not_routed(self):
        from src.workflows.lead_pipeline import LeadPipeline

        pipeline = LeadPipeline(dry_run=True)
        pipeline.llm = AsyncMock()
        pipeline.llm.complete = AsyncMock(side_effect=[
            # enrichment
            '{"company_description":"Small local shop","company_stage":"smb","likely_pain_points":[],"relevant_ai_use_cases":[],"conversation_starter":"Hi there"}',
            # low score
            '{"score":30,"breakdown":{"role_fit":5,"industry_fit":5,"company_size_fit":10,"geography_fit":5,"intent_signals":5},"qualified":false,"reasoning":"Poor ICP fit.","outreach_angle":""}',
        ])
        pipeline.slack.post_message = AsyncMock()

        result = await pipeline.run(self._make_valid_lead())

        route_step = next((s for s in result.steps if s.name == "route"), None)
        if route_step and route_step.output:
            assert route_step.output.get("routed") is False
