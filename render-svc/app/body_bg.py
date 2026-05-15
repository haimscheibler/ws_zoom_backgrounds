"""Extract the company homepage's computed `body { background-color }`.

Used by the "Match Website" plate. We can't just regex the homepage HTML
because most modern sites set body bg via external CSS or CSS-in-JS — we
need a real browser to compute it. Playwright is already a dep (for video
recording), so we reuse it.

The extraction is cached per domain on disk so repeat /generate calls for
the same company don't re-spin Chromium. Cache is small (one line per
domain), gitignored alongside .apollo_cache.json.

Failure modes that fall back to "" (caller uses the default plate):
  - homepage unreachable / Chromium crash
  - extracted color is rgba(0,0,0,0) or "transparent" (most sites)
  - extracted color is pure white (#ffffff) — no point creating a third
    plate that's identical to the built-in `white` one
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path(__file__).parent / ".body_bg_cache.json"
EXTRACT_TIMEOUT_MS = 12_000
CACHE_TTL_SECONDS = 7 * 24 * 3600  # weekly — companies redesign rarely


def _read_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


_RGBA_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)",
    re.I,
)


def _parse_to_hex(css_color: str) -> str:
    """Convert what `getComputedStyle` returns (always `rgb(...)` or
    `rgba(...)`) to a 6-digit hex. Reject transparent and near-white. The
    near-white reject is opinionated: the auto plate's whole point is to
    differentiate from the built-in `white` plate; if the site IS white,
    the user can just pick `white` directly."""
    if not css_color:
        return ""

    m = _RGBA_RE.match(css_color.strip())
    if not m:
        return ""

    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
    a = float(m.group(4)) if m.group(4) else 1.0
    if a < 0.2:
        return ""  # transparent — falls through to default plate

    # Near-white reject — anything brighter than ~#f5f5f5 is "close enough
    # to white" that we'd be cluttering the picker with a duplicate.
    if min(r, g, b) > 245:
        return ""

    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def extract_body_bg(domain: str, *, cache_path: Path = DEFAULT_CACHE_PATH) -> str:
    """Return a `#rrggbb` for the homepage body's bg, or "" if not usable.

    Synchronous Playwright. Safe to call from a worker thread. Caller is
    responsible for falling back to a default plate on "" return."""
    if not domain:
        return ""

    cache = _read_cache(cache_path)
    cached = cache.get(domain.lower())
    if cached and (time.time() - cached.get("ts", 0)) < CACHE_TTL_SECONDS:
        log.debug("body-bg cache hit: %s = %s", domain, cached.get("hex"))
        return cached.get("hex", "")

    hex_value = ""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            # Try https with www first; cheap retry on raw bare-domain if
            # the www variant 404s. We use `domcontentloaded` rather than
            # `networkidle` — body bg is set by the time DOM is parsed, and
            # `networkidle` adds 3-5s on sites with analytics pixels.
            for url in (
                f"https://www.{domain}",
                f"https://{domain}",
            ):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=EXTRACT_TIMEOUT_MS)
                    css_color = page.evaluate(
                        "() => getComputedStyle(document.body).backgroundColor"
                    )
                    hex_value = _parse_to_hex(css_color or "")
                    if hex_value:
                        break
                except Exception as e:
                    log.debug("body-bg goto %s failed: %s", url, e)
            browser.close()
    except Exception as e:
        log.warning("body-bg extract failed for %s: %s", domain, e)

    cache[domain.lower()] = {"hex": hex_value, "ts": int(time.time())}
    _write_cache(cache_path, cache)
    log.info("body-bg %s → %s", domain, hex_value or "(unusable)")
    return hex_value
