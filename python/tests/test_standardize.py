"""The standardized address columns. Every address here is invented."""

from __future__ import annotations

import pytest

from extract_text.standardize import standardize_address, standardize_unit
from extract_text.usps_tables import SUFFIXES, UNITS


@pytest.mark.parametrize("street, unit, want_street, want_unit", [
    # house number run into the street, a unit the engine split out
    ("1234-EXAMPLE AVE. NE BLDG ZZ Apt # 102", "BLDG ZZ Apt # 102",
     "1234 EXAMPLE AVE NE", "BLDG ZZ APT 102"),
    # spelled-out suffix, directional, and designator; no unit column given
    ("1234 Example Avenue South, Apartment 5", None, "1234 EXAMPLE AVE S", "APT 5"),
    ("12345 Southeast 999th Place", "", "12345 SE 999TH PL", ""),
    # a pound sign alone stays; a fraction stays with the house number
    ("1234 1/2 Sample St #3", "#3", "1234 1/2 SAMPLE ST", "# 3"),
    ("1234 S 999th St Unit B-4", "Unit B-4", "1234 S 999TH ST", "UNIT B-4"),
    ("1234 Example Ave North", None, "1234 EXAMPLE AVE N", ""),
    # a directional that is the street's name stays spelled out
    ("1234 North Street", None, "1234 NORTH ST", ""),
    ("1234 West Avenue", None, "1234 WEST AVE", ""),
    # Pub. 28 233.23: the second of two directionals is part of the name
    ("1234 East West Example Hwy", None, "1234 E WEST EXAMPLE HWY", ""),
    ("1234A Sample Way", None, "1234A SAMPLE WAY", ""),
    # a numbered street run into the house number splits; a range does not
    ("12345-999TH AVE NE", None, "12345 999TH AVE NE", ""),
    ("1234-1236 Sample Way", None, "1234-1236 SAMPLE WAY", ""),
])
def test_street_and_unit(street, unit, want_street, want_unit):
    got = standardize_address(street, unit)
    assert got["street_std"] == want_street
    assert got["unit_std"] == want_unit


def test_one_line_address_and_house_number():
    got = standardize_address("1234 Example Avenue South", "Apt # 5", "Seattle", "Wa", "98100-1234")
    assert got == {"house_number": "1234", "street_std": "1234 EXAMPLE AVE S",
                   "unit_std": "APT 5",
                   "address_std": "1234 EXAMPLE AVE S APT 5, SEATTLE, WA 98100-1234"}


def test_no_street_gives_blanks():
    assert standardize_address(None, "APT 5", "SEATTLE", "WA", "98100") == {
        "house_number": "", "street_std": "", "unit_std": "", "address_std": ""}


def test_tables_came_from_the_publication():
    assert SUFFIXES["AVENUE"] == SUFFIXES["AV"] == "AVE"
    assert SUFFIXES["MEADOWS"] == "MDWS" and SUFFIXES["MDW"] == "MDW"
    assert UNITS["APARTMENT"] == "APT" and UNITS["SUITE"] == "STE"
    assert standardize_unit("Suite # 200") == "STE 200"
