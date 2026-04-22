"""Refresh the Threads long-lived token for another 60 days.

Meta's User Token Generator (2025+) issues long-lived (60 day) tokens directly,
so the traditional short→long exchange step is no longer needed. What remains
is a periodic refresh — call this script before the token ages past 60 days
and paste the new token into secrets/.env.

Usage:
    .venv/Scripts/python scripts/refresh_threads_token.py

Reads the current token from secrets/.env (THREADS_ACCESS_TOKEN), refreshes it,
and prints the new token + expiry + Threads User ID.

Docs: https://developers.facebook.com/docs/threads/get-started/long-lived-tokens
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

from aya_afi.config.settings import Settings

GRAPH_BASE = "https://graph.threads.net"


def main() -> int:
    env_path = Path(__file__).resolve().parent.parent / "secrets" / ".env"
    load_dotenv(env_path)
    settings = Settings()

    current = settings.threads_access_token
    if not current:
        print("THREADS_ACCESS_TOKEN missing in secrets/.env", file=sys.stderr)
        return 2

    with httpx.Client(timeout=15.0) as client:
        refresh = client.get(
            f"{GRAPH_BASE}/refresh_access_token",
            params={"grant_type": "th_refresh_token", "access_token": current},
        )
        if refresh.status_code != 200:
            print(f"refresh failed: {refresh.status_code} {refresh.text}", file=sys.stderr)
            return 1
        payload = refresh.json()
        new_token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 0))

        me = client.get(
            f"{GRAPH_BASE}/v1.0/me",
            params={"fields": "id,username", "access_token": new_token},
        )
        if me.status_code != 200:
            print(f"me lookup failed: {me.status_code} {me.text}", file=sys.stderr)
            return 1
        user = me.json()

    expiry = datetime.now(UTC) + timedelta(seconds=expires_in)
    print("=" * 70)
    print("Threads long-lived token refreshed")
    print("=" * 70)
    print(f"expires_in           : {expires_in} sec (~{expires_in // 86400} days)")
    print(f"new expiry (UTC)     : {expiry.isoformat(timespec='seconds')}")
    print(f"username             : {user.get('username')}")
    print(f"THREADS_USER_ID      : {user['id']}")
    print(f"THREADS_ACCESS_TOKEN : {new_token}")
    print("=" * 70)
    print("Paste the last two lines into secrets/.env (overwrite old values).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
