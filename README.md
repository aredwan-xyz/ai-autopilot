# 🤖 AI Business Autopilot System

> **Autonomous AI agents that run your business operations — so you don't have to.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](http://makeapullrequest.com)

---

## What is This?

The **AI Business Autopilot System** is a production-ready, multi-agent automation framework that connects AI reasoning with your real business tools. It handles repetitive operational workflows autonomously — from lead qualification and email triage to content publishing, invoice tracking, and client reporting.

Built for founders, operators, and small teams who want to run lean while scaling output.

---

## Core Capabilities

| Module | What it Does |
|--------|-------------|
| **LeadAgent** | Scrapes, scores, and enriches inbound leads. Auto-qualifies and routes to CRM |
| **EmailAgent** | Reads, categorizes, drafts replies, and triages inbox at set intervals |
| **ContentAgent** | Generates, schedules, and publishes social content from a brief or calendar |
| **ReportAgent** | Pulls KPIs from integrations and generates weekly/monthly PDF reports |
| **InvoiceAgent** | Monitors overdue invoices, sends follow-ups, flags critical accounts |
| **SupportAgent** | Handles tier-1 support tickets, escalates complex issues to humans |
| **ResearchAgent** | Deep-dives topics, competitors, or markets and returns structured briefs |
| **SchedulerAgent** | Orchestrates all agents on cron-like schedules with retry/fallback logic |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator Layer                    │
│              (SchedulerAgent + EventBus)                 │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
    ┌──────────▼──────────┐   ┌──────────▼──────────┐
    │    Agent Runtime     │   │   Workflow Engine    │
    │  (LLM + Tool Calls)  │   │  (DAG + State Mgmt) │
    └──────────┬──────────┘   └──────────┬──────────┘
               │                          │
    ┌──────────▼──────────────────────────▼──────────┐
    │               Integration Layer                  │
    │  Gmail │ Slack │ Notion │ Airtable │ HubSpot    │
    │  Stripe │ LinkedIn │ Twitter │ Webhook │ S3      │
    └─────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/yourorg/ai-autopilot.git
cd ai-autopilot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Fill in your API keys and integration credentials
```

### 3. Run Your First Agent

```bash
# Run a single agent
python -m src.agents.email_agent --mode triage --dry-run

# Start the full autopilot scheduler
python -m src.orchestrator start

# Launch the dashboard
python -m src.api.server
```

### 4. Open the Dashboard

Navigate to `http://localhost:8000` to view the live agent dashboard.

---

## Project Structure

```
ai-autopilot/
├── src/
│   ├── agents/              # Individual AI agent implementations
│   │   ├── base_agent.py    # Abstract base class for all agents
│   │   ├── email_agent.py   # Email triage + auto-reply
│   │   ├── lead_agent.py    # Lead scoring + CRM routing
│   │   ├── content_agent.py # Content generation + scheduling
│   │   ├── report_agent.py  # KPI reports + PDF generation
│   │   ├── invoice_agent.py # Invoice monitoring + follow-ups
│   │   ├── support_agent.py # Tier-1 support handling
│   │   └── research_agent.py# Deep research + briefing
│   ├── workflows/           # Multi-step workflow definitions
│   │   ├── lead_pipeline.py
│   │   ├── content_calendar.py
│   │   └── client_onboarding.py
│   ├── integrations/        # Third-party service connectors
│   │   ├── gmail.py
│   │   ├── slack.py
│   │   ├── notion.py
│   │   ├── hubspot.py
│   │   ├── stripe.py
│   │   └── airtable.py
│   ├── api/                 # REST API + Dashboard backend
│   │   ├── server.py
│   │   ├── routes/
│   │   └── websocket.py
│   ├── utils/               # Shared utilities
│   │   ├── llm.py           # LLM client wrapper (Anthropic/OpenAI)
│   │   ├── memory.py        # Agent memory + context management
│   │   ├── logger.py        # Structured logging
│   │   └── retry.py         # Retry + backoff utilities
│   ├── config/
│   │   ├── settings.py      # Pydantic settings model
│   │   └── agents.yaml      # Agent configuration
│   └── orchestrator.py      # Main scheduler/orchestrator
├── tests/
├── docs/
├── scripts/
├── .github/workflows/
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## Configuration

All agents are configured via `src/config/agents.yaml`:

```yaml
agents:
  email_agent:
    enabled: true
    schedule: "*/15 * * * *"   # Every 15 minutes
    max_emails_per_run: 50
    auto_reply: true
    escalation_threshold: 0.7

  lead_agent:
    enabled: true
    schedule: "0 9 * * 1-5"    # 9am weekdays
    min_score_to_route: 65
    crm_target: hubspot
```

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/new-agent`)
3. Write tests for new agents
4. Submit a PR with a clear description

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for full guidelines.

---

## License

MIT © CodeBeez / Abid Redwan. See [LICENSE](LICENSE) for details.
