"""HTML/CSS animated template → 1920×1080 H.264 MP4 loop for Zoom.

Pipeline:
  1. Jinja2 renders the template with brand data → temp HTML file.
  2. Playwright headless Chromium loads the HTML at a fixed 1920×1080 viewport
     and records to WebM (VP8) via `record_video_dir`.
  3. We hold the page open for exactly LOOP_SECONDS, then close — that flushes
     and finalises the WebM segment.
  4. imageio-ffmpeg transcodes WebM → MP4 (H.264, yuv420p, faststart) which
     Zoom accepts as a virtual background. Also extracts the first frame as
     a poster PNG for the frontend preview.

Why CSS-animation-then-record rather than baking per-frame GIFs (as
Automated_Email_Signatures does): Zoom flattens GIFs to a static image, and
authoring in CSS means designers can iterate in a browser instead of editing
Pillow frame-blending code.

Seamless loop: every @keyframes block uses matched `0%, 100%` states. Recording
exactly one animation period (LOOP_SECONDS) guarantees the last frame matches
the first, regardless of when in the cycle recording starts.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import imageio_ffmpeg
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .brand_scraper import BrandAssets, _fetch  # _fetch handles UA rotation + SSL fallback

log = logging.getLogger(__name__)

VIEWPORT_W = 1920
VIEWPORT_H = 1080
DEFAULT_LOOP_SECONDS = 10
DEFAULT_FPS = 30
# Playwright's `record_video` starts recording the moment the page is created —
# which is before HTML parses and paints. That yields ~0.5-1.0s of white frames
# at the head of the WebM. We record extra and trim it off in the transcode.
WARMUP_SECONDS = 1.0

TEMPLATE_DIR = Path(__file__).parent / "templates"
OUTPUT_DIR_DEFAULT = Path(__file__).parent / "static" / "output"

_jinja = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(("html", "j2")),
)


@dataclass
class RenderResult:
    slug: str
    mp4_path: Path
    poster_path: Path


def _make_slug(full_name: str, domain: str) -> str:
    """Filesystem-safe, human-readable, time-suffixed slug. The timestamp
    suffix prevents two concurrent renders for the same person colliding on
    output filenames — important once we have more than one user."""
    base = f"{full_name}_{domain}".lower()
    base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_")
    return f"{base[:50]}_{int(time.time())}"


def _inline_image(url: str, *, label: str = "image") -> str:
    """Fetch image bytes and return a `data:` URL so the template doesn't
    depend on a network round-trip during render. Chromium's `networkidle`
    is inconsistent at picking up remote `<img>` fetches from a `file://`
    page; inlining sidesteps the problem and also future-proofs against
    CDNs that 403 on a headless browser UA (LinkedIn's photo URLs in
    particular).

    Returns "" on fetch failure rather than the raw URL — for the watermark
    we'd rather omit a layer than have a half-loaded broken image flash
    through the recording window. The caller decides how to fall back."""
    if not url:
        return ""
    resp = _fetch(url, quiet=True)
    if resp is None or not resp.content:
        log.warning("%s fetch failed for inlining: %s", label, url[:80])
        return ""

    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not ctype.startswith("image/"):
        # Some CDNs mislabel; guess from extension as a last resort.
        guessed, _ = mimetypes.guess_type(url)
        ctype = guessed if (guessed or "").startswith("image/") else "image/png"

    b64 = base64.b64encode(resp.content).decode("ascii")
    return f"data:{ctype};base64,{b64}"


def _render_html(
    full_name: str,
    title: str,
    brand: BrandAssets,
    plate_css: str,
    photo_url: str,
) -> str:
    """Render the background template.

    `photo_url` and `brand.logo_url` independently drive the corner
    watermark. The template uses a `brand_mark_mode` flag to pick the
    correct animation:
      both       — slow photo↔logo crossfade (10s loop)
      photo      — photo with a subtle scale pulse
      logo       — logo with a subtle scale pulse (legacy behaviour)
      none       — corner watermark omitted entirely
    The mode is computed here rather than in the template so the gate
    logic in main.py and the visual logic stay in sync."""
    inlined_logo = _inline_image(brand.logo_url, label="logo")
    inlined_photo = _inline_image(photo_url, label="photo")

    if inlined_photo and inlined_logo:
        mode = "both"
    elif inlined_photo:
        mode = "photo"
    elif inlined_logo:
        mode = "logo"
    else:
        mode = "none"
    log.info("    brand mark mode: %s", mode)

    tpl = _jinja.get_template("background.html.j2")
    return tpl.render(
        full_name=full_name,
        title=title,
        company_name=brand.company_name or brand.domain,
        logo_url=inlined_logo,
        photo_url=inlined_photo,
        brand_mark_mode=mode,
        brand_color=brand.brand_color,
        plate_css=plate_css,
    )


def _record_webm(html_path: Path, video_dir: Path, loop_seconds: int) -> Path:
    """Open the HTML in headless Chromium, hold for `loop_seconds`, return
    the WebM that Playwright wrote. Runs sync inside the calling thread —
    the FastAPI handler dispatches this via `run_in_executor`."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        # `--autoplay-policy=no-user-gesture-required` would matter if we add
        # <video>/<audio>; harmless to leave off for CSS-only animations.
        browser = pw.chromium.launch(
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        context = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            record_video_dir=str(video_dir),
            record_video_size={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=1,  # actual pixel match, no retina upscaling
        )
        page = context.new_page()
        # `networkidle` ensures the logo image has loaded — otherwise the
        # first second of video would be a blank logo plate.
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle", timeout=20_000)

        # Record WARMUP + loop_seconds. The warmup chunk is trimmed during
        # the ffmpeg transcode (it contains the pre-paint white flash). The
        # CSS animations are 10s loops so the residual phase shift is fine —
        # any contiguous 10s slice of the WebM is a valid seamless loop.
        page.wait_for_timeout(int((WARMUP_SECONDS + loop_seconds) * 1000) + 300)

        # Closing the context finalises the video file.
        context.close()
        browser.close()

    # Playwright names the file with a random hash; grab whatever WebM landed.
    candidates = sorted(video_dir.glob("*.webm"))
    if not candidates:
        raise RuntimeError("Playwright did not produce a video file")
    return candidates[-1]


def _transcode_to_mp4(webm_path: Path, mp4_path: Path, loop_seconds: int, fps: int) -> None:
    """WebM (VP8) → MP4 (H.264) via the bundled imageio-ffmpeg binary.

    Settings chosen for Zoom:
      - yuv420p          required by Zoom (and QuickTime); WebM's yuva420p
                         breaks playback otherwise
      - crf 20           visually lossless at 1080p for this kind of soft
                         gradient content; output stays around 3-5 MB
      - faststart        moov atom at the front → instant playback in the
                         browser <video> preview
      - -t LOOP_SECONDS  hard-trim in case Playwright recorded a few extra
                         frames past close()
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        # `-ss` BEFORE `-i` is fast input-seek: skips the pre-paint white
        # frames cheaply by jumping past them in the demuxer.
        "-ss", str(WARMUP_SECONDS),
        "-i", str(webm_path),
        "-t", str(loop_seconds),
        "-vf", f"fps={fps},scale={VIEWPORT_W}:{VIEWPORT_H}:flags=lanczos",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-crf", "20",
        "-preset", "medium",
        "-movflags", "+faststart",
        "-an",  # no audio track — Zoom backgrounds don't use sound
        str(mp4_path),
    ]
    log.info("transcoding %s → %s", webm_path.name, mp4_path.name)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.error("ffmpeg stderr:\n%s", proc.stderr[-2000:])
        raise RuntimeError(f"ffmpeg transcode failed (exit {proc.returncode})")


def _extract_poster(mp4_path: Path, poster_path: Path) -> None:
    """First-frame PNG, used as the `<video poster>` in the preview UI so the
    user sees the background instantly without waiting for the MP4 to buffer."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-i", str(mp4_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(poster_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log.warning("poster extract failed:\n%s", proc.stderr[-500:])


def render_background(
    full_name: str,
    title: str,
    brand: BrandAssets,
    plate_css: str,
    photo_url: str = "",
    output_dir: Optional[Path] = None,
    loop_seconds: int = DEFAULT_LOOP_SECONDS,
    fps: int = DEFAULT_FPS,
) -> RenderResult:
    """Top-level entry point. Synchronous; safe to call from a thread."""
    out_dir = output_dir or Path(os.environ.get("OUTPUT_DIR") or OUTPUT_DIR_DEFAULT)
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _make_slug(full_name, brand.domain or "unknown")
    mp4_path = out_dir / f"{slug}.mp4"
    poster_path = out_dir / f"{slug}.png"

    html = _render_html(full_name, title, brand, plate_css, photo_url)

    with tempfile.TemporaryDirectory(prefix="zoombg_") as tmp:
        tmp_path = Path(tmp)
        html_path = tmp_path / "background.html"
        html_path.write_text(html, encoding="utf-8")

        video_dir = tmp_path / "video"
        video_dir.mkdir()

        webm_path = _record_webm(html_path, video_dir, loop_seconds)
        _transcode_to_mp4(webm_path, mp4_path, loop_seconds, fps)
        _extract_poster(mp4_path, poster_path)

        # Defensive: remove the WebM if it somehow ended up in out_dir
        shutil.rmtree(video_dir, ignore_errors=True)

    log.info("rendered %s (%.1f MB)", mp4_path.name, mp4_path.stat().st_size / 1e6)
    return RenderResult(slug=slug, mp4_path=mp4_path, poster_path=poster_path)
