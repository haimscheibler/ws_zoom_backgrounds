"""Zoom Marketplace App integration — STUB.

Goal: push a rendered MP4 URL into a user's Zoom virtual-background slot
so it auto-applies the next time they join a meeting.

Required Zoom setup (Marketplace developer account):
  - App type: Server-to-Server OAuth (no per-user OAuth needed for
    organisations using the SCIM/SSO flow; for individual users we'd
    add user-level OAuth)
  - Scopes: user:write:settings:virtual_backgrounds, user:read:user
  - Env vars: ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET, ZOOM_ACCOUNT_ID

API reference:
  https://developers.zoom.us/docs/api/users/#tag/users/POST/users/{userId}/settings/virtual_backgrounds

Note: Zoom requires the virtual background source URL to be HTTPS and
publicly reachable (their CDN fetches and stores a copy server-side).
Our MP4s live in GCS at `mktg.wisestamp.com/backgrounds/...` already —
that's the URL we pass through.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


CLIENT_ID_ENV = "ZOOM_CLIENT_ID"
CLIENT_SECRET_ENV = "ZOOM_CLIENT_SECRET"
ACCOUNT_ID_ENV = "ZOOM_ACCOUNT_ID"


@dataclass
class ZoomPushResult:
    success: bool
    zoom_background_id: str = ""
    error: str = ""


def is_configured() -> bool:
    return all(
        os.environ.get(k, "").strip()
        for k in (CLIENT_ID_ENV, CLIENT_SECRET_ENV, ACCOUNT_ID_ENV)
    )


def push_virtual_background(
    zoom_user_id: str,
    mp4_url: str,
    *,
    is_default: bool = True,
) -> ZoomPushResult:
    """Upload an MP4 URL to a Zoom user's virtual-background slot.

    `is_default=True` makes it the user's currently-active background;
    `False` adds it to their library but doesn't activate it (useful for
    the campaign-engine case where we want to seed a background ahead of
    time without surprise-changing what they're using).

    Returns success + Zoom's internal background ID (used to delete /
    update / re-activate later).
    """
    raise NotImplementedError(
        "Zoom Marketplace App push not implemented yet. "
        "See ARCHITECTURE.md → 'Required external accounts' §3."
    )


def remove_virtual_background(
    zoom_user_id: str,
    zoom_background_id: str,
) -> bool:
    """Delete a previously-pushed background from a Zoom user's library —
    used to clean up per-meeting backgrounds after the meeting ends, so
    the user's library doesn't fill with single-use Acme/Stripe/etc."""
    raise NotImplementedError(
        "Zoom Marketplace App cleanup not implemented yet."
    )
