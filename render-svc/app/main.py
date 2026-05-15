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
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import photo as photo_mod
from .apollo import enrich as apollo_enrich
from .brand_scraper import BrandAssets, brand_from_apollo, scrape_brand
from .models import BackgroundRequest, BackgroundResponse
from .render import OUTPUT_DIR_DEFAULT, render_background

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("render-svc")

app = FastAPI(title="WiseStamp Zoom Backgrounds — Render Service")

# Local dev: Next.js on :3000 calls FastAPI on :8080. In production the two
# would share a domain and CORS could be locked down further.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR") or OUTPUT_DIR_DEFAULT)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


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

    loop_seconds = int(os.environ.get("LOOP_SECONDS", "10"))
    fps = int(os.environ.get("VIDEO_FPS", "30"))

    # 5. Render (CPU-bound — Playwright + ffmpeg).
    result = await loop.run_in_executor(
        None,
        render_background,
        req.full_name, effective_title, brand, None, loop_seconds, fps,
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
    )
