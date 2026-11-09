"""Measure a rule change: re-read every corrected document with the
deterministic engine as it is now, and count, field by field, what the
change fixed and what it broke.

    python -I scripts/rules_eval.py --out SCAN_DIR [--out SCAN_DIR ...]
    python -I scripts/rules_eval.py --out SCAN_DIR --save-rows RUN.tsv
    python -I scripts/rules_eval.py --out SCAN_DIR --against RUN.tsv
    python -I scripts/rules_eval.py --out SCAN_DIR --rows 1-60,75 --shapes

The baseline is the engine's reading saved in the scan (the engine as it
was the day the scan ran), or, with `--against`, the per-document results
of an earlier run of this script saved with `--save-rows`, so two versions
of the rules can be compared on the same answers without a re-scan.

Each document is read again from its file. The loaded page text is kept in
`SCAN_DIR/_rules_eval_cache/` (governed storage, beside the scan's own text)
so a second run skips the OCR. Interior pages the engine's fallback reads
are not cached and are read again each run.

What is printed is counts, row numbers, kinds of error, and with `--shapes`
each wrong value in masked form (letters A/a, digits 9), the way
`extract-text score --shapes` prints them. Nothing printed or saved with
`--save-rows` is a name, an address, a case number, or a file name.

`--rows` limits the run to some rows of one scan, for keeping a held-out
set out of rule work: develop with `--shapes` on the development rows only
and look at the held-out rows' counts, never their shapes.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import pickle
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from extract_text.corrections import _sha256, load_corrections
from extract_text.deterministic import extract_from_document
from extract_text.documents import load_document
from extract_text.pipeline import flatten_extraction, machine_reading, read_scan
from extract_text.score import FIELDS, compare, mask

CACHE_NAME = "_rules_eval_cache"


def parse_rows(spec: str) -> set[int]:
    """'1-5,9' as {1, 2, 3, 4, 5, 9}."""
    rows = set()
    for part in filter(None, (p.strip() for p in spec.split(","))):
        lo, _, hi = part.partition("-")
        rows.update(range(int(lo), int(hi or lo) + 1))
    return rows


def cached_document(src: Path, cache: Path):
    """The loaded document, from the cache when the file is unchanged."""
    key = hashlib.sha256(str(src.resolve()).encode()).hexdigest()[:24]
    sha = _sha256(src)
    hit = cache / f"{key}.pkl"
    if hit.exists():
        with open(hit, "rb") as f:
            saved_sha, doc = pickle.load(f)
        if saved_sha == sha:
            return doc
    doc = load_document(src)
    cache.mkdir(parents=True, exist_ok=True)
    with open(hit, "wb") as f:
        pickle.dump((sha, copy.deepcopy(doc)), f)
    return doc


def scored_fields(truth: dict, reading: dict) -> list[str]:
    """The fields a correction scores, as `extract-text score` decides."""
    fields = []
    for field in FIELDS:
        if field.startswith("attorney") and "attorneys" not in truth:
            continue
        if field == "attorneys" and "attorneys" not in reading:
            continue
        fields.append(field)
    return fields


def evaluate(out_dir: Path, rows_wanted: set[int] | None):
    """Per document and field: the kind of wrong at the baseline (the scan)
    and now (None when right), with the masked values of what is wrong now."""
    latest = load_corrections(out_dir)
    rows, details = read_scan(out_dir)
    cache = out_dir / CACHE_NAME
    results, skipped = [], Counter()
    for row_no, c in sorted(latest.items()):
        if rows_wanted is not None and row_no not in rows_wanted:
            continue
        if c["verdict"] == "unreadable":
            skipped["unreadable"] += 1
            continue
        if not 1 <= row_no <= len(rows):
            skipped["row not in scan"] += 1
            continue
        src = Path(details[row_no - 1].get("file", ""))
        if c.get("sha256") and _sha256(src) != c["sha256"]:
            skipped["document changed since graded"] += 1
            continue
        try:
            doc = cached_document(src, cache)
            now = machine_reading(flatten_extraction(extract_from_document(doc)))
        except Exception as exc:  # one unreadable file must not stop the run
            skipped[f"error: {type(exc).__name__}"] += 1
            continue
        then = machine_reading(rows[row_no - 1])
        wrong_then, wrong_now = compare(c["truth"], then), compare(c["truth"], now)
        for field in scored_fields(c["truth"], now):
            said = c["truth"].get(field, c["truth"].get("attorneys")
                                  if field == "attorney_firm" else None)
            results.append({
                "scan": out_dir.name, "row": row_no, "field": field,
                "then": wrong_then.get(field), "now": wrong_now.get(field),
                "got": mask(now.get(field)), "want": mask(said),
            })
    return results, skipped


def save_rows(results, path: Path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["scan", "row", "field", "kind"])
        for r in results:
            w.writerow([r["scan"], r["row"], r["field"], r["now"] or "right"])


def load_against(path: Path) -> dict:
    with open(path, newline="") as f:
        return {(r["scan"], int(r["row"]), r["field"]): (None if r["kind"] == "right" else r["kind"])
                for r in csv.DictReader(f, delimiter="\t")}


def report(results, skipped, baseline: str, shapes: bool) -> str:
    per = defaultdict(lambda: {"n": 0, "then": 0, "now": 0, "fixed": [], "broke": []})
    for r in results:
        f = per[r["field"]]
        f["n"] += 1
        f["then"] += r["then"] is None
        f["now"] += r["now"] is None
        if r["then"] is not None and r["now"] is None:
            f["fixed"].append(r["row"])
        if r["then"] is None and r["now"] is not None:
            f["broke"].append(r["row"])
    docs = len({(r["scan"], r["row"]) for r in results})
    lines = [f"{docs} corrected documents re-read with the engine as it is now; "
             f"baseline: {baseline}."]
    if skipped:
        lines.append("Not scored: " + ", ".join(f"{n} {k}" for k, n in skipped.most_common()))
    lines += ["", f"  {'field':<17}{'n':>5}{'before':>8}{'now':>8}{'fixed':>7}{'broke':>7}"]
    for field in FIELDS:
        if field not in per:
            continue
        f = per[field]
        lines.append(f"  {field:<17}{f['n']:>5}{f['then']:>8}{f['now']:>8}"
                     f"{len(f['fixed']):>7}{len(f['broke']):>7}")
    changed = [(field, per[field]) for field in FIELDS
               if field in per and (per[field]["fixed"] or per[field]["broke"])]
    if changed:
        lines += ["", "rows that changed (row numbers in each scan)"]
        for field, f in changed:
            if f["fixed"]:
                lines.append(f"  {field:<17}fixed  " + " ".join(f"#{n}" for n in f["fixed"]))
            if f["broke"]:
                lines.append(f"  {field:<17}broke  " + " ".join(f"#{n}" for n in f["broke"]))
    if shapes:
        lines += ["", "shapes of what is wrong now (letters A/a, digits 9): "
                      "engine value, then the answer"]
        for field in FIELDS:
            items = [r for r in results if r["field"] == field and r["now"] is not None]
            if not items:
                continue
            lines.append(f"  {field}")
            for r in items:
                lines.append(f"    #{r['row']:<4} {r['now']:<14} {r['got'] or '(blank)'}")
                lines.append(f"    {'':<20}{r['want'] or '(blank)'}")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", action="append", required=True, type=Path,
                   help="a scan folder with corrections.jsonl; repeat for several")
    p.add_argument("--rows", default=None,
                   help="only these rows, e.g. 1-60,75 (one --out only)")
    p.add_argument("--against", type=Path, default=None,
                   help="a --save-rows file from an earlier run to use as the baseline")
    p.add_argument("--save-rows", type=Path, default=None,
                   help="write each document's result per field (kinds only) to this TSV")
    p.add_argument("--shapes", action="store_true",
                   help="also print what is wrong now in masked form")
    p.add_argument("--save", type=Path, default=None, help="also write the report here")
    args = p.parse_args(argv)
    if args.rows and len(args.out) > 1:
        p.error("--rows needs a single --out")

    started = time.time()
    wanted = parse_rows(args.rows) if args.rows else None
    results, skipped = [], Counter()
    for out in args.out:
        r, s = evaluate(out, wanted)
        results += r
        skipped += s

    baseline = "the engine's reading saved in the scan"
    if args.against:
        before = load_against(args.against)
        kept = []
        for r in results:
            key = (r["scan"], r["row"], r["field"])
            if key in before:
                r["then"] = before[key]
                kept.append(r)
        results, baseline = kept, f"the run saved in {args.against.name}"

    text = report(results, skipped, baseline, args.shapes)
    print(text)
    # wall time, for planning re-runs
    print(f"{time.time() - started:.0f} s", file=sys.stderr)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(text + "\n")
    if args.save_rows:
        save_rows(results, args.save_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
