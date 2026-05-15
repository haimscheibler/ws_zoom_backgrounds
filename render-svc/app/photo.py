"""Profile-photo resolution.

For Zoom backgrounds the photo is captured but not rendered (the user is on
camera). It's used as one of two signals for the quality gate: a generate
request is rejected if BOTH the company logo AND the photo are missing.

Chain (Apollo-first, like Automated_Email_Signatures):
  1. Apollo `photo_url` (already filtered for LinkedIn placeholder silhouettes
     in apollo.py)
  2. Gravatar by email md5 — only when Apollo gave us an email, and only if
     the gravatar actually exists (`?d=404` makes the service 404 on miss
     instead of returning a placeholder)

NOT included on purpose: UI-Avatars initials. The email-signatures pipeline
falls back to them because a signature can't be blank — but for the Zoom
background gate, initials would defeat the "real data" intent. If both
Apollo and Gravatar miss, the caller treats `photo_url=""` and falls through
to the gate check.
"""
from __future__ import annotations

import hashlib
import logging

import requests

log = logging.getLogger(__name__)

GRAVATAR_TIMEOUT = 4


def gravatar_url(email: str, size: int = 200) -> str:
    h = hashlib.md5(email.lower().strip().encode("utf-8")).hexdigest()
    # `d=404` → Gravatar returns 404 when the user has no avatar registered,
    # which is how we detect the miss and skip claiming we found a photo.
    return f"https://www.gravatar.com/avatar/{h}?s={size}&d=404"


def gravatar_exists(email: str) -> bool:
    if not email or "@" not in email:
        return False
    try:
        r = requests.head(
            gravatar_url(email, size=80),
            timeout=GRAVATAR_TIMEOUT,
            allow_redirects=True,
        )
        return r.status_code == 200
    except requests.RequestException:
        return False


def resolve_photo(apollo_photo_url: str, apollo_email: str) -> tuple[str, str]:
    """Return (url, source). Source is `apollo`, `gravatar`, or `none`.

    `none` is the signal to the caller that no real photo was found. The
    gate in main.py rejects renders where both `none` and "no logo" hold."""
    if apollo_photo_url:
        return apollo_photo_url, "apollo"
    if apollo_email and gravatar_exists(apollo_email):
        return gravatar_url(apollo_email), "gravatar"
    return "", "none"
