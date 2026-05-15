"""Pydantic request/response schemas for the render service."""
from __future__ import annotations

from pydantic import BaseModel, Field


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


class PlateOption(BaseModel):
    """One entry in the GET /plates picker response. `css` is the same
    string the server uses when rendering — the front-end can paint
    accurate thumbnails by applying it to a div."""
    key: str
    label: str
    css: str
    text_on_light: bool


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
