# Contributing to AI Business Autopilot

Thank you for your interest in contributing!

## Development Setup

```bash
git clone https://github.com/yourorg/ai-autopilot.git
cd ai-autopilot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Adding a New Agent

1. Create `src/agents/your_agent.py` inheriting from `BaseAgent`
2. Implement `run(self, run: AgentRun) -> AgentRun`
3. Register it in `src/orchestrator.py` in `AGENT_REGISTRY`
4. Add config to `src/config/agents.yaml`
5. Write tests in `tests/test_agents.py`

## Code Standards

- Type hints on all public methods
- Docstrings on all classes
- `structlog` for all logging (no `print`)
- `dry_run` flag respected — never execute real actions in dry mode
- Tests for all new agents using `AsyncMock` for integrations

## Running Tests

```bash
pytest tests/ -v
```

## Pull Request Checklist

- [ ] Tests pass locally
- [ ] New agent has tests with `dry_run=True`
- [ ] Integration clients are injected (not hardcoded)
- [ ] `.env.example` updated if new env vars added
- [ ] `agents.yaml` updated with new agent config
