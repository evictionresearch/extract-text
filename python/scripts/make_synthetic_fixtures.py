#!/usr/bin/env python3
"""Generate the synthetic test fixtures.

    python3 python/scripts/make_synthetic_fixtures.py

Writes into python/tests/fixtures/:

    synthetic_summons_efiled.pdf    a PDF with a digital text layer, built
                                    from raw PDF syntax (no library), the way
                                    an e-filed document reads
    synthetic_summons_scanned.pdf   the same page as an image-only PDF, the
                                    way a scanned document reads (OCR path)
    synthetic_summons.tif           the same page as a TIFF (OCR path)
    synthetic_summons_page1.png     the same page as a PNG, for the AI
                                    vision lane
    synthetic_summons.txt           a flat-text single-column version

Every value is invented. The names and addresses follow the same
illustrative convention as the project's public materials (EXAMPLE PROPERTY
LLC, JANE Q. TENANT, 1234 EXAMPLE AVE S). The phone number uses the
555-01xx range reserved for fiction. No value here refers to any real case,
person, or place of residence, and `scripts/pii_sweep.py` whitelists exactly
these values and no others.

The page mimics Washington pleading paper: a rail of line numbers down the
left margin (the thing that breaks flat OCR), a two-column caption, the
mid-page TO: service block, and the attorney block in the bottom-right
corner.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

PAGE_W, PAGE_H = 612, 792  # US letter, points

# (x_pt, y_pt_from_top, size_pt, text)
ITEMS = (
    [(40, 100 + (i - 1) * 24, 9, str(i)) for i in range(1, 27)]  # the rail
    + [
        (150, 64, 12, "SUPERIOR COURT OF WASHINGTON"),
        (190, 82, 12, "COUNTY OF SAMPLE"),
        # caption, two columns
        (90, 120, 10, "EXAMPLE PROPERTY LLC,"),
        (350, 120, 10, "Case No. 25-2-00001-0"),
        (200, 140, 10, "Plaintiff,"),
        (350, 140, 10, "SUMMONS"),
        (90, 160, 10, "v."),
        (350, 160, 10, "(RESIDENTIAL UNLAWFUL DETAINER)"),
        (90, 180, 10, "JANE Q. TENANT and JON Q. TENANT,"),
        (90, 198, 10, "and ALL OTHER OCCUPANTS,"),
        (200, 218, 10, "Defendants."),
        # the service block
        (90, 300, 10, "TO: JANE Q. TENANT and JON Q. TENANT,"),
        (90, 318, 10, "and ALL OTHER OCCUPANTS"),
        (90, 336, 10, "1234 EXAMPLE AVE S APT 5"),
        (90, 354, 10, "SEATTLE, WA 98100"),
        # notice prose
        (90, 410, 10, "A lawsuit has been started against you in the above entitled Court by"),
        (90, 428, 10, "EXAMPLE PROPERTY LLC, Plaintiff. Plaintiff's claim is stated in the written"),
        (90, 446, 10, "Complaint, a copy of which is served upon you with this Summons."),
        (90, 496, 10, "DATED: May 6, 2025."),
        # signature block
        (340, 496, 10, "Alex B. Counsel, WSBA #99999"),
        (340, 514, 10, "Attorneys for Plaintiff"),
        # attorney footer, bottom right
        (340, 640, 10, "EXAMPLE LAW GROUP PLLC"),
        (340, 656, 10, "100 MAIN ST STE 200"),
        (340, 672, 10, "SEATTLE, WA 98101"),
        (340, 688, 10, "(206) 555-0100"),
    ]
)

FLAT_TEXT = """\
SUPERIOR COURT OF WASHINGTON
COUNTY OF SAMPLE

EXAMPLE PROPERTY LLC,
                              Plaintiff,
v.
JANE Q. TENANT and JON Q. TENANT,
                              Defendants.

Case No. 25-2-00001-0

SUMMONS (RESIDENTIAL UNLAWFUL DETAINER)

TO: JANE Q. TENANT and JON Q. TENANT
1234 EXAMPLE AVE S APT 5
SEATTLE, WA 98100

A lawsuit has been started against you in the above entitled Court by
EXAMPLE PROPERTY LLC, Plaintiff. Plaintiff's claim is stated in the written
Complaint, a copy of which is served upon you with this Summons.

DATED: May 6, 2025.
EXAMPLE LAW GROUP PLLC
Alex B. Counsel, WSBA #99999
Attorneys for Plaintiff
100 MAIN ST STE 200
SEATTLE, WA 98101
(206) 555-0100
"""


# ---------------------------------------------------------------------------
# a PDF with a real text layer, from raw PDF syntax
# ---------------------------------------------------------------------------


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_text_pdf(items) -> bytes:
    ops = ["BT"]
    for x, y_top, size, text in items:
        y = PAGE_H - y_top - size  # PDF origin is bottom-left
        ops.append(f"/F1 {size} Tf 1 0 0 1 {x} {y} Tm ({_esc(text)}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
         "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>").encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


# ---------------------------------------------------------------------------
# the same page as an image, for the OCR and vision paths
# ---------------------------------------------------------------------------

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def draw_page_image(items, dpi=300):
    from PIL import Image, ImageDraw, ImageFont

    scale = dpi / 72
    im = Image.new("L", (int(PAGE_W * scale), int(PAGE_H * scale)), 255)
    draw = ImageDraw.Draw(im)
    font_path = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
    if font_path is None:
        raise SystemExit(
            "No TrueType font found to draw the synthetic scan; add a path "
            "to FONT_CANDIDATES."
        )
    fonts = {}
    for x, y_top, size, text in items:
        px = int(round(size * scale))
        if px not in fonts:
            fonts[px] = ImageFont.truetype(font_path, px)
        draw.text((x * scale, y_top * scale), text, font=fonts[px], fill=0)
    return im


def main():
    FIXTURES.mkdir(parents=True, exist_ok=True)

    (FIXTURES / "synthetic_summons_efiled.pdf").write_bytes(build_text_pdf(ITEMS))
    (FIXTURES / "synthetic_summons.txt").write_text(FLAT_TEXT)

    page = draw_page_image(ITEMS, dpi=300)
    page.save(FIXTURES / "synthetic_summons_scanned.pdf", "PDF", resolution=300.0)
    page.convert("1").save(FIXTURES / "synthetic_summons.tif",
                           compression="group4", dpi=(300, 300))
    small = draw_page_image(ITEMS, dpi=150)
    small.save(FIXTURES / "synthetic_summons_page1.png", dpi=(150, 150))

    for f in sorted(FIXTURES.glob("synthetic_*")):
        print(f"{f.relative_to(FIXTURES.parents[1])}  {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
