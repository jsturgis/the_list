"""A Show flyer's accent colour: the one swatch used to tint the Show page's panels, to complement the flyer
without impacting contrast (DESIGN.md, "Show flyer"). Worked out at ingest, like a Band photo's focal point
(app/ingestion/photo_focus.py), from pixels alone — no network, no LLM."""
from __future__ import annotations

import colorsys
import io

from PIL import Image

_SAMPLE_SIZE = (100, 100)
_PALETTE_COLORS = 8


def accent_color(data: bytes) -> str | None:
    """The flyer's one most colourful swatch, as `#rrggbb`, weighted by how much of the image it covers: the
    swatch with the largest `count * saturation`. A flyer with no real colour (black, white, or grey, as a
    purely monochrome poster can be) has no accent, rather than forcing a swatch on it. Unreadable image data
    also has no accent: a flyer's colour is a nice-to-have, never worth failing ingestion over.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            thumbnail = image.convert("RGB")
            thumbnail.thumbnail(_SAMPLE_SIZE)
            palette_image = thumbnail.quantize(colors=_PALETTE_COLORS, method=Image.Quantize.MEDIANCUT)
    except Exception:
        return None

    counts = palette_image.getcolors()
    if not counts:
        return None
    palette = palette_image.getpalette() or []

    best: tuple[int, int, int] | None = None
    best_score = 0.0
    for count, index in counts:
        r, g, b = palette[index * 3:index * 3 + 3]
        _, _, saturation = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        score = count * saturation
        if score > best_score:
            best_score = score
            best = (r, g, b)

    if best is None or best_score == 0:
        return None
    r, g, b = best
    return f"#{r:02x}{g:02x}{b:02x}"
