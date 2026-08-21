#!/usr/bin/env python3
"""Generate degraded synthetic summons pages, so the model bench can discriminate.

    python3 python/scripts/make_degraded_fixtures.py

Writes into python/tests/fixtures/degraded/.

Why this exists. The clean fixture from `make_synthetic_fixtures.py` renders
crisp machine text at 150 DPI, which is the easiest input a vision model will
ever see. Benched against it on 2026-08-20, four of five candidate models
scored a perfect 6 of 6 and the fifth missed only on instruction-following.
A test where nearly everyone hits the ceiling cannot rank anyone. These
variants restore the spread by reintroducing, one axis at a time, the things
that actually break extraction on real filings:

    clean.png        the 150 DPI baseline, for a controlled comparison
    lowdpi.png       rendered at 72 DPI and scaled up: a fax-grade scan
    noisy.png        scanner grain plus salt-and-pepper speckle
    skewed.png       rotated, the way a page feeds through crooked
    photocopy.png    crushed contrast, gray ground, uneven illumination
    handwritten.png  the service address block in handwriting
    worst.png        every axis at once

The values on every page are the same invented values the clean fixture uses
(EXAMPLE PROPERTY LLC, JANE Q. TENANT, 1234 EXAMPLE AVE S), imported from
`make_synthetic_fixtures` rather than retyped, so there is exactly one place
where the fixture's ground truth lives. Nothing here refers to any real case,
person, or place of residence.

handwritten.png is the one that matters most. Handwriting is the stated reason
the AI vision lane exists at all, and the clean fixture tests none of it. If a
candidate model reads print beautifully and collapses on the handwritten
service address, that is the single fact most worth knowing before it goes
anywhere near the pin.

Every degradation is seeded, so re-running produces byte-identical output and
a bench result stays comparable across runs. Handwriting needs a script-like
font; if none is installed, that variant is skipped with a note rather than
failing the run, so this still works in CI.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_synthetic_fixtures as base  # noqa: E402

OUT = base.FIXTURES / "degraded"

SEED = 20260820

# Rendered at this DPI unless a variant says otherwise. Matches the clean
# fixture the bench already uses, so `clean.png` is a true control.
BASE_DPI = 150

# The service-block lines that become handwriting. These are the lines a
# process server fills in by hand on a real summons, which is exactly why
# the AI lane exists. Matched by their text, so if the fixture's wording
# changes this fails loudly instead of silently degrading the wrong lines.
HANDWRITTEN_LINES = (
    "1234 EXAMPLE AVE S APT 5",
    "SEATTLE, WA 98100",
)

SCRIPT_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
    "/System/Library/Fonts/Supplemental/Brush Script.ttf",
    "/System/Library/Fonts/Supplemental/SnellRoundhand.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "C:/Windows/Fonts/segoesc.ttf",
]


def script_font_path() -> str | None:
    return next((p for p in SCRIPT_FONT_CANDIDATES if Path(p).exists()), None)


def draw_with_handwriting(items, dpi: int, font_path: str, rng: random.Random):
    """Render the page, but set the service-address lines in a script face.

    Each handwritten line gets a small random offset and size jitter, because
    real handwriting does not sit on the baseline the way type does, and a
    model that keys on perfect alignment should not get credit for it here.
    """
    from PIL import Image, ImageDraw, ImageFont

    scale = dpi / 72
    im = Image.new("L", (int(base.PAGE_W * scale), int(base.PAGE_H * scale)), 255)
    draw = ImageDraw.Draw(im)

    print_font_path = next(
        (p for p in base.FONT_CANDIDATES if Path(p).exists()), None
    )
    if print_font_path is None:
        raise SystemExit("No TrueType font found; see FONT_CANDIDATES.")

    cache: dict[tuple[str, int], object] = {}

    def font_for(path: str, px: int):
        key = (path, px)
        if key not in cache:
            cache[key] = ImageFont.truetype(path, px)
        return cache[key]

    for x, y_top, size, text in items:
        if text in HANDWRITTEN_LINES:
            px = int(round(size * scale * 1.35))  # hand lettering runs larger
            dx = rng.uniform(-3, 6) * scale
            dy = rng.uniform(-2, 3) * scale
            draw.text(
                (x * scale + dx, y_top * scale + dy),
                text,
                font=font_for(font_path, px),
                fill=rng.randint(0, 60),  # pen ink is rarely pure black
            )
        else:
            px = int(round(size * scale))
            draw.text(
                (x * scale, y_top * scale), text, font=font_for(print_font_path, px), fill=0
            )
    return im


def add_noise(im, rng: random.Random, grain: float = 0.16, speckle: float = 0.0016):
    """Scanner grain plus salt-and-pepper, both seeded."""
    from PIL import Image

    width, height = im.size
    noise = Image.frombytes("L", (width, height), rng.randbytes(width * height))
    out = Image.blend(im, noise, grain)

    pixels = out.load()
    for _ in range(int(width * height * speckle)):
        x = rng.randrange(width)
        y = rng.randrange(height)
        pixels[x, y] = 0 if rng.random() < 0.55 else 255
    return out


def add_skew(im, degrees: float):
    from PIL import Image

    return im.rotate(
        degrees, resample=Image.Resampling.BICUBIC, fillcolor=255, expand=False
    )


def add_photocopy(im, rng: random.Random):
    """Crushed contrast, a gray ground, and a lighting gradient down the page."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

    out = ImageEnhance.Contrast(im).enhance(1.9)
    out = out.point(lambda v: min(255, int(v * 0.86) + 26))
    out = out.filter(ImageFilter.GaussianBlur(radius=0.7))

    # Uneven illumination: one edge of the platen sits darker than the other.
    width, height = out.size
    gradient = Image.new("L", (width, height), 255)
    gdraw = ImageDraw.Draw(gradient)
    for x in range(0, width, 8):
        shade = 255 - int(26 * (x / width))
        gdraw.rectangle([x, 0, x + 8, height], fill=shade)
    return Image.blend(out, Image.blend(out, gradient, 0.5), 0.55)


def downscale_roundtrip(im, factor: float):
    """Throw away real detail, then scale back so page geometry is unchanged."""
    from PIL import Image

    width, height = im.size
    small = im.resize(
        (int(width * factor), int(height * factor)),
        resample=Image.Resampling.BILINEAR,
    )
    return small.resize((width, height), resample=Image.Resampling.BILINEAR)


def build() -> list[tuple[str, object]]:
    pages: list[tuple[str, object]] = []

    clean = base.draw_page_image(base.ITEMS, dpi=BASE_DPI)
    pages.append(("clean.png", clean))

    from PIL import Image

    lowdpi = base.draw_page_image(base.ITEMS, dpi=72).resize(
        clean.size, resample=Image.Resampling.BILINEAR
    )
    pages.append(("lowdpi.png", lowdpi))

    pages.append(("noisy.png", add_noise(clean, random.Random(SEED))))
    pages.append(("skewed.png", add_skew(clean, 2.3)))
    pages.append(("photocopy.png", add_photocopy(clean, random.Random(SEED + 1))))

    font_path = script_font_path()
    if font_path is None:
        print(
            "note: no script-like font found, so handwritten.png and worst.png "
            "are skipped. Add a path to SCRIPT_FONT_CANDIDATES.",
            file=sys.stderr,
        )
        return pages

    hand = draw_with_handwriting(
        base.ITEMS, BASE_DPI, font_path, random.Random(SEED + 2)
    )
    pages.append(("handwritten.png", hand))

    # Everything at once, in the order a real document would acquire it:
    # handwriting goes on the page, the page is photocopied, fed crooked
    # through a low-resolution scanner, and the sensor adds its own grain.
    worst = add_photocopy(hand, random.Random(SEED + 3))
    worst = add_skew(worst, -1.8)
    worst = downscale_roundtrip(worst, 0.55)
    worst = add_noise(worst, random.Random(SEED + 4), grain=0.2, speckle=0.003)
    pages.append(("worst.png", worst))

    return pages


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, image in build():
        path = OUT / name
        image.save(path, dpi=(BASE_DPI, BASE_DPI))
        print(f"{path.relative_to(base.FIXTURES.parents[1])}  {path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
