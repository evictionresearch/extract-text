#!/usr/bin/env python3
"""Sweep this repository for anything that looks like a real court record.

Run before sharing the repository, before tagging a release, and any time a
test fixture changes:

    python3 python/scripts/pii_sweep.py            # from the repo root
    python3 python/scripts/pii_sweep.py --repo PATH

The rule it enforces is CONTRIBUTING.md's one rule with no exceptions: no
real party names, addresses, or case numbers, not in tests, not in fixtures,
not in a docstring, not in git history. The sweep looks for the *shapes* of
those values:

- Washington superior court case numbers (##-2-#####-#)
- street addresses (house number + street name + suffix)
- ZIP-bearing "City, WA 98###" lines

and prints a numbered triage list. A hit is not automatically a violation;
the documented synthetic values are expected and whitelisted, and pattern
text inside the extraction rules themselves is skipped. Everything else is
for a person to judge.

Where it looks, and why each location is labeled separately:

- **tracked** files (what a clone actually contains) — highest severity
- **history**: every blob reachable from any ref (`git rev-list --all`) —
  a clean worktree with a dirty history is the failure mode that actually
  bites, because hosting platforms serve old commits
- **untracked** files on disk, including gitignored ones — not published,
  but one `git add -f` away from it

Exit status is 0 when only whitelisted values were found, 2 otherwise, so
this can gate CI.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# The synthetic values this repository's fixtures and documentation use, and
# nothing else. Extend this list only for values invented for fixtures; see
# CONTRIBUTING.md. Matching ignores punctuation and case.
SYNTHETIC_WHITELIST = [
    "25-2-00001-0",                # the synthetic WA case number
    "RG-24-108833",                # the synthetic California-style case number
    "CV-2024-0912",                # grounding-test case number
    "1234 EXAMPLE AVE S",          # synthetic defendant street
    "1234 EXAMPLE AVENUE SOUTH SEATTLE WA 98100",  # same, comparison normal form
    "100 MAIN ST STE 200",         # synthetic law firm street
    "SEATTLE, WA 98100",           # synthetic defendant city line
    "SEATTLE, WA 98101",           # synthetic law firm city line
    "SEATTLE, WA 98111",           # regression-test probe city line
    "PUYALLUP, WA 98374",          # OCR-repair regression probe city line
    "9876 SAMPLE AVE",             # direction-boundary regression probe
    "1234 Example Ave",             # pattern documentation example (from the docs)
    "1234 Example Avenue",
    "1234 115th St Ct",
    "123 4th Street",              # the Cityscape rail-failure illustration
    "123 4th street",
    "L234 EXAMPLE ST",              # OCR-repair documentation example
    "1234 Example",
    "Sampleton, WA 98100",         # invented city used in the card tests
    "99999 NOWHERE PKWY",          # card test: an address that is on no page
    "1234 MARLOW EVERLY WAY",      # card test: invented street named for a person
    "1243 EXAMPLE AVE",            # demo deck: one digit of the synthetic street
    # Rail-digit regression probes. The leading 1-2 digit number stands in for a
    # pleading line number glued to the house number; the streets are invented.
    "13 39 EXAMPLE VALLEY DRIVE",
    # Improvement-pass regression tests, all invented (Sampleton / Exemplar /
    # Mockford / Quibble are not real places, streets, or firms)
    "1949 S. Exemplar",
    "112 West Mockford",
    "1234 Street #11",
    "1234 Street",
    "3116 Street",              # docstring shape for the clerk-omitted name
    "900 EXAMPLE STREET",
    "EXAMPLE STREET Quibble Pllc",
    "1800 EXAMPLE ST",
    "1234 67th Street Court",
    "1234 150",                 # superscript-ordinal probe "1234 150(TM) ST"
    "1234 115th St Ct",
    "742 EVERGREEN TERRACE",    # fictional address from The Simpsons
    "EVERGREEN TERRACE SPRINGFIELD",
    "25 2 00001 0",             # the synthetic case number, spaced form
    "18 1234 SAMPLE AVE",
    "13 39th EXAMPLE AVE",
    "29 ST. SAMPLE AVENUE",
    "5 500 PINE ST",
    # The multi-document corpus vocabulary (scripts/make_corpus.py). Street
    # names come from a reserved word list (SAMPLE, SPECIMEN, PLACEHOLDER,
    # EXEMPLAR, NOTIONAL); none is a Washington street. The case numbers
    # continue the synthetic 25-2-0000N-0 series the fixtures already use.
    # The corpus draws only from these fixed lists, never randomizing new
    # strings, so this block is the complete set it can produce.
    "5678 SAMPLE AVENUE",
    "9012 SPECIMEN DRIVE",
    "3456 PLACEHOLDER LANE",
    "7890 EXEMPLAR COURT",
    "2468 NOTIONAL TERRACE",
    "250 SPECIMEN BOULEVARD",
    "25-2-00002-0",
    "25-2-00003-0",
    "25-2-00004-0",
    "25-2-00005-0",
    "25-2-00006-0",
    "1357 SPECIMEN ROAD",
    "8642 EXAMPLE PARKWAY",
    "4680 SAMPLE CIRCLE",
    "9753 EXEMPLAR LOOP",
    "1470 NOTIONAL CROSSING",
    "3690 PLACEHOLDER HIGHWAY",
    "25-2-00007-0",
    "25-2-00008-0",
    "25-2-00009-0",
    "25-2-00010-0",
    "25-2-00011-0",
    "25-2-00012-0",
]

# Skipped paths: this script, the two rule files whose job is to hold the
# patterns and their documentation, binaries, and third-party code that is
# never shipped (installed environments).
PATH_SKIP_RE = re.compile(
    r"(pii_sweep\.py$"
    r"|src/extract_text/deterministic/(patterns|summons)\.py"
    r"|\.pyc$|\.png$|\.git/"
    r"|(^|/)\.?venv/|site-packages/|node_modules/|(^|/)renv/)"
)

# Street-shaped matches whose "street name" opens with ordinary prose are
# pattern noise ("2024 in the District Court"), not addresses.
_PROSE_LEAD_RE = re.compile(
    r"^\d+\s+(in|or|of|the|a|an|and|at|on|to|for|is|are|per|means|with)\b",
    re.IGNORECASE,
)

WA_CASE_RE = re.compile(r"\b\d{2}[- ]2[- ]\d{5}[- ]\d\b")
STREET_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Za-z0-9'.\-]+\s+){0,4}"
    r"(?:AVE(?:NUE)?|STREET|ROAD|DRIVE|LANE|BLVD|BOULEVARD|COURT|CIRCLE|"
    r"PLACE|PKWY|PARKWAY|HIGHWAY|TERRACE|LOOP|TRAIL|CROSSING)\b",
    re.IGNORECASE,
)
CITY_ZIP_RE = re.compile(r"\b[A-Z][A-Za-z .'-]{2,30},?\s+WA\.?\s+9[89]\d{3}\b")

PATTERNS = (("wa_case_number", WA_CASE_RE),
            ("street_address", STREET_RE),
            ("city_wa_zip", CITY_ZIP_RE))


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9# ]", "", s.lower())


def whitelisted(match_text: str) -> bool:
    m = _norm(match_text)
    return any(_norm(w) in m or m in _norm(w) for w in SYNTHETIC_WHITELIST)


def scan_text(text: str, origin: str, severity: str, findings: list) -> None:
    if PATH_SKIP_RE.search(origin):
        return
    for lineno, line in enumerate(text.splitlines(), 1):
        for label, pat in PATTERNS:
            for m in pat.finditer(line):
                if label == "street_address" and _PROSE_LEAD_RE.match(m.group(0)):
                    continue
                findings.append({
                    "severity": severity,
                    "origin": origin,
                    "line": lineno,
                    "kind": label,
                    "match": m.group(0),
                    "ok": whitelisted(m.group(0)),
                })


def looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=None,
                    help="repository root (default: found from this script)")
    ap.add_argument("--show-whitelisted", action="store_true",
                    help="also list hits that matched the synthetic whitelist")
    args = ap.parse_args()

    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parents[2]
    findings: list[dict] = []

    # 1. tracked files, current worktree content
    tracked = set(git(repo, "ls-files").splitlines())
    for rel in sorted(tracked):
        p = repo / rel
        if not p.is_file():
            continue
        data = p.read_bytes()
        if looks_binary(data):
            continue
        scan_text(data.decode("utf-8", "replace"), rel, "tracked", findings)

    # 2. every blob in history on any ref
    seen_blobs = set()
    revs = git(repo, "rev-list", "--all").split()
    for rev in revs:
        for entry in git(repo, "ls-tree", "-r", rev).splitlines():
            meta, _, path = entry.partition("\t")
            parts = meta.split()
            if len(parts) < 3 or parts[1] != "blob":
                continue
            blob = parts[2]
            key = (blob, path)
            if key in seen_blobs:
                continue
            seen_blobs.add(key)
            raw = subprocess.run(
                ["git", "-C", str(repo), "cat-file", "blob", blob],
                capture_output=True).stdout
            if looks_binary(raw):
                continue
            scan_text(raw.decode("utf-8", "replace"),
                      f"{path} @ {rev[:10]}", "history", findings)

    # 3. untracked files on disk, including ignored ones
    others = git(repo, "ls-files", "--others").splitlines()
    ignored = set(git(repo, "ls-files", "--others", "-i",
                      "--exclude-standard").splitlines())
    for rel in sorted(others):
        p = repo / rel
        if not p.is_file() or ".git/" in rel:
            continue
        data = p.read_bytes()
        if looks_binary(data):
            continue
        sev = "untracked-ignored" if rel in ignored else "untracked"
        scan_text(data.decode("utf-8", "replace"), rel, sev, findings)

    # de-duplicate history hits that are identical to a current tracked hit
    current = {(f["origin"], f["line"], f["match"]) for f in findings
               if f["severity"] == "tracked"}
    deduped = []
    for f in findings:
        if f["severity"] == "history":
            path_only = f["origin"].split(" @ ")[0]
            if (path_only, f["line"], f["match"]) in current:
                continue
        deduped.append(f)

    order = {"tracked": 0, "untracked": 1, "history": 2, "untracked-ignored": 3}
    deduped.sort(key=lambda f: (order.get(f["severity"], 9), f["origin"], f["line"]))

    to_show = [f for f in deduped if not f["ok"] or args.show_whitelisted]
    real = [f for f in deduped if not f["ok"]]

    if not to_show:
        print("Clean: no address-shaped or case-number-shaped text found "
              "beyond the documented synthetic values.")
    else:
        print(f"{len(to_show)} hits to triage "
              f"({len(real)} not on the synthetic whitelist):\n")
        for i, f in enumerate(to_show, 1):
            tag = "" if not f["ok"] else "  [whitelisted synthetic]"
            print(f"{i:3d}. [{f['severity']}] {f['origin']}:{f['line']} "
                  f"{f['kind']}: {f['match']!r}{tag}")
        print("\nA hit is a shape, not a verdict. Confirm each non-whitelisted "
              "value is synthetic, then either fix the file or add the value "
              "to SYNTHETIC_WHITELIST with a comment saying what it is.")
    return 2 if real else 0


if __name__ == "__main__":
    sys.exit(main())
