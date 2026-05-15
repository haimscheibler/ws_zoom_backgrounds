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
    text_on_light: bool  # True when the plate is mostly light — nametag
    # nametag colour scheme stays the same either way (dark translucent), but
    # this flag is exposed in case a future template variant needs to flip.


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
)

_BY_KEY = {p.key: p for p in PRESETS}
DEFAULT_PLATE_KEY = "soft"


def get(key: str) -> Plate:
    """Return the named plate, or the default when `key` is unknown/blank.

    We don't raise on unknown keys — the front-end can always reach this with
    a typo or a deprecated plate key, and rendering the default is friendlier
    than 500-ing the whole request."""
    return _BY_KEY.get(key) or _BY_KEY[DEFAULT_PLATE_KEY]
