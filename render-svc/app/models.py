"""Pydantic request/response schemas for the render service."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class BannerConfig(BaseModel):
    """Event-style promotional banner — ports the email-signature banner.py
    layout (eyebrow + title + date/location + CTA pill) to the bottom edge
    of the video frame.

    `cta_url` is the URL embedded as a QR code on the right end of the
    banner so meeting participants can "click" it from their phone. Without
    a cta_url the banner still renders but with no QR — useful for pure
    awareness pushes ("Hiring engineers!") where there's no booking link.

    When `image_url` is set (a path returned from `POST /uploads/banner`),
    we skip the text-composition path entirely and render the uploaded
    image at the banner slot. event_name remains required as a fallback
    so the form's validation stays consistent — but it's not used visually.
    """
    event_name: str = Field(min_length=1, max_length=80)
    event_dates: str = Field(default="", max_length=60)
    event_location: str = Field(default="", max_length=60)
    eyebrow: str = Field(default="MEET ME AT", max_length=40)
    cta_text: str = Field(default="LET'S MEET", max_length=20)
    cta_url: str = Field(default="", max_length=400)
    image_url: str = Field(default="", max_length=400)  # /uploads/banners/X.ext when uploaded


class Campaign(BaseModel):
    """A saved banner preset the marketer can reuse across renders.

    `expires_at` is an opaque string (ISO date or "") — when set, the
    frontend uses it to grey out / filter expired campaigns. The server
    doesn't enforce expiration at /generate time; treating it as a hint
    rather than a hard cutoff keeps last-minute "the banner expired
    overnight but we still need to send" cases unblocked.
    """
    id: str
    name: str  # marketer-facing label, e.g. "Q2 Gartner Push"
    banner: BannerConfig
    created_at: int  # unix seconds
    updated_at: int  # unix seconds
    expires_at: str = ""  # ISO date "YYYY-MM-DD" or "" for no expiry


class CampaignCreate(BaseModel):
    """Request body for POST /campaigns. id/created_at/updated_at are
    server-assigned, so the client doesn't supply them."""
    name: str = Field(min_length=1, max_length=80)
    banner: BannerConfig
    expires_at: str = Field(default="", max_length=20)


class BackgroundRequest(BaseModel):
    """Input for /generate.

    `company_url` accepts anything we can extract a domain from — a bare domain
    (acme.com), full URL (https://acme.com/about), or LinkedIn company URL is
    fine. We normalise downstream.

    `plate` picks the static background surface (see plates.py PRESETS). The
    brand watermark (logo + nametag) overlays on top. Unknown values fall
    back to the default plate rather than 400ing — keeps the API forgiving
    as we rename/retire plates over time.
    """
    full_name: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=120)
    company_url: str = Field(min_length=3, max_length=200)
    plate: str = Field(default="", max_length=40)

    # Standalone QR code toggle. Renders a small QR card mirroring the
    # nametag's position. If unset but Apollo gave us a linkedin_url for
    # this person, we default to that — the most common "connect with me"
    # use case. Set explicitly to "" with `qr_disabled=true` to hide.
    qr_url: str = Field(default="", max_length=400)
    qr_caption: str = Field(default="Scan to connect", max_length=40)
    qr_disabled: bool = False  # explicit opt-out to override the LinkedIn auto-default

    # Promotional banner along the bottom edge. None = no banner.
    banner: Optional[BannerConfig] = None


class BrandPreview(BaseModel):
    """Lightweight brand-scrape result for the front-end live preview.

    Skips Apollo entirely — this is meant to be cheap (one homepage fetch,
    ~500ms) and called interactively as the user types the company URL.
    The full /generate path still runs Apollo + the quality gate when the
    user actually clicks "Generate".
    """
    domain: str
    company_name: str
    logo_url: str
    brand_color: str


class PlateOption(BaseModel):
    """One entry in the GET /plates picker response. `css` is the same
    string the server uses when rendering — the front-end can paint
    accurate thumbnails by applying it to a div."""
    key: str
    label: str
    css: str
    text_on_light: bool
    image_attribution: str = ""  # surfaced in the picker tooltip for legal traceability
    is_custom: bool = False      # true for user-uploaded plates; lets the picker show a delete affordance


class BackgroundResponse(BaseModel):
    slug: str
    mp4_url: str            # served path or absolute URL (depending on PUBLIC_BASE_URL)
    poster_url: str         # first-frame PNG for the <video poster> preview
    company_name: str
    domain: str
    logo_url: str
    brand_color: str        # #RRGGBB, WCAG-darkened if needed

    # Enrichment metadata — captured for downstream features (corner-photo
    # crossfade, social-icon overlays) and exposed so the caller can see
    # which source filled each field.
    photo_url: str = ""
    photo_source: str = "none"      # apollo | gravatar | none
    linkedin_url: str = ""
    socials: dict[str, str] = {}    # {linkedin: url, twitter: url, ...}
    enrichment_source: str = ""     # apollo+scrape | apollo-only | scrape-only | none
    plate_key: str = ""             # which plate was applied (after fallback)
