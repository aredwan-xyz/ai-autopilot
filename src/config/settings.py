"""
Settings — Pydantic-based environment configuration.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    DEFAULT_LLM_PROVIDER: str = "anthropic"
    DEFAULT_MODEL: str = "claude-opus-4-5"

    # App
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "dev-secret-change-me"
    LOG_LEVEL: str = "INFO"
    DASHBOARD_PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./autopilot.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Google / Gmail
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_CREDENTIALS_FILE: str = "credentials/google_token.json"

    # Slack
    SLACK_BOT_TOKEN: str = ""
    SLACK_SIGNING_SECRET: str = ""
    SLACK_DEFAULT_CHANNEL: str = "#autopilot-alerts"

    # Notion
    NOTION_API_KEY: str = ""
    NOTION_DATABASE_ID_LEADS: str = ""
    NOTION_DATABASE_ID_CONTENT: str = ""

    # HubSpot
    HUBSPOT_ACCESS_TOKEN: str = ""
    HUBSPOT_PORTAL_ID: str = ""

    # Airtable
    AIRTABLE_API_KEY: str = ""
    AIRTABLE_BASE_ID: str = ""

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Reports
    REPORT_OUTPUT_DIR: str = "./reports"
    REPORT_RECIPIENTS: str = ""


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
