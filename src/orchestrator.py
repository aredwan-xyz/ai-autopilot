"""
Orchestrator — The central scheduler and coordinator for all AI agents.

Manages:
  - Cron-like scheduling via APScheduler
  - Agent lifecycle (start, stop, retry)
  - Event broadcasting to connected dashboard clients
  - Run history and status tracking
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import structlog
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.agents.base_agent import AgentRun, AgentStatus, BaseAgent
from src.agents.content_agent import ContentAgent
from src.agents.email_agent import EmailAgent
from src.agents.lead_agent import LeadAgent
from src.agents.report_agent import ReportAgent
from src.config.settings import settings

logger = structlog.get_logger("orchestrator")

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "email_agent": EmailAgent,
    "lead_agent": LeadAgent,
    "content_agent": ContentAgent,
    "report_agent": ReportAgent,
}


class Orchestrator:
    """Manages all agents and their schedules."""

    def __init__(self, config_path: str = "src/config/agents.yaml", dry_run: bool = False):
        self.config_path = config_path
        self.dry_run = dry_run
        self.scheduler = AsyncIOScheduler()
        self.run_history: list[AgentRun] = []
        self.active_agents: dict[str, BaseAgent] = {}
        self._event_listeners: list[Any] = []
        self.log = logger

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Load config, register all agents, and start the scheduler."""
        self.log.info("orchestrator_starting", dry_run=self.dry_run)
        config = self._load_config()

        for agent_name, agent_config in config.get("agents", {}).items():
            if not agent_config.get("enabled", True):
                self.log.info("agent_disabled", name=agent_name)
                continue

            agent_class = AGENT_REGISTRY.get(agent_name)
            if not agent_class:
                self.log.warning("unknown_agent", name=agent_name)
                continue

            agent = agent_class(config=agent_config, dry_run=self.dry_run)
            self.active_agents[agent_name] = agent

            schedule = agent_config.get("schedule")
            if schedule:
                self.scheduler.add_job(
                    self._run_agent,
                    CronTrigger.from_crontab(schedule),
                    args=[agent_name],
                    id=agent_name,
                    name=f"Agent: {agent_name}",
                    max_instances=1,
                    coalesce=True,
                )
                self.log.info("agent_scheduled", name=agent_name, schedule=schedule)

        self.scheduler.start()
        self.log.info(
            "orchestrator_started",
            agents=list(self.active_agents.keys()),
            jobs=len(self.scheduler.get_jobs()),
        )

    async def stop(self) -> None:
        """Gracefully shut down the scheduler."""
        self.scheduler.shutdown(wait=True)
        self.log.info("orchestrator_stopped")

    # ------------------------------------------------------------------
    # Agent execution
    # ------------------------------------------------------------------

    async def _run_agent(self, agent_name: str) -> AgentRun | None:
        """Execute a single agent by name."""
        agent = self.active_agents.get(agent_name)
        if not agent:
            self.log.error("agent_not_found", name=agent_name)
            return None

        self.log.info("agent_triggered", name=agent_name, source="scheduler")
        run = await agent.execute()

        self.run_history.append(run)
        # Keep history bounded
        if len(self.run_history) > 500:
            self.run_history = self.run_history[-500:]

        await self._broadcast_event("agent_run_complete", run.to_dict())
        return run

    async def trigger(self, agent_name: str) -> AgentRun | None:
        """Manually trigger an agent outside its schedule."""
        self.log.info("agent_manual_trigger", name=agent_name)
        return await self._run_agent(agent_name)

    async def run_all(self) -> list[AgentRun]:
        """Run all enabled agents sequentially (useful for testing)."""
        results = []
        for name in self.active_agents:
            run = await self._run_agent(name)
            if run:
                results.append(run)
        return results

    # ------------------------------------------------------------------
    # Status & history
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return current system status."""
        return {
            "active_agents": list(self.active_agents.keys()),
            "scheduled_jobs": [
                {
                    "id": job.id,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                }
                for job in self.scheduler.get_jobs()
            ],
            "recent_runs": [r.to_dict() for r in self.run_history[-20:]],
            "uptime_since": datetime.utcnow().isoformat(),
        }

    def get_agent_last_run(self, agent_name: str) -> AgentRun | None:
        agent = self.active_agents.get(agent_name)
        return agent.last_run if agent else None

    # ------------------------------------------------------------------
    # Event broadcasting (for WebSocket dashboard)
    # ------------------------------------------------------------------

    def add_event_listener(self, listener: Any) -> None:
        self._event_listeners.append(listener)

    async def _broadcast_event(self, event_type: str, data: dict) -> None:
        message = {"event": event_type, "data": data, "timestamp": datetime.utcnow().isoformat()}
        for listener in self._event_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(message)
                else:
                    listener(message)
            except Exception as e:
                self.log.warning("event_broadcast_error", error=str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        try:
            with open(self.config_path) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            self.log.warning("config_not_found", path=self.config_path)
            return {}


# ------------------------------------------------------------------
# CLI entrypoint
# ------------------------------------------------------------------

async def main(dry_run: bool = False):
    """Start the orchestrator and keep it running."""
    orch = Orchestrator(dry_run=dry_run)
    await orch.start()

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        await orch.stop()


if __name__ == "__main__":
    import typer

    app = typer.Typer()

    @app.command()
    def start(dry_run: bool = typer.Option(False, "--dry-run", help="Don't execute real actions")):
        """Start the AI Autopilot orchestrator."""
        asyncio.run(main(dry_run=dry_run))

    app()
