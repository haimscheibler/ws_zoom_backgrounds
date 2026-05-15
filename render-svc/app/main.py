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

from .brand_scraper import scrape_brand
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

    # Brand scrape is HTTP-bound (homepage fetch + logo fetch); run off-loop.
    brand = await loop.run_in_executor(None, scrape_brand, domain)
    log.info("    brand: company=%s logo=%s color=%s",
             brand.company_name, bool(brand.logo_url), brand.brand_color)

    loop_seconds = int(os.environ.get("LOOP_SECONDS", "10"))
    fps = int(os.environ.get("VIDEO_FPS", "30"))

    # Render is CPU-bound (Playwright + ffmpeg); run off-loop.
    result = await loop.run_in_executor(
        None,
        render_background,
        req.full_name, req.title, brand, None, loop_seconds, fps,
    )

    return BackgroundResponse(
        slug=result.slug,
        mp4_url=_public_url(f"/output/{result.mp4_path.name}"),
        poster_url=_public_url(f"/output/{result.poster_path.name}"),
        company_name=brand.company_name or domain,
        domain=domain,
        logo_url=brand.logo_url,
        brand_color=brand.brand_color,
    )
