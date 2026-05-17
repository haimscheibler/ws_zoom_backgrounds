"""FastAPI entry point for the render service.

Endpoints:
  POST /generate    Brand-scrape + render personalised 1920×1080 MP4. Returns
                    paths the frontend uses to preview and download.
  GET  /output/*    Static file serving for rendered MP4s/posters during local
                    dev. In production these move behind a CDN.
  GET  /healthz     Liveness check.

The actual work runs synchronously inside `run_in_executor` because both
Playwright sync-API and ffmpeg subprocesses are blocking; the FastAPI event
loop stays free for other requests.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import campaigns as campaigns_mod
from . import meetings as meetings_mod
from . import photo as photo_mod
from . import plates as plates_mod
from . import uploads as uploads_mod
from .apollo import enrich as apollo_enrich
from .body_bg import extract_body_bg
from .brand_scraper import BrandAssets, brand_from_apollo, scrape_brand
from .calendar import attendees as attendees_mod
from .models import (
    BackgroundRequest,
    BackgroundResponse,
    BannerConfig,
    BrandPreview,
    Campaign,
    CampaignCreate,
    Meeting,
    MeetingCreate,
    MeetingRenderRequest,
    PlateOption,
    WelcomeState,
)
from .render import OUTPUT_DIR_DEFAULT, render_background

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("render-svc")

# Operator-facing startup banner: surfaces whether the Apollo path is wired
# so a deployment misconfiguration is visible in Cloud Run logs immediately,
# not 30 minutes later when someone reports gate-rejection rates spiking.
if os.environ.get("APOLLO_API_KEY", "").strip():
    log.info("Apollo enrichment ENABLED (APOLLO_API_KEY set)")
else:
    log.warning(
        "Apollo enrichment DISABLED (APOLLO_API_KEY missing). Brand data "
        "will rely on homepage scraping only — the quality gate (logo OR "
        "photo) will reject more requests than in the Apollo-enabled path."
    )

app = FastAPI(title="WiseStamp Zoom Backgrounds — Render Service")

# Local dev: Next.js on :3000 calls FastAPI on :8080. In production the two
# would share a domain and CORS could be locked down further.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR") or OUTPUT_DIR_DEFAULT)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

# User uploads (custom plates + banner images). Served as static files so
# the picker thumbnails resolve via plain HTTP. Render-time inlining
# bypasses this mount entirely and reads the file directly.
uploads_mod.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads",
    StaticFiles(directory=str(uploads_mod.UPLOADS_DIR)),
    name="uploads",
)


def _extract_domain(company_url: str) -> str:
    """Accept anything URL-shaped — bare domain, full URL, with or without
    scheme — and return a clean lowercase domain (no protocol, no path,
    no `www.`)."""
    raw = company_url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    netloc = urlparse(raw).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # Strip port if present
    netloc = netloc.split(":")[0]
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", netloc):
        raise ValueError(f"Could not parse a domain from {company_url!r}")
    return netloc


def _public_url(relative_path: str) -> str:
    """Returns a full URL when PUBLIC_BASE_URL is set (Cloud Run / deployed
    case); otherwise returns the relative path the Next.js dev proxy uses."""
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if base:
        return f"{base}{relative_path}"
    return relative_path


def _split_name(full_name: str) -> tuple[str, str]:
    """Split a free-form name into (first, last). Last name absorbs every
    token after the first — handles 'Mary Jane van der Berg' as
    ('Mary', 'Jane van der Berg'), which is what Apollo's matcher expects."""
    parts = full_name.strip().split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# ── Campaigns CRUD ──────────────────────────────────────────────────────────
# Banner library: marketers create named campaigns (Gartner June Push, Q2
# Hiring, etc.), then the /generate flow can reference a campaign id instead
# of passing the banner fields free-form. No auth in MVP — production must
# gate these endpoints behind admin auth.

@app.get("/campaigns", response_model=list[Campaign])
def list_campaigns() -> list[Campaign]:
    return campaigns_mod.list_all()


@app.post("/campaigns", response_model=Campaign, status_code=201)
def create_campaign(payload: CampaignCreate) -> Campaign:
    return campaigns_mod.create(
        name=payload.name, banner=payload.banner, expires_at=payload.expires_at,
    )


@app.get("/campaigns/{campaign_id}", response_model=Campaign)
def get_campaign(campaign_id: str) -> Campaign:
    c = campaigns_mod.get(campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return c


@app.put("/campaigns/{campaign_id}", response_model=Campaign)
def update_campaign(campaign_id: str, payload: CampaignCreate) -> Campaign:
    c = campaigns_mod.update(
        campaign_id,
        name=payload.name, banner=payload.banner, expires_at=payload.expires_at,
    )
    if c is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return c


@app.delete("/campaigns/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: str) -> None:
    if not campaigns_mod.delete(campaign_id):
        raise HTTPException(status_code=404, detail="campaign not found")


# ── Meetings (demo flow for the auto-updater) ────────────────────────────
# Each meeting carries its own attendee list + welcome template. The render
# orchestrator at /meetings/{id}/render resolves the primary external
# company from the attendees, scrapes its display name for the welcome
# message, then dispatches an internal /generate with a meeting-specific
# BannerConfig. The AE's own branding (logo, colours, photo) comes from
# the per-request MeetingRenderRequest — frontend stores it in localStorage.

@app.get("/meetings", response_model=list[Meeting])
def list_meetings() -> list[Meeting]:
    return meetings_mod.list_all()


@app.post("/meetings", response_model=Meeting, status_code=201)
def create_meeting(payload: MeetingCreate) -> Meeting:
    return meetings_mod.create(payload)


@app.get("/meetings/{meeting_id}", response_model=Meeting)
def get_meeting(meeting_id: str) -> Meeting:
    m = meetings_mod.get(meeting_id)
    if m is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    return m


@app.delete("/meetings/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: str) -> None:
    if not meetings_mod.delete(meeting_id):
        raise HTTPException(status_code=404, detail="meeting not found")


@app.post("/meetings/seed", response_model=list[Meeting])
def seed_meetings() -> list[Meeting]:
    """Replace the meetings store with a fresh batch of demo meetings whose
    start times are relative to *now*. Lets the demo always feel current
    without re-seeding the database manually."""
    return meetings_mod.seed_demo_meetings()


@app.post("/meetings/{meeting_id}/render", response_model=Meeting)
async def render_meeting(meeting_id: str, ae: MeetingRenderRequest) -> Meeting:
    """Render this meeting's personalised background.

    The full pipeline a real calendar-trigger would invoke:
      1. Resolve which external company the meeting is *with* (skip the
         AE's own colleagues; skip generic personal email domains; if
         multiple external companies are present, take the one with the
         most attendees).
      2. Brand-scrape the external company for a usable display name.
      3. Compose a banner with welcome_text rendered from the meeting's
         template (e.g., "Welcome, Acme team! 👋"), event_name set to
         the meeting title.
      4. Dispatch the existing /generate pipeline with the AE's own
         branding (their company URL drives colour/logo extraction).
      5. Persist the rendered MP4 URLs back on the meeting record so the
         UI can show ready/idle status without re-asking the server.
    """
    meeting = meetings_mod.get(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")

    meetings_mod.update(meeting_id, render_status="rendering", last_render_error="")

    try:
        # 1. AE's own domain — explicit override or derive from URL
        ae_domain = ae.own_domain or _extract_domain(ae.company_url)

        # 2. Resolve ALL external companies in the meeting (not just the
        #    primary). For a 1:1 with one external attendee, this returns
        #    a single company; for a multi-company call (e.g. partner +
        #    customer joint pitch), it returns one entry per company so
        #    each gets their own welcome banner painted in their own
        #    brand color.
        emails = [a.email for a in meeting.attendees]
        companies = attendees_mod.resolve_all(
            emails,
            organiser_email=f"{ae.full_name.lower().replace(' ', '.')}@{ae_domain}",
            organiser_company_domain=ae_domain,
        )
        # Title-derived fallback when there are no external attendees
        # (some meetings list nobody but the organiser). We still want a
        # banner pointing at the right company.
        if not companies:
            fallback = attendees_mod.resolve(
                emails,
                organiser_email=f"{ae.full_name.lower().replace(' ', '.')}@{ae_domain}",
                organiser_company_domain=ae_domain,
                event_title=meeting.title,
            )
            if fallback.primary_domain:
                companies = [attendees_mod.CompanyOnMeeting(
                    domain=fallback.primary_domain,
                    representative_email=fallback.primary_email,
                    attendee_count=0,
                )]
        if not companies:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Could not resolve an external company from the attendees. "
                    "Add at least one attendee whose email isn't your domain "
                    "or a personal-email provider."
                ),
            )
        log.info("    meeting %s: %d external companies → %s",
                 meeting_id, len(companies),
                 ", ".join(c.domain for c in companies))

        # 3. Brand-scrape each external company in parallel. We only need
        #    their display name + brand color — no full Apollo path. Done
        #    concurrently because each scrape is ~500ms of network and
        #    a 3-company meeting otherwise stacks 1.5s of sequential I/O.
        loop = asyncio.get_event_loop()

        async def _scrape(domain: str) -> tuple[str, str]:
            brand = await loop.run_in_executor(None, scrape_brand, domain)
            return brand.company_name or domain, brand.brand_color

        scraped = await asyncio.gather(
            *(_scrape(c.domain) for c in companies),
            return_exceptions=False,
        )

        # 4. Compose welcome states — one per external company. Each carries
        #    its own brand color so the banner background paints in their
        #    palette while their welcome is rotating in.
        welcome_states: list[WelcomeState] = []
        for company, (company_display, company_color) in zip(companies, scraped):
            welcome_states.append(WelcomeState(
                text=meeting.welcome_template.format(company=company_display),
                brand_color=company_color,
            ))

        # The "primary" company for response metadata = the most-represented
        # external company (first in the resolve_all sort order).
        primary_company_display = welcome_states[0].text
        primary_domain = companies[0].domain

        banner = BannerConfig(
            event_name=meeting.title,
            cta_text="LET'S CONNECT",
            cta_url=ae.qr_url,
            welcome_states=welcome_states,
        )

        # 5. Dispatch /generate with AE's branding
        bg_req = BackgroundRequest(
            full_name=ae.full_name,
            title=ae.title,
            company_url=ae.company_url,
            plate=meeting.plate or "office_studio",
            qr_url=ae.qr_url,
            qr_caption="Scan to connect",
            banner=banner,
        )
        result = await generate(bg_req)

        # 6. Persist render state
        # `primary_company_name` surfaces the most-represented external
        # company for the meetings-page UI badge ("Auto-detected company →
        # Stripe"). When the meeting has multiple companies, the UI can
        # show all of them later — for now we show the top one and the UI
        # can grow a "+N more" affordance.
        return meetings_mod.update(
            meeting_id,
            render_status="ready",
            rendered_at=int(time.time()),
            rendered_mp4_url=result.mp4_url,
            rendered_poster_url=result.poster_url,
            primary_company_name=scraped[0][0],
            primary_domain=primary_domain,
            last_render_error="",
        )
    except HTTPException as e:
        meetings_mod.update(meeting_id, render_status="failed",
                            last_render_error=str(e.detail))
        raise
    except Exception as e:
        log.exception("meeting render failed: %s", meeting_id)
        meetings_mod.update(meeting_id, render_status="failed",
                            last_render_error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/preview-brand", response_model=BrandPreview)
async def preview_brand(company_url: str) -> BrandPreview:
    """Fast brand scrape for the front-end live preview. No Apollo, no
    render — just homepage scrape (~500ms) for company_name + logo + brand
    color. Called as the user types the URL so the preview reflects real
    brand assets instead of placeholder colors."""
    try:
        domain = _extract_domain(company_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    loop = asyncio.get_event_loop()
    brand = await loop.run_in_executor(None, scrape_brand, domain)
    return BrandPreview(
        domain=domain,
        company_name=brand.company_name or domain,
        logo_url=brand.logo_url,
        brand_color=brand.brand_color,
    )


def _custom_plate_to_option(record: dict) -> PlateOption:
    """Convert a custom-upload record to a PlateOption for /plates.

    Picker CSS uses an absolute URL so the browser can fetch the image
    from the render-svc origin (not the Next.js origin where the picker
    runs). The same image is inlined as a data URL at render time —
    bypassing this URL entirely — so the thumbnail and the render are
    independent paths that both work.
    """
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not base:
        # In local dev the picker fetches the image directly from this
        # service's origin. Hard-code the local port so the picker still
        # works even when the front-end's NEXT_PUBLIC_RENDER_SVC and our
        # listen port get out of sync.
        base = "http://localhost:8080"
    image_url = f"{base}{record['url']}"
    return PlateOption(
        key=f"custom_{record['id']}",
        label=record["label"],
        css=(
            "background: linear-gradient(180deg, rgba(0,0,0,0.0) 0%, "
            "rgba(0,0,0,0.35) 100%), "
            f"url('{image_url}') center/cover no-repeat;"
        ),
        text_on_light=False,
        image_attribution="Custom upload",
        is_custom=True,
    )


@app.get("/plates", response_model=list[PlateOption])
def list_plates() -> list[PlateOption]:
    """Front-end picker source. Returns CSS strings the picker re-applies to
    DOM nodes to paint accurate thumbnails — keeps the server out of
    thumbnail-generation duty. Built-in presets come first; user-uploaded
    custom plates appended at the end (newest-first within that group)."""
    out = [
        PlateOption(
            key=p.key, label=p.label, css=p.css,
            text_on_light=p.text_on_light,
            image_attribution=p.image_attribution,
        )
        for p in plates_mod.PRESETS
    ]
    out.extend(_custom_plate_to_option(r) for r in uploads_mod.list_custom_plates())
    return out


# ── Custom plate uploads ────────────────────────────────────────────────────

@app.post("/upload/plate", response_model=PlateOption, status_code=201)
async def upload_plate(
    file: UploadFile = File(...),
    label: str = Form(""),
) -> PlateOption:
    """Multipart upload for a custom Zoom-background image. Stored on disk
    + catalogued in `.custom_plates.json`; appears in /plates afterwards
    and renders just like a built-in image plate."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="upload must be an image")
    raw = await file.read()
    try:
        record = uploads_mod.save_plate_upload(
            raw,
            filename=file.filename or "",
            content_type=file.content_type or "image/png",
            label=label,
        )
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    return _custom_plate_to_option(record)


@app.delete("/upload/plate/{plate_id}", status_code=204)
def delete_uploaded_plate(plate_id: str) -> None:
    if not uploads_mod.delete_custom_plate(plate_id):
        raise HTTPException(status_code=404, detail="custom plate not found")


# ── Pre-built banner uploads ─────────────────────────────────────────────────

@app.post("/upload/banner", status_code=201)
async def upload_banner(file: UploadFile = File(...)) -> dict:
    """One-shot upload for a pre-rendered banner image. The caller takes
    the returned `image_url` and stuffs it into BannerConfig.image_url
    on the /generate request — the render path will inline the bytes and
    composite the image at the bottom-edge banner slot."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="upload must be an image")
    raw = await file.read()
    try:
        rec = uploads_mod.save_banner_upload(
            raw,
            filename=file.filename or "",
            content_type=file.content_type or "image/png",
        )
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))
    return {"image_url": rec["url"], "id": rec["id"]}


@app.post("/generate", response_model=BackgroundResponse)
async def generate(req: BackgroundRequest) -> BackgroundResponse:
    try:
        domain = _extract_domain(req.company_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    log.info("generate: %s @ %s", req.full_name, domain)

    loop = asyncio.get_event_loop()
    first_name, last_name = _split_name(req.full_name)

    # 1. Apollo enrichment (HTTP-bound). Returns an empty object when the
    #    API key is unset or Apollo has no match — never raises.
    apollo = await loop.run_in_executor(
        None, apollo_enrich, first_name, last_name, domain,
    )
    log.info("    apollo: person=%s org=%s photo=%s logo=%s",
             apollo.found_person(), apollo.found_org(),
             bool(apollo.photo_url), bool(apollo.org_logo_url))

    # 2. Brand assets. Try Apollo's org block first — it's pre-curated and
    #    avoids a homepage scrape — then fall through to homepage scraping
    #    when Apollo didn't return an org, or returned one without a logo.
    def _build_brand() -> tuple[BrandAssets, str]:
        b = brand_from_apollo(apollo, domain) if apollo.found_org() else None
        if b is not None and b.logo_url:
            return b, "apollo"
        # Apollo missed or had no logo — scrape the homepage. If Apollo did
        # give us a company_name/socials, we don't lose them: the scrape
        # result replaces the BrandAssets wholesale, but logo + color come
        # from the homepage which is what we actually needed.
        return scrape_brand(domain), "scrape" if b is None else "scrape+apollo-org"

    brand, brand_source = await loop.run_in_executor(None, _build_brand)
    log.info("    brand: source=%s company=%s logo=%s color=%s",
             brand_source, brand.company_name, bool(brand.logo_url), brand.brand_color)

    # 3. Profile photo. Apollo first, then Gravatar via Apollo's email if
    #    we have one. UI-Avatars initials are NOT in the chain on purpose —
    #    initials would defeat the quality gate's intent.
    photo_url, photo_source = await loop.run_in_executor(
        None, photo_mod.resolve_photo, apollo.photo_url, apollo.email,
    )

    # 4. QUALITY GATE. Mirror the email-signatures intent: don't ship a
    #    branded artifact when we found neither a company logo nor a real
    #    profile photo for this person.
    if not brand.logo_url and not photo_url:
        log.warning("    GATE FAILED: no logo, no photo for %s @ %s",
                    req.full_name, domain)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not enrich {req.full_name} @ {domain}: Apollo had no "
                f"match and the company homepage didn't yield a logo. We "
                f"require at least a company logo or a profile photo to "
                f"generate a background. Try a different person, verify the "
                f"company URL, or check that APOLLO_API_KEY is set."
            ),
        )

    # Title: caller's input wins, fall back to Apollo's canonical title.
    effective_title = req.title or apollo.title

    # Merge socials — Apollo org socials + anything the scraper found.
    socials = dict(brand.socials)
    if apollo.linkedin_url and "linkedin" not in socials:
        # Person's LinkedIn is more useful than the org's for a personal bg.
        socials.setdefault("linkedin", apollo.linkedin_url)

    enrichment_source = (
        "apollo+scrape" if apollo.found_org() and brand_source.startswith("scrape")
        else "apollo" if brand_source == "apollo"
        else "scrape"
    )

    # Plate resolution. Three paths:
    #   - "custom_X": user-uploaded image; inline from disk
    #   - "auto":     scrape homepage body bg via Playwright
    #   - anything else: built-in preset (or fallback to default on miss)
    # `effective_plate_key` is what we surface in the response — distinct
    # from `plate.key` because the auto-plate fallback path mutates the
    # plate object but we want the response to show what the user asked for
    # when it matched, and the fallback's key when it didn't.
    plate_css: str
    effective_plate_key: str

    if req.plate.startswith("custom_"):
        custom_id = req.plate[len("custom_"):]
        record = uploads_mod.get_custom_plate(custom_id)
        if record:
            path = Path(record["path"])
            if path.exists():
                from .render import inline_image_from_path
                data_uri = inline_image_from_path(
                    path, record.get("content_type", "image/png"),
                )
                plate_css = (
                    "background: linear-gradient(180deg, rgba(0,0,0,0.0) 0%, "
                    "rgba(0,0,0,0.35) 100%), "
                    f"url('{data_uri}') center/cover no-repeat;"
                )
                effective_plate_key = req.plate
                log.info("    plate: %s (%s)", req.plate, record["label"])
            else:
                # Metadata exists but file is gone — surface the mismatch
                # in the log and fall back rather than silently 500'ing.
                fallback = plates_mod.get("")
                plate_css = fallback.css
                effective_plate_key = fallback.key
                log.warning("    plate: custom file missing, fallback → %s",
                            fallback.key)
        else:
            fallback = plates_mod.get("")
            plate_css = fallback.css
            effective_plate_key = fallback.key
            log.warning("    plate: custom_%s not found, fallback → %s",
                        custom_id, fallback.key)
    elif req.plate == plates_mod.AUTO_PLATE_KEY:
        resolved_hex = await loop.run_in_executor(None, extract_body_bg, domain)
        if resolved_hex:
            plate_css = f"background: {resolved_hex};"
            effective_plate_key = plates_mod.AUTO_PLATE_KEY
            log.info("    plate: auto → %s", resolved_hex)
        else:
            fallback = plates_mod.get("")
            plate_css = fallback.css
            effective_plate_key = fallback.key
            log.info("    plate: auto unusable, fallback → %s", fallback.key)
    else:
        plate = plates_mod.get(req.plate)
        plate_css = plate.css
        effective_plate_key = plate.key
        log.info("    plate: %s", plate.key)

    loop_seconds = int(os.environ.get("LOOP_SECONDS", "10"))
    fps = int(os.environ.get("VIDEO_FPS", "30"))

    # Standalone QR: caller's URL wins. When the caller leaves it blank and
    # hasn't explicitly disabled QR, we default to the person's Apollo
    # LinkedIn (most common "scan to connect" use case). qr_disabled lets
    # the caller turn it off entirely without having to send an empty URL.
    if req.qr_disabled:
        effective_qr_url = ""
    elif req.qr_url:
        effective_qr_url = req.qr_url
    else:
        effective_qr_url = apollo.linkedin_url
    if effective_qr_url:
        log.info("    qr: %s", effective_qr_url[:80])

    # 5. Render (CPU-bound — Playwright + ffmpeg).
    result = await loop.run_in_executor(
        None,
        render_background,
        req.full_name, effective_title, brand, plate_css, photo_url,
        effective_qr_url, req.qr_caption, req.banner,
        None, loop_seconds, fps,
    )

    return BackgroundResponse(
        slug=result.slug,
        mp4_url=_public_url(f"/output/{result.mp4_path.name}"),
        poster_url=_public_url(f"/output/{result.poster_path.name}"),
        company_name=brand.company_name or domain,
        domain=domain,
        logo_url=brand.logo_url,
        brand_color=brand.brand_color,
        photo_url=photo_url,
        photo_source=photo_source,
        linkedin_url=apollo.linkedin_url,
        socials=socials,
        enrichment_source=enrichment_source,
        plate_key=effective_plate_key,
    )
