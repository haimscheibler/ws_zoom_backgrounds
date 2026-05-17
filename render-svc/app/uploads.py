"""User-uploaded plate images and pre-rendered banner images.

Two flavours:

  - **Custom plates** are catalogued (appear in /plates alongside the
    built-in presets so users can re-select them later). Metadata stored in
    `.custom_plates.json`; image bytes in `static/uploads/plates/`.

  - **Banner images** are single-use uploads the user drops into a
    BannerConfig.image_url. No metadata — just bytes on disk that the
    /generate path inlines at render time.

File storage on local disk is fine for MVP — same caveat as
`campaigns.json`: a Cloud Run cold start wipes the container's writable
layer, so this needs migrating to GCS + Firestore before production.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import tempfile
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

# Co-located under static/ so the existing /uploads StaticFiles mount can
# serve them via HTTP for the picker thumbnails.
APP_DIR = Path(__file__).parent
UPLOADS_DIR = APP_DIR / "static" / "uploads"
PLATES_DIR = UPLOADS_DIR / "plates"
BANNERS_DIR = UPLOADS_DIR / "banners"
PLATES_STORE = APP_DIR / ".custom_plates.json"

# 10 MB cap — generous for 1920×1080 PNGs / JPEGs, blocks pathological
# uploads. Backgrounds bigger than this almost certainly have an issue we
# don't want to silently accept.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _ensure_dirs() -> None:
    PLATES_DIR.mkdir(parents=True, exist_ok=True)
    BANNERS_DIR.mkdir(parents=True, exist_ok=True)


def _ext_for(filename: str, content_type: str) -> str:
    """Pick a sane extension. Browsers don't always set Content-Type
    accurately, and `filename` can be anything — combine signals."""
    # Filename hint first
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return suffix
    # Fall back to content-type
    guessed = mimetypes.guess_extension(content_type or "image/png") or ".png"
    return guessed if guessed != ".jpe" else ".jpg"


# ── Custom plates ────────────────────────────────────────────────────────

def _read_plates_store() -> list[dict]:
    if not PLATES_STORE.exists():
        return []
    try:
        return json.loads(PLATES_STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log.warning("custom plates: store read failed (%s); starting empty", e)
        return []


def _write_plates_store(items: list[dict]) -> None:
    # Atomic via tmp + rename — same pattern as campaigns.py
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(PLATES_STORE.parent),
        delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(items, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)
    tmp_path.replace(PLATES_STORE)


def save_plate_upload(
    raw_bytes: bytes,
    *,
    filename: str,
    content_type: str,
    label: str,
) -> dict:
    """Persist a new custom plate. Returns its metadata record."""
    _ensure_dirs()
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"file too large ({len(raw_bytes)} > {MAX_UPLOAD_BYTES})")

    plate_id = uuid.uuid4().hex[:12]
    ext = _ext_for(filename, content_type)
    rel_path = f"plates/{plate_id}{ext}"
    abs_path = UPLOADS_DIR / rel_path
    abs_path.write_bytes(raw_bytes)

    record = {
        "id": plate_id,
        "label": (label.strip() or filename or "Custom plate")[:60],
        "path": str(abs_path),                  # for render-time file:// inline
        "url": f"/uploads/{rel_path}",          # for /plates picker thumbnail
        "content_type": content_type or "image/png",
        "created_at": int(time.time()),
    }
    items = _read_plates_store()
    items.append(record)
    _write_plates_store(items)
    log.info("custom plate uploaded: %s (%s)", plate_id, record["label"])
    return record


def list_custom_plates() -> list[dict]:
    """Return all custom-uploaded plates, newest-first."""
    items = _read_plates_store()
    items.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return items


def get_custom_plate(plate_id: str) -> dict | None:
    for r in _read_plates_store():
        if r.get("id") == plate_id:
            return r
    return None


def delete_custom_plate(plate_id: str) -> bool:
    items = _read_plates_store()
    target = next((r for r in items if r.get("id") == plate_id), None)
    if target is None:
        return False
    new_items = [r for r in items if r.get("id") != plate_id]
    _write_plates_store(new_items)
    # Best-effort file cleanup. Don't fail if the file is already gone —
    # the metadata removal is the authoritative deletion.
    try:
        Path(target["path"]).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("custom plate file cleanup failed: %s", e)
    log.info("custom plate deleted: %s", plate_id)
    return True


# ── Pre-rendered banner uploads ──────────────────────────────────────────
# Not catalogued; user uploads in the moment, the URL flows into
# BannerConfig.image_url and gets inlined at render time.

def save_banner_upload(
    raw_bytes: bytes,
    *,
    filename: str,
    content_type: str,
) -> dict:
    """Persist a pre-built banner image. Returns id + url for the caller
    to wire into BannerConfig.image_url."""
    _ensure_dirs()
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"file too large ({len(raw_bytes)} > {MAX_UPLOAD_BYTES})")

    banner_id = uuid.uuid4().hex[:12]
    ext = _ext_for(filename, content_type)
    rel_path = f"banners/{banner_id}{ext}"
    abs_path = UPLOADS_DIR / rel_path
    abs_path.write_bytes(raw_bytes)
    log.info("banner uploaded: %s", banner_id)
    return {
        "id": banner_id,
        "url": f"/uploads/{rel_path}",
        "path": str(abs_path),
    }


def get_banner_path(url: str) -> Path | None:
    """Resolve a `/uploads/banners/X.ext` URL back to a server file path
    for render-time inlining. Returns None if the URL is malformed or the
    file is gone."""
    if not url.startswith("/uploads/banners/"):
        return None
    rel = url[len("/uploads/"):]
    p = UPLOADS_DIR / rel
    return p if p.exists() else None
