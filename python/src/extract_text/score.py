"""Score the engines against the review page's corrections.

`extract-text score --out DIR` reads `DIR/corrections.jsonl` and scores the
scan as it is now in `DIR`, so a re-scan after a rule change is measured
against the same answers. It prints, for each engine, how often each field
was right, what kind of wrong the rest were, and which flags the wrong rows
carried. With `--shapes` it also prints each wrong value in masked form,
letters as A, digits as 9, punctuation kept, so the pattern of a failure can
be seen without the record.

Nothing printed is a name, an address, a case number, or a file name. The
report is meant to leave the governed data tree: it is what a maintainer
needs to fix a rule, and nothing a record holder would object to.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from .corrections import ATTORNEY_FIELDS, TRUTH_FIELDS, _sha256, load_corrections
from .parties import _party_key, _strip_group_terms
from .pipeline import _unit_key, ai_reading, machine_reading, read_scan
from .similarity import norm

FIELDS = ("plaintiff", "defendants", *TRUTH_FIELDS[1:], "attorneys", *ATTORNEY_FIELDS)
SHAPE_WIDTH = 48


def mask(value) -> str:
    """The shape of a value without its content: letters become A or a,
    digits 9, everything else stays. Long values are cut."""
    if isinstance(value, list):
        value = "; ".join(value)
    shaped = re.sub(r"[A-Z]", "A", re.sub(r"[a-z]", "a", str(value or "")))
    shaped = re.sub(r"[0-9]", "9", shaped)
    return shaped if len(shaped) <= SHAPE_WIDTH else shaped[:SHAPE_WIDTH - 1] + "…"


def _squash(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().casefold()


def _name_keys(names) -> list[str]:
    keys = []
    for n in names or []:
        key = _party_key(_strip_group_terms(str(n))[0])
        if key:
            keys.append(key)
    return sorted(keys)


def _party_wrong(t, m):
    """How one party name is wrong, or None when it is right."""
    if _squash(t) == _squash(m):
        return None
    if not _squash(m):
        return "blank"
    if not _squash(t):
        return "extra"
    return "near" if _party_key(t) == _party_key(m) else "different"


def _firm_among(lines, firm):
    """How a firm is wrong against the lines of a combined attorney box, or
    None when it is one of them."""
    if any(_squash(n) == _squash(firm) for n in lines if _squash(n)):
        return None
    if not _squash(firm):
        return "blank" if any(_squash(n) for n in lines) else None
    if not any(_squash(n) for n in lines):
        return "extra"
    return "near" if _party_key(firm) in {_party_key(n) for n in lines} else "different"


def _names_wrong(td, md):
    """How a list of names is wrong, or None when it is right. Compared as a
    set, so order never counts."""
    if [_squash(n) for n in td] == [_squash(n) for n in md]:
        return None
    tk, mk = _name_keys(td), _name_keys(md)
    if not mk:
        return "blank"
    if not tk:
        return "extra"
    if tk == mk:
        return "near"
    if set(tk) < set(mk):
        return "extra names"
    if set(mk) < set(tk):
        return "missing names"
    return "different"


def compare(truth: dict, reading: dict) -> dict:
    """Each field the reading gets wrong, with the kind of wrong.

    `blank` is a miss, `extra` a value where the page has none, `near` the
    right content with different formatting (case, punctuation, Ave for
    Avenue, a group term, LLC), and `different` anything else. Defendants
    and attorneys are compared as a set of names, so order never counts; a
    superset is `extra names` and a subset `missing names`. The attorney
    block is compared only when the answer has one."""
    found = {
        "plaintiff": _party_wrong(truth.get("plaintiff", ""), reading.get("plaintiff", "")),
        "defendants": _names_wrong(truth.get("defendants") or [],
                                   reading.get("defendants") or []),
    }
    if "attorneys" in truth and "attorney_firm" not in truth:
        # one box for attorneys and firm (from round 2): a reading's names and
        # firm together against the box's lines, and its firm alone against
        # any line, since the AI engine reads only the firm
        firm = reading.get("attorney_firm", "")
        if "attorneys" in reading:
            found["attorneys"] = _names_wrong(
                truth["attorneys"] or [], [*(reading["attorneys"] or []), *([firm] if firm else [])])
        if "attorney_firm" in reading:
            found["attorney_firm"] = _firm_among(truth["attorneys"] or [], firm)
    elif "attorneys" in truth:
        if "attorneys" in reading:
            found["attorneys"] = _names_wrong(truth["attorneys"] or [],
                                              reading["attorneys"] or [])
        found["attorney_firm"] = _party_wrong(truth.get("attorney_firm", ""),
                                              reading.get("attorney_firm", ""))
    wrong = {k: v for k, v in found.items() if v}

    same = {
        "street": lambda a, b: norm(a) == norm(b),
        "unit": lambda a, b: _unit_key(a) == _unit_key(b),
        "city": lambda a, b: _squash(a) == _squash(b),
        "state": lambda a, b: _squash(a) == _squash(b),
        "zip": lambda a, b: str(a or "")[:5] == str(b or "")[:5],
    }
    if "attorneys" in truth:
        # norm is the validation's metric and knows Ste but not Suite, which
        # office addresses spell out often
        suite = lambda a: norm(re.sub(r"\bsuite\b", "ste", a, flags=re.I))
        same["attorney_address"] = lambda a, b: suite(a) == suite(b)
    for field, alike in same.items():
        t, m = str(truth.get(field) or ""), str(reading.get(field) or "")
        if _squash(t) == _squash(m):
            continue
        if not m.strip():
            wrong[field] = "blank"
        elif not t.strip():
            wrong[field] = "extra"
        elif alike(t, m):
            wrong[field] = "near"
        else:
            wrong[field] = "different"
    return wrong


def score(out_dir) -> dict:
    """Per-engine, per-field tallies: the latest correction per row, scored
    against the scan in `out_dir` as it is now."""
    out = Path(out_dir)
    latest = load_corrections(out)
    rows, details = read_scan(out)
    tallies = {
        "n": len(latest),
        "unreadable": sum(1 for c in latest.values() if c["verdict"] == "unreadable"),
        "by_sample": Counter(c["sampled_as"] for c in latest.values()),
        "used_ai_fill": sum(1 for c in latest.values() if c.get("used_ai_fill")),
        "by_reviewer": Counter(c.get("reviewer", "") for c in latest.values()),
        "skipped": 0,
        "engines": {},
        "flags_on_wrong": Counter(),
        "shapes": defaultdict(list),
    }
    scored = []  # (correction, {"deterministic": wrong, "ai": wrong|None}, row)
    for row_no, c in sorted(latest.items()):
        if c["verdict"] == "unreadable":
            continue
        if not 1 <= row_no <= len(rows):
            tallies["skipped"] += 1
            continue
        row, detail = rows[row_no - 1], details[row_no - 1]
        src = Path(detail.get("file", ""))
        if c.get("sha256") and _sha256(src) != c["sha256"]:
            tallies["skipped"] += 1
            continue
        machine = machine_reading(row)
        ai = ai_reading(detail) or c.get("ai")
        readings = {"deterministic": (machine, compare(c["truth"], machine))}
        if ai:
            readings["ai"] = (ai, compare(c["truth"], ai))
        scored.append((c, readings, row))

    for engine in ("deterministic", "ai"):
        seen = [(c, r[engine], row) for c, r, row in scored if engine in r]
        if not seen:
            continue
        per_field = {}
        for field in FIELDS:
            f = {"n": 0, "right": 0, "near": 0, "right_random": 0,
                 "n_random": 0, "kinds": Counter()}
            for c, (reading, wrong), row in seen:
                # answers saved before the attorney boxes existed are not
                # scored on the attorney block
                if field.startswith("attorney") and "attorneys" not in c["truth"]:
                    continue
                # nor is an engine scored on a field it does not read
                if field == "attorneys" and "attorneys" not in reading:
                    continue
                f["n"] += 1
                random_row = c["sampled_as"] == "random"
                f["n_random"] += random_row
                kind = wrong.get(field)
                if kind is None:
                    f["right"] += 1
                    f["right_random"] += random_row
                    continue
                f["kinds"][kind] += 1
                f["near"] += kind == "near"
                raw = ""
                if engine == "deterministic" and field in ("street", "unit", "city", "zip"):
                    raw = mask(row.get("defendant_address_raw", ""))
                # a combined attorney box has no firm of its own; its lines
                # are what a firm was checked against
                said = c["truth"].get(field, c["truth"].get("attorneys") if field == "attorney_firm" else None)
                tallies["shapes"][(engine, field)].append(
                    (c["row"], kind, mask(reading.get(field)), mask(said), raw))
            if f["n"]:
                per_field[field] = f
        tallies["engines"][engine] = per_field
        if engine == "deterministic":
            for c, (reading, wrong), row in seen:
                if {k for k, v in wrong.items() if v != "near"}:
                    for flag in filter(None, (row.get("flags") or "").split(";")):
                        tallies["flags_on_wrong"][flag] += 1
    return tallies


def _pct(right, n) -> str:
    return f"{100 * right / n:5.1f}%" if n else "    –"


def report(out_dir, shapes=False) -> str:
    """The printed report."""
    t = score(out_dir)
    lines = [f"Corrections in {Path(out_dir).name}: {t['n']} documents reviewed, "
             f"{t['unreadable']} unreadable, "
             + ", ".join(f"{n} {how}" for how, n in sorted(t["by_sample"].items()))
             + (f", {t['used_ai_fill']} filled from the AI engine" if t["used_ai_fill"] else ""),
             "Scored against the scan as it is now in that folder.",
             "Graded by " + ", ".join(f"{who or 'unknown'} ({n})"
                                      for who, n in t["by_reviewer"].most_common()) + "."]
    if t["skipped"]:
        lines.append(f"{t['skipped']} corrections skipped: the document at that row has "
                     "changed since the correction was saved (a different scan?).")
    if not t["engines"]:
        lines.append("No readable corrections yet.")
        return "\n".join(lines)
    for engine, per_field in t["engines"].items():
        lines += ["", f"{engine} engine, share of fields right, then right or near "
                      "(random rows alone in brackets)"]
        for field, f in per_field.items():
            kinds = ", ".join(f"{n} {k}" for k, n in f["kinds"].most_common())
            lines.append(f"  {field:<17}{_pct(f['right'], f['n'])} "
                         f"{_pct(f['right'] + f['near'], f['n'])} of {f['n']:>4}"
                         f"  [{_pct(f['right_random'], f['n_random']).strip()} of {f['n_random']}]"
                         + (f"   wrong: {kinds}" if kinds else ""))
    if t["flags_on_wrong"]:
        lines += ["", "flags carried by rows the deterministic engine got wrong"]
        lines += [f"  {n:>4}  {flag}" for flag, n in t["flags_on_wrong"].most_common()]
    if shapes and t["shapes"]:
        lines += ["", "shapes of wrong values (letters A/a, digits 9): engine value, then the "
                      "right answer, then the block the address was read from"]
        for (engine, field), items in t["shapes"].items():
            lines.append(f"  {engine} · {field}")
            for row, kind, got, want, raw in items:
                lines.append(f"    #{row:<4} {kind:<14} {got or '(blank)'}")
                lines.append(f"    {'':<20}{want or '(blank)'}")
                if raw:
                    lines.append(f"    {'':<20}from: {raw}")
    return "\n".join(lines)


def _street_in_text(street: str, text: str):
    """Whether a street appears in a document's text: ("exact", line),
    ("near", line) for the closest line at or above the same-street
    threshold, or ("absent", None)."""
    from .similarity import SAME_STREET_THRESHOLD, ratio

    want = norm(street)
    if not want:
        return "absent", None
    best, best_line = 0.0, None
    for line in (text or "").splitlines():
        have = norm(line)
        if not have:
            continue
        if want in have:
            return "exact", line
        # the street against every window of the line the same length in words
        words = have.split()
        width = max(1, len(want.split()))
        for i in range(0, max(1, len(words) - width + 1)):
            r = ratio(want, " ".join(words[i:i + width]))
            if r > best:
                best, best_line = r, line
    if best >= SAME_STREET_THRESHOLD:
        return "near", best_line
    return "absent", None


def where_report(out_dir) -> str:
    """For each document whose deterministic street is wrong, whether the
    graders' street is in the document's text at all: an OCR failure
    (absent), a rule failure (exact or near, the text has it), with the
    matching line masked. Reads each document again, so it is slow on
    scans. Prints no record value."""
    from .documents import load_document

    out = Path(out_dir)
    latest = load_corrections(out)
    rows, details = read_scan(out)
    found = Counter()
    lines = []
    for row_no, c in sorted(latest.items()):
        if c["verdict"] == "unreadable" or not 1 <= row_no <= len(rows):
            continue
        truth_street = str(c["truth"].get("street") or "")
        if not truth_street:
            continue
        reading = machine_reading(rows[row_no - 1])
        kind = compare(c["truth"], reading).get("street")
        if kind in (None, "near"):
            continue
        src = Path(details[row_no - 1].get("file", ""))
        if c.get("sha256") and _sha256(src) != c["sha256"]:
            found["skipped: document changed"] += 1
            continue
        try:
            text = load_document(src).text
        except Exception as exc:  # one unreadable file must not stop the report
            found[f"error: {type(exc).__name__}"] += 1
            continue
        where, line = _street_in_text(truth_street, text)
        found[where] += 1
        flags = (rows[row_no - 1].get("flags") or "").replace(";", " ")
        lines.append(f"  #{row_no:<4} {kind:<10} {where:<7} {mask(line) if line else ''}"
                     + (f"   flags: {flags}" if flags else ""))
    head = [f"Street wrong in the deterministic engine on {sum(found.values())} documents: "
            + ", ".join(f"{n} {k}" for k, n in found.most_common()),
            "  exact or near: the text holds the street, so a rule missed it; "
            "absent: the OCR never produced it",
            "  #row  kind       where   matching line, masked"]
    return "\n".join(head + lines)
