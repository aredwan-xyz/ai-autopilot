"""
Base Agent — Abstract foundation for all AI autopilot agents.

Every agent inherits from BaseAgent and implements:
  - run()     → main execution logic
  - validate() → pre-run checks
  - report()  → structured output summary
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

from src.utils.llm import LLMClient
from src.utils.retry import with_retry

logger = structlog.get_logger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentRun:
    """Represents a single agent execution record."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str = ""
    status: AgentStatus = AgentStatus.IDLE
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items_processed: int = 0
    items_actioned: int = 0
    errors: list[str] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent": self.agent_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_s": self.duration_seconds,
            "items_processed": self.items_processed,
            "items_actioned": self.items_actioned,
            "errors": self.errors,
            "output": self.output,
            "dry_run": self.dry_run,
        }


class BaseAgent(ABC):
    """
    Abstract base class for all AI Autopilot agents.

    Usage:
        class MyAgent(BaseAgent):
            name = "my_agent"

            async def run(self, run: AgentRun) -> AgentRun:
                # your logic here
                return run
    """

    name: str = "base_agent"
    description: str = ""
    version: str = "1.0.0"

    def __init__(self, config: dict | None = None, dry_run: bool = False):
        self.config = config or {}
        self.dry_run = dry_run
        self.llm = LLMClient()
        self.log = structlog.get_logger(self.name)
        self._last_run: AgentRun | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute(self) -> AgentRun:
        """Execute the agent with full lifecycle management."""
        run = AgentRun(agent_name=self.name, dry_run=self.dry_run)
        run.started_at = datetime.utcnow()
        run.status = AgentStatus.RUNNING

        self.log.info("agent_start", run_id=run.run_id, dry_run=self.dry_run)

        try:
            if not await self.validate():
                run.status = AgentStatus.SKIPPED
                self.log.warning("agent_skipped", reason="validation_failed")
                return run

            run = await self.run(run)
            run.status = AgentStatus.SUCCESS

        except Exception as exc:
            run.status = AgentStatus.FAILED
            run.errors.append(str(exc))
            self.log.error("agent_failed", error=str(exc), exc_info=True)

        finally:
            run.finished_at = datetime.utcnow()
            self._last_run = run
            self.log.info(
                "agent_complete",
                run_id=run.run_id,
                status=run.status.value,
                duration=run.duration_seconds,
                processed=run.items_processed,
                actioned=run.items_actioned,
            )

        return run

    # ------------------------------------------------------------------
    # Abstract methods — implement in each agent
    # ------------------------------------------------------------------

    @abstractmethod
    async def run(self, run: AgentRun) -> AgentRun:
        """Core agent logic. Must update and return the run object."""
        ...

    async def validate(self) -> bool:
        """Pre-run validation. Override to add checks. Default: always valid."""
        return True

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    async def think(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> str:
        """Call the LLM and return the text response."""
        return await self.llm.complete(
            prompt=prompt,
            system=system or self._default_system_prompt(),
            max_tokens=max_tokens,
        )

    def _default_system_prompt(self) -> str:
        return (
            f"You are an autonomous AI agent called '{self.name}'. "
            f"{self.description} "
            "Respond concisely. When asked to produce structured data, return only valid JSON."
        )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def cfg(self, key: str, default: Any = None) -> Any:
        """Safe config accessor."""
        return self.config.get(key, default)

    @property
    def last_run(self) -> AgentRun | None:
        return self._last_run
