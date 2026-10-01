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

# Two more King County layouts, added 2026-09-30 after the first new-user
# test on real cases showed the rules failing on both. Values invented as
# above; the shapes are what matter.
#
# The e-filed layout (2010s): a boxed caption with the rail's line numbers
# and the box's rule beside the party names, a CASE NUMBER stamp with the
# courthouse code as a separate word, a "TO THE DEFENDANT(S):" service block
# whose second line is the complex's name, and the notice sentence that
# mentions "no case number has been assigned".
_RULE = [(72, 116 + i * 12, 9, "|") for i in range(0, 12)]  # the caption box's left rule
KC_EFILED_ITEMS = (
    [(40, 100 + (i - 1) * 24, 9, str(i)) for i in range(1, 27)]
    + _RULE
    + [
        (400, 40, 8, "FILED"),
        (400, 52, 7, "SAMPLE COUNTY"),
        (400, 62, 7, "SUPERIOR COURT CLERK"),
        (400, 72, 7, "E-FILED"),
        (400, 82, 7, "CASE NUMBER: 25-2-00007-1 SEA"),
        (170, 104, 8, "IN THE SUPERIOR COURT OF THE STATE OF WASHINGTON"),
        (190, 114, 8, "IN AND FOR THE COUNTY OF SAMPLE"),
        (80, 136, 8, "EXAMPLE HOUSING INSTITUTE,"),
        (300, 136, 8, "NO."),
        (200, 148, 8, "Plaintiff,"),
        (80, 160, 8, "vs."),
        (300, 160, 8, "EVICTION SUMMONS"),
        (300, 170, 8, "(Residential)"),
        (80, 184, 8, "PAT Q. OCCUPANT,"),
        (200, 196, 8, "Defendant(s)."),
        (80, 210, 8, "#  00000.0000"),
        (180, 250, 8, "THIS IS NOTICE OF A LAWSUIT TO EVICT YOU."),
        (200, 260, 8, "PLEASE READ IT CAREFULLY."),
        (170, 270, 8, "THE DEADLINE FOR YOUR WRITTEN RESPONSE IS:"),
        (200, 284, 8, "4:30 P.M., on September 13, 2025"),
        (80, 306, 8, "TO THE DEFENDANT(S):"),
        (200, 306, 8, "PAT Q. OCCUPANT"),
        (200, 316, 8, "EXAMPLE COURT APARTMENTS"),
        (200, 326, 8, "5678 SAMPLE AVENUE"),
        (200, 336, 8, "Seattle, Washington 98100"),
        (80, 360, 8, "This is notice of a lawsuit to evict you from the property which you are renting. Your landlord is"),
        (80, 370, 8, "asking the court to terminate your tenancy, direct the sheriff to remove you and your belongings from the"),
        (80, 380, 8, "property, enter a money judgment against you for unpaid rent and/or damages for your use of the property,"),
        (80, 390, 8, "and for court costs and attorney's fees."),
        (80, 404, 8, "If you want to defend yourself in this lawsuit, you must respond to the eviction complaint in writing on"),
        (80, 414, 8, "or before the deadline stated above. You must respond in writing even if no case number has been assigned"),
        (80, 424, 8, "by the court yet."),
        (80, 640, 8, "SUMMONS- 1"),
        (380, 640, 8, "SAMPLE & SPECIMEN PLLC"),
        (380, 650, 7, "100 MAIN ST STE 200"),
        (380, 660, 7, "SEATTLE, WASHINGTON 98101"),
        (380, 670, 7, "TELEPHONE: (206) 555-0100"),
    ]
)

# The pre-printed layout (2000s): "Plaintiff(s)," and "Defendant(s)" labels
# with the parenthetical, a two-line plaintiff (name, then a DBA line), the
# case number stamped with the courthouse code glued to the check digit, OCR
# debris ("=)", "ao") where the rail meets the text, the co-defendant boilerplate
# on the TO: line itself, and a building-plus-apartment unit.
KC_PRINTED_ITEMS = (
    [(40, 100 + (i - 1) * 20, 9, str(i)) for i in range(1, 33)]
    + [
        (300, 40, 9, "FILED"),
        (300, 52, 7, "SAMPLE COUNTY"),
        (300, 62, 7, "SUPERIOR COURT CLERK"),
        (110, 100, 8, "SUPERIOR COURT OF WASHINGTON FOR COUNTY OF SAMPLE"),
        (62, 120, 8, "=)"),
        (75, 120, 8, "ao"),
        (90, 120, 8, "EXAMPLE GREENS LLC"),
        (330, 120, 12, "25-2-00008-3SEA"),
        (90, 130, 8, "DBA EXAMPLE GREENS"),
        (200, 142, 8, "Plaintiff(s),"),
        (300, 142, 8, ")"),
        (200, 154, 8, "vs."),
        (300, 154, 8, ")  EVICTION SUMMONS"),
        (90, 166, 8, "PAT Q. OCCUPANT"),
        (300, 166, 8, ")  (RESIDENTIAL)"),
        (90, 176, 8, "LEE R. OCCUPANT"),
        (90, 186, 8, "ALL OTHER OCCUPANTS"),
        (300, 196, 8, "ORIGINAL"),
        (180, 208, 8, "Defendant(s)"),
        (170, 236, 8, "THIS IS NOTICE OF A LAWSUIT TO EVICT YOU"),
        (190, 246, 8, "PLEASE READ IT CAREFULLY"),
        (170, 256, 8, "THE DEADLINE FOR YOUR WRITTEN RESPONSE IS:"),
        (200, 266, 8, "5:00 p.m. on 1/25/2026"),
        (90, 290, 8, "TO:  PAT Q. OCCUPANT"),
        (230, 290, 8, "ALL OTHER OCCUPANTS"),
        (115, 300, 8, "LEE R. OCCUPANT"),
        (115, 310, 8, "1234-EXAMPLE AVE. NE BLDG ZZ Apt # 102"),
        (115, 320, 8, "SAMPLETON, WA 98100 County of SAMPLE"),
        (90, 344, 8, "This is notice of a lawsuit to evict you from the property"),
        (90, 354, 8, "which you are renting.  Your landlord is asking the court to"),
        (90, 364, 8, "terminate your tenancy, direct the sheriff to remove you and your"),
        (90, 374, 8, "belongings from the property, enter a money judgment against you"),
        (90, 384, 8, "for unpaid rent and/or damages for your use of the property, and"),
        (90, 394, 8, "for court costs and attorney's fees."),
        (90, 412, 8, "If you want to defend yourself in this lawsuit, you must"),
        (90, 422, 8, "respond to the eviction complaint in writing on or before the"),
        (90, 432, 8, "deadline stated above. You must respond in writing even if no case"),
        (90, 442, 8, "number has been assigned by the court yet."),
        (330, 700, 7, "ALEX B. COUNSEL"),
        (330, 709, 7, "ATTORNEY AT LAW"),
        (330, 718, 7, "100 MAIN ST STE 200"),
        (330, 727, 7, "SEATTLE, WA 98101"),
        (330, 736, 7, "(206) 555-0100"),
        (90, 736, 8, "SUMMONS ON COMPLAINT  -"),
        (90, 746, 8, "PAGE 1 (RCW 59.18.365)"),
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

    for name, items in (("kc_efiled", KC_EFILED_ITEMS), ("kc_printed", KC_PRINTED_ITEMS)):
        (FIXTURES / f"synthetic_{name}.pdf").write_bytes(build_text_pdf(items))
        draw_page_image(items, dpi=300).save(
            FIXTURES / f"synthetic_{name}_scanned.pdf", "PDF", resolution=300.0)

    for f in sorted(FIXTURES.glob("synthetic_*")):
        print(f"{f.relative_to(FIXTURES.parents[1])}  {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
