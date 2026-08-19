"""Tests for card building, especially the parts that keep names off a card."""

from pathlib import Path

import pytest

from extract_text import documents
from extract_text.cards import (
    NEVER_REDACT,
    display_address,
    locate_address,
    name_tokens,
    render_card,
    safe_to_show,
)
from extract_text.deterministic import extract_from_document

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# display text
# ---------------------------------------------------------------------------

def test_display_joins_the_parts_a_person_reads():
    assert display_address("1234 EXAMPLE AVE S", "", "Seattle", "WA", "98100") == \
        "1234 EXAMPLE AVE S, Seattle, WA 98100"


def test_display_does_not_repeat_a_unit_already_inside_the_street():
    # street carries the whole regex match, unit included; appending would
    # produce "APT 5 APT 5"
    out = display_address("1234 EXAMPLE AVE S APT 5", "APT 5", "Seattle", "WA", "98100")
    assert out.count("APT 5") == 1


def test_display_appends_a_unit_that_is_missing_from_the_street():
    out = display_address("1234 EXAMPLE AVE S", "APT 5", "Seattle", "WA", "98100")
    assert out.startswith("1234 EXAMPLE AVE S APT 5,")


def test_display_omits_missing_parts_without_stray_commas():
    assert display_address("1234 EXAMPLE AVE S", "", "", "", "") == "1234 EXAMPLE AVE S"
    assert display_address("1234 EXAMPLE AVE S", "", "Sampleton", "", "") == \
        "1234 EXAMPLE AVE S, Sampleton"


# ---------------------------------------------------------------------------
# which words get painted over
# ---------------------------------------------------------------------------

class _P:
    def __init__(self, name):
        self.name = name


class _Rec:
    def __init__(self, defendants=(), plaintiffs=(), attorney=None):
        self.defendants = list(defendants)
        self.plaintiffs = list(plaintiffs)
        self.attorney = attorney


def test_party_names_are_selected_for_redaction():
    rec = _Rec(defendants=[_P("JANE Q. TENANT"), _P("JON Q. TENANT")])
    toks = name_tokens(rec, "1234 EXAMPLE AVE S APT 5 SEATTLE WA 98100")
    assert {"JANE", "JON", "TENANT"} <= toks


def test_placeholder_names_are_redacted_because_real_people_share_them():
    # "John and Jane Doe, unknown occupants" is boilerplate, but John, Jane and
    # Doe are also real names, so they are covered rather than spared
    rec = _Rec(defendants=[_P("JOHN DOE and JANE DOE, unknown occupants")])
    toks = name_tokens(rec, "1234 EXAMPLE AVE S, Sampleton, WA 98100")
    assert {"JOHN", "JANE", "DOE"} <= toks
    assert "OCCUPANTS" not in toks and "UNKNOWN" not in toks


def test_a_surname_is_selected():
    rec = _Rec(defendants=[_P("Quill Fernwater and Robin Fernwater")])
    toks = name_tokens(rec, "1234 EXAMPLE AVE S APT 5, Sampleton, WA 98100")
    assert "FERNWATER" in toks and "QUILL" in toks


def test_a_street_named_after_a_person_stays_legible():
    # redacting a word that is part of the address would hide the very thing
    # the rater is being asked to check
    rec = _Rec(defendants=[_P("Marlow Everly")])
    toks = name_tokens(rec, "1234 MARLOW EVERLY WAY, Sampleton, WA 98100")
    assert "EVERLY" not in toks
    assert "MARLOW" not in toks


def test_address_vocabulary_is_never_redacted():
    rec = _Rec(defendants=[_P("North South Avenue Court")])
    assert name_tokens(rec, "") == set()


def test_short_and_numeric_tokens_are_ignored_as_ocr_debris():
    rec = _Rec(defendants=[_P("NN OO 4B X Q")])
    assert name_tokens(rec, "") == set()


def test_never_redact_covers_courtroom_role_words():
    for w in ("ATTORNEY", "PLAINTIFF", "DEFENDANT", "FOR", "COUNSEL"):
        assert w in NEVER_REDACT


# ---------------------------------------------------------------------------
# the safety rule
# ---------------------------------------------------------------------------

def test_a_card_with_nothing_redacted_is_withheld():
    ok, why = safe_to_show(set())
    assert ok is False and why == "no_name_redacted"


def test_a_card_with_a_redacted_name_may_be_shown():
    ok, why = safe_to_show({"SCHMITT"})
    assert ok is True and why == ""


# ---------------------------------------------------------------------------
# locating and rendering, against the synthetic fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fixture_doc():
    path = FIXTURES / "synthetic_summons_efiled.pdf"
    if not path.exists():
        pytest.skip("synthetic fixtures not built")
    doc = documents.load_document(path)
    return doc, extract_from_document(doc, expected_case_number="25-2-00001-0")


def test_locate_finds_a_box_inside_the_page(fixture_doc):
    doc, x = fixture_doc
    addr = x.record.defendant_address
    assert addr is not None
    box = locate_address(doc, addr.raw, addr.street or "", 1)
    assert box is not None
    x0, y0, x1, y1 = box
    assert 0.0 <= x0 < x1 <= 1.0
    assert 0.0 <= y0 < y1 <= 1.0


def test_locate_returns_none_for_text_that_is_not_on_the_page(fixture_doc):
    doc, _ = fixture_doc
    assert locate_address(doc, "99999 NOWHERE PKWY, Atlantis, XX 00000", "99999", 1) is None


def test_the_box_is_a_band_not_the_whole_page(fixture_doc):
    # the same address appears twice on a summons; taking the union of every
    # match would span most of the sheet
    doc, x = fixture_doc
    addr = x.record.defendant_address
    _, y0, _, y1 = locate_address(doc, addr.raw, addr.street or "", 1)
    assert (y1 - y0) < 0.25


def test_render_writes_a_readable_crop(fixture_doc, tmp_path):
    doc, x = fixture_doc
    addr = x.record.defendant_address
    box = locate_address(doc, addr.raw, addr.street or "", 1)
    out = render_card(doc.path, 1, box, tmp_path / "c.png",
                      words=doc.words, redact=name_tokens(x.record, addr.raw))
    assert out is not None and out.exists()
    from PIL import Image
    with Image.open(out) as im:
        assert im.width >= 40 and im.height >= 20


def test_first_row_blanking_covers_the_top_line(fixture_doc, tmp_path):
    """On a transcription crop the name is the first row under the label, and
    it has to go even though OCR produced no word box for it."""
    doc, x = fixture_doc
    addr = x.record.defendant_address
    box = locate_address(doc, addr.raw, addr.street or "", 1)
    wide = (0.10, max(0.0, box[1] - 0.03), 0.92, box[3])

    from PIL import Image
    plain = render_card(doc.path, 1, wide, tmp_path / "p.png")
    blanked = render_card(doc.path, 1, wide, tmp_path / "b.png", blank_first_row=True)
    assert plain is not None
    if blanked is None:
        return          # refused because the row spanned the crop; also correct

    def dark(p):
        with Image.open(p) as im:
            return sum(im.convert("L").histogram()[:40])

    assert dark(blanked) > dark(plain)


def test_blanking_refuses_rather_than_returning_a_black_card(fixture_doc, tmp_path):
    """A band whose ink does not separate into rows must yield no card at all.

    On handwriting the rows frequently join, and blanking "the first row" then
    covers the address too. Returning None makes the caller drop the document
    instead of shipping a black rectangle.
    """
    doc, _ = fixture_doc
    thin = (0.10, 0.300, 0.92, 0.318)      # a band barely one text row tall
    out = render_card(doc.path, 1, thin, tmp_path / "t.png", blank_first_row=True)
    if out is not None:
        from PIL import Image
        with Image.open(out) as im:
            hist = im.convert("L").histogram()
            assert sum(hist[:40]) < 0.9 * (im.width * im.height)


def test_redaction_darkens_the_page(fixture_doc, tmp_path):
    """A redacted render must contain strictly more black than a clean one."""
    doc, x = fixture_doc
    addr = x.record.defendant_address
    box = locate_address(doc, addr.raw, addr.street or "", 1)
    wide = (0.0, max(0.0, box[1] - 0.06), 1.0, box[3])   # include the name line

    from PIL import Image
    plain = render_card(doc.path, 1, wide, tmp_path / "plain.png")
    black = render_card(doc.path, 1, wide, tmp_path / "black.png",
                        words=doc.words, redact={"TENANT", "JANE", "PROPERTY"})
    assert plain and black

    def dark_pixels(p):
        with Image.open(p) as im:
            hist = im.convert("L").histogram()
            return sum(hist[:40])

    assert dark_pixels(black) > dark_pixels(plain)
