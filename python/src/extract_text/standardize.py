"""A standardized form of the defendant's address, beside the one as printed.

Court documents spell the same address many ways ("Avenue", "Ave.", "AV";
"Apt # 5", "Apartment 5"; "1234-Example Ave" with the house number run into
the street). Matching an address to another list (a county's address
points, a consumer file, a geocoder) misses whenever the spellings differ,
so this writes each address in one form, following USPS Publication 28:

- upper case, no periods or commas
- the house number on its own (`1234-EXAMPLE AVE` becomes `1234 EXAMPLE AVE`)
- a directional before or after the street name abbreviated (NORTHEAST to
  NE, Pub. 28 section 233), unless it is the whole name or sits between the
  name and the suffix, where Pub. 28 spells it out
- the street suffix, the last word of the name, in its standard
  abbreviation (AVENUE, AV, AVE all to AVE; Appendix C1)
- unit designators abbreviated (APARTMENT to APT; Appendix C2), with the
  pound sign dropped after a designator and kept when it stands alone

Only the form changes. Nothing is looked up, so a misread address stays
misread, just consistently spelled. The as-printed columns are untouched.
"""

from __future__ import annotations

import re

from .usps_tables import SUFFIXES, UNITS

DIRECTIONALS = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
    "N": "N", "S": "S", "E": "E", "W": "W", "NE": "NE", "NW": "NW", "SE": "SE", "SW": "SW",
}

# a house number, optionally with a letter (1234A), and a street run into it
# with a hyphen (1234-EXAMPLE, 1234-287TH); a range (1234-1236) is not split
_HOUSE = re.compile(r"^(\d+[A-Z]?)(?:-([A-Z].*|\d+(?:ST|ND|RD|TH)))?$")
_FRACTION = re.compile(r"^\d+/\d+$")


def _tokens(s: str | None) -> list[str]:
    s = (s or "").upper().replace(".", "").replace(",", " ")
    s = re.sub(r"#\s*", "# ", s)          # "#102" and "# 102" alike
    return [t for t in s.split() if not re.fullmatch(r"-+", t)]   # a bare dash run


def _unit_start(tokens: list[str]) -> int:
    for i, t in enumerate(tokens):
        if i > 0 and (t == "#" or t in UNITS):
            return i
    return len(tokens)


def standardize_unit(unit: str | None) -> str:
    out = []
    for t in _tokens(unit):
        if t == "#" and out and out[-1] in UNITS.values():
            continue                       # "APT # 102" is "APT 102"
        out.append(UNITS.get(t, t))
    return " ".join(out)


def standardize_address(street: str | None, unit: str | None = None, city: str | None = None,
                        state: str | None = None, zip_code: str | None = None) -> dict:
    """House number, standardized street (no unit), standardized unit, and
    the whole address on one line. Every value is "" when there is no
    street."""
    blank = {"house_number": "", "street_std": "", "unit_std": "", "address_std": ""}
    toks = _tokens(street)
    if not toks:
        return blank

    # the unit: the engine's own unit column when it ends the street line,
    # otherwise the first unit designator or pound sign after the number
    unit_toks = _tokens(unit)
    if unit_toks and toks[-len(unit_toks):] == unit_toks and len(toks) > len(unit_toks):
        body, unit_part = toks[:-len(unit_toks)], unit_toks
    else:
        cut = _unit_start(toks)
        body, unit_part = toks[:cut], toks[cut:] or unit_toks

    house = ""
    m = _HOUSE.match(body[0])
    if m:
        house = m.group(1)
        body = ([m.group(2)] if m.group(2) else []) + body[1:]
        if body and _FRACTION.match(body[0]):       # 1234 1/2 MAIN ST
            house, body = f"{house} {body[0]}", body[1:]

    # a directional that would leave only a suffix behind is the name
    # itself ("NORTH ST"), so it stays spelled out
    if body and body[0] in DIRECTIONALS and (len(body) > 2 or (len(body) == 2 and body[1] not in SUFFIXES)):
        body[0] = DIRECTIONALS[body[0]]
    post = ""
    if len(body) > 2 and body[-1] in DIRECTIONALS and body[-2] in SUFFIXES:
        post, body = DIRECTIONALS[body[-1]], body[:-1]
    if len(body) > 1 and body[-1] in SUFFIXES:
        body[-1] = SUFFIXES[body[-1]]
    street_std = " ".join(p for p in (house, " ".join(body), post) if p)
    unit_std = standardize_unit(" ".join(unit_part))

    place = " ".join(p for p in ((state or "").upper().strip(), (zip_code or "").strip()) if p)
    tail = ", ".join(p for p in ((city or "").upper().strip(), place) if p)
    line = " ".join(p for p in (street_std, unit_std) if p)
    return {"house_number": house, "street_std": street_std, "unit_std": unit_std,
            "address_std": f"{line}, {tail}" if tail else line}
