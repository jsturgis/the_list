"""Tests for a Show flyer's accent colour: the one swatch used to tint the Show page's panels (DESIGN.md,
"Show flyer")."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from app.ingestion.flyer_color import accent_color


def _bytes(image: Image.Image, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    image.save(buf, fmt)
    return buf.getvalue()


def test_a_solid_coloured_flyer_gives_back_that_colour():
    image = Image.new("RGB", (100, 100), (200, 40, 40))
    assert accent_color(_bytes(image)) == "#c82828"


def test_the_most_common_saturated_colour_wins_over_a_smaller_patch():
    # A large blue field with a small, more saturated red corner: blue covers more area, so it should win even
    # though red is more saturated on its own (weighted by count, not just by saturation). Quantization can nudge
    # the exact swatch, so this checks the colour it picked is blue, not that it's one literal hex value.
    image = Image.new("RGB", (100, 100), (40, 60, 200))
    ImageDraw.Draw(image).rectangle([0, 0, 9, 9], fill=(220, 20, 20))
    hex_color = accent_color(_bytes(image))
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    assert b > r and b > g


def test_white_and_black_are_ignored_in_favour_of_the_one_colourful_patch():
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    ImageDraw.Draw(image).rectangle([40, 40, 59, 59], fill=(0, 0, 0))
    ImageDraw.Draw(image).rectangle([0, 0, 19, 19], fill=(30, 150, 90))
    assert accent_color(_bytes(image)) == "#1e965a"


def test_a_flyer_with_no_colour_at_all_has_no_accent():
    image = Image.new("RGB", (100, 100), (128, 128, 128))
    assert accent_color(_bytes(image)) is None


def test_unreadable_image_data_has_no_accent():
    assert accent_color(b"not an image") is None
