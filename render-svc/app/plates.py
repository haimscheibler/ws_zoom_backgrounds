"""Background plates — the static surface the brand watermark sits on top of.

A plate is just a CSS `background` declaration. The chosen plate fills the
full 1920×1080 frame as a static layer; the brand overlay (logo + nametag)
is rendered over it with its own subtle motion. Confining all motion to the
corners — away from the speaker's silhouette — is friendlier to Zoom's
person-segmentation algorithm than tinting the entire frame with drifting
gradients.

Plates are pure CSS for now (zero binary assets, no stock-image licensing
concerns). Image-based plates (real office photos, blueprints, etc.) can be
added by introducing a `bg_image` field and serving the file from
app/static/plates/.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plate:
    key: str
    label: str
    css: str          # complete CSS `background:` value used in the template
    text_on_light: bool
    # When set, the plate is image-backed: the CSS uses background-image
    # pointing at this URL, with a dark gradient overlay so the watermark
    # text stays legible against a busy photo. For production deployments
    # the user should mirror these images to their own CDN — the Unsplash
    # source URLs are stable but not contractually guaranteed.
    image_url: str = ""
    # Attribution shown nowhere in the rendered output, but logged at boot
    # so license requirements are traceable. Required for Unsplash photos.
    image_attribution: str = ""


AUTO_PLATE_KEY = "auto"


PRESETS: tuple[Plate, ...] = (
    Plate(
        key="white",
        label="White",
        css="background: #ffffff;",
        text_on_light=True,
    ),
    Plate(
        key="soft",
        label="Soft Studio",
        # Very subtle blue-grey gradient that mimics a softbox-lit wall —
        # reads as "professional video call" without committing to a specific
        # background scene.
        css=(
            "background: radial-gradient(ellipse 1800px 1200px at 50% 40%, "
            "#fbfcff 0%, #eef1f8 50%, #dde2ee 100%);"
        ),
        text_on_light=True,
    ),
    Plate(
        key="charcoal",
        label="Charcoal",
        css=(
            "background: radial-gradient(ellipse 1800px 1200px at 50% 50%, "
            "#1f2738 0%, #131826 50%, #0a0e1a 100%);"
        ),
        text_on_light=False,
    ),
    Plate(
        key="office_warm",
        label="Office Warm",
        # Approximates the warm cream/beige of a daylit office wall. Real
        # office stock photos can be wired in later as a `bg_image` field.
        css=(
            "background: radial-gradient(ellipse 1800px 1200px at 30% 30%, "
            "#f7ecdb 0%, #e8d4b3 50%, #c9b08a 100%);"
        ),
        text_on_light=True,
    ),
    Plate(
        key="midnight",
        label="Midnight Blue",
        css=(
            "background: radial-gradient(ellipse 1800px 1200px at 50% 30%, "
            "#1b2d4f 0%, #0f1b35 50%, #060a1d 100%);"
        ),
        text_on_light=False,
    ),
    # ── Image-backed plates ───────────────────────────────────────────────
    # The CSS pairs a dark gradient overlay (top transparent → bottom
    # ~35% black) with the photo. This keeps the watermark text legible
    # against a busy photographic background without obliterating the
    # photo's character. `linear-gradient` is on top of `url(...)` because
    # CSS layers paint in reverse order (first declared = topmost).
    Plate(
        key="office_studio",
        label="Studio Office",
        css=(
            "background: "
            "linear-gradient(180deg, rgba(0,0,0,0.0) 0%, rgba(0,0,0,0.35) 100%), "
            "url('https://images.unsplash.com/photo-1497366216548-37526070297c?w=1920&q=80&auto=format&fit=crop') "
            "center/cover no-repeat;"
        ),
        text_on_light=False,
        image_url="https://images.unsplash.com/photo-1497366216548-37526070297c?w=1920&q=80&auto=format&fit=crop",
        image_attribution="Photo by Nastuh Abootalebi on Unsplash",
    ),
    Plate(
        key="office_warmwood",
        label="Warm Wood",
        css=(
            "background: "
            "linear-gradient(180deg, rgba(0,0,0,0.0) 0%, rgba(0,0,0,0.35) 100%), "
            "url('https://images.unsplash.com/photo-1524758631624-e2822e304c36?w=1920&q=80&auto=format&fit=crop') "
            "center/cover no-repeat;"
        ),
        text_on_light=False,
        image_url="https://images.unsplash.com/photo-1524758631624-e2822e304c36?w=1920&q=80&auto=format&fit=crop",
        image_attribution="Photo by Annie Spratt on Unsplash",
    ),
    Plate(
        key="library",
        label="Library",
        css=(
            "background: "
            "linear-gradient(180deg, rgba(0,0,0,0.0) 0%, rgba(0,0,0,0.4) 100%), "
            "url('https://images.unsplash.com/photo-1521587760476-6c12a4b040da?w=1920&q=80&auto=format&fit=crop') "
            "center/cover no-repeat;"
        ),
        text_on_light=False,
        image_url="https://images.unsplash.com/photo-1521587760476-6c12a4b040da?w=1920&q=80&auto=format&fit=crop",
        image_attribution="Photo by Susan Q Yin on Unsplash",
    ),
    # The auto plate is a special case: its CSS is resolved server-side by
    # body_bg.py at /generate time, using the company's homepage's computed
    # body { background-color }. The thumbnail in the picker is a striped
    # placeholder — we don't know the actual color until the user picks
    # and submits. Placed last so it doesn't shift the default selection.
    Plate(
        key=AUTO_PLATE_KEY,
        label="Match Website",
        css=(
            "background: repeating-linear-gradient("
            "135deg, #2a3550 0 14px, #324063 14px 28px);"
        ),
        text_on_light=False,
    ),
)

_BY_KEY = {p.key: p for p in PRESETS}
DEFAULT_PLATE_KEY = "soft"


def get(key: str) -> Plate:
    """Return the named plate, or the default when `key` is unknown/blank.

    We don't raise on unknown keys — the front-end can always reach this with
    a typo or a deprecated plate key, and rendering the default is friendlier
    than 500-ing the whole request."""
    return _BY_KEY.get(key) or _BY_KEY[DEFAULT_PLATE_KEY]
