# Integration Setup Guide

Quick reference for connecting each third-party service.

---

## Gmail

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project → Enable the **Gmail API**
3. Create **OAuth 2.0 credentials** (Desktop App type)
4. Download and save as `credentials/client_secret.json`
5. Run the setup script:

```bash
python scripts/setup_gmail.py
```

This opens a browser for OAuth consent and saves the token to `credentials/google_token.json`.

---

## Slack

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. Add these **Bot Token Scopes**: `chat:write`, `files:write`, `channels:read`
3. Install to your workspace and copy the **Bot User OAuth Token**
4. Add to `.env`:

```
SLACK_BOT_TOKEN=xoxb-your-token
```

5. Invite the bot to your channels:
   - `#autopilot-alerts`
   - `#autopilot-leads`
   - `#content-review`
   - `#autopilot-reports`

---

## Notion

1. Go to [notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create a new integration → Copy the **Internal Integration Token**
3. Create databases for: Leads, Content Calendar, Reports
4. Share each database with your integration (click Share → Invite)
5. Copy each database ID from the URL

```
NOTION_API_KEY=secret_xxxx
NOTION_DATABASE_ID_LEADS=your-db-id
NOTION_DATABASE_ID_CONTENT=your-db-id
```

---

## HubSpot

1. Go to **Settings** → **Integrations** → **Private Apps**
2. Create a private app with scopes: `crm.objects.contacts.write`, `crm.objects.deals.read`
3. Copy the **Access Token**

```
HUBSPOT_ACCESS_TOKEN=pat-na1-xxxx
```

---

## Stripe

1. Go to [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys)
2. Copy your **Secret Key** (use test key for development)
3. For webhooks: create an endpoint pointing to `https://yourdomain.com/webhooks/stripe`

```
STRIPE_SECRET_KEY=sk_live_xxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxx
```

---

## Airtable

1. Go to [airtable.com/create/tokens](https://airtable.com/create/tokens)
2. Create a token with scopes: `data.records:read`, `data.records:write`
3. Copy your **Base ID** from the API docs page of your base

```
AIRTABLE_API_KEY=pat-xxxx
AIRTABLE_BASE_ID=appXXXXXXXX
```

---

## Testing Integrations

After configuring, run the health check script:

```bash
python scripts/check_integrations.py
```

This will test each configured integration and report connection status.
