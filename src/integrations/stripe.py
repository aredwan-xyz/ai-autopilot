"""Stripe Integration"""
from __future__ import annotations
from datetime import datetime
import structlog
from src.config.settings import settings

logger = structlog.get_logger("stripe")


class StripeClient:
    def __init__(self):
        self.log = logger

    def _get_stripe(self):
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe

    async def get_period_revenue(self, start: datetime, end: datetime) -> dict:
        stripe = self._get_stripe()
        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())

        try:
            charges = stripe.Charge.list(
                created={"gte": start_ts, "lte": end_ts},
                limit=100,
            )
            collected = sum(c.amount for c in charges.data if c.status == "succeeded") / 100

            invoices = stripe.Invoice.list(
                due_date={"lte": end_ts},
                status="open",
                limit=100,
            )
            outstanding = sum(i.amount_due for i in invoices.data) / 100

            subscriptions = stripe.Subscription.list(status="active", limit=100)
            mrr = sum(
                s.items.data[0].price.unit_amount * s.items.data[0].quantity
                for s in subscriptions.data
                if s.items.data and s.items.data[0].price.recurring
            ) / 100

            return {
                "collected": collected,
                "outstanding": outstanding,
                "mrr": mrr,
                "new_revenue": collected,
            }
        except Exception as e:
            self.log.error("stripe_revenue_failed", error=str(e))
            return {}
