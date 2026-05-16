"""Microsoft Graph (Calendar) read-only integration — STUB.

Real implementation steps:
  1. Add `msal` (Microsoft Authentication Library) to requirements
  2. Use the **on-behalf-of** flow for delegated access:
     GET /me/events?$filter=start/dateTime ge {now} and start/dateTime le {now+10m}
  3. Persist refresh tokens via MSAL's token cache (in-memory or disk)
"""
from __future__ import annotations

import os

from . import CalendarEvent


CLIENT_ID_ENV = "MICROSOFT_OAUTH_CLIENT_ID"
CLIENT_SECRET_ENV = "MICROSOFT_OAUTH_CLIENT_SECRET"
TENANT_ENV = "MICROSOFT_OAUTH_TENANT_ID"  # "common" for multi-tenant
SCOPES = ["Calendars.Read", "User.Read"]


def is_configured() -> bool:
    return bool(
        os.environ.get(CLIENT_ID_ENV, "").strip()
        and os.environ.get(CLIENT_SECRET_ENV, "").strip()
    )


def start_oauth_flow(redirect_uri: str, state: str) -> str:
    raise NotImplementedError(
        "Microsoft Graph OAuth not implemented — see ARCHITECTURE.md for "
        f"setup. Need: {CLIENT_ID_ENV}, {CLIENT_SECRET_ENV}, {TENANT_ENV}."
    )


def handle_oauth_callback(code: str, state: str, redirect_uri: str) -> dict:
    raise NotImplementedError(
        "Microsoft Graph OAuth not implemented — see ARCHITECTURE.md."
    )


def list_upcoming(
    refresh_token: str,
    *,
    lookahead_seconds: int = 600,
    max_results: int = 25,
) -> list[CalendarEvent]:
    raise NotImplementedError(
        "Microsoft Graph event listing not implemented — see ARCHITECTURE.md."
    )
