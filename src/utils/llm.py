"""
LLM Client — Unified wrapper for Anthropic and OpenAI with retry logic.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

import structlog

from src.config.settings import settings

logger = structlog.get_logger("llm")


class LLMClient:
    """
    Thin async wrapper around Anthropic (default) and OpenAI.

    Usage:
        client = LLMClient()
        response = await client.complete("Write a haiku about automation")
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
    ):
        self.provider = provider or settings.DEFAULT_LLM_PROVIDER
        self.model = model or settings.DEFAULT_MODEL
        self.log = logger

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        retries: int = 3,
    ) -> str:
        """Call the configured LLM and return the text response."""

        for attempt in range(1, retries + 1):
            try:
                if self.provider == "anthropic":
                    return await self._call_anthropic(prompt, system, max_tokens, temperature)
                elif self.provider == "openai":
                    return await self._call_openai(prompt, system, max_tokens, temperature)
                else:
                    raise ValueError(f"Unknown LLM provider: {self.provider}")

            except Exception as e:
                self.log.warning(
                    "llm_call_failed",
                    attempt=attempt,
                    retries=retries,
                    error=str(e),
                )
                if attempt == retries:
                    raise
                await asyncio.sleep(2**attempt)  # exponential backoff

        return ""  # unreachable but satisfies type checker

    async def _call_anthropic(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        response = await client.messages.create(**kwargs)
        return response.content[0].text

    async def _call_openai(
        self,
        prompt: str,
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    async def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        schema_hint: str | None = None,
    ) -> dict:
        """Request a JSON response and parse it."""
        import json

        json_system = (system or "") + "\nRespond ONLY with valid JSON. No markdown, no explanation."
        if schema_hint:
            json_system += f"\nExpected schema: {schema_hint}"

        raw = await self.complete(prompt, system=json_system, max_tokens=1024, temperature=0.3)

        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw.strip())
