"""Measuring engines against answers a person typed.

The pieces a head-to-head needs, kept apart from any one script so every
comparison in the project is made the same way:

- `wilson`: the interval around a share, so "51 of 65" is never read as a
  rate to the point
- `mcnemar_exact`: whether two engines scored on the same documents differ
  by more than chance (the exact test on the documents where exactly one
  of them is right)
- `truth_key` and `reading_key`: one typed address line, or an engine's
  reading, as a house number, a standardized street, a unit, and a ZIP
- `compare_address`: the paper's forgiving measure (a similarity of 0.7 or
  more counts as the same street) beside a strict one (the same house
  number and the same standardized street name and direction)
- `score_lane`, `paired`, `tiers`: the tables, in counts
- `loss_category`: for a street the rules missed, which stage lost it

Nothing here reads a file or prints a value. The functions take values and
return counts, shares, and row keys; the script that calls them decides
what leaves governed storage, which is counts only.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from math import comb, sqrt

from .similarity import SAME_STREET_THRESHOLD, norm, ratio
from .standardize import UNITS, standardize_address

#: how a typed address line was split into street and the rest, most
#: trustworthy first; reported with every score so a weak split is visible
SPLIT_KINDS = ("pattern", "no_suffix", "comma", "whole", "blank")


def wilson(right: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """The Wilson 95 percent interval for `right` of `n`, as shares."""
    if n <= 0:
        return (0.0, 0.0)
    p = right / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar_exact(first_only: int, second_only: int) -> float:
    """Two-sided exact test on the documents where exactly one engine is
    right: the chance of a split at least this lopsided if the two engines
    were equally good. 1.0 when no document separates them."""
    n = first_only + second_only
    if n == 0:
        return 1.0
    k = min(first_only, second_only)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def seeded_split(cases: list[str], test_n: int, seed: int) -> dict[str, str]:
    """Each case as 'test' or 'dev', by one seeded shuffle of the sorted
    cases: the same cases, seed, and size always give the same split."""
    order = sorted(set(cases))
    random.Random(seed).shuffle(order)
    test = set(order[:max(0, test_n)])
    return {c: ("test" if c in test else "dev") for c in order}


def seeded_draw(cases: list[str], n: int, seed: int) -> list[str]:
    """`n` of the cases, by a seeded shuffle of the sorted cases; a larger
    `n` with the same seed keeps every case a smaller one drew."""
    order = sorted(set(cases))
    random.Random(seed).shuffle(order)
    return order[:n] if n else order


_ZIP_RE = re.compile(r"\b(9[89]\d{3})\b")
_STATE_TAIL_RE = re.compile(r"[,\s]+(?:WA|WASH\.?|WASHINGTON)\b.*$", re.IGNORECASE)


def split_address(text: str) -> dict:
    """A typed address line as its street (unit included), unit, and ZIP,
    with `how` it was split. The package's own address patterns are tried
    first; a line they cannot read is cut at its first comma, and failing
    that used whole, less the state and ZIP at its end."""
    from .deterministic.summons import parse_address, parse_address_nosuffix

    line = re.sub(r"\s+", " ", text or "").strip(" ,.;")
    zips = _ZIP_RE.findall(line)
    out = {"street": "", "unit": "", "zip": zips[-1] if zips else "", "how": "blank"}
    if not line:
        return out
    for how, parser in (("pattern", parse_address), ("no_suffix", parse_address_nosuffix)):
        parsed = parser(line)
        if parsed and parsed.get("street"):
            out.update(street=parsed["street"], unit=parsed.get("unit") or "", how=how)
            return out
    if "," in line:
        out.update(street=line.split(",", 1)[0].strip(), how="comma")
        return out
    whole = _ZIP_RE.sub("", _STATE_TAIL_RE.sub("", line)).strip(" ,.;")
    out.update(street=whole, how="whole")
    return out


def _key(street: str, unit: str, zip_code: str) -> dict:
    street, unit = (street or "").strip(), (unit or "").strip()
    std = standardize_address(street, unit)
    # The rules engine's street holds its unit; the AI engine's does not, and
    # it sometimes puts part of the street in the unit ("1234 MAIN ST" and
    # "N APT 5"). Both are judged on the whole line they read: the unit is
    # joined back on, and the line's own unit word marks where the street
    # ends. A unit with no such word ("B") keeps the engine's split.
    if unit and street and not street.upper().endswith(unit.upper()):
        joined = standardize_address(f"{street} {unit}")
        if joined["unit_std"]:
            std = joined
    return {"house": std["house_number"], "street": std["street_std"],
            "unit": std["unit_std"], "zip": (zip_code or "").strip()[:5]}


def truth_key(plain_address: str) -> dict:
    """The typed address as a comparison key, plus the line itself for the
    paper's measure and `how` the line was split."""
    parts = split_address(plain_address)
    return {**_key(parts["street"], parts["unit"], parts["zip"]),
            "how": parts["how"], "plain": plain_address or ""}


def reading_key(reading: dict | None) -> dict:
    """An engine's reading as a comparison key. A reading holds `street`,
    `unit`, `zip`, and `raw` (the address as the engine returned it)."""
    r = reading or {}
    return {**_key(r.get("street") or "", r.get("unit") or "", r.get("zip") or ""),
            "raw": r.get("raw") or ""}


def _unit_id(unit: str) -> str:
    """A standardized unit without its designator words, so a typed "#5"
    and a printed "APT 5" are the same unit; a building kept on one side
    only still differs."""
    designators = set(UNITS.values()) | {"#"}
    return " ".join(t for t in unit.split() if t not in designators)


def compare_address(truth: dict, reading: dict | None) -> dict:
    """One reading against one typed address.

    `extracted`: the engine returned a street. `ratio` and `paper`: the
    2024 paper's measure, on the whole address line. `house`, `street`: the
    strict measure, the house number and the standardized street (name,
    type, and direction; the unit apart). `unit`: the units agree once their
    designator words are set aside, both empty included. `zip`: None when either side has none."""
    got = reading_key(reading)
    extracted = bool(got["street"])
    raw = got["raw"] or (reading or {}).get("street") or ""
    r = ratio(norm(raw), norm(truth["plain"])) if raw else 0.0
    both_zip = bool(truth["zip"]) and bool(got["zip"])
    return {
        "extracted": extracted,
        "ratio": round(r, 3),
        "paper": r >= SAME_STREET_THRESHOLD,
        "house": extracted and bool(truth["house"]) and got["house"] == truth["house"],
        "street": extracted and bool(truth["street"]) and got["street"] == truth["street"],
        "unit": _unit_id(got["unit"]) == _unit_id(truth["unit"]),
        "unit_read": bool(got["unit"]),
        "zip": (got["zip"] == truth["zip"]) if both_zip else None,
    }


def score_lane(truths: dict[str, dict], readings: dict[str, dict], cases: list[str]) -> dict:
    """Counts for one lane over `cases`: how many it read an address on,
    the paper's measure, and the strict one, with the strict street count
    split by how each typed line was split. The unit is judged only where
    the typed line has one."""
    out = Counter()
    by_how = {how: [0, 0] for how in SPLIT_KINDS}
    ratios = []
    for case in cases:
        c = compare_address(truths[case], readings.get(case))
        out["n"] += 1
        out["extracted"] += c["extracted"]
        out["paper"] += c["paper"]
        out["house"] += c["house"]
        out["street"] += c["street"]
        if truths[case]["unit"]:
            out["truth_units"] += 1
            out["unit_kept"] += c["unit"]
            out["street_and_unit"] += c["street"] and c["unit"]
        else:
            # typed lines often leave the unit off, so a unit read here is
            # not counted wrong; it is only counted
            out["no_truth_unit"] += 1
            out["unit_added"] += c["unit_read"]
        if c["zip"] is not None:
            out["zip_both"] += 1
            out["zip"] += c["zip"]
        if c["extracted"]:
            ratios.append(c["ratio"])
        how = truths[case]["how"]
        by_how[how][0] += 1
        by_how[how][1] += c["street"]
    out = dict(out)
    out["mean_ratio_extracted"] = round(sum(ratios) / len(ratios), 3) if ratios else 0.0
    out["street_by_split"] = {how: tuple(v) for how, v in by_how.items() if v[0]}
    return out


def paired(truths: dict[str, dict], first: dict[str, dict], second: dict[str, dict],
           cases: list[str], field: str = "street") -> dict:
    """Two lanes on the same cases: both right, only the first, only the
    second, neither, and the exact paired test."""
    counts = Counter()
    for case in cases:
        a = bool(compare_address(truths[case], first.get(case))[field])
        b = bool(compare_address(truths[case], second.get(case))[field])
        counts["both" if a and b else "first_only" if a else "second_only" if b else "neither"] += 1
    n = sum(counts.values())
    return {"n": n, "both": counts["both"], "first_only": counts["first_only"],
            "second_only": counts["second_only"], "neither": counts["neither"],
            "p": mcnemar_exact(counts["first_only"], counts["second_only"]),
            "difference": (counts["second_only"] - counts["first_only"]) / n if n else 0.0}


def _same_street(a: dict | None, b: dict | None) -> bool:
    ka, kb = reading_key(a), reading_key(b)
    return bool(ka["street"]) and ka["street"] == kb["street"]


def tiers(truths: dict[str, dict], lanes: dict[str, dict[str, dict]], cases: list[str],
          listed: dict[str, dict[str, str]] | None = None) -> list[dict]:
    """Accept signals, each with how many cases it covers and how many of
    those have the street right: a lane's street confirmed by the address
    list, two lanes reading the same street, and both together. `listed`
    maps a lane to each case's address-list verdict ('match' and so on)."""
    listed = listed or {}
    names = list(lanes)
    signals = []  # (label, whether it holds for a case, the lane it is judged on)
    for a in names:
        if a in listed:
            signals.append((f"{a} and the address list",
                            lambda c, a=a: listed[a].get(c) == "match", a))
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            def agree(c, a=a, b=b):
                return _same_street(lanes[a].get(c), lanes[b].get(c))

            signals.append((f"{a} = {b}", agree, a))
            if a in listed:
                signals.append((f"{a} = {b} and the address list",
                                lambda c, a=a, agree=agree: agree(c) and listed[a].get(c) == "match", a))
    out = []
    for label, holds, judged in signals:
        covered = [c for c in cases if holds(c)]
        right = sum(bool(compare_address(truths[c], lanes[judged].get(c))["street"]) for c in covered)
        out.append({"signal": label, "n": len(cases), "covered": len(covered), "right": right})
    return out


#: where a street the rules missed was lost, in the order the engine works
LOSS_KINDS = ("not in the text", "in the text, no candidate", "a candidate, not chosen",
              "chosen block, parsed wrong")


def loss_category(truth: dict, in_text: str, candidate_streets: list[tuple[str, str]],
                  chosen_raw: str) -> str:
    """Which stage lost a street the rules got wrong or left blank.

    `in_text` is whether the typed street is in the page text the engine
    read ('exact', 'near', or 'absent'). `candidate_streets` holds each
    address candidate the engine found as (street, unit), in its ranked
    order; the one it chose is not always first, since a candidate that
    matches the attorney's address is passed over. `chosen_raw` is the
    chosen address as read. Called only for a street the rules got wrong,
    so a candidate that matches the typed street was not the one chosen."""
    want = truth["street"]
    keys = [_key(s, u, "")["street"] for s, u in candidate_streets]
    if want and want in keys:
        return "a candidate, not chosen"
    if chosen_raw and want:
        plain_street = norm(split_address(truth["plain"])["street"])
        if plain_street and plain_street in norm(chosen_raw):
            return "chosen block, parsed wrong"
        if ratio(norm(chosen_raw), norm(truth["plain"])) >= SAME_STREET_THRESHOLD:
            return "chosen block, parsed wrong"
    if in_text == "absent":
        return "not in the text"
    return "in the text, no candidate"
