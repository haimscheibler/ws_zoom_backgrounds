"""Demo-meeting storage — JSON file, atomic writes, same pattern as
campaigns.py and uploads.py.

Persistence model matches what the Tier 3 calendar-trigger architecture
will store eventually: a list of upcoming meetings with their attendees +
rendered background state. For now, meetings are seeded manually (or via
/meetings/seed); when Google Calendar OAuth is wired in, the same model
just gets populated from calendar polls instead.

NOT FOR PRODUCTION: no auth, single-tenant, disk JSON. Same upgrade path
as the other stores (GCS + Firestore) when shipping past the demo.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .models import Meeting, MeetingAttendee, MeetingCreate

log = logging.getLogger(__name__)

DEFAULT_STORE_PATH = Path(__file__).parent / ".meetings.json"


def _store_path() -> Path:
    p = os.environ.get("MEETINGS_STORE", "")
    return Path(p) if p else DEFAULT_STORE_PATH


def _read_all() -> list[dict]:
    p = _store_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("meetings: store read failed (%s); starting empty", e)
        return []


def _write_all(items: list[dict]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(p.parent), delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(items, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(p)


# ── CRUD ─────────────────────────────────────────────────────────────────

def list_all() -> list[Meeting]:
    raw = _read_all()
    out: list[Meeting] = []
    for item in raw:
        try:
            out.append(Meeting(**item))
        except Exception as e:
            log.warning("meetings: skipping malformed entry %s: %s",
                        item.get("id"), e)
    # Soonest-first — UI puts "next up" at the top.
    out.sort(key=lambda m: m.start_time)
    return out


def get(meeting_id: str) -> Optional[Meeting]:
    for m in list_all():
        if m.id == meeting_id:
            return m
    return None


def create(payload: MeetingCreate) -> Meeting:
    now = int(time.time())
    m = Meeting(
        id=str(uuid.uuid4()),
        title=payload.title.strip(),
        start_time=payload.start_time,
        duration_minutes=payload.duration_minutes,
        attendees=payload.attendees,
        welcome_template=payload.welcome_template,
        plate=payload.plate,
        created_at=now,
        updated_at=now,
    )
    items = _read_all()
    items.append(m.model_dump())
    _write_all(items)
    log.info("meetings: created %s (%s)", m.id, m.title)
    return m


def update(meeting_id: str, **fields: Any) -> Optional[Meeting]:
    """Partial update — only provided fields change. updated_at bumped.
    Render-state fields (render_status, rendered_mp4_url, etc.) flow
    through here too so the render orchestrator doesn't need a separate
    writer."""
    items = _read_all()
    for i, item in enumerate(items):
        if item.get("id") != meeting_id:
            continue
        for k, v in fields.items():
            item[k] = v
        item["updated_at"] = int(time.time())
        items[i] = item
        _write_all(items)
        return Meeting(**item)
    return None


def delete(meeting_id: str) -> bool:
    items = _read_all()
    new_items = [m for m in items if m.get("id") != meeting_id]
    if len(new_items) == len(items):
        return False
    _write_all(new_items)
    log.info("meetings: deleted %s", meeting_id)
    return True


def clear_all() -> int:
    """Drop every meeting. Used by the seed endpoint to reset before
    inserting fresh demo data. Returns the count removed."""
    items = _read_all()
    _write_all([])
    log.info("meetings: cleared %d entries", len(items))
    return len(items)


# ── Demo seed ────────────────────────────────────────────────────────────

# Pre-built fictional-but-realistic meetings. Times are *relative* to call
# time so the demo always feels "right now" — first meeting starts in 4
# minutes (great for showing the "next up" highlight), then staggered
# throughout the day. Email addresses use real public-company domains so
# the Apollo + brand-scrape path produces real, recognisable logos.
SEED_TEMPLATES: list[dict] = [
    {
        "title": "Stripe / WiseStamp — Q2 partnership intro",
        "minutes_from_now": 4,
        "duration_minutes": 30,
        "attendees": [
            {"name": "Patrick Collison", "email": "patrick@stripe.com"},
            {"name": "John Collison", "email": "john@stripe.com"},
        ],
        "welcome_template": "Welcome, {company} team! 👋",
    },
    {
        "title": "Anthropic — design review",
        "minutes_from_now": 95,
        "duration_minutes": 45,
        "attendees": [
            {"name": "Dario Amodei", "email": "dario@anthropic.com"},
        ],
        "welcome_template": "Great to be back, {company}! 👋",
    },
    {
        "title": "HubSpot expansion call",
        "minutes_from_now": 240,  # 4 hours
        "duration_minutes": 30,
        "attendees": [
            {"email": "leadership@hubspot.com"},
        ],
        "welcome_template": "Welcome, {company} team!",
    },
    {
        "title": "Shopify Plus — pilot kickoff",
        "minutes_from_now": -45,  # already ended — shows the "past" state
        "duration_minutes": 30,
        "attendees": [
            {"email": "partnerships@shopify.com"},
        ],
        "welcome_template": "Welcome, {company} crew! 👋",
    },
]


def seed_demo_meetings() -> list[Meeting]:
    """Replace the store with a fresh set of demo meetings whose start
    times are relative to *now*. Idempotent for demo purposes — calling
    twice gives the same set of meetings, just shifted to current time."""
    clear_all()
    now = int(time.time())
    out: list[Meeting] = []
    for t in SEED_TEMPLATES:
        out.append(create(MeetingCreate(
            title=t["title"],
            start_time=now + (t["minutes_from_now"] * 60),
            duration_minutes=t["duration_minutes"],
            attendees=[MeetingAttendee(**a) for a in t["attendees"]],
            welcome_template=t["welcome_template"],
        )))
    return out
