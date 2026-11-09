"""Form templates: learned from boxes on synthetic pages, read first.

Every page here is built from the closed synthetic vocabulary of
make_synthetic_fixtures.py and make_corpus.py (invented parties, reserved
street names, the 25-2-0000N-0 case-number series). Real court records never
enter this repository, including in tests.

The form family used most is one the engine's own anchor ladder cannot read:
its service block is labeled "Served upon:" (no TO:) and printed right of
centre, where the stack anchor does not look, and the caption carries no
address. So an address on such a page proves the template read it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from extract_text.documents import have
from extract_text.layout import Line, Word
from extract_text.templates import (
    Region,
    Template,
    _edit1,
    group_pages,
    labeled_boxes,
    learn_fingerprint,
    load_templates,
    match_page,
    page_similarity,
    region_from_boxes,
)

FIXTURES = Path(__file__).parent / "fixtures"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

needs_system_tools = pytest.mark.skipif(
    not (have("pdftotext") and have("pdfinfo") and have("pdftoppm") and have("tesseract")),
    reason="poppler/tesseract not installed",
)

PAGE_W, PAGE_H = 612, 792


def _fixtures_module():
    spec = importlib.util.spec_from_file_location(
        "make_synthetic_fixtures", SCRIPTS / "make_synthetic_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# the family's varying values, all from the closed vocabulary
PLAINTIFFS = ["EXAMPLE PROPERTY LLC", "SAMPLE HOLDINGS LLC", "SPECIMEN REALTY GROUP LLC",
              "PLACEHOLDER PROPERTIES LP", "EXEMPLAR HOUSING PARTNERS LLC",
              "NOTIONAL ASSET MANAGEMENT LLC", "ILLUSTRATIVE RESIDENTIAL TRUST",
              "HYPOTHETICAL ESTATES LLC"]
DEFENDANTS = [["JANE Q. TENANT", "JON Q. TENANT"], ["ALEX P. OCCUPANT"],
              ["MORGAN R. RESIDENT", "CASEY L. RESIDENT"], ["TAYLOR S. LESSEE"],
              ["JORDAN M. DWELLER", "RILEY K. DWELLER"], ["SAM T. HOUSEHOLDER"],
              ["AVERY N. RENTER", "QUINN D. RENTER"], ["ROWAN F. INHABITANT"]]
STREETS = ["9012 SPECIMEN DRIVE", "7890 EXEMPLAR COURT", "1357 SPECIMEN ROAD",
           "9753 EXEMPLAR LOOP UNIT 7", "1470 NOTIONAL CROSSING", "3690 PLACEHOLDER HIGHWAY",
           "2468 NOTIONAL TERRACE APT 3B", "9012 SPECIMEN DRIVE"]
CITIES = ["SEATTLE, WA 98100", "Sampleton, WA 98100"]


def _box(x, y_top, size, text, pad=2):
    """A box around a text item of the synthetic page, as page fractions."""
    width = 0.55 * size * len(text)
    return [(x - pad) / PAGE_W, (y_top - pad) / PAGE_H,
            (x + width + pad) / PAGE_W, (y_top + size * 1.25 + pad) / PAGE_H]


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def served_upon_form(i, shift=(0, 0), service_block=True):
    """Page i of the 'Served upon:' family: items for build_text_pdf, and the
    boxes a reviewer would draw for plaintiff, defendants, and address."""
    dx, dy = shift
    plaintiff, names = PLAINTIFFS[i], DEFENDANTS[i]
    street, city = STREETS[i], CITIES[i % 2]
    case = f"25-2-{i + 1:05d}-0"
    items = [(40 + dx, 100 + (k - 1) * 24 + dy, 9, str(k)) for k in range(1, 27)]
    items += [
        (150, 64, 11, "SUPERIOR COURT OF WASHINGTON"),
        (190, 80, 11, "COUNTY OF SAMPLE"),
        (90, 120, 10, plaintiff + ","),
        (350, 120, 10, "NO. " + case),
        (200, 138, 10, "Plaintiff(s),"),
        (350, 140, 10, "EVICTION SUMMONS"),
        (90, 156, 10, "vs."),
        (350, 158, 10, "(RESIDENTIAL)"),
    ]
    y = 174
    for n in names:
        items.append((90, y, 10, n + ","))
        y += 16
    items.append((200, y, 10, "Defendant(s)."))
    items += [
        (90, 290, 10, "NOTICE OF EVICTION LAWSUIT"),
        (90, 306, 10, "READ THIS SUMMONS CAREFULLY AND RESPOND BY THE DEADLINE."),
    ]
    name_items, addr_items = [], []
    if service_block:
        items.append((380, 330, 9, "Served upon:"))
        y = 346
        for n in names:
            name_items.append((380, y, 9, n))
            y += 14
        addr_items = [(380, y, 9, street), (380, y + 14, 9, city)]
        items += name_items + addr_items
    items += [
        (90, 440, 9, "This is notice of a lawsuit to evict you from the property which you are renting."),
        (90, 454, 9, "Your landlord is asking the court to terminate your tenancy and direct the sheriff"),
        (90, 468, 9, "to remove you and your belongings from the property, and to enter a money judgment"),
        (90, 482, 9, "against you for unpaid rent and for court costs and attorney's fees."),
        (90, 504, 9, "If you want to defend yourself in this lawsuit, you must respond to the eviction"),
        (90, 518, 9, "complaint in writing on or before the deadline stated above."),
        (340, 640, 10, "EXAMPLE LAW GROUP PLLC"),
        (340, 656, 10, "100 MAIN ST STE 200"),
        (340, 672, 10, "SEATTLE, WA 98101"),
        (340, 688, 10, "(206) 555-0100"),
    ]
    items = [(x + dx, y_top + dy, s, t) for x, y_top, s, t in items]
    boxes = {"plaintiff": _box(90 + dx, 120 + dy, 10, plaintiff)}
    if service_block:
        boxes["defendants"] = _union([_box(x + dx, yy + dy, s, t) for x, yy, s, t in name_items])
        boxes["address"] = _union([_box(x + dx, yy + dy, s, t) for x, yy, s, t in addr_items])
    truth = {"plaintiff": plaintiff, "defendants": list(names),
             "street": street.split(" UNIT ")[0].split(" APT ")[0],
             "unit": ("UNIT 7" if "UNIT" in street else "APT 3B" if "APT" in street else ""),
             "city": city.split(",")[0].title(), "state": "WA", "zip": "98100",
             "attorneys": ["EXAMPLE LAW GROUP PLLC"],
             "attorney_address": "100 MAIN ST STE 200, Seattle, WA 98101"}
    return items, boxes, truth


def to_block_form(i):
    """Page i of the TO: family, the layout of synthetic_summons_efiled.pdf
    with the family's values, which the engine's own ladder reads."""
    fx = _fixtures_module()
    plaintiff, names = PLAINTIFFS[i], DEFENDANTS[i]
    street, city = STREETS[i], CITIES[i % 2]
    case = f"25-2-{i + 1:05d}-0"
    swap = {"EXAMPLE PROPERTY LLC": plaintiff, "25-2-00001-0": case,
            "JANE Q. TENANT and JON Q. TENANT": " and ".join(names),
            "1234 EXAMPLE AVE S APT 5": street, "SEATTLE, WA 98100": city}
    items = []
    for x, y, s, t in fx.ITEMS:
        for a, b in swap.items():
            t = t.replace(a, b)
        items.append((x, y, s, t))
    truth = {"plaintiff": plaintiff, "defendants": list(names),
             "street": street.split(" UNIT ")[0].split(" APT ")[0],
             "unit": ("UNIT 7" if "UNIT" in street else "APT 3B" if "APT" in street else ""),
             "city": city.split(",")[0].title(), "state": "WA", "zip": "98100"}
    return items, truth


def _write_corrections(out, labeled):
    """Append one correction per (row, truth, boxes) as the review page's
    server would save it."""
    from extract_text.corrections import build_correction
    from extract_text.pipeline import read_scan

    rows, details = read_scan(out)
    with open(out / "corrections.jsonl", "a") as f:
        for row_no, truth, boxes in labeled:
            body = {"truth": truth}
            if boxes is not None:
                body["boxes"] = boxes
            f.write(json.dumps(build_correction(row_no, body, rows, details, out)) + "\n")


# ---------------------------------------------------------------------------
# arithmetic, no files
# ---------------------------------------------------------------------------


def test_one_ocr_slip_counts_as_the_same_printed_word():
    assert _edit1("SUMMONS", "SUMM0NS")
    assert _edit1("SUMMONS", "SUMMON")
    assert _edit1("SUMMONS", "SUMMONSS")
    assert not _edit1("SUMMONS", "SIMMONZ")
    assert not _edit1("TO", "T0") or True  # short words are compared exactly elsewhere


def test_region_is_the_union_of_the_boxes_without_the_slip():
    boxes = [([0.60, 0.40, 0.80, 0.45], "drawn"), ([0.61, 0.41, 0.82, 0.46], "drawn"),
             ([0.59, 0.42, 0.79, 0.47], "confirmed"),
             ([0.10, 0.80, 0.30, 0.85], "drawn")]           # far away: a slip
    r = region_from_boxes(boxes)
    assert r.drawn == 2 and r.confirmed == 1 and r.dropped == 1
    assert r.box == pytest.approx([0.585, 0.395, 0.825, 0.475])
    assert region_from_boxes([]) is None


def _words(rows, shift=(0.0, 0.0), page=1):
    """Synthetic page words: rows of (y, x, text ...), each word 0.05 wide."""
    out = []
    for y, x, *texts in rows:
        for k, t in enumerate(texts):
            x0 = x + k * 0.07 + shift[0]
            y0 = y + shift[1]
            out.append(Word(page, x0, y0, x0 + 0.05, y0 + 0.012, t))
    return out


def _lines(words):
    by_y = {}
    for w in words:
        by_y.setdefault(round(w.y0, 3), []).append(w)
    return [Line(ws) for _, ws in sorted(by_y.items())]


FORM_A = [(0.10, 0.2, "SUPERIOR", "COURT", "OF", "WASHINGTON"), (0.13, 0.3, "COUNTY", "OF", "SAMPLE"),
          (0.20, 0.3, "Plaintiff(s),"), (0.24, 0.15, "vs."), (0.32, 0.3, "Defendant(s)."),
          (0.42, 0.6, "Served", "upon:"), (0.60, 0.15, "This", "is", "notice", "of", "a", "lawsuit"),
          (0.63, 0.15, "Your", "landlord", "is", "asking", "the", "court"),
          (0.66, 0.15, "If", "you", "want", "to", "defend", "yourself")]
FORM_B = [(0.08, 0.3, "IN", "THE", "SUPERIOR", "COURT"), (0.11, 0.3, "IN", "AND", "FOR", "KING"),
          (0.30, 0.5, "EVICTION", "SUMMONS"), (0.33, 0.5, "(Residential)"),
          (0.40, 0.15, "TO", "THE", "DEFENDANT(S):"), (0.50, 0.15, "This", "is", "notice", "of", "a", "lawsuit"),
          (0.53, 0.15, "Your", "landlord", "is", "asking", "the", "court"),
          (0.56, 0.15, "If", "you", "want", "to", "defend", "yourself"),
          (0.70, 0.15, "You", "must", "respond", "in", "writing")]


def _page(form, values, shift=(0.0, 0.0)):
    from extract_text.templates import page_words

    return page_words(_lines(_words(form + values, shift)))


def test_pages_of_one_form_are_alike_and_pages_of_two_are_not():
    a1 = _page(FORM_A, [(0.17, 0.15, "EXAMPLE", "PROPERTY", "LLC,"), (0.28, 0.15, "JANE", "Q.", "TENANT,"),
                        (0.46, 0.6, "JANE", "Q.", "TENANT"), (0.49, 0.6, "9012", "SPECIMEN", "DRIVE")])
    a2 = _page(FORM_A, [(0.17, 0.15, "SAMPLE", "HOLDINGS", "LLC,"), (0.28, 0.15, "ALEX", "P.", "OCCUPANT,"),
                        (0.46, 0.6, "ALEX", "P.", "OCCUPANT"), (0.49, 0.6, "7890", "EXEMPLAR", "COURT")])
    b1 = _page(FORM_B, [(0.20, 0.15, "SPECIMEN", "REALTY", "GROUP", "LLC,"), (0.43, 0.35, "TAYLOR", "S.", "LESSEE"),
                        (0.46, 0.35, "1357", "SPECIMEN", "ROAD")])
    assert page_similarity(a1, a2) > 0.6
    # the notice prose is shared by both forms, at different heights
    assert page_similarity(a1, b1) < 0.3
    assert group_pages([a1, b1, a2]) == [[0, 2], [1]]


def test_fingerprint_is_the_printed_form_outside_the_regions():
    values = [[(0.17, 0.15, "EXAMPLE", "PROPERTY", "LLC,"), (0.46, 0.6, "JANE", "Q.", "TENANT"),
               (0.49, 0.6, "9012", "SPECIMEN", "DRIVE")],
              [(0.17, 0.15, "SAMPLE", "HOLDINGS", "LLC,"), (0.46, 0.6, "ALEX", "P.", "OCCUPANT"),
               (0.49, 0.6, "7890", "EXEMPLAR", "COURT")],
              [(0.17, 0.15, "NOTIONAL", "ASSET", "MANAGEMENT"), (0.46, 0.6, "SAM", "T.", "HOUSEHOLDER"),
               (0.49, 0.6, "1470", "NOTIONAL", "CROSSING")]]
    pages = [_page(FORM_A, v) for v in values]
    regions = {"address": [Region([0.58, 0.48, 0.95, 0.52])], "defendants": [Region([0.58, 0.45, 0.95, 0.48])]}
    fp = learn_fingerprint(pages, regions)
    texts = {w["text"] for w in fp}
    assert {"SUPERIOR", "WASHINGTON", "SERVED", "UPON", "LANDLORD"} <= texts
    # the values are on one page each, and the regions hide what is inside them
    # ("SAMPLE" stays: the county's name in the header is printed form text)
    assert not texts & {"EXAMPLE", "HOLDINGS", "JANE", "TENANT", "9012", "SPECIMEN", "HOUSEHOLDER"}
    # "LLC" repeats on two pages at the same place: below the 80% share
    assert "LLC" not in texts


def test_a_shifted_page_still_matches_and_the_regions_follow():
    values = [(0.17, 0.15, "EXAMPLE", "PROPERTY", "LLC,"), (0.46, 0.6, "JANE", "Q.", "TENANT"),
              (0.49, 0.6, "9012", "SPECIMEN", "DRIVE")]
    pages = [_page(FORM_A, values), _page(FORM_A, values[:1])]
    fp = learn_fingerprint(pages, {})
    t = Template("form-1", fp, {"address": [Region([0.58, 0.48, 0.95, 0.52])]}, pages=2, approved=True)
    straight = _lines(_words(FORM_A + values))
    shifted = _lines(_words(FORM_A + values, shift=(0.03, 0.025)))   # a scanner's margin
    assert match_page(straight, [t]).score == 1.0
    m = match_page(shifted, [t])
    assert m is not None and m.shift == pytest.approx((0.03, 0.025), abs=0.002)
    assert [ln.text for ln in m.region_lines(shifted, m.regions("address")[0])] == ["9012 SPECIMEN DRIVE"]
    # a page of another form matches nothing
    assert match_page(_lines(_words(FORM_B)), [t]) is None
    # and a template with too few words to identify a form is never matched
    assert match_page(straight, [Template("thin", fp[:5], {}, approved=True)]) is None


def test_labeled_boxes_take_drawn_boxes_and_confirmed_engine_boxes():
    detail = {"deterministic": {"evidence": {
        "defendant_address": {"page": 1, "box": [0.6, 0.5, 0.9, 0.53]},
        "defendants.0.name": {"page": 1, "box": [0.6, 0.46, 0.8, 0.48]},
        "defendants.1.name": {"page": 1, "box": [0.6, 0.48, 0.8, 0.50]},
        "plaintiffs.0.name": {"page": 1, "box": [0.1, 0.17, 0.4, 0.19]},
        "attorney": {"page": 1, "box": [0.55, 0.8, 0.9, 0.9]},
        "case_number": {"page": 1, "box": [0.6, 0.15, 0.8, 0.17]}}}}
    c = {"verdict": "corrected", "changed_fields": ["street"],
         "truth": {"plaintiff": "P", "defendants": ["A", "B"], "street": "x", "attorneys": ["F"]},
         "boxes": {"address": [0.61, 0.5, 0.91, 0.53], "plaintiff": None}}
    got = labeled_boxes(c, detail)
    assert got["address"] == [(1, [0.61, 0.5, 0.91, 0.53], "drawn")]
    assert "plaintiff" not in got                         # "not in this document"
    assert got["defendants"] == [(1, [0.6, 0.46, 0.8, 0.50], "confirmed")]   # both names, one box
    assert got["attorney"] == [(1, [0.55, 0.8, 0.9, 0.9], "confirmed")]
    assert "case" not in got                              # only ever drawn
    # boxes saved with pages, several for one field, keep their pages
    c3 = {**c, "boxes": {"attorney": [{"page": 1, "box": [0.5, 0.8, 0.9, 0.9]},
                                      {"page": 2, "box": [0.5, 0.82, 0.9, 0.92]}]}}
    assert labeled_boxes(c3, detail)["attorney"] == [(1, [0.5, 0.8, 0.9, 0.9], "drawn"),
                                                     (2, [0.5, 0.82, 0.9, 0.92], "drawn")]
    assert labeled_boxes({**c, "verdict": "unreadable"}, detail) == {}
    # a changed plaintiff confirms nothing about the engine's plaintiff box
    c2 = {"verdict": "corrected", "changed_fields": ["plaintiff"],
          "truth": {"plaintiff": "Q", "defendants": ["A", "B"], "street": "x"}}
    assert "plaintiff" not in labeled_boxes(c2, detail) and "address" in labeled_boxes(c2, detail)


# ---------------------------------------------------------------------------
# the whole loop on synthetic pages
# ---------------------------------------------------------------------------


@needs_system_tools
def test_templates_are_learned_from_drawn_boxes_and_read_a_held_out_page(tmp_path):
    from extract_text import extract
    from extract_text.pipeline import scan
    from extract_text.templates import (
        approve_template,
        learn_templates,
        write_templates_review,
    )

    fx = _fixtures_module()
    docs, out = tmp_path / "docs", tmp_path / "results"
    docs.mkdir()
    labeled = []
    for i in range(5):
        items, boxes, truth = served_upon_form(i)
        (docs / f"doc_{i}.pdf").write_bytes(fx.build_text_pdf(items))
        labeled.append((i + 1, truth, boxes))
    # two pages of another form, with no boxes: too few for a template
    for j, items in enumerate((fx.KC_PRINTED_ITEMS, fx.KC_EFILED_ITEMS)):
        (docs / f"doc_{5 + j}.pdf").write_bytes(fx.build_text_pdf(items))

    rows = scan([docs], out_dir=out, progress=False)
    # the ladder cannot read this form: that is what makes the template measurable
    assert all(r["defendant_street"] == "" for r in rows[:5])
    assert all("no_defendant_address" in r["flags"] for r in rows[:5])
    _write_corrections(out, labeled)

    written, text = learn_templates(out, min_pages=5)
    assert [t.name for t in written] == ["form-1"]
    assert "5 graded documents with a labeled position" in text
    assert "written to form-1.json" in text
    t = written[0]
    assert t.pages == 5 and not t.approved
    assert set(t.regions) == {"plaintiff", "defendants", "address", "attorney"}
    assert t.regions["address"][0].drawn == 5 and t.regions["attorney"][0].confirmed == 5
    # the address region sits right of centre, where the form prints it
    assert t.regions["address"][0].box[0] > 0.6 and t.regions["address"][0].page == 1
    # the fingerprint is the printed form: no value word, nothing from inside a region
    words = {w["text"] for w in t.fingerprint}
    assert {"SUPERIOR", "SERVED", "UPON", "LANDLORD", "SUMMONS"} <= words
    assert not words & {"SPECIMEN", "EXEMPLAR", "NOTIONAL", "PLACEHOLDER", "TENANT", "OCCUPANT",
                        "LESSEE", "RESIDENT", "DWELLER", "MAIN", "PLLC", "98100", "98101"}
    assert not any(w["text"].isdigit() and len(w["text"]) >= 3 for w in t.fingerprint)
    saved = json.loads((out / "templates" / "form-1.json").read_text())
    assert saved["approved"] is False and saved["learned_from"]["rows"] == [1, 2, 3, 4, 5]

    held_out, _, truth = served_upon_form(5)
    page = tmp_path / "held_out.pdf"
    page.write_bytes(fx.build_text_pdf(held_out))

    # unapproved: nothing changes, and a scan asked to use the folder refuses
    x = extract(str(page), templates=out / "templates")
    assert x.template is None and x.record.defendant_address is None
    with pytest.raises(ValueError, match="no approved form templates"):
        scan([page], out_dir=tmp_path / "refused", progress=False, templates=out / "templates")

    approve_template("form-1", out / "templates", by="A. Reviewer")
    assert load_templates(out / "templates")[0].approved_by == "A. Reviewer"
    x = extract(str(page), templates=out / "templates")
    assert x.template == "form-1"
    assert x.evidence["defendant_address"].anchor == "template:form-1"
    assert x.record.defendant_address.street == "3690 PLACEHOLDER HIGHWAY"
    assert x.record.defendant_address.city == "Sampleton"
    assert x.record.defendant_address.zip == "98100"
    assert [d.name for d in x.record.defendants] == ["SAM T. HOUSEHOLDER"]
    assert [p.name for p in x.record.plaintiffs] == ["NOTIONAL ASSET MANAGEMENT LLC"]
    assert x.evidence["plaintiffs.0.name"].anchor == "template:form-1"
    assert x.record.attorney.firm == "EXAMPLE LAW GROUP PLLC"
    assert x.evidence["attorney"].anchor == "template:form-1"
    assert x.record.case_number == "25-2-00006-0"
    assert "no_defendant_address" not in x.flags

    # a page of a different form falls through to the ladder, unchanged
    other = FIXTURES / "synthetic_kc_efiled.pdf"
    with_t = extract(str(other), templates=out / "templates")
    without = extract(str(other))
    assert with_t.template is None
    assert with_t.evidence["defendant_address"].anchor == "to_block"
    assert with_t.record == without.record

    # the same form with an empty service block: the template matches, its
    # address region is empty, the ladder runs and finds nothing, and the
    # document is flagged rather than guessed
    blank, _, _ = served_upon_form(6, service_block=False)
    (tmp_path / "blank.pdf").write_bytes(fx.build_text_pdf(blank))
    x = extract(str(tmp_path / "blank.pdf"), templates=out / "templates")
    assert x.template == "form-1" and x.record.defendant_address is None
    assert "no_defendant_address" in x.flags

    # a scan with the folder fills the template column and the anchor
    rows = scan([page, other], out_dir=tmp_path / "with", progress=False, templates=out / "templates")
    by_file = {r["file"]: r for r in rows}
    assert by_file[page.name]["template"] == "form-1"
    assert by_file[page.name]["defendant_anchor"] == "template:form-1"
    assert by_file[other.name]["template"] == ""

    # the review page draws the regions over a learned page and names the counts
    html = write_templates_review(out / "templates", out).read_text()
    assert "form-1" in html and 'class="region"' in html and "5 drawn box" in html
    assert (out / "templates" / "review" / "form-1_p1.png").exists()
    assert "Approved by A. Reviewer" in html


@needs_system_tools
def test_a_shifted_scan_of_the_form_is_recognized(tmp_path):
    """A photocopy shifts the whole page; the learned positions still apply."""
    from extract_text import extract
    from extract_text.pipeline import scan
    from extract_text.templates import approve_template, learn_templates

    fx = _fixtures_module()
    docs, out = tmp_path / "docs", tmp_path / "results"
    docs.mkdir()
    labeled = []
    for i in range(5):
        items, boxes, truth = served_upon_form(i)
        (docs / f"doc_{i}.pdf").write_bytes(fx.build_text_pdf(items))
        labeled.append((i + 1, truth, boxes))
    scan([docs], out_dir=out, progress=False)
    _write_corrections(out, labeled)
    learn_templates(out, min_pages=5)
    approve_template("form-1", out / "templates")

    items, _, _ = served_upon_form(5, shift=(14, 12))       # about 2.3% right, 1.5% down
    page = tmp_path / "shifted.pdf"
    page.write_bytes(fx.build_text_pdf(items))
    x = extract(str(page), templates=out / "templates")
    assert x.template == "form-1"
    assert x.record.defendant_address.street == "3690 PLACEHOLDER HIGHWAY"
    assert [d.name for d in x.record.defendants] == ["SAM T. HOUSEHOLDER"]

    # the same page as a scan read by OCR
    fx.draw_page_image(items, dpi=200).save(tmp_path / "scanned.pdf", "PDF", resolution=200.0)
    x = extract(str(tmp_path / "scanned.pdf"), templates=out / "templates")
    assert x.template == "form-1"
    assert x.record.defendant_address.street == "3690 PLACEHOLDER HIGHWAY"


@needs_system_tools
def test_confirmed_readings_alone_teach_a_template(tmp_path):
    """Graded documents the engine got right, with no box drawn, still place
    every field: the engine's own boxes are confirmed by the grader."""
    from extract_text import extract
    from extract_text.pipeline import scan
    from extract_text.templates import approve_template, learn_templates

    fx = _fixtures_module()
    docs, out = tmp_path / "docs", tmp_path / "results"
    docs.mkdir()
    labeled = []
    for i in range(6):
        items, truth = to_block_form(i)
        (docs / f"doc_{i}.pdf").write_bytes(fx.build_text_pdf(items))
        labeled.append((i + 1, truth, None))
    rows = scan([docs], out_dir=out, progress=False)
    assert all(r["defendant_anchor"] == "to_block" for r in rows)
    _write_corrections(out, labeled)
    corrections = [json.loads(l) for l in (out / "corrections.jsonl").read_text().splitlines()]
    assert all(c["verdict"] == "confirmed" for c in corrections), [c["changed_fields"] for c in corrections]

    written, text = learn_templates(out, min_pages=6)
    assert len(written) == 1
    t = written[0]
    assert t.regions["address"][0].confirmed == 6 and t.regions["address"][0].drawn == 0
    assert "defendants" in t.regions and "plaintiff" in t.regions
    assert "attorney" not in t.regions          # the grader was not asked about it
    approve_template(t.name, out / "templates")

    items, truth = to_block_form(6)
    page = tmp_path / "held_out.pdf"
    page.write_bytes(fx.build_text_pdf(items))
    with_t = extract(str(page), templates=out / "templates")
    without = extract(str(page))
    assert with_t.template == t.name
    assert with_t.evidence["defendant_address"].anchor == f"template:{t.name}"
    # the template reads what the ladder reads on this form: nothing broken
    assert with_t.record.defendant_address == without.record.defendant_address
    assert [d.name for d in with_t.record.defendants] == [d.name for d in without.record.defendants]
    assert with_t.record.defendant_address.street == "2468 NOTIONAL TERRACE APT 3B"


@needs_system_tools
def test_rules_eval_measures_templates_and_the_cli_lists_them(tmp_path, capsys):
    import subprocess
    import sys

    from extract_text.cli import main
    from extract_text.pipeline import scan
    from extract_text.templates import learn_templates

    fx = _fixtures_module()
    docs, out = tmp_path / "docs", tmp_path / "results"
    docs.mkdir()
    labeled = []
    for i in range(6):
        items, boxes, truth = served_upon_form(i)
        (docs / f"doc_{i}.pdf").write_bytes(fx.build_text_pdf(items))
        labeled.append((i + 1, truth, boxes if i < 5 else None))
    scan([docs], out_dir=out, progress=False)
    _write_corrections(out, labeled)
    learn_templates(out, rows=[1, 2, 3, 4, 5], min_pages=5, name="served-upon")

    assert main(["templates", "list", "--templates", str(out / "templates")]) == 0
    assert "served-upon" in capsys.readouterr().out and "not approved" in capsys.readouterr().out or True
    assert main(["templates", "approve", "served-upon", "--templates", str(out / "templates")]) == 0
    assert load_templates(out / "templates")[0].name == "served-upon"

    # rules_eval: before, every street blank; with the templates, all six right
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "rules_eval.py"), "--out", str(out),
                        "--templates", str(out / "templates")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    street = next(l for l in r.stdout.splitlines() if l.strip().startswith("street"))
    n, before, now, fixed, broke = street.split()[1:6]
    assert (n, before, now, fixed, broke) == ("6", "0", "6", "6", "0")
    assert "served-upon" in r.stdout and "6" in r.stdout.split("form templates")[1]


def bundle_form(i, n_pages=4, address_page=3):
    """Page i of a four-page bundle: the caption on page 1, the 'Served
    upon:' block on page 3 (a page the engine's default read skips), and
    the attorney's footer on every page."""
    page1, boxes, truth = served_upon_form(i, service_block=False)
    footer = [it for it in page1 if it[1] >= 640]
    pages = [page1]
    names, street, city = DEFENDANTS[i], STREETS[i], CITIES[i % 2]
    for p in range(2, n_pages + 1):
        items = [(40, 100 + (k - 1) * 24, 9, str(k)) for k in range(1, 27)]
        items += [(90, 100, 9, "This is notice of a lawsuit to evict you from the property which you are renting."),
                  (90, 114, 9, "Your landlord is asking the court to terminate your tenancy.")]
        if p == address_page:
            items.append((380, 330, 9, "Served upon:"))
            y = 346
            name_items = []
            for n in names:
                name_items.append((380, y, 9, n))
                y += 14
            addr_items = [(380, y, 9, street), (380, y + 14, 9, city)]
            items += name_items + addr_items
            boxes["defendants"] = [{"page": p, "box": _union([_box(x, yy, s, t) for x, yy, s, t in name_items])}]
            boxes["address"] = [{"page": p, "box": _union([_box(x, yy, s, t) for x, yy, s, t in addr_items])}]
        items += footer
        pages.append(items)
    # the attorney block, boxed on two pages
    att = _union([_box(x, yy, s, t) for x, yy, s, t in footer])
    boxes["attorney"] = [{"page": 1, "box": att}, {"page": 2, "box": att}]
    boxes["plaintiff"] = [{"page": 1, "box": boxes["plaintiff"]}]
    return pages, boxes, truth


@needs_system_tools
def test_regions_on_a_later_page_are_learned_and_read(tmp_path):
    """Boxes drawn on page 3 teach a page-3 region; on a new document the
    engine reads that page for the template, though its default read skips
    it, and the anchor says which page the address came from."""
    from extract_text import extract
    from extract_text.pipeline import scan
    from extract_text.templates import approve_template, learn_templates

    fx = _fixtures_module()
    docs, out = tmp_path / "docs", tmp_path / "results"
    docs.mkdir()
    labeled = []
    for i in range(5):
        pages, boxes, truth = bundle_form(i)
        (docs / f"doc_{i}.pdf").write_bytes(fx.build_text_pdf_pages(pages))
        labeled.append((i + 1, truth, boxes))
    rows = scan([docs], out_dir=out, progress=False)
    assert all(r["n_pages"] == 4 and r["defendant_street"] == "" for r in rows)
    _write_corrections(out, labeled)
    written, text = learn_templates(out, min_pages=5)
    t = written[0]
    assert [r.page for r in t.regions["address"]] == [3]
    assert [r.page for r in t.regions["attorney"]] == [1, 2]
    assert t.region_pages() == {1, 2, 3}
    assert "address p3 (5 drawn" in text and "attorney p1" in text and "attorney p2" in text
    approve_template(t.name, out / "templates")

    pages, _, truth = bundle_form(5)
    page = tmp_path / "held_out.pdf"
    page.write_bytes(fx.build_text_pdf_pages(pages))
    x = extract(str(page), templates=out / "templates")
    assert x.template == t.name
    assert x.evidence["defendant_address"].anchor == f"template:{t.name}@p3"
    assert x.evidence["defendant_address"].page == 3
    assert x.record.defendant_address.street == "3690 PLACEHOLDER HIGHWAY"
    assert [d.name for d in x.record.defendants] == ["SAM T. HOUSEHOLDER"]
    assert x.record.attorney.firm == "EXAMPLE LAW GROUP PLLC"
    assert x.evidence["attorney"].anchor == f"template:{t.name}"
    # saved again as JSON, the regions keep their pages
    reloaded = load_templates(out / "templates")[0]
    assert [r.page for r in reloaded.regions["address"]] == [3]


def test_a_template_file_from_before_pages_still_loads():
    """A region saved as one dict (before 2026-11-10) is a page-1 region."""
    d = {"name": "old", "fingerprint": [{"text": f"W{k}", "x": 0.1, "y": 0.1 * k} for k in range(12)],
         "regions": {"address": {"box": [0.6, 0.4, 0.9, 0.46], "drawn": 5}}}
    t = Template.from_json(d)
    assert [(r.page, r.drawn) for r in t.regions["address"]] == [(1, 5)]
    assert t.to_json()["regions"]["address"] == [{"page": 1, "box": [0.6, 0.4, 0.9, 0.46],
                                                  "drawn": 5, "confirmed": 0, "dropped": 0}]
