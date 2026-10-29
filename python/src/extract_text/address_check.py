"""Check extracted addresses against a list of real addresses.

A county's address points (or any list of the addresses that exist in a
place) settle a question the document cannot: does this address exist? Each
extraction's standardized street (standardize.py) is looked up among the
listed addresses with the same house number, in the same ZIP code or city.

- `match`: the house number and street are listed in that ZIP code (or, with
  no ZIP code read, that city).
- `near`: not listed as read, but the same house number is listed on a
  street spelled almost the same (similarity at least `min_similarity`, and
  no other listed street as few edits away), or
  on the same street in the same city under a different ZIP code. The listed
  address is offered in `address_suggested`. It is a suggestion for a
  person, never written over what the engine read.
- `no_match`: neither. The extraction may be wrong, or the address may no
  longer exist (lists are current; filings are not), or the list may miss it.
- blank: nothing to check (no house number or street was read).

Deterministic and local: the list is a file on this computer and nothing
leaves it. Units are not checked, since unit coverage in address lists is
patchy.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .similarity import lev, ratio
from .standardize import standardize_address

# Column names in published address lists, by preset. Each source's own
# README records where and when it was retrieved.
PRESETS = {
    "king_county_wa": {"street": "ADDR_FULL", "zip": "ZIP5", "city": "POSTALCTYNAME"},
}

MIN_SIMILARITY = 0.8


def _split(street_std: str, house: str) -> str:
    """The standardized street without its house number."""
    return street_std[len(house):].strip() if house and street_std.startswith(house) else street_std


class AddressList:
    """Listed addresses indexed by house number and ZIP code, and by house
    number and city."""

    def __init__(self):
        self.by_zip = defaultdict(set)     # (house, zip5) -> {street}
        self.by_city = defaultdict(set)    # (house, CITY) -> {(street, zip5)}
        self.n = 0

    def add(self, street: str, zip_code: str = "", city: str = "") -> None:
        std = standardize_address(street)
        house = std["house_number"]
        body = _split(std["street_std"], house)
        if not house or not body:
            return
        z = (zip_code or "").strip()[:5]
        c = (city or "").strip().upper()
        if z:
            self.by_zip[(house, z)].add(body)
        if c:
            self.by_city[(house, c)].add((body, z))
        self.n += 1

    @classmethod
    def from_csv(cls, path, street: str, zip: str | None = None, city: str | None = None,
                 house_number: str | None = None) -> AddressList:
        """Read a CSV of addresses. `street` names the column holding the
        house number and street (or, with `house_number`, the street alone);
        `zip` and `city` name the ZIP code and city columns."""
        out = cls()
        with open(Path(path).expanduser(), newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = [c for c in (street, zip, city, house_number) if c and c not in reader.fieldnames]
            if missing:
                raise ValueError(f"no column named {missing[0]!r} in {Path(path).name}")
            for r in reader:
                s = r[street]
                if house_number:
                    s = f"{r[house_number]} {s}"
                out.add(s, r[zip] if zip else "", r[city] if city else "")
        return out

    @classmethod
    def from_preset(cls, path, preset: str) -> AddressList:
        if preset not in PRESETS:
            raise ValueError(f"no preset {preset!r}; known: {', '.join(PRESETS)}")
        return cls.from_csv(path, **PRESETS[preset])

    def check(self, street, unit=None, city=None, state=None, zip_code=None,
              min_similarity: float = MIN_SIMILARITY) -> dict:
        blank = {"address_check": "", "address_suggested": "", "address_check_similarity": ""}
        std = standardize_address(street, unit, city, state, zip_code)
        house = std["house_number"]
        body = _split(std["street_std"], house)
        if not house or not body:
            return blank
        z = (zip_code or "").strip()[:5]
        c = (city or "").strip().upper()
        in_zip = self.by_zip.get((house, z), set()) if z else set()
        in_city = self.by_city.get((house, c), set()) if c else set()

        if body in in_zip or (not z and any(b == body for b, _ in in_city)):
            return {**blank, "address_check": "match", "address_check_similarity": 1.0}

        # the same street in the same city under another ZIP code
        other_zip = sorted(zc for b, zc in in_city if b == body and zc != z)
        if len(other_zip) == 1:
            return self._near(house, body, std, city, state, other_zip[0], 1.0)

        # a street spelled almost the same, at the same house number; the
        # fewest edits wins, and two streets equally few edits away are a tie,
        # so neither is offered
        candidates = {(b, z) for b in in_zip} | (in_city if not in_zip else set())
        scored = sorted((lev(body, b), -ratio(body, b), b, zc) for b, zc in candidates)
        if scored:
            edits, neg_sim, b, zc = scored[0]
            tie = len(scored) > 1 and scored[1][0] == edits
            if -neg_sim >= min_similarity and not tie:
                return self._near(house, b, std, city, state, zc or z, -neg_sim)
        best = round(-scored[0][1], 3) if scored else ""
        return {**blank, "address_check": "no_match", "address_check_similarity": best}

    @staticmethod
    def _near(house, body, std, city, state, zip5, sim) -> dict:
        line = " ".join(p for p in (house, body, std["unit_std"]) if p)
        place = " ".join(p for p in ((state or "").upper(), zip5) if p)
        tail = ", ".join(p for p in ((city or "").upper(), place) if p)
        return {"address_check": "near", "address_suggested": f"{line}, {tail}" if tail else line,
                "address_check_similarity": round(sim, 3)}


def check_scan(out_dir, addresses: AddressList, min_similarity: float = MIN_SIMILARITY,
               write: bool = True) -> list[dict]:
    """Check every row of a finished scan. Returns one dict per row (`doc`,
    the row's number on the review page, then the three check columns) and,
    with `write`, saves them to address_check.csv in the scan folder, which
    holds addresses and so stays on governed storage."""
    from .pipeline import read_scan

    rows, _ = read_scan(Path(out_dir))
    out = []
    for i, r in enumerate(rows, 1):
        res = addresses.check(r.get("defendant_street"), r.get("defendant_unit"),
                              r.get("defendant_city"), r.get("defendant_state"),
                              r.get("defendant_zip"), min_similarity=min_similarity)
        out.append({"doc": i, **res})
    if write:
        with open(Path(out_dir) / "address_check.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0]) if out else
                               ["doc", "address_check", "address_suggested", "address_check_similarity"])
            w.writeheader()
            w.writerows(out)
    return out


def summary(results: list[dict]) -> str:
    """Counts only, safe to share."""
    n = Counter(r["address_check"] or "not checked" for r in results)
    parts = [f"{n[k]} {k}" for k in ("match", "near", "no_match", "not checked") if n[k]]
    return f"Address check, {len(results)} documents: " + ", ".join(parts)


def evaluation(out_dir, results: list[dict]) -> str | None:
    """How the check did against the scan's saved corrections, counts only:
    for documents whose street the engine read right and wrong (house number
    and street, compared in standard form), how many the check called match,
    near, and no_match, and how often a near's suggestion was the corrected
    street. None when the folder has no corrections."""
    from .corrections import load_corrections

    latest = load_corrections(out_dir)
    if not latest:
        return None
    from .pipeline import read_scan

    rows, _ = read_scan(Path(out_dir))
    table, suggested_right, n = Counter(), Counter(), 0
    for row_no, c in latest.items():
        if c.get("verdict") == "unreadable" or not 1 <= row_no <= len(rows):
            continue
        t = c.get("truth") or {}
        truth = standardize_address(t.get("street"))["street_std"]
        r = rows[row_no - 1]
        read = standardize_address(r.get("defendant_street"), r.get("defendant_unit"))["street_std"]
        engine = ("no address on the document" if not truth
                  else "engine right" if read == truth else "engine wrong")
        status = results[row_no - 1]["address_check"] or "not checked"
        table[(engine, status)] += 1
        n += 1
        if status == "near" and truth:
            suggestion = results[row_no - 1]["address_suggested"]
            suggested_right[suggestion == truth or suggestion.startswith(truth + " ")
                            or suggestion.startswith(truth + ",")] += 1
    cols = ("engine right", "engine wrong", "no address on the document")
    lines = [f"Against {n} corrected documents (street as corrected, in standard form):",
             f"  {'':<12}" + "".join(f"{c:>28}" for c in cols)]
    for status in ("match", "near", "no_match", "not checked"):
        lines.append(f"  {status:<12}" + "".join(f"{table[(c, status)]:>28}" for c in cols))
    if sum(suggested_right.values()):
        lines.append(f"  a near's suggestion was the corrected street in {suggested_right[True]} "
                     f"of {sum(suggested_right.values())}")
    return "\n".join(lines)
