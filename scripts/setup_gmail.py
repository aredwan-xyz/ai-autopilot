#!/usr/bin/env python3
"""
Gmail OAuth Setup Script

Run this once to authenticate your Google account and generate credentials.
Requires: credentials/client_secret.json (download from Google Cloud Console)

Usage:
    python scripts/setup_gmail.py
"""

import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.labels",
]

CLIENT_SECRET = Path("credentials/client_secret.json")
TOKEN_FILE = Path("credentials/google_token.json")


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("❌ Missing dependencies. Run: pip install google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    if not CLIENT_SECRET.exists():
        print(f"❌ Missing: {CLIENT_SECRET}")
        print("\nTo set up Gmail access:")
        print("1. Go to https://console.cloud.google.com")
        print("2. Create a project and enable the Gmail API")
        print("3. Create OAuth 2.0 credentials (Desktop App)")
        print("4. Download and save as credentials/client_secret.json")
        sys.exit(1)

    TOKEN_FILE.parent.mkdir(exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json())
    print(f"✅ Gmail authenticated! Token saved to {TOKEN_FILE}")
    print("\nYou can now run the email agent:")
    print("  python -m src.agents.email_agent --dry-run")


if __name__ == "__main__":
    main()
