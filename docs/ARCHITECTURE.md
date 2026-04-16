# Architecture Guide

## System Overview

The AI Business Autopilot is a **multi-agent automation framework** built on an orchestrator-agent pattern. Each agent is a self-contained unit of business logic powered by an LLM and connected to external services via integration clients.

---

## Core Design Principles

### 1. Dry-Run First
Every agent accepts a `dry_run=True` flag that disables all external writes (no emails sent, no CRM updates, no Slack messages). Always develop and test with `dry_run=True`.

### 2. Fail Gracefully
Agent failures are caught at the orchestrator level and logged — they never crash the system. Each run produces an `AgentRun` object with full status, error list, and metrics.

### 3. Separation of Concerns
- **Agents** contain business logic and LLM prompting
- **Integrations** are thin wrappers around third-party APIs
- **Workflows** compose multiple agents into multi-step pipelines
- **Orchestrator** handles scheduling and lifecycle management

### 4. Observable by Default
All agents emit structured JSON logs via `structlog`. The dashboard receives real-time events via WebSocket.

---

## Agent Lifecycle

```
Orchestrator.execute(agent_name)
    → AgentRun created (IDLE)
    → agent.validate()           # Check credentials, config
    → AgentRun status: RUNNING
    → agent.run(run)             # Core business logic
    → AgentRun status: SUCCESS / FAILED
    → Event broadcast to WebSocket clients
    → AgentRun appended to history
```

---

## Adding a New Integration

1. Create `src/integrations/your_service.py`
2. Implement async methods matching the agent's needs
3. Add credentials to `.env.example` and `src/config/settings.py`
4. Inject the client in the agent's `__init__`
5. Mock it in tests with `AsyncMock`

### Integration Pattern

```python
class MyServiceClient:
    def __init__(self):
        self.api_key = settings.MY_SERVICE_API_KEY

    async def fetch_data(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.myservice.com/data",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            resp.raise_for_status()
            return resp.json()
```

---

## LLM Prompting Strategy

Each agent uses a two-part prompting approach:

- **System prompt** (`AGENT_NAME_PROMPT`): defines role, output schema, tone
- **User prompt**: the actual data to process

For structured outputs, always request JSON explicitly in the system prompt and use `json.loads()` with a try/except fallback.

---

## Scheduling

Schedules are defined in `src/config/agents.yaml` as cron expressions:

| Expression | Meaning |
|---|---|
| `*/15 * * * *` | Every 15 minutes |
| `0 9 * * 1-5` | 9am on weekdays |
| `0 7 * * 1` | 7am every Monday |
| `0 */6 * * *` | Every 6 hours |

An empty schedule means the agent is on-demand only (triggered via API or manually).

---

## Database Schema

The system uses SQLite by default (configurable to PostgreSQL).

### `agent_memory` table
Used by `AgentMemory` for run-to-run state persistence.

```sql
CREATE TABLE agent_memory (
    key         TEXT PRIMARY KEY,  -- "{agent_name}:{key}"
    value       TEXT NOT NULL,     -- JSON-encoded value
    updated_at  TEXT NOT NULL,
    expires_at  TEXT               -- optional TTL
);
```

---

## Security Considerations

- **Never commit `.env`** — it contains API keys
- **Credentials directory** is gitignored — contains Google OAuth tokens
- **Dry-run in development** — prevents accidental real-world actions
- **Rate limiting** — agents use exponential backoff on retries
- **No hardcoded secrets** — all config via environment variables
