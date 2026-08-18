"""Rule engine tests.

Every fixture here is synthetic. Real court records never enter this repository,
including in tests. See CONTRIBUTING.md.
"""

from __future__ import annotations

import pytest

from extract_text import compare, extract_deterministic
from extract_text.deterministic import parse_date, parse_money

SYNTHETIC_COMPLAINT = """\
IN THE SUPERIOR COURT OF THE STATE OF CALIFORNIA
COUNTY OF ALAMEDA

Case No. RG-24-108833

ACME HOLDINGS LLC and RIVERSIDE PROPERTIES INC.,
                                              Plaintiffs,
v.
JORDAN A. RIVERA and CASEY OKONKWO,
                                              Defendants.

COMPLAINT FOR UNLAWFUL DETAINER

Date Filed: 03/14/2024
Amount Claimed: $4,820.00

Judgment Entered: 05/02/2024
Judgment Amount: $5,140.75
Disposition: Judgment for Plaintiff
Disposition Date: 05/02/2024
"""

EMPTY_DOCUMENT = "This page intentionally left blank."


@pytest.fixture
def extraction():
    return extract_deterministic(SYNTHETIC_COMPLAINT)


def test_reads_scalar_fields(extraction):
    record = extraction.record
    assert record.case_number == "RG-24-108833"
    assert record.county == "ALAMEDA"
    assert record.filing_date.isoformat() == "2024-03-14"
    assert record.amount_claimed == 4820.00


def test_case_type_is_recorded_as_written(extraction):
    """Not normalized. The document says it in caps, so we say it in caps."""
    assert extraction.record.case_type == "UNLAWFUL DETAINER"


def test_reads_judgment(extraction):
    judgment = extraction.record.judgment
    assert judgment is not None
    assert judgment.amount == 5140.75
    assert judgment.date.isoformat() == "2024-05-02"


def test_splits_caption_into_parties(extraction):
    plaintiffs = [p.name for p in extraction.record.plaintiffs]
    defendants = [d.name for d in extraction.record.defendants]
    assert "ACME HOLDINGS LLC" in plaintiffs
    assert "RIVERSIDE PROPERTIES INC." in plaintiffs
    assert "JORDAN A. RIVERA" in defendants
    assert "CASEY OKONKWO" in defendants


def test_flags_business_parties(extraction):
    by_name = {p.name: p for p in extraction.record.plaintiffs}
    assert by_name["ACME HOLDINGS LLC"].is_business is True
    by_name = {d.name: d for d in extraction.record.defendants}
    assert by_name["CASEY OKONKWO"].is_business is False


def test_every_field_carries_a_locatable_span(extraction):
    """The audit guarantee: rule output can always be checked against source."""
    assert extraction.evidence
    for path, ev in extraction.evidence.items():
        assert ev.grounded, f"{path} not grounded"
        assert ev.span is not None, f"{path} has no span"
        start, end = ev.span
        assert SYNTHETIC_COMPLAINT[start:end] == ev.quote


def test_absent_fields_stay_none():
    extraction = extract_deterministic(EMPTY_DOCUMENT)
    assert extraction.record.case_number is None
    assert extraction.record.judgment is None
    assert extraction.record.plaintiffs == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("03/14/2024", "2024-03-14"),
        ("3-14-24", "2024-03-14"),
        ("2024-03-14", "2024-03-14"),
        ("March 14, 2024", "2024-03-14"),
        ("Mar 14 2024", "2024-03-14"),
    ],
)
def test_parses_the_date_shapes_courts_use(raw, expected):
    assert parse_date(raw).isoformat() == expected


def test_unparseable_date_returns_none_rather_than_raising():
    assert parse_date("sometime last spring") is None


@pytest.mark.parametrize(
    "raw,expected", [("$4,820.00", 4820.0), ("$ 1,000", 1000.0), ("$0.50", 0.5)]
)
def test_parses_money(raw, expected):
    assert parse_money(raw) == expected


def test_comparing_an_extraction_to_itself_agrees_completely(extraction):
    report = compare(extraction, extraction)
    assert report.disagreements == []
    assert report.agreement_rate == 1.0
    assert report.needs_review == []


def test_comparison_separates_disagreement_from_coverage_gaps(extraction):
    sparse = extract_deterministic(EMPTY_DOCUMENT)
    report = compare(extraction, sparse)
    assert report.disagreements == []
    assert report.only_one_found
    assert all(f.status == "only_a" for f in report.only_one_found)
    assert report.agreement_rate == 0.0
