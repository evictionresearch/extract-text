#!/usr/bin/env python3
"""Generate a multi-document synthetic summons corpus, with per-document truth.

    python3 python/scripts/make_corpus.py            # 24 documents
    python3 python/scripts/make_corpus.py --count 48

Writes into python/tests/fixtures/corpus/: one PNG per document plus a
`truth.json` mapping each filename to the six fields the AI lane extracts.

Why this exists. The degraded fixtures vary image *quality* but hold content
fixed, so they are one document rendered seven ways: n=1, not n=7. Six fields
from one document supports no confidence interval, which is why the first
bench could eliminate a model but not rank the survivors. This corpus varies
the content too, so a model's score is an average over many independent
readings instead of a single lucky or unlucky one.

Three axes vary together, each on its own cycle so they do not stay in phase:

- **Content.** Party names, street, city, case number, law firm, firm address,
  county, and filing date, drawn from the closed vocabulary below.
- **Layout.** Four page arrangements. Real summonses do not agree on where the
  caption, the service block, or the attorney block sits, and a model that has
  memorized one arrangement should not score as though it can read.
- **Quality.** The degradations from `make_degraded_fixtures`, cycled across
  documents, so the corpus spans clean print through handwriting on a bad
  photocopy.

Every value is invented and drawn from a fixed vocabulary, never randomized
into novel strings, so the set of values this repository contains stays
enumerable and auditable. Street names come from a reserved word list
(EXAMPLE, SAMPLE, SPECIMEN, PLACEHOLDER, EXEMPLAR, NOTIONAL) that is not a
real Washington street name; cities and ZIPs reuse the invented pairs the
fixtures already use; phone numbers stay in the 555-01xx range reserved for
fiction. `scripts/pii_sweep.py` whitelists these values explicitly.

This corpus is a screening tool and nothing more. It measures robustness to
the variation we thought to build, which is not the same as robustness to real
filings. MAINTENANCE.md step 3, a few hundred real documents on governed
storage, remains the only bar that can move the pinned default.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_degraded_fixtures as deg  # noqa: E402
import make_synthetic_fixtures as base  # noqa: E402

OUT = base.FIXTURES / "corpus"
SEED = 20260821

# --- the closed vocabulary -------------------------------------------------
# Fixed lists, cycled deterministically. Nothing here is generated from parts
# at random, so the complete set of values in this repository stays countable.

PLAINTIFFS = [
    "EXAMPLE PROPERTY LLC",
    "SAMPLE HOLDINGS LLC",
    "SPECIMEN REALTY GROUP LLC",
    "PLACEHOLDER PROPERTIES LP",
    "EXEMPLAR HOUSING PARTNERS LLC",
    "NOTIONAL ASSET MANAGEMENT LLC",
    "ILLUSTRATIVE RESIDENTIAL TRUST",
    "HYPOTHETICAL ESTATES LLC",
]

# Surnames are housing roles, not family names, so no invented person can be
# confused for a real one.
DEFENDANTS = [
    "JANE Q. TENANT and JON Q. TENANT",
    "ALEX P. OCCUPANT",
    "MORGAN R. RESIDENT and CASEY L. RESIDENT",
    "TAYLOR S. LESSEE",
    "JORDAN M. DWELLER and RILEY K. DWELLER",
    "SAM T. HOUSEHOLDER",
    "AVERY N. RENTER and QUINN D. RENTER",
    "ROWAN F. INHABITANT",
]

STREETS = [
    "1234 EXAMPLE AVE S APT 5",
    "5678 SAMPLE AVENUE",
    "9012 SPECIMEN DRIVE",
    "3456 PLACEHOLDER LANE UNIT 12",
    "7890 EXEMPLAR COURT",
    "2468 NOTIONAL TERRACE APT 3B",
    "1357 SPECIMEN ROAD",
    "8642 EXAMPLE PARKWAY STE B",
    "4680 SAMPLE CIRCLE",
    "9753 EXEMPLAR LOOP UNIT 7",
    "1470 NOTIONAL CROSSING",
    "3690 PLACEHOLDER HIGHWAY",
]

CITY_ZIPS = [
    "SEATTLE, WA 98100",
    "Sampleton, WA 98100",
]

CASE_NUMBERS = [
    "25-2-00001-0",
    "25-2-00002-0",
    "25-2-00003-0",
    "25-2-00004-0",
    "25-2-00005-0",
    "25-2-00006-0",
    "25-2-00007-0",
    "25-2-00008-0",
    "25-2-00009-0",
    "25-2-00010-0",
    "25-2-00011-0",
    "25-2-00012-0",
]

LAW_FIRMS = [
    "EXAMPLE LAW GROUP PLLC",
    "SAMPLE & SPECIMEN ATTORNEYS AT LAW",
    "PLACEHOLDER LEGAL PLLC",
    "EXEMPLAR LAW OFFICES",
    "NOTIONAL & ILLUSTRATIVE ATTORNEYS",
    "HYPOTHETICAL COUNSEL GROUP PLLC",
]

FIRM_STREETS = [
    "100 MAIN ST STE 200",
    "900 EXAMPLE STREET",
    "1800 EXAMPLE ST",
    "250 SPECIMEN BOULEVARD SUITE 400",
]

FIRM_CITY_ZIP = "SEATTLE, WA 98101"

COUNTIES = ["SAMPLE", "SPECIMEN", "EXEMPLAR", "PLACEHOLDER"]
DATES = ["May 6, 2025", "June 18, 2025", "August 2, 2025", "October 29, 2025"]
COUNSEL = [
    "Alex B. Counsel, WSBA #99999",
    "Dana R. Advocate, WSBA #99998",
    "Pat J. Barrister, WSBA #99997",
]
PHONE = "(206) 555-0100"

# Quality treatments, cycled across documents. None means leave it clean.
TREATMENTS = ("clean", "lowdpi", "skewed", "photocopy", "noisy", "handwritten", "worst")


def record_for(index: int) -> dict:
    """One document's field values. Each axis cycles on a different period so
    combinations do not repeat until the vocabulary is exhausted."""
    street = STREETS[index % len(STREETS)]
    city = CITY_ZIPS[index % len(CITY_ZIPS)]
    firm_street = FIRM_STREETS[index % len(FIRM_STREETS)]
    return {
        "plaintiff": PLAINTIFFS[index % len(PLAINTIFFS)],
        "defendant": DEFENDANTS[(index + 1) % len(DEFENDANTS)],
        "street": street,
        "city_zip": city,
        "address": f"{street} {city}",
        "case_number": CASE_NUMBERS[(index + 2) % len(CASE_NUMBERS)],
        "law_firm": LAW_FIRMS[(index + 1) % len(LAW_FIRMS)],
        "firm_street": firm_street,
        "law_firm_address": f"{firm_street} {FIRM_CITY_ZIP}",
        "county": COUNTIES[(index + 3) % len(COUNTIES)],
        "date": DATES[index % len(DATES)],
        "counsel": COUNSEL[index % len(COUNSEL)],
        "layout": index % 4,
        "treatment": TREATMENTS[index % len(TREATMENTS)],
    }


def rail(count: int = 26, x: int = 40, top: int = 100, step: int = 24):
    return [(x, top + (i - 1) * step, 9, str(i)) for i in range(1, count + 1)]


def layout_items(rec: dict) -> list:
    """Build the page for one record, in one of four arrangements.

    Layout 0 is the arrangement the original fixture uses. The rest move the
    blocks that real filings move: which side the case caption sits on, where
    the service block falls, and whether the attorney block is bottom-right or
    directly under the signature line.
    """
    which = rec["layout"]
    items: list = []

    if which != 3:  # layout 3 is a form with no pleading rail
        items += rail()

    items += [
        (150, 64, 12, "SUPERIOR COURT OF WASHINGTON"),
        (190, 82, 12, f"COUNTY OF {rec['county']}"),
    ]

    if which in (0, 2):
        caption_x, meta_x = 90, 350
    else:  # mirrored caption
        caption_x, meta_x = 320, 90

    items += [
        (caption_x, 120, 10, f"{rec['plaintiff']},"),
        (meta_x, 120, 10, f"Case No. {rec['case_number']}"),
        (caption_x + 110, 140, 10, "Plaintiff,"),
        (meta_x, 140, 10, "SUMMONS"),
        (caption_x, 160, 10, "v."),
        (meta_x, 160, 10, "(RESIDENTIAL UNLAWFUL DETAINER)"),
        (caption_x, 180, 10, f"{rec['defendant']},"),
        (caption_x, 198, 10, "and ALL OTHER OCCUPANTS,"),
        (caption_x + 110, 218, 10, "Defendants."),
    ]

    service_y = {0: 300, 1: 300, 2: 560, 3: 300}[which]
    items += [
        (90, service_y, 10, f"TO: {rec['defendant']},"),
        (90, service_y + 18, 10, "and ALL OTHER OCCUPANTS"),
        (90, service_y + 36, 10, rec["street"]),
        (90, service_y + 54, 10, rec["city_zip"]),
    ]

    prose_y = {0: 410, 1: 410, 2: 300, 3: 500}[which]
    items += [
        (90, prose_y, 10,
         "A lawsuit has been started against you in the above entitled Court by"),
        (90, prose_y + 18, 10,
         f"{rec['plaintiff']}, Plaintiff. Plaintiff's claim is stated in the written"),
        (90, prose_y + 36, 10,
         "Complaint, a copy of which is served upon you with this Summons."),
        (90, prose_y + 86, 10, f"DATED: {rec['date']}."),
    ]

    if which == 2:  # attorney block stacked under the signature, left column
        firm_x, firm_y = 90, 640
    elif which == 3:  # compact form: attorney block high on the right
        firm_x, firm_y = 340, 430
    else:
        firm_x, firm_y = 340, 640

    items += [
        (340, prose_y + 86, 10, rec["counsel"]),
        (340, prose_y + 104, 10, "Attorneys for Plaintiff"),
        (firm_x, firm_y, 10, rec["law_firm"]),
        (firm_x, firm_y + 16, 10, rec["firm_street"]),
        (firm_x, firm_y + 32, 10, FIRM_CITY_ZIP),
        (firm_x, firm_y + 48, 10, PHONE),
    ]
    return items


def collisions(items: list, tolerance: float = 2.0) -> list[tuple[str, str]]:
    """Text runs that overlap on the page.

    Overlapping text is not a degradation, it is a broken fixture: the truth
    file still claims a field the page renders unreadably, so a model gets
    marked wrong for something no reader could get right. Layout coordinates
    are hand-placed and easy to miss by a few points, so this measures rather
    than trusts. Widths come from the real font metrics, in points, which is
    the same unit the layout is written in.
    """
    from PIL import ImageFont

    font_path = next((p for p in base.FONT_CANDIDATES if Path(p).exists()), None)
    if font_path is None:
        return []

    boxes = []
    for x, y, size, text in items:
        width = ImageFont.truetype(font_path, size).getlength(text)
        boxes.append((x, y, x + width, y + size * 1.2, text))

    hits = []
    for i, (ax0, ay0, ax1, ay1, atext) in enumerate(boxes):
        for bx0, by0, bx1, by1, btext in boxes[i + 1:]:
            overlap_x = min(ax1, bx1) - max(ax0, bx0)
            overlap_y = min(ay1, by1) - max(ay0, by0)
            if overlap_x > tolerance and overlap_y > tolerance:
                hits.append((atext, btext))
    return hits


def render(rec: dict, items: list, rng: random.Random):
    """Render one record at its assigned quality treatment."""
    treatment = rec["treatment"]
    handwritten_lines = (rec["street"], rec["city_zip"])

    if treatment in ("handwritten", "worst"):
        font = deg.script_font_path()
        if font is None:
            treatment = "photocopy"  # graceful fallback where no script face exists
        else:
            saved = deg.HANDWRITTEN_LINES
            deg.HANDWRITTEN_LINES = handwritten_lines
            try:
                page = deg.draw_with_handwriting(items, deg.BASE_DPI, font, rng)
            finally:
                deg.HANDWRITTEN_LINES = saved
            if treatment == "handwritten":
                return page
            page = deg.add_photocopy(page, rng)
            page = deg.add_skew(page, -1.8)
            page = deg.downscale_roundtrip(page, 0.55)
            return deg.add_noise(page, rng, grain=0.2, speckle=0.003)

    page = base.draw_page_image(items, dpi=deg.BASE_DPI)
    if treatment == "clean":
        return page
    if treatment == "lowdpi":
        from PIL import Image

        return base.draw_page_image(items, dpi=72).resize(
            page.size, resample=Image.Resampling.BILINEAR
        )
    if treatment == "skewed":
        return deg.add_skew(page, 2.3)
    if treatment == "photocopy":
        return deg.add_photocopy(page, rng)
    if treatment == "noisy":
        return deg.add_noise(page, rng)
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=24)
    args = parser.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.png"):
        stale.unlink()

    truth = {}
    overlaps: list[str] = []
    for index in range(args.count):
        rec = record_for(index)
        items = layout_items(rec)
        for atext, btext in collisions(items):
            overlaps.append(f"  doc_{index:03d} (layout {rec['layout']}): {atext!r} / {btext!r}")
        page = render(rec, items, random.Random(SEED + index))
        name = f"doc_{index:03d}.png"
        page.save(OUT / name, dpi=(deg.BASE_DPI, deg.BASE_DPI))
        truth[name] = {
            "plaintiff": rec["plaintiff"],
            "defendant": rec["defendant"],
            "address": rec["address"],
            "law_firm": rec["law_firm"],
            "law_firm_address": rec["law_firm_address"],
            "case_number": rec["case_number"],
            "layout": rec["layout"],
            "treatment": rec["treatment"],
        }

    if overlaps:
        print(
            f"ERROR: {len(overlaps)} overlapping text runs. A field that renders "
            "on top of another is unreadable, so the truth file would be lying "
            "about it. Fix the layout coordinates before using this corpus.",
            file=sys.stderr,
        )
        print("\n".join(overlaps), file=sys.stderr)
        return 1

    (OUT / "truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

    total = sum((OUT / n).stat().st_size for n in truth)
    treatments = sorted({v["treatment"] for v in truth.values()})
    print(f"{len(truth)} documents, {total / 1e6:.1f} MB, in {OUT}")
    print(f"layouts: 4    treatments: {', '.join(treatments)}")
    print(f"truth:   {OUT / 'truth.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
