"""Per-meeting render scheduler — STUB.

The scheduling loop:
  every minute:
    for each user with a connected calendar:
      events = google.list_upcoming(token, lookahead=600)
            + microsoft.list_upcoming(token, lookahead=600)
      for event in events:
        if not already rendered for this event:
          attendee = attendees.resolve(event.attendees, ...)
          if attendee.primary_domain:
            render_for_meeting(user, event, attendee.primary_domain)
            mark as rendered

Real implementation needs persistent state:
  - User → calendar tokens (Firestore or Postgres)
  - Event ID → render state (rendered? URL? pushed to Zoom?)
  - The scheduler itself needs to run somewhere with timer guarantees —
    Cloud Run can't do internal cron, so this typically becomes a
    Cloud Scheduler hitting an internal `/tick` endpoint every 60s,
    OR a separate worker on Cloud Run Jobs.

This stub exposes the function signature only — implementation deferred
until OAuth + state storage are wired.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def tick() -> dict:
    """One scheduler iteration. Returns a summary of work done this tick
    so it can be logged / surfaced in a monitoring dashboard:

        {
          "users_checked": int,
          "events_found": int,
          "renders_dispatched": int,
          "skipped_already_rendered": int,
        }

    Called by Cloud Scheduler every minute, or by a worker loop locally.
    """
    log.info("scheduler.tick() called — calendar integration not yet implemented")
    return {
        "users_checked": 0,
        "events_found": 0,
        "renders_dispatched": 0,
        "skipped_already_rendered": 0,
        "status": "stub",
    }


def render_for_meeting(
    user_id: str,
    event_id: str,
    primary_domain: str,
) -> None:
    """Kick off a /generate render targeted at this specific meeting.

    Inputs come pre-resolved by `attendees.resolve()`:
      - user_id: the AE / employee whose background we're updating
      - event_id: stable calendar event identifier
      - primary_domain: the external company we're personalising for

    Produces an MP4 + (later) pushes it to the user's Zoom client via
    `zoom_app.push_virtual_background()`.
    """
    raise NotImplementedError(
        "Per-meeting render dispatch not implemented yet. "
        "See ARCHITECTURE.md → 'Data flow per meeting' section."
    )
