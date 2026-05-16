"""Persistent banner campaigns — the marketer-facing library that backs the
banner dropdown in the /generate form.

Storage is a single JSON file on disk. Atomic writes via temp-file rename
so concurrent requests can't observe a half-written campaigns list. Fine
for the MVP scale (dozens to low-hundreds of campaigns); upgrade to a
proper database (Firestore, Postgres) when (a) write contention becomes
an issue, (b) campaign auth / multi-tenant scopes are needed, or (c)
queryable history is needed.

NOTE: no authentication. In production the /campaigns CRUD endpoints
must sit behind admin auth — anyone with the URL today can edit anyone
else's campaign. Documented in README.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from .models import BannerConfig, Campaign

log = logging.getLogger(__name__)

DEFAULT_STORE_PATH = Path(__file__).parent / ".campaigns.json"


def _store_path() -> Path:
    """Path to the campaigns JSON file. CAMPAIGNS_STORE env var overrides
    for tests / per-environment isolation; defaults to a file next to the
    app code (gitignored)."""
    p = os.environ.get("CAMPAIGNS_STORE", "")
    return Path(p) if p else DEFAULT_STORE_PATH


def _read_all() -> list[dict]:
    p = _store_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("campaigns: store read failed (%s); starting empty", e)
        return []


def _write_all(items: list[dict]) -> None:
    """Atomic write: tmp-file in the same directory, then rename. Same
    directory ensures the rename is a same-filesystem operation (POSIX
    guarantees rename is atomic within a filesystem)."""
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(p.parent), delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(items, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(p)


# ── CRUD ───────────────────────────────────────────────────────────────────

def list_all() -> list[Campaign]:
    raw = _read_all()
    out: list[Campaign] = []
    for item in raw:
        try:
            out.append(Campaign(**item))
        except Exception as e:
            log.warning("campaigns: skipping malformed entry %s: %s",
                        item.get("id"), e)
    # Newest first — the marketer most often wants to edit what they just
    # created or use it in a /generate call.
    out.sort(key=lambda c: c.created_at, reverse=True)
    return out


def get(campaign_id: str) -> Optional[Campaign]:
    for c in list_all():
        if c.id == campaign_id:
            return c
    return None


def create(name: str, banner: BannerConfig, expires_at: str = "") -> Campaign:
    now = int(time.time())
    c = Campaign(
        id=str(uuid.uuid4()),
        name=name.strip(),
        banner=banner,
        created_at=now,
        updated_at=now,
        expires_at=expires_at or "",
    )
    items = _read_all()
    items.append(c.model_dump())
    _write_all(items)
    log.info("campaigns: created %s (%s)", c.id, c.name)
    return c


def update(
    campaign_id: str,
    *,
    name: Optional[str] = None,
    banner: Optional[BannerConfig] = None,
    expires_at: Optional[str] = None,
) -> Optional[Campaign]:
    items = _read_all()
    for i, item in enumerate(items):
        if item.get("id") == campaign_id:
            if name is not None:
                item["name"] = name.strip()
            if banner is not None:
                item["banner"] = banner.model_dump()
            if expires_at is not None:
                item["expires_at"] = expires_at
            item["updated_at"] = int(time.time())
            items[i] = item
            _write_all(items)
            log.info("campaigns: updated %s", campaign_id)
            return Campaign(**item)
    return None


def delete(campaign_id: str) -> bool:
    items = _read_all()
    new_items = [c for c in items if c.get("id") != campaign_id]
    if len(new_items) == len(items):
        return False
    _write_all(new_items)
    log.info("campaigns: deleted %s", campaign_id)
    return True
