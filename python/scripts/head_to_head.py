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
    python scripts/head_to_head.py run      --out OUT --lanes rules,ai --n 500
    python scripts/head_to_head.py score    --truth TRUTH.csv --out OUT --n 500 \\
                                            [--addresses LIST.csv --preset king_county_wa]
    python scripts/head_to_head.py loss     --truth TRUTH.csv --out OUT --n 500
    python scripts/head_to_head.py loss     --truth TRUTH.csv --out OUT --part dev --n 0 --shapes
    python scripts/head_to_head.py grade    --truth TRUTH.csv --out OUT --batch split [--serve]
    python scripts/head_to_head.py score    --truth TRUTH.csv --out OUT --blind split

`describe` says what the truth file holds and how its address lines split,
before anything is run. `split` writes OUT/manifest.csv once: every case of
the chosen provenance that has a summons on disk, marked 'test' or 'dev' by
a seeded draw. The test part is for scoring only; rule work reads shapes
from the dev part and never from the test part. `run` reads a seeded draw
of one part with each lane and keeps the readings in OUT/readings/; it can
be stopped and started again. `score` prints the tables. `loss` says, for
each street the rules missed, which stage lost it; with `--shapes`, on the
dev part only, it also prints the masked shape of each lost street beside
the shape of what the rules read, for rule work.

`grade` builds a blind grading page for one batch of the scored part in
OUT/grade_BATCH/: the form starts empty, no engine reading, box, flag, file
name, or case number is on the page, and the documents come in a seeded
shuffle. Batch `split` is the documents where exactly one of `rules` and
`ai` has the strict street; batch `rest` is those where neither has it plus
a seeded draw of 30 where both do. Which group each document is in stays in
OUT/grade_BATCH/key.json, which the page never reads. `score --blind BATCH`
prints, per group, how often the blind answer agrees with the typed line,
with the rules, and with the model, in counts.

Lanes: `rules` is the rules engine as it is in this checkout. `ai` is the
local model through Ollama reading the page image with the default prompt.
`ai-v1` is the same model and backend with Cheng Ren's prompt (`v1`), which
says where on the page each field sits; its reading rule against `ai` is in
MAINTENANCE.md (2026-11-20) and `score` prints it.
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
LANES = ("rules", "ai", "ai-v1", "ai-text")
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
    if name == "ai-v1":
        # Cheng Ren's prompt, which says where on the page each field sits
        from extract_text.ai.vision import LocalVisionBackend

        backend = LocalVisionBackend(model=model, prompt_format="v1")
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
    if args.blind:
        return cmd_score_blind(args)
    out = Path(args.out).expanduser()
    manifest = read_manifest(out)
    status = json.loads((out / "split.json").read_text())["status"]
    truth_rows = load_truth(args.truth, status)
    drawn = drawn_cases(manifest, args.part, args.n, args.seed)
    lanes = {}
    wanted = [x.strip() for x in args.lanes.split(",") if x.strip()] if args.lanes else LANES
    for lane in wanted:
        if lane not in LANES:
            raise SystemExit(f"no lane called {lane!r}; known: {', '.join(LANES)}")
        got = load_readings(out, lane)
        if got:
            lanes[lane] = got
        elif args.lanes:
            raise SystemExit(f"no readings for the {lane} lane yet; run 'run' first")
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
        if "ai" in lanes and "ai-v1" in lanes:
            p = ev.paired(truths, lanes["ai"], lanes["ai-v1"], cases)
            met = 100 * p["difference"] >= 3 and p["p"] < 0.05
            lines += ["", "Reading rule for Cheng Ren's prompt, written before the run (2026-11-20): if ai-v1 "
                          "beats ai by 3 points or more on strict street with p below 0.05, its position "
                          "wording goes into the default prompt for the address, once names are checked on "
                          "the graded 2017 documents; otherwise the default stays.",
                      f"  ai-v1 minus ai: {100 * p['difference']:.1f} points, p = {p['p']:.4f}. "
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
# the blind check: grade, and score --blind

GRADE_LANES = ("rules", "ai")


def _scored_cases(args, out: Path):
    """The cases of the drawn part that every lane of the blind check read,
    their typed lines as keys, and those lanes' readings."""
    manifest = read_manifest(out)
    status = json.loads((out / "split.json").read_text())["status"]
    truth_rows = load_truth(args.truth, status)
    drawn = drawn_cases(manifest, args.part, args.n, args.seed)
    lanes = {lane: load_readings(out, lane) for lane in GRADE_LANES}
    for lane, got in lanes.items():
        if not got:
            raise SystemExit(f"no readings for the {lane} lane yet; run 'run' first")
    cases = [c for c in drawn if c in truth_rows and all(c in got for got in lanes.values())]
    truths = {c: ev.truth_key(truth_rows[c]["plainAddress"]) for c in cases}
    return cases, truths, lanes, {r["case_number"]: r for r in manifest}


def cmd_grade(args) -> int:
    from extract_text.documents import doc_pages
    from extract_text.pipeline import write_review

    out = Path(args.out).expanduser()
    cases, truths, lanes, manifest = _scored_cases(args, out)
    picked = ev.blind_batch(truths, lanes["rules"], lanes["ai"], cases, args.batch, args.seed,
                            n_both=args.both)
    if not picked:
        raise SystemExit(f"batch {args.batch!r} holds no documents")
    folder = out / f"grade_{args.batch}"
    key_path = folder / "key.json"
    if key_path.is_file():
        # the batch is fixed once made: answers are kept by row number, so a
        # different draw or order would put them against the wrong documents
        earlier = [r["case"] for r in json.loads(key_path.read_text())["rows"]]
        if earlier != [c for c, _ in picked] and not args.force:
            raise SystemExit(f"{folder.name} already holds a batch of other documents or another "
                             "order. Pass --force only to throw it and its answers away on purpose.")
        made = earlier == [c for c, _ in picked]
    else:
        made = False
    folder.mkdir(parents=True, exist_ok=True)
    if not made:
        # answers to an earlier batch are set aside under a dated name, never deleted
        stamp = time.strftime("%Y%m%d_%H%M%S")
        for stale in ("corrections.jsonl", "corrections.csv"):
            if (folder / stale).exists():
                (folder / stale).rename(folder / f"{stale}.set_aside_{stamp}")
        key_path.write_text(json.dumps({
            "batch": args.batch, "part": args.part, "n": args.n, "seed": args.seed,
            "made": time.strftime("%Y-%m-%d %H:%M"),
            "rows": [{"row": i, "case": c, "group": g} for i, (c, g) in enumerate(picked, 1)]}))
    # a scan-shaped folder holding the documents and nothing any engine read,
    # so the page has nothing to show even by mistake
    rows = []
    for case, _ in picked:
        path = Path(manifest[case]["doc_path"])
        try:
            n_pages = doc_pages(path)
        except Exception:
            n_pages = 1
        rows.append({"file": str(path), "n_pages": n_pages})
    with open(folder / "extracted.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=("file", "n_pages"))
        w.writeheader()
        w.writerows(rows)
    with open(folder / "extracted.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps({"file": r["file"]}) + "\n")
    (folder / "blind.json").write_text(json.dumps({"fields": "address", "batch": args.batch}))
    write_review(folder, n=len(rows), blind=True, fields="address", pages=1)
    groups = Counter(g for _, g in picked)
    print(f"Batch '{args.batch}': {len(picked)} documents of the {args.part} part "
          f"({', '.join(f'{g} {groups[g]}' for g in ev.BLIND_BATCHES[args.batch])}), "
          f"in a shuffled order (seed {args.seed})" + (", as made before" if made else "") + ". "
          "Which group each document is in is kept in the batch folder's key file, not on the page.",
          flush=True)
    if args.serve:
        from extract_text.corrections import serve_review

        serve_review(folder, port=args.port, open_browser=not args.no_open)
    else:
        # the same command with --serve opens it; it finds the batch made before
        # and keeps every answer. (`extract-text review --serve` does too, from
        # a package new enough to know blind pages, 2026-11-20 on.)
        print("To grade, run this same command again with --serve.")
    return 0


def _blind_report(args, out: Path, batch: str) -> list[str]:
    from extract_text.corrections import load_corrections

    folder = out / f"grade_{batch}"
    if not (folder / "key.json").is_file():
        return [f"Batch '{batch}': not built yet ('grade --batch {batch}')."]
    key = json.loads((folder / "key.json").read_text())
    cases, truths, lanes, _ = _scored_cases(args, out)
    answers = load_corrections(folder)
    tally = {g: Counter() for g in ev.BLIND_BATCHES[batch]}
    for r in key["rows"]:
        t = tally.setdefault(r["group"], Counter())
        t["documents"] += 1
        c = answers.get(r["row"])
        if c is None:
            continue
        if not c.get("blind"):
            t["not blind"] += 1
            continue
        t["graded"] += 1
        if c.get("verdict") == "unreadable":
            t["cannot tell"] += 1
            continue
        answer = ev.answer_key(c["truth"])
        if not answer["street"]:
            t["no street typed"] += 1
            continue
        case = r["case"]
        m = ev.blind_compare(answer, truths[case], {lane: lanes[lane].get(case) for lane in GRADE_LANES})
        t["answered"] += 1
        t["typed"] += m["typed"]
        t["rules"] += m["rules"]
        t["ai"] += m["ai"]
        engines = [m[lane] for lane in GRADE_LANES]
        t["typed differs, an engine agrees"] += (not m["typed"]) and any(engines)
        t["typed differs, both engines agree"] += (not m["typed"]) and all(engines)
        t["agrees with none"] += not (m["typed"] or any(engines))
    total = sum(tally.values(), Counter())
    lines = [f"Blind check, batch '{batch}' (seed {key['seed']}): {total['documents']} documents, "
             f"{total['graded']} graded blind so far"
             + (f", {total['not blind']} answers not blind (left out)" if total["not blind"] else "")
             + f"; {total['cannot tell']} can't tell, {total['no street typed']} with no street typed, "
             f"{total['answered']} with a street.",
             "Strict street (house number and standardized street) of the blind answer, where a street was typed:",
             f"  {'group':<12}{'answered':>9}{'= typed line':>14}{'= rules':>10}{'= ai':>8}"
             f"{'typed differs,':>18}{'typed differs,':>16}{'agrees':>11}",
             f"  {'':<12}{'':>9}{'':>14}{'':>10}{'':>8}{'an engine agrees':>18}{'both agree':>16}{'with none':>11}"]
    for g, t in [*tally.items(), ("all", total)]:
        lines.append(f"  {g:<12}{t['answered']:>9}{t['typed']:>14}{t['rules']:>10}{t['ai']:>8}"
                     f"{t['typed differs, an engine agrees']:>18}{t['typed differs, both engines agree']:>16}"
                     f"{t['agrees with none']:>11}")
    return lines


def cmd_score_blind(args) -> int:
    out = Path(args.out).expanduser()
    batches = [b.strip() for b in args.blind.split(",") if b.strip()]
    for b in batches:
        if b not in ev.BLIND_BATCHES:
            raise SystemExit(f"no batch called {b!r}; known: {', '.join(ev.BLIND_BATCHES)}")
    lines = []
    for b in batches:
        lines += ([""] if lines else []) + _blind_report(args, out, b)
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
    from extract_text.score import _street_in_text, mask

    if args.shapes and args.part == "test":
        raise SystemExit("--shapes reads the dev part only: no shape from the test part may "
                         "inform a rule, or the test part stops being a test")
    out = Path(args.out).expanduser()
    manifest = {r["case_number"]: r for r in read_manifest(out)}
    status = json.loads((out / "split.json").read_text())["status"]
    truth_rows = load_truth(args.truth, status)
    cases = [c for c in drawn_cases(list(manifest.values()), args.part, args.n, args.seed) if c in truth_rows]
    kinds, by_state, anchors, n_right, errors = Counter(), Counter(), Counter(), 0, 0
    # with --shapes: (kind, typed shape, rules shape) for each lost street, and
    # how the model did on it where it read the document
    exact, words, model = Counter(), Counter(), Counter()
    ai = load_readings(out, "ai") if args.shapes else {}
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
        if args.shapes:
            read_street = reading["street"]
            exact[(kind, mask(typed_street), mask(read_street) if read_street else "(blank)")] += 1
            words[(kind, ev.word_shape(typed_street), ev.word_shape(read_street) if read_street else "(blank)")] += 1
            got = ai.get(case)
            if got and not got.get("error"):
                model[(kind, "read")] += 1
                model[(kind, "right")] += bool(ev.compare_address(truth, got)["street"])
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
    if args.shapes:
        lines += ["", "Shapes of the lost streets: the typed street beside the street the rules read, "
                      "letters A or a, digits 9 (the typed line's street part, unit included; "
                      "'(blank)' where the rules read none).",
                  "By words (each run of letters or digits as one mark), then letter by letter, "
                  f"the {args.top} most common pairs in each category."]
        for kind in ev.LOSS_KINDS:
            if not kinds[kind]:
                continue
            read, right = model[(kind, "read")], model[(kind, "right")]
            lines += ["", f"{kind}: {kinds[kind]} lost. The ai lane read {read} of them"
                      + (f" and has the street right on {right} ({_pct(right, read)})" if read else
                         " (no ai readings for these documents yet)") + "."]
            for title, table in (("by words", words), ("letter by letter", exact)):
                pairs = Counter({(t, r): v for (k, t, r), v in table.items() if k == kind})
                lines.append(f"  {title} ({len(pairs)} different pairs):")
                for (typed, got), count in pairs.most_common(args.top):
                    lines.append(f"    {count:>5}  {typed:<34} read as  {got}")
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
    a.add_argument("--lanes", default=None,
                   help="comma-separated lanes to score (default: every lane with readings); "
                        "only documents every chosen lane read are scored")
    a.add_argument("--blind", default=None, metavar="BATCH",
                   help="score the blind answers of a batch made by 'grade' (split, rest, or both "
                        "as split,rest) instead of the lanes")
    a.set_defaults(fn=cmd_score)

    a = sub.add_parser("grade", help="build the blind grading page for one batch, in counts")
    common(a)
    draw(a)
    a.add_argument("--batch", required=True, choices=tuple(ev.BLIND_BATCHES))
    a.add_argument("--both", type=int, default=30,
                   help="with --batch rest: how many documents both lanes have right to draw")
    a.add_argument("--serve", action="store_true", help="open the page for grading when it is built")
    a.add_argument("--port", type=int, default=8765)
    a.add_argument("--no-open", action="store_true", help="with --serve, do not open a browser window")
    a.add_argument("--force", action="store_true")
    a.set_defaults(fn=cmd_grade)

    a = sub.add_parser("loss", help="which stage lost each street the rules missed")
    common(a)
    draw(a)
    a.add_argument("--save", default=None)
    a.add_argument("--shapes", action="store_true",
                   help="also the masked shapes of each lost street beside the rules' reading, "
                        "and how often the ai lane has it right; dev part only")
    a.add_argument("--top", type=int, default=15, help="with --shapes: pairs shown per category")
    a.set_defaults(fn=cmd_loss)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
