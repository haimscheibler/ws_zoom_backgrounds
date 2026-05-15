"""Brand asset extraction: logo URL, company name, dominant brand color."""
from __future__ import annotations

import colorsys
import io
import logging
import random
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from colorthief import ColorThief

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# Rotated on rate-limit retries to evade per-UA blocks.
ALT_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]
HTTP_TIMEOUT = 10
DEFAULT_BRAND_COLOR = "#005afd"  # WiseStamp blue, used when extraction fails


@dataclass
class BrandAssets:
    domain: str
    company_name: str
    logo_url: str  # absolute URL or empty string
    brand_color: str  # #RRGGBB
    socials: dict[str, str] = field(default_factory=dict)  # {"linkedin": url, "x": url, ...}


# Patterns for extracting prospect-company social handles from homepage links.
# Excludes share/intent URLs, which look like real profile links but aren't.
_SOCIAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("linkedin",  re.compile(r"linkedin\.com/(?:company|in|school|showcase)/[^/?#\s]+", re.I)),
    ("twitter",   re.compile(r"(?:twitter\.com|x\.com)/(?!intent|share|home)[A-Za-z0-9_]{1,15}\b", re.I)),
    ("facebook",  re.compile(r"facebook\.com/(?!sharer|dialog|tr|plugins)[^/?#\s]+", re.I)),
    ("instagram", re.compile(r"instagram\.com/(?!p|explore|reel)[^/?#\s]+", re.I)),
    ("youtube",   re.compile(r"youtube\.com/(?:c|channel|user|@)[^/?#\s]+", re.I)),
]
# Fixed render order — independent of where icons appear in the homepage HTML.
_SOCIAL_RENDER_ORDER = ["linkedin", "twitter", "facebook", "instagram", "youtube"]


def _extract_socials(soup: BeautifulSoup, base_url: str) -> dict[str, str]:
    """First-match-wins extraction of social handles from anchor tags. Returned
    dict is in `_SOCIAL_RENDER_ORDER` so the template renders consistently."""
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        absolute = urljoin(base_url, a["href"].strip())
        for kind, pat in _SOCIAL_PATTERNS:
            if kind in found:
                continue
            if pat.search(absolute):
                found[kind] = absolute
        if len(found) == len(_SOCIAL_PATTERNS):
            break
    return {k: found[k] for k in _SOCIAL_RENDER_ORDER if k in found}


_BROWSERY_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Intentionally not advertising "br" — `requests` doesn't natively decode
    # brotli, and a server that picks it leaves us with binary garbage.
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def _fetch(url: str, *, allow_insecure: bool = True, quiet: bool = False) -> requests.Response | None:
    """GET a URL with sane defaults. On SSL cert errors, retry with verify=False.
    On 403/429 (rate-limit / anti-bot), retry up to 2 times with rotating User-
    Agents and short backoff — this catches transient Cloudflare-style blocks
    without committing to a full headless browser fallback. When `quiet` is True,
    expected failures are logged at DEBUG instead of WARNING."""
    fail_log = log.debug if quiet else log.warning
    uas = [USER_AGENT, *ALT_USER_AGENTS]

    last_status: int | None = None
    for attempt, ua in enumerate(uas[:3]):  # 1 primary + up to 2 retries
        headers = {"User-Agent": ua, **_BROWSERY_HEADERS}
        try:
            r = requests.get(url, timeout=HTTP_TIMEOUT, headers=headers, allow_redirects=True)
            if r.status_code in (403, 429):
                last_status = r.status_code
                # Brief jittered backoff before next UA (skip on final attempt)
                if attempt < 2:
                    time.sleep(0.4 + random.random() * 0.6)
                continue
            r.raise_for_status()
            if attempt > 0:
                log.debug("fetch %s succeeded after %d retries (UA rotation)", url, attempt)
            return r
        except requests.exceptions.SSLError as e:
            if not allow_insecure:
                fail_log("SSL fetch failed %s: %s", url, e)
                return None
            fail_log("SSL error on %s — retrying without cert verification", url)
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(url, timeout=HTTP_TIMEOUT, headers=headers, allow_redirects=True, verify=False)
                r.raise_for_status()
                return r
            except requests.RequestException as e2:
                fail_log("insecure fetch also failed %s: %s", url, e2)
                return None
        except requests.RequestException as e:
            fail_log("fetch failed %s: %s", url, e)
            return None

    fail_log("fetch failed %s: status=%s after UA rotation", url, last_status)
    return None


def _fetch_homepage(domain: str) -> requests.Response | None:
    """Try several URL variants until one resolves to a usable page."""
    candidates = [
        f"https://{domain}",
        f"https://www.{domain}" if not domain.startswith("www.") else None,
        f"http://{domain}",
        f"http://www.{domain}" if not domain.startswith("www.") else None,
    ]
    for url in [c for c in candidates if c]:
        page = _fetch(url)
        if page is not None and page.content:
            return page
    return None


def _try_external_logo(domain: str) -> str:
    """Last-resort logo lookup via public services. Returns the first URL that
    resolves to a real image. Note: Clearbit's logo.clearbit.com was retired
    after HubSpot's acquisition (DNS no longer resolves), so we use Google's
    favicon API. Quality is lower (64-128px) but coverage is universal. Swap
    to logo.dev with an API token for higher-resolution logos in production."""
    candidates = [
        f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
    ]
    for url in candidates:
        r = _fetch(url)
        if r is None:
            continue
        if not r.headers.get("content-type", "").lower().startswith("image/"):
            continue
        if len(r.content) < 200:  # filter tiny placeholders
            continue
        return url
    return ""


def _derive_name_from_domain(domain: str) -> str:
    """assetbuilt.com → 'Assetbuilt'; my-fence.com.au → 'My Fence'."""
    base = domain.split(".")[0]
    base = re.sub(r"[-_]+", " ", base)
    return " ".join(w.capitalize() for w in base.split() if w) or domain


def _extract_company_name(soup: BeautifulSoup, domain: str) -> str:
    def _is_urly(s: str) -> bool:
        # Some sites (e.g. caterpillar.com) set og:site_name or <title> to a
        # URL string. Reject those — fall through to the next candidate.
        return s.lower().startswith(("http://", "https://")) or "://" in s

    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        candidate = og["content"].strip()
        if candidate and not _is_urly(candidate):
            return candidate
    title = soup.find("title")
    if title and title.string:
        # Strip common separators like " | Home", " - Official Site"
        raw = title.string.strip()
        candidate = re.split(r"\s[\|\-–—:•·]\s", raw)[0].strip()
        if 2 <= len(candidate) <= 60 and not _is_urly(candidate):
            return candidate
    return _derive_name_from_domain(domain)


_LOGO_HINT_RE = re.compile(r"logo", re.I)
# Class/id values that strongly indicate THE company logo (vs a partner badge,
# certification icon, etc.). Matched as substring on the joined class+id blob.
_STRONG_LOGO_CLASSES = (
    "site-logo", "header-logo", "brand-logo", "company-logo",
    "main-logo", "masthead-logo", "navbar-logo", "navbar-brand",
)
# Words that look "logo-y" but aren't the brand: certification badges, partner
# logos, stock UI imagery, etc. Matched as substring on the full attrs blob.
_LOGO_STOPLIST = (
    "eho", "ada", "ssl", "secured", "verified", "partner", "sponsor",
    "imagebox", "placeholder", "spinner", "loading",
    # Sekisui's homepage embeds Tata + Enel partner-logos; skip those.
    "tata", "enel",
)


# Words that often appear in UI-element image filenames/alts and would falsely
# pass the "logo" hint check (e.g. play.svg with alt="logo-color"). Penalised
# in scoring rather than hard-rejected so a true `*-logo-*` image with one of
# these in the alt can still win on aggregate.
_LOGO_UI_PENALTY_WORDS = ("play", "btn", "button", "arrow", "chevron", "menu", "video", "search")


def _logo_score(img) -> float:
    """Rank an <img> as a logo candidate. Returns 0 if not a candidate at all
    (no 'logo' hint or stoplist match), otherwise a positive score where
    higher = more likely the brand logo. Caller picks the max."""
    blob = " ".join(str(img.get(k, "")) for k in ("class", "id", "alt", "src", "title")).lower()
    if not _LOGO_HINT_RE.search(blob):
        return 0.0
    if any(s in blob for s in _LOGO_STOPLIST):
        return 0.0

    src = (img.get("src") or "").lower()
    alt = (img.get("alt") or "").lower()
    cls_id = " ".join(img.get("class", []) or []).lower() + " " + (img.get("id") or "").lower()

    score = 1.0  # baseline for any non-rejected candidate

    if any(h in cls_id for h in _STRONG_LOGO_CLASSES):
        score += 5.0
    elif "logo" in cls_id.split():
        score += 2.0

    if "logo" in src:               # filename has "logo" — strong signal
        score += 3.0

    # UI-element penalty: filenames like play.svg, search-btn.png shouldn't
    # win even when their class/alt contains "logo" by coincidence.
    if any(w in src for w in _LOGO_UI_PENALTY_WORDS):
        score -= 3.0
    if any(w in alt for w in _LOGO_UI_PENALTY_WORDS):
        score -= 1.0

    return max(score, 0.0)


def _extract_logo_url(soup: BeautifulSoup, base_url: str) -> str:
    """Find the best brand-logo URL on the page.

    Priority is tuned for circular avatar display + brand-color extraction,
    where a square brand mark beats a wide wordmark and either beats
    `og:image` (almost always a hero/marketing photo on enterprise sites).
    """
    # 1. apple-touch-icon — square, high-res, designed-to-be-an-icon. Ideal
    #    for our circular slot. Skips letterboxing of wide wordmarks.
    ati = soup.find("link", rel=lambda v: v and "apple-touch-icon" in v.lower())
    if ati and ati.get("href"):
        return urljoin(base_url, ati["href"].strip())

    # 2. Score every <img> and take the best logo candidate. Inside <header>
    #    or <nav> gets a small bonus.
    candidates: list[tuple[float, str]] = []
    for img in soup.find_all("img", src=True):
        score = _logo_score(img)
        if score <= 0:
            continue
        if img.find_parent(["header", "nav"]):
            score += 1.0
        candidates.append((score, img["src"].strip()))
    if candidates:
        candidates.sort(key=lambda c: c[0], reverse=True)
        return urljoin(base_url, candidates[0][1])

    # 3. Standard favicon — a real brand mark at small size. Prefer this over
    #    og:image which is almost always a hero / marketing photo.
    icon = soup.find("link", rel=lambda v: v and "icon" in v.lower())
    if icon and icon.get("href"):
        return urljoin(base_url, icon["href"].strip())

    # 4. og:image — last resort. Some small/single-page sites set it to the
    #    actual logo, but most enterprise sites set it to a marketing hero.
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return urljoin(base_url, og["content"].strip())

    return ""


def _is_useful_color(rgb: tuple[int, int, int]) -> bool:
    """Reject near-white, near-black, and washed-out greys."""
    r, g, b = rgb
    brightness = r + g + b
    if brightness > 720 or brightness < 60:  # too white / too black
        return False
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return s > 0.2  # require some saturation


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


# --- WCAG contrast guard --------------------------------------------------

# Brand color is used for: name (large bold text), website link, and as a
# pill background under white social icons. All three need decent contrast
# against the white card background. WCAG calls 3:1 the minimum for large
# text and graphical UI elements, which matches our usage.
MIN_BRAND_CONTRAST = 3.0


def _hex_to_rgb01(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _relative_luminance(rgb01: tuple[float, float, float]) -> float:
    """WCAG 2.1 relative luminance (sRGB → linear → weighted sum)."""
    def _c(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (_c(c) for c in rgb01)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_against_white(rgb01: tuple[float, float, float]) -> float:
    return 1.05 / (_relative_luminance(rgb01) + 0.05)


def _ensure_contrast(hex_color: str, min_contrast: float = MIN_BRAND_CONTRAST) -> str:
    """If hex_color has poor contrast against white, darken it in HLS space
    until it passes. Hue + saturation are preserved — only lightness drops —
    so the brand identity stays recognisable (vivid yellow → dark mustard,
    not a generic dark fallback)."""
    if not hex_color:
        return hex_color
    rgb = _hex_to_rgb01(hex_color)
    if _contrast_against_white(rgb) >= min_contrast:
        return hex_color
    h, l, s = colorsys.rgb_to_hls(*rgb)
    for _ in range(40):
        l -= 0.025
        if l <= 0.05:
            break
        rgb = colorsys.hls_to_rgb(h, l, s)
        if _contrast_against_white(rgb) >= min_contrast:
            break
    return _rgb_to_hex(tuple(int(round(c * 255)) for c in rgb))


# --------------------------------------------------------------------------


_SVG_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_SVG_RGB_RE = re.compile(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", re.I)
# Common CSS named colors that show up in SVG fills. Keep the list short —
# enterprise logos overwhelmingly use hex/rgb. We resolve names to RGB so the
# usual `_is_useful_color` filter applies.
_SVG_NAMED_COLORS = {
    "red": (255, 0, 0), "green": (0, 128, 0), "blue": (0, 0, 255),
    "navy": (0, 0, 128), "teal": (0, 128, 128), "orange": (255, 165, 0),
    "purple": (128, 0, 128), "yellow": (255, 255, 0),
}


def _extract_svg_brand_color(svg_bytes: bytes) -> str:
    """Pull the dominant brand color from an SVG by counting color references.

    SVG logos are a special case: ColorThief can't decode them (they're XML,
    not raster), but the colors are right there in `fill=`, `stroke=`,
    `<stop stop-color>`, and inline `style=` attributes. Count occurrences,
    drop near-white/black/grey via the same filter we use for raster logos,
    and return the most-frequent useful color.
    """
    try:
        text = svg_bytes.decode("utf-8", errors="replace")
    except Exception:
        return DEFAULT_BRAND_COLOR

    candidates: list[tuple[int, int, int]] = []

    for m in _SVG_HEX_RE.finditer(text):
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        try:
            candidates.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
        except ValueError:
            continue

    for m in _SVG_RGB_RE.finditer(text):
        try:
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if all(0 <= c <= 255 for c in (r, g, b)):
                candidates.append((r, g, b))
        except ValueError:
            continue

    # Light pass over named colors — only inside fill/stroke contexts so we
    # don't pick up "blue" mentions in <title> text.
    for ctx_match in re.finditer(r'(?:fill|stroke)\s*=\s*"([a-zA-Z]+)"', text):
        name = ctx_match.group(1).lower()
        if name in _SVG_NAMED_COLORS:
            candidates.append(_SVG_NAMED_COLORS[name])

    if not candidates:
        return DEFAULT_BRAND_COLOR

    from collections import Counter
    counts = Counter(candidates).most_common()
    for rgb, _ in counts:
        if _is_useful_color(rgb):
            return _rgb_to_hex(rgb)
    # Nothing passed the saturation/brightness filter — return the most
    # common color (probably white/grey/black; downstream contrast guard
    # will darken it if needed).
    return _rgb_to_hex(counts[0][0]) if counts else DEFAULT_BRAND_COLOR


def _looks_like_svg(image_bytes: bytes) -> bool:
    """Quick content sniff — works regardless of HTTP Content-Type, which
    some CDNs mislabel."""
    head = image_bytes[:512].lstrip().lower()
    return head.startswith(b"<svg") or head.startswith(b"<?xml") and b"<svg" in head


def _extract_brand_color(image_bytes: bytes) -> str:
    if _looks_like_svg(image_bytes):
        return _extract_svg_brand_color(image_bytes)
    try:
        thief = ColorThief(io.BytesIO(image_bytes))
        palette = thief.get_palette(color_count=6, quality=5)
    except Exception as e:
        log.warning("color extraction failed: %s", e)
        return DEFAULT_BRAND_COLOR

    for rgb in palette:
        if _is_useful_color(rgb):
            return _rgb_to_hex(rgb)
    # Fall back to dominant if nothing passes the filter
    return _rgb_to_hex(palette[0]) if palette else DEFAULT_BRAND_COLOR


def scrape_brand(domain: str) -> BrandAssets:
    """Best-effort brand extraction. Always returns a usable BrandAssets."""
    if not domain:
        return BrandAssets("", "", "", DEFAULT_BRAND_COLOR)

    page = _fetch_homepage(domain)
    company_name = ""
    logo_url = ""
    socials: dict[str, str] = {}

    if page is not None:
        # Pass raw bytes — BeautifulSoup's UnicodeDammit handles encoding
        # detection better than `requests`, which defaults to ISO-8859-1
        # when the server omits a charset (corrupts UTF-8: "•" → "â€¢").
        soup = BeautifulSoup(page.content, "lxml")
        company_name = _extract_company_name(soup, domain)
        logo_url = _extract_logo_url(soup, str(page.url))
        socials = _extract_socials(soup, str(page.url))

    if not company_name:
        company_name = _derive_name_from_domain(domain)

    if not logo_url:
        fallback = _try_external_logo(domain)
        if fallback:
            log.info("using external logo fallback for %s", domain)
            logo_url = fallback

    brand_color = DEFAULT_BRAND_COLOR
    if logo_url:
        img = _fetch(logo_url)
        if img is not None and img.content:
            brand_color = _extract_brand_color(img.content)

    # Some logos are white-on-transparent (designed for dark-themed headers,
    # e.g. Sekisui's PNG wordmark). Color extraction returns the default in
    # that case. Try the favicon as a backup color source — favicons are
    # typically the brand mark in actual brand colors, even when the main
    # logo is monochrome.
    if brand_color == DEFAULT_BRAND_COLOR and page is not None:
        fav = soup.find("link", rel=lambda v: v and "icon" in v.lower())
        fav_url = urljoin(str(page.url), fav["href"].strip()) if fav and fav.get("href") else ""
        if fav_url and fav_url != logo_url:
            fav_img = _fetch(fav_url, quiet=True)
            if fav_img is not None and fav_img.content:
                fallback_color = _extract_brand_color(fav_img.content)
                if fallback_color != DEFAULT_BRAND_COLOR:
                    log.info("    brand color: logo gave no color, used favicon → %s",
                             fallback_color)
                    brand_color = fallback_color

    # Final guard: if the extracted color would render as illegible text or
    # under-contrast pill, darken until WCAG-compliant. Hue is preserved.
    safe_color = _ensure_contrast(brand_color)
    if safe_color != brand_color:
        log.info("    brand color %s darkened to %s for contrast", brand_color, safe_color)
    brand_color = safe_color

    return BrandAssets(
        domain=domain,
        company_name=company_name,
        logo_url=logo_url,
        brand_color=brand_color,
        socials=socials,
    )


def brand_from_apollo(enrichment, domain: str) -> BrandAssets | None:
    """Build BrandAssets directly from Apollo's organization block.

    Returns None if Apollo had no usable org data (caller should fall through
    to scrape_brand). Otherwise returns a fully-populated BrandAssets:
      - company_name, logo_url, socials  → straight from Apollo
      - brand_color                      → ColorThief on Apollo's logo image,
                                           with WCAG contrast guard
      - socials missing from Apollo (instagram/youtube) → omitted; the template
                                           just doesn't render those icons

    Apollo's logo URL is hosted on its own AWS CDN (zenprospect-production
    bucket), so it's stable and won't 403 or rotate like LinkedIn URLs.
    """
    org_name = (enrichment.company_name or "").strip()
    logo_url = (enrichment.org_logo_url or "").strip()
    if not org_name and not logo_url:
        return None  # Apollo had no org block — caller should scrape

    socials: dict[str, str] = {}
    if enrichment.org_linkedin_url:
        socials["linkedin"] = enrichment.org_linkedin_url
    if enrichment.org_twitter_url:
        socials["twitter"] = enrichment.org_twitter_url
    if enrichment.org_facebook_url:
        socials["facebook"] = enrichment.org_facebook_url

    brand_color = DEFAULT_BRAND_COLOR
    if logo_url:
        img = _fetch(logo_url, quiet=True)
        if img is not None and img.content:
            brand_color = _extract_brand_color(img.content)

    safe_color = _ensure_contrast(brand_color)
    if safe_color != brand_color:
        log.info("    brand color %s darkened to %s for contrast",
                 brand_color, safe_color)
    brand_color = safe_color

    return BrandAssets(
        domain=domain,
        company_name=org_name or _derive_name_from_domain(domain),
        logo_url=logo_url,
        brand_color=brand_color,
        socials=socials,
    )
