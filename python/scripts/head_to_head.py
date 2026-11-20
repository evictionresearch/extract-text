"""Score the engines against addresses a person typed, on the same documents.

The truth file is a CSV with one typed address per case, made before either
engine existed (columns `case`, `plainAddress`, `extractStatus`, `county`).
The court images sit in ARCHIVE/<county>/<year>/<case>/. Everything this
script writes holds names and addresses, so OUT must be governed storage,
beside the records. What it prints is counts, shares, and masked shapes
(letters A, digits 9), and nothing printed is a name, an address, a case
number, or a file name.

    python scripts/head_to_head.py describe --truth TRUTH.csv
    python scripts/head_to_head.py split    --truth TRUTH.csv --archive ARCHIVE --out OUT
    python scripts/head_to_head.py run      --out OUT --lanes rules,ai,ai-text --n 500
    python scripts/head_to_head.py score    --truth TRUTH.csv --out OUT --n 500 \\
                                            [--addresses LIST.csv --preset king_county_wa]
    python scripts/head_to_head.py loss     --truth TRUTH.csv --out OUT --n 500

`describe` says what the truth file holds and how its address lines split,
before anything is run. `split` writes OUT/manifest.csv once: every case of
the chosen provenance that has a summons on disk, marked 'test' or 'dev' by
a seeded draw. The test part is for scoring only; rule work reads shapes
from the dev part and never from the test part. `run` reads a seeded draw
of one part with each lane and keeps the readings in OUT/readings/; it can
be stopped and started again. `score` prints the tables. `loss` says, for
each street the rules missed, which stage lost it.

Lanes: `rules` is the rules engine as it is in this checkout. `ai` is the
local model through Ollama reading the page image with the default prompt.
`ai-text` is the same model reading the page text through the text backend
(`extract(text, backend="local")`), which holds the answer to a schema and
asks for a quotation for every value. On 2026-11-19, on the made-up
fixtures, `qwen3.5:9b` returned no street and no quotation through it on
any of 14 reads at temperature 0, and the backend sets no temperature, so
the model's own default of 1 applies. It is not part of the 2026-11 run;
the reading rule applies to `ai`. The reading rule for a run is written down before it (MAINTENANCE.md and
the project's issue tracker), not after.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

from extract_text import evaluate as ev

DEFAULT_SEED = 20261119
DEFAULT_MODEL = "qwen3.5:9b"
LANES = ("rules", "ai", "ai-text")
MANIFEST_FIELDS = ("case_number", "county", "year", "truth_status", "doc_variant", "doc_path", "part")


def load_truth(path, status: str) -> dict[str, dict]:
    """The typed addresses of one provenance, by case."""
    with open(Path(path).expanduser(), newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    need = {"case", "plainAddress", "extractStatus", "county"}
    missing = need - set(rows[0].keys() if rows else [])
    if missing:
        raise SystemExit(f"the truth file has no column named {sorted(missing)[0]!r}")
    return {r["case"].strip(): r for r in rows
            if r["extractStatus"] == status and r["plainAddress"].strip() and r["case"].strip()}


def read_manifest(out: Path) -> list[dict]:
    path = out / "manifest.csv"
    if not path.is_file():
        raise SystemExit(f"no manifest in {out.name}; run 'split' first")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def drawn_cases(manifest: list[dict], part: str, n: int, seed: int) -> list[str]:
    return ev.seeded_draw([r["case_number"] for r in manifest if r["part"] == part], n, seed)


def _pct(k: int, n: int) -> str:
    if not n:
        return "    -"
    lo, hi = ev.wilson(k, n)
    return f"{100 * k / n:5.1f}% ({100 * lo:.0f} to {100 * hi:.0f})"


# ---------------------------------------------------------------------------
# describe


def cmd_describe(args) -> int:
    from extract_text.score import mask

    with open(Path(args.truth).expanduser(), newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"{len(rows)} rows. Columns: {', '.join(rows[0].keys()) if rows else '(none)'}")
    by_status = Counter(r.get("extractStatus", "") for r in rows)
    print("By provenance: " + ", ".join(f"{k or '(empty)'} {v}" for k, v in by_status.most_common()))
    by_county = Counter(r.get("county", "") for r in rows if r.get("extractStatus") == args.status)
    print(f"'{args.status}' rows by county: " + ", ".join(f"{k or '(empty)'} {v}" for k, v in by_county.most_common()))
    truth = load_truth(args.truth, args.status)
    keys = [ev.truth_key(r["plainAddress"]) for r in truth.values()]
    n = len(keys)
    print(f"\n{n} '{args.status}' rows with a case and an address.")
    how = Counter(k["how"] for k in keys)
    print("How the typed line splits into street and the rest: "
          + ", ".join(f"{h} {how[h]}" for h in ev.SPLIT_KINDS if how[h]))
    print(f"With a ZIP code: {sum(bool(k['zip']) for k in keys)}. With a unit: {sum(bool(k['unit']) for k in keys)}. "
          f"With a house number: {sum(bool(k['house']) for k in keys)}.")
    years = Counter("20" + c[:2] for c in truth)
    print("By filing year (from the case number): " + ", ".join(f"{y} {v}" for y, v in sorted(years.items())))
    shapes = Counter(mask(r["plainAddress"]) for r in truth.values())
    print(f"\nThe {args.top} most common shapes of the typed line (letters A or a, digits 9):")
    for shape, count in shapes.most_common(args.top):
        print(f"  {count:>5}  {shape}")
    for kind in ("no_suffix", "comma", "whole"):
        odd = Counter(mask(r["plainAddress"]) for r, k in zip(truth.values(), keys) if k["how"] == kind)
        if odd:
            print(f"\nSplit by '{kind}' ({sum(odd.values())} lines), the {args.top} most common shapes:")
            for shape, count in odd.most_common(args.top):
                print(f"  {count:>5}  {shape}")
    return 0


# ---------------------------------------------------------------------------
# split


def cmd_split(args) -> int:
    from extract_text.pipeline import choose_summons

    out = Path(args.out).expanduser()
    if (out / "manifest.csv").exists() and not args.force:
        raise SystemExit("a manifest is already there. The split is made once; "
                         "pass --force only to throw the old one away on purpose.")
    truth = load_truth(args.truth, args.status)
    archive = Path(args.archive).expanduser()
    found, skipped = [], Counter()
    for case, r in sorted(truth.items()):
        year = "20" + case[:2]
        case_dir = archive / r["county"] / year / case
        if not case_dir.is_dir():
            skipped["no case folder"] += 1
            continue
        doc, variant = choose_summons(case_dir)
        if doc is None:
            skipped["no summons in the folder"] += 1
            continue
        found.append({"case_number": case, "county": r["county"], "year": year,
                      "truth_status": r["extractStatus"], "doc_variant": variant, "doc_path": str(doc)})
    parts = ev.seeded_split([r["case_number"] for r in found], args.test, args.seed)
    for r in found:
        r["part"] = parts[r["case_number"]]
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(found)
    (out / "split.json").write_text(json.dumps(
        {"status": args.status, "seed": args.seed, "test": args.test, "made": time.strftime("%Y-%m-%d %H:%M")}))
    n_test = sum(r["part"] == "test" for r in found)
    print(f"{len(truth)} '{args.status}' cases in the truth file; {len(found)} have a summons on disk"
          + ("; not used: " + ", ".join(f"{v} {k}" for k, v in skipped.items()) if skipped else "") + ".")
    print(f"Split with seed {args.seed}: {n_test} test, {len(found) - n_test} dev.")
    print("By county and year: " + ", ".join(
        f"{k} {v}" for k, v in sorted(Counter(f"{r['county']} {r['year']}" for r in found).items())))
    print("By kind of summons file: " + ", ".join(
        f"{k} {v}" for k, v in Counter(r["doc_variant"] for r in found).most_common()))
    return 0


# ---------------------------------------------------------------------------
# run


def _reading(row: dict) -> dict:
    """An engine's flat row as the reading the scores compare."""
    return {"street": row.get("defendant_street", "") or "", "unit": row.get("defendant_unit", "") or "",
            "city": row.get("defendant_city", "") or "", "state": row.get("defendant_state", "") or "",
            "zip": row.get("defendant_zip", "") or "", "raw": row.get("defendant_address_raw", "") or "",
            "anchor": row.get("defendant_anchor", "") or "", "flags": row.get("flags", "") or "",
            "n_ungrounded": row.get("n_ungrounded", "")}


def make_lane(name: str, model: str, cache: Path):
    """A function that reads one document with the lane called `name`."""
    from extract_text.documents import cached_document
    from extract_text.pipeline import flatten_extraction

    if name == "rules":
        from extract_text.deterministic import extract_from_document

        return lambda path: _reading(flatten_extraction(extract_from_document(cached_document(path, cache))))
    if name == "ai":
        from extract_text.ai.vision import LocalVisionBackend

        backend = LocalVisionBackend(model=model)
        return lambda path: _reading(flatten_extraction(backend.extract_file(path)))
    if name == "ai-text":
        from extract_text.ai.local_backend import LocalBackend

        backend = LocalBackend(model=model)
        return lambda path: _reading(flatten_extraction(backend.extract(cached_document(path, cache).text)))
    raise SystemExit(f"no lane called {name!r}; known: {', '.join(LANES)}")


def load_readings(out: Path, lane: str) -> dict[str, dict]:
    path = out / "readings" / f"{lane}.jsonl"
    if not path.is_file():
        return {}
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return {r["case"]: r for r in rows}  # a case read twice keeps its last reading


def cmd_run(args) -> int:
    out = Path(args.out).expanduser()
    manifest = {r["case_number"]: r for r in read_manifest(out)}
    cases = drawn_cases(list(manifest.values()), args.part, args.n, args.seed)
    (out / "readings").mkdir(parents=True, exist_ok=True)
    print(f"{len(cases)} cases drawn from the {args.part} part (seed {args.seed}).")
    for lane in [x.strip() for x in args.lanes.split(",") if x.strip()]:
        have = load_readings(out, lane)
        todo = [c for c in cases if c not in have or (args.retry and have[c].get("error"))]
        read = make_lane(lane, args.model, out / "_cache")
        errors, start = Counter(), time.monotonic()
        with open(out / "readings" / f"{lane}.jsonl", "a") as f:
            for i, case in enumerate(todo, 1):
                t0 = time.monotonic()
                try:
                    reading = read(Path(manifest[case]["doc_path"]))
                except Exception as exc:  # one document must not stop the run
                    reading = {"error": type(exc).__name__}
                    errors[type(exc).__name__] += 1
                reading.update(case=case, lane=lane, seconds=round(time.monotonic() - t0, 1))
                f.write(json.dumps(reading) + "\n")
                f.flush()
                if i % 25 == 0 or i == len(todo):
                    print(f"  {lane}: {i} of {len(todo)}", file=sys.stderr)
        took = time.monotonic() - start
        print(f"{lane}: {len(cases) - len(todo)} already read, {len(todo)} read now in {took:.0f} s"
              + (f" ({took / len(todo):.1f} s a document)" if todo else "")
              + ("; errors: " + ", ".join(f"{v} {k}" for k, v in errors.items()) if errors else "") + ".")
    return 0


# ---------------------------------------------------------------------------
# score


def _listed(readings: dict[str, dict], addresses) -> dict[str, str]:
    out = {}
    for case, r in readings.items():
        if r.get("error") or not r.get("street"):
            out[case] = ""
            continue
        out[case] = addresses.check(r["street"], r.get("unit"), r.get("city"), r.get("state"),
                                    r.get("zip"))["address_check"]
    return out


def cmd_score(args) -> int:
    out = Path(args.out).expanduser()
    manifest = read_manifest(out)
    status = json.loads((out / "split.json").read_text())["status"]
    truth_rows = load_truth(args.truth, status)
    drawn = drawn_cases(manifest, args.part, args.n, args.seed)
    lanes = {}
    for lane in LANES:
        got = load_readings(out, lane)
        if got:
            lanes[lane] = got
    if not lanes:
        raise SystemExit("no readings yet; run 'run' first")
    cases = [c for c in drawn if c in truth_rows and all(c in got for got in lanes.values())]
    truths = {c: ev.truth_key(truth_rows[c]["plainAddress"]) for c in cases}
    lines = [f"Head to head on the {args.part} part: {len(cases)} of {len(drawn)} drawn cases read by every lane "
             f"({', '.join(lanes)}). Seed {args.seed}.",
             "Shares carry a 95 percent interval in brackets."]
    how = Counter(t["how"] for t in truths.values())
    lines.append("Typed lines split by: " + ", ".join(f"{h} {how[h]}" for h in ev.SPLIT_KINDS if how[h]) + ".")
    for lane, got in lanes.items():
        errors = sum(bool(got[c].get("error")) for c in cases)
        s = ev.score_lane(truths, got, cases)
        n = s["n"]
        secs = [got[c].get("seconds") or 0 for c in cases]
        lines += ["", f"{lane}" + (f" ({errors} documents failed to read)" if errors else "")
                  + f", {sum(secs) / len(secs):.1f} s a document" if secs else f"{lane}",
                  f"  returned an address        {_pct(s.get('extracted', 0), n)} of {n}",
                  f"  paper's measure, same street (0.7 or more)  {_pct(s.get('paper', 0), n)}; "
                  f"mean similarity where returned {s['mean_ratio_extracted']:.3f}",
                  f"  strict: house number right {_pct(s.get('house', 0), n)}",
                  f"  strict: street right       {_pct(s.get('street', 0), n)}",
                  f"  unit kept, where the typed line has one  {_pct(s.get('unit_kept', 0), s.get('truth_units', 0))}"
                  f" of {s.get('truth_units', 0)}",
                  f"  street and unit, where the typed line has one  "
                  f"{_pct(s.get('street_and_unit', 0), s.get('truth_units', 0))}",
                  f"  a unit read where the typed line has none (not counted wrong)  "
                  f"{s.get('unit_added', 0)} of {s.get('no_truth_unit', 0)}",
                  f"  ZIP agrees, where both have one  {_pct(s.get('zip', 0), s.get('zip_both', 0))}"
                  f" of {s.get('zip_both', 0)}",
                  "  strict street by how the typed line was split: "
                  + ", ".join(f"{h} {r} of {k}" for h, (k, r) in s["street_by_split"].items())]
    names = list(lanes)
    if len(names) > 1:
        lines += ["", "Paired, strict street (documents where exactly one lane is right decide the test)",
                  "  first / second            both  first only  second only  neither   second minus first   p"]
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                p = ev.paired(truths, lanes[a], lanes[b], cases)
                lines.append(f"  {a + ' / ' + b:<24}{p['both']:>6}{p['first_only']:>12}{p['second_only']:>13}"
                             f"{p['neither']:>9}{100 * p['difference']:>15.1f} points   {p['p']:.4f}")
        if "rules" in lanes and "ai" in lanes:
            p = ev.paired(truths, lanes["rules"], lanes["ai"], cases)
            met = 100 * p["difference"] >= 5 and p["p"] < 0.05
            lines += ["", "Reading rule, written before the run: where a model is allowed it leads on the address "
                          "if its strict street share beats the rules' by 5 points or more with p below 0.05.",
                      f"  model minus rules: {100 * p['difference']:.1f} points, p = {p['p']:.4f}. "
                      f"The rule is {'met' if met else 'not met'}."]
            if args.n and len(cases) < args.n:
                lines.append(f"  The rule was written for {args.n} documents; this is {len(cases)}, "
                             "so it is a reading in progress, not the result.")
    listed = {}
    if args.addresses:
        from extract_text.address_check import AddressList

        addresses = (AddressList.from_preset(args.addresses, args.preset) if args.preset
                     else AddressList.from_csv(args.addresses, street=args.street_column,
                                               zip=args.zip_column, city=args.city_column))
        listed = {lane: _listed(got, addresses) for lane, got in lanes.items()}
        lines += ["", f"Address list: {addresses.n} listed addresses."]
        for lane in lanes:
            verdicts = Counter(listed[lane].get(c) or "nothing to check" for c in cases)
            lines.append(f"  {lane}: " + ", ".join(f"{v} {k}" for k, v in verdicts.most_common()))
    rows = ev.tiers(truths, lanes, cases, listed)
    if rows:
        lines += ["", "Accept signals: how many documents each covers, and how often the street is right when it holds",
                  "  signal                                         covers            street right when it holds"]
        for r in rows:
            lines.append(f"  {r['signal']:<44}{_pct(r['covered'], r['n']):>20}   "
                         f"{r['right']} of {r['covered']}  {_pct(r['right'], r['covered'])}")
    report = "\n".join(lines)
    print(report)
    if args.save:
        Path(args.save).expanduser().write_text(report + "\n")
    return 0


# ---------------------------------------------------------------------------
# loss


def cmd_loss(args) -> int:
    from extract_text.deterministic import extract_from_document
    from extract_text.deterministic.summons import extract_summons_fields
    from extract_text.documents import cached_document
    from extract_text.pipeline import flatten_extraction
    from extract_text.score import _street_in_text

    out = Path(args.out).expanduser()
    manifest = {r["case_number"]: r for r in read_manifest(out)}
    status = json.loads((out / "split.json").read_text())["status"]
    truth_rows = load_truth(args.truth, status)
    cases = [c for c in drawn_cases(list(manifest.values()), args.part, args.n, args.seed) if c in truth_rows]
    kinds, by_state, anchors, n_right, errors = Counter(), Counter(), Counter(), 0, 0
    for case in cases:
        truth = ev.truth_key(truth_rows[case]["plainAddress"])
        try:
            doc = cached_document(Path(manifest[case]["doc_path"]), out / "_cache")
            reading = _reading(flatten_extraction(extract_from_document(doc)))
            # the engine's own candidates, on the pages it ended up reading
            candidates = extract_summons_fields(doc)[0]["candidates"]
        except Exception:
            errors += 1
            continue
        if ev.compare_address(truth, reading)["street"]:
            n_right += 1
            continue
        typed_street = ev.split_address(truth["plain"])["street"]
        in_text = _street_in_text(typed_street, doc.text)[0]
        streets = [(c.get("street") or "", c.get("unit") or "") for c in candidates]
        kind = ev.loss_category(truth, in_text, streets, reading["raw"])
        kinds[kind] += 1
        by_state[(kind, "blank" if not reading["street"] else "wrong")] += 1
        anchors[reading["anchor"] or "(no address)"] += 1
    n_lost = sum(kinds.values())
    lines = [f"Where the rules lose the street, on {len(cases)} drawn cases of the {args.part} part "
             f"(seed {args.seed}): {n_right} right, {n_lost} lost"
             + (f", {errors} failed to read" if errors else "") + ".", ""]
    for kind in ev.LOSS_KINDS:
        blank, wrong = by_state[(kind, "blank")], by_state[(kind, "wrong")]
        lines.append(f"  {kind:<30}{kinds[kind]:>5}  {_pct(kinds[kind], n_lost)}   (left blank {blank}, read wrong {wrong})")
    lines += ["", "The lost streets by the anchor the engine used: "
              + ", ".join(f"{k} {v}" for k, v in anchors.most_common()),
              "", "not in the text: the page text the engine read does not hold the typed street (OCR, or a page not read).",
              "in the text, no candidate: the street is on the page and no address-shaped candidate was built from it.",
              "a candidate, not chosen: the engine found it and picked another address.",
              "chosen block, parsed wrong: the engine picked the right block and split it wrongly."]
    report = "\n".join(lines)
    print(report)
    if args.save:
        Path(args.save).expanduser().write_text(report + "\n")
    return 0


# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(a, truth=True, out=True):
        if truth:
            a.add_argument("--truth", required=True, help="the CSV of typed addresses")
        if out:
            a.add_argument("--out", required=True, help="a folder in governed storage")

    def draw(a):
        a.add_argument("--part", choices=("test", "dev"), default="test")
        a.add_argument("--n", type=int, default=500, help="how many cases of the part to draw (0 for all)")
        a.add_argument("--seed", type=int, default=DEFAULT_SEED)

    a = sub.add_parser("describe", help="what the truth file holds, in counts and masked shapes")
    common(a, out=False)
    a.add_argument("--status", default="thesis", help="the provenance to use (the extractStatus column)")
    a.add_argument("--top", type=int, default=15)
    a.set_defaults(fn=cmd_describe)

    a = sub.add_parser("split", help="write the manifest once, with a seeded test and dev split")
    common(a)
    a.add_argument("--archive", required=True, help="the folder of court images: ARCHIVE/county/year/case/")
    a.add_argument("--status", default="thesis")
    a.add_argument("--test", type=int, default=1000, help="cases in the test part")
    a.add_argument("--seed", type=int, default=DEFAULT_SEED)
    a.add_argument("--force", action="store_true")
    a.set_defaults(fn=cmd_split)

    a = sub.add_parser("run", help="read a seeded draw with each lane")
    common(a, truth=False)
    draw(a)
    a.add_argument("--lanes", default="rules", help="comma-separated: " + ", ".join(LANES))
    a.add_argument("--model", default=DEFAULT_MODEL, help="the Ollama model tag for the ai lanes")
    a.add_argument("--retry", action="store_true", help="read again the documents that failed")
    a.set_defaults(fn=cmd_run)

    a = sub.add_parser("score", help="print the tables, in counts")
    common(a)
    draw(a)
    a.add_argument("--addresses", default=None, help="a CSV of real addresses, for the accept signals")
    a.add_argument("--preset", default=None, help="a known list's columns, such as king_county_wa")
    a.add_argument("--street-column", default="address")
    a.add_argument("--zip-column", default=None)
    a.add_argument("--city-column", default=None)
    a.add_argument("--save", default=None, help="also write the report here")
    a.set_defaults(fn=cmd_score)

    a = sub.add_parser("loss", help="which stage lost each street the rules missed")
    common(a)
    draw(a)
    a.add_argument("--save", default=None)
    a.set_defaults(fn=cmd_loss)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
