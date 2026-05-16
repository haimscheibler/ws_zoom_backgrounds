"""Google Calendar read-only integration — STUB.

Real implementation steps (once OAuth client is registered):
  1. Add `google-auth-oauthlib`, `google-api-python-client` to requirements
  2. Implement `start_oauth_flow()` to redirect to Google consent screen
  3. Implement `handle_oauth_callback()` to exchange code → tokens, persist
     per-user refresh token in render-svc's user store (TBD: SQLite or
     Firestore)
  4. Implement `list_upcoming()` using events().list with
     timeMin=now, timeMax=now+lookahead, singleEvents=True

See ARCHITECTURE.md for the OAuth app registration checklist.
"""
from __future__ import annotations

import os
from typing import Optional

from . import CalendarEvent


CLIENT_ID_ENV = "GOOGLE_OAUTH_CLIENT_ID"
CLIENT_SECRET_ENV = "GOOGLE_OAUTH_CLIENT_SECRET"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def is_configured() -> bool:
    """True when both env vars are set — call from /healthz to surface
    misconfiguration in monitoring before the first user tries to connect."""
    return bool(
        os.environ.get(CLIENT_ID_ENV, "").strip()
        and os.environ.get(CLIENT_SECRET_ENV, "").strip()
    )


def start_oauth_flow(redirect_uri: str, state: str) -> str:
    """Returns the Google consent URL the front-end redirects the user to.
    `state` is a CSRF token + user-id payload the callback verifies."""
    raise NotImplementedError(
        "Google Calendar OAuth not implemented yet — see ARCHITECTURE.md "
        f"for required setup. Need: {CLIENT_ID_ENV} + {CLIENT_SECRET_ENV} "
        "env vars and an OAuth client registered in Google Cloud Console."
    )


def handle_oauth_callback(
    code: str,
    state: str,
    redirect_uri: str,
) -> dict:
    """Exchange the auth code for tokens. Returns:
    {
      "user_email": str,
      "refresh_token": str,
      "expires_at": int,
    }
    Caller persists the refresh_token for future per-user calendar reads."""
    raise NotImplementedError(
        "Google Calendar OAuth not implemented yet — see ARCHITECTURE.md."
    )


def list_upcoming(
    refresh_token: str,
    *,
    lookahead_seconds: int = 600,
    max_results: int = 25,
) -> list[CalendarEvent]:
    """Pull events between now and now+lookahead_seconds using a stored
    refresh token. Returns normalised CalendarEvent objects."""
    raise NotImplementedError(
        "Google Calendar event listing not implemented yet — see "
        "ARCHITECTURE.md."
    )
