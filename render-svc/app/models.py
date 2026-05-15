"""Pydantic request/response schemas for the render service."""
from __future__ import annotations

from pydantic import BaseModel, Field


class BackgroundRequest(BaseModel):
    """Input for /generate.

    `company_url` accepts anything we can extract a domain from — a bare domain
    (acme.com), full URL (https://acme.com/about), or LinkedIn company URL is
    fine. We normalise downstream.
    """
    full_name: str = Field(min_length=1, max_length=80)
    title: str = Field(default="", max_length=120)
    company_url: str = Field(min_length=3, max_length=200)


class BackgroundResponse(BaseModel):
    slug: str
    mp4_url: str            # served path or absolute URL (depending on PUBLIC_BASE_URL)
    poster_url: str         # first-frame PNG for the <video poster> preview
    company_name: str
    domain: str
    logo_url: str
    brand_color: str        # #RRGGBB, WCAG-darkened if needed
