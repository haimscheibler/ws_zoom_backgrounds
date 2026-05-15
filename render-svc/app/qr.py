"""QR code rendering for the "clickable" CTA workaround.

Zoom virtual backgrounds are pure pixels — there's no way to embed a real
hyperlink. The standard escape hatch is a QR code: viewer scans with their
phone, phone opens the URL. This is what the Tier 2 spec in the project
plan calls out as "QR overlay" — we render it as a small element near the
nametag or composited into the banner.

Output is a `data:image/png;base64,…` URL so the template doesn't need any
network round-trip during render — same approach as `_inline_image()` in
render.py.
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import qrcode
from qrcode.constants import ERROR_CORRECT_M

log = logging.getLogger(__name__)

# Pixel size of each "module" (cell) in the rendered QR. With box_size=10 and
# border=2, a typical-length URL renders as a roughly 330×330 PNG, which
# scales cleanly to the ~180×180 slot we use in the template.
DEFAULT_BOX_SIZE = 10
DEFAULT_BORDER = 2


def render_qr_data_uri(
    url: str,
    *,
    fill: str = "#0a1626",
    bg: str = "#ffffff",
) -> str:
    """Return a data: URL containing a PNG QR encoding `url`.

    Returns "" on empty input or generation failure — caller treats that
    as "no QR available, render without it" rather than failing the whole
    pipeline.

    Error-correction level M (15%) is the right tradeoff for video: high
    enough that a participant's phone camera can scan from across a room
    even with motion blur, low enough that the rendered QR isn't gigantic
    for long URLs.
    """
    if not url:
        return ""
    try:
        qr = qrcode.QRCode(
            error_correction=ERROR_CORRECT_M,
            box_size=DEFAULT_BOX_SIZE,
            border=DEFAULT_BORDER,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill, back_color=bg)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        log.warning("QR render failed for %s: %s", url[:60], e)
        return ""


def render_qr_png_bytes(
    url: str,
    *,
    fill: str = "#0a1626",
    bg: str = "#ffffff",
) -> Optional[bytes]:
    """Variant that returns raw PNG bytes — used by banner.py when it needs
    to paste a QR into a larger Pillow composite instead of inlining as a
    data URL."""
    if not url:
        return None
    try:
        qr = qrcode.QRCode(
            error_correction=ERROR_CORRECT_M,
            box_size=DEFAULT_BOX_SIZE,
            border=DEFAULT_BORDER,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill, back_color=bg)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        log.warning("QR png bytes render failed for %s: %s", url[:60], e)
        return None
