"""Calendar integration stubs — Google Calendar + Microsoft Graph.

Read-only access to a user's upcoming meetings, used by `scheduler.py` to
trigger per-meeting personalised renders 5 minutes before each meeting
starts.

Everything in this package is a stub: the function signatures and data
models are real, but actual OAuth flows + API calls raise
`NotImplementedError` until the external accounts are registered. See
ARCHITECTURE.md (repo root) for the setup checklist.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CalendarEvent:
    """One upcoming meeting, normalised across calendar providers."""
    event_id: str
    title: str
    start_unix: int          # UTC, seconds since epoch
    end_unix: int
    organiser_email: str
    attendees: list[str] = field(default_factory=list)
    description: str = ""
    location: str = ""       # may be a Zoom join URL or physical location
    source: str = ""         # "google" | "microsoft"
