#!/usr/bin/env python3
"""Build a game round from a truth-scored run.

When a labeled truth set exists, rater time should not be spent re-confirming
what the labels already settle. This builder splits a scored run three ways:

- **Disagreement cards** — the engine's answer differs from the truth label
  (below `--card-threshold` on the paper metric). These are the cards worth
  human eyes: either the engine is wrong, the decades-old label is wrong, or
  the document genuinely changed. The swipe adjudicates label vs engine.
- **Gold probes, real ones** — cards whose engine answer matches truth
  exactly become known-answer probes shown UNALTERED (`true_label=yes`),
  alongside the usual one-digit corruptions (`true_label=no`). Earlier rounds
  could only make no-probes by corrupting text; a truth set finally provides
  yes-probes, so a rater who swipes "no" on everything is caught too.
- Everything else (clear agreement) is auto-settled by the label and stays
  out of the deck.

Usage:
    python3 python/scripts/build_truth_round.py \
        --run RUN_DIR            # holds extracted.csv + val_scores.csv
        --manifest MANIFEST.csv  # doc paths for the same cases
        --out DECK_DIR [--card-threshold 0.95] [--max-cards 400]
        [--probes-yes 20] [--probes-no 20] [--seed 42]
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import warnings
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _toks(s):
    return [t for t in re.split(r"[^A-Za-z0-9#]+", (s or "").upper()) if t]


def build_card(job, out_dir):
    """Render one card (crop + redaction) for a case. Same rules as ever."""
    from extract_text import documents
    from extract_text.cards import (
        NEVER_REDACT,
        locate_address,
        render_card,
        safe_to_show,
    )

    rec = dict(job, status="", crop="", redacted="")
    try:
        doc = documents.load_document(job["doc_path"])
    except Exception as e:                                    # noqa: BLE001
        rec["status"] = f"error:{type(e).__name__}"
        return rec

    redact = set()
    for name in (job.get("names") or "").split(";"):
        for t in _toks(name):
            if len(t) >= 3 and t.isalpha():
                redact.add(t)
    redact -= set(_toks(job["address_raw"]))
    redact -= NEVER_REDACT
    rec["redacted"] = ";".join(sorted(redact))
    ok, why = safe_to_show(redact)
    if not ok:
        rec["status"] = f"withheld:{why}"
        return rec

    page = int(job.get("page") or 1)
    box = locate_address(doc, job["address_raw"], job.get("street", ""), page)
    if box is None:
        rec["status"] = "no_crop"
        return rec
    png = render_card(job["doc_path"], page, box,
                      Path(out_dir) / "crops" / f"{job['card_id']}.png",
                      words=doc.words, redact=redact)
    if png is None:
        rec["status"] = "crop_failed"
        return rec
    rec["crop"] = f"crops/{job['card_id']}.png"
    rec["status"] = "ok"
    return rec


def corrupt_digit(text, rng):
    starts = [m.start() for m in re.finditer(r"\d", text)]
    if not starts:
        return None
    i = rng.choice(starts)
    d = str((int(text[i]) + rng.randint(1, 8)) % 10)
    out = text[:i] + d + text[i + 1:]
    return out if out != text else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--card-threshold", type=float, default=0.95)
    ap.add_argument("--max-cards", type=int, default=400)
    ap.add_argument("--probes-yes", type=int, default=20)
    ap.add_argument("--probes-no", type=int, default=20)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    run = Path(os.path.expanduser(args.run))
    out = Path(os.path.expanduser(args.out))
    (out / "crops").mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    scores = list(csv.DictReader(open(run / "val_scores.csv")))
    ext = {r["case_number"]: r for r in csv.DictReader(open(run / "extracted.csv"))}
    man = {r["case_number"]: r for r in csv.DictReader(open(os.path.expanduser(args.manifest)))}

    yielded = [s for s in scores if s["extracted"] == "True"
               and s["case_number"] in ext and s["case_number"] in man]
    disagree = [s for s in yielded if float(s["ratio"]) < args.card_threshold]
    exact = [s for s in yielded if float(s["ratio"]) >= 0.999]
    rng.shuffle(disagree)
    rng.shuffle(exact)
    disagree = disagree[: args.max_cards]

    def job(s, cid):
        e = ext[s["case_number"]]
        m = man[s["case_number"]]
        names = ";".join(filter(None, (e.get("defendant_names", ""),
                                       e.get("plaintiffs", ""),
                                       e.get("attorney_names", ""))))
        # what the rater sees: street + unit + city/state/zip, as elsewhere
        disp_parts = [e.get("defendant_street", ""), e.get("defendant_city", ""),
                      " ".join(filter(None, (e.get("defendant_state", ""),
                                             e.get("defendant_zip", ""))))]
        display = ", ".join(p for p in disp_parts if p)
        return {"card_id": cid, "case_number": s["case_number"],
                "county": m["county"], "year": m["year"],
                "truth_status": s["truth_status"], "doc_path": m["doc_path"],
                "page": 1, "address_raw": e.get("defendant_address_raw", ""),
                "street": e.get("defendant_street", ""), "display": display,
                "names": names, "ratio": s["ratio"], "kind": "disagreement"}

    jobs = [job(s, f"T{i:04d}") for i, s in enumerate(disagree, 1)]
    gold_yes = [job(s, f"GY{i:03d}") for i, s in enumerate(exact[: args.probes_yes], 1)]
    for g in gold_yes:
        g["kind"] = "gold_yes"
    gold_no = []
    for i, s in enumerate(exact[args.probes_yes: args.probes_yes + args.probes_no], 1):
        g = job(s, f"GN{i:03d}")
        bad = corrupt_digit(g["display"], rng)
        if bad is None:
            continue
        g["kind"], g["display_shown"] = "gold_no", bad
        gold_no.append(g)

    alljobs = jobs + gold_yes + gold_no
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(build_card, j, str(out)): j for j in alljobs}
        for i, f in enumerate(as_completed(futs), 1):
            j = futs[f]
            try:
                results.append({**j, **f.result()})
            except Exception as e:                            # noqa: BLE001
                results.append({**j, "status": f"worker:{type(e).__name__}"})
            if i % 50 == 0:
                print(f"  {i}/{len(alljobs)}", file=sys.stderr)

    ok = [r for r in results if r.get("status") == "ok"]
    deck, gold = [], []
    for r in sorted(ok, key=lambda r: r["card_id"]):
        shown = r.get("display_shown") or r["display"]
        deck.append({"id": r["card_id"], "img": r["crop"], "guess": shown,
                     "src": "rules"})
        if r["kind"] == "gold_yes":
            gold.append({"probe_id": r["card_id"], "source_card": r["case_number"],
                         "true_label": "yes", "corruption": "none (truth-exact)"})
        elif r["kind"] == "gold_no":
            gold.append({"probe_id": r["card_id"], "source_card": r["case_number"],
                         "true_label": "no", "corruption": "digit"})
    rng.shuffle(deck)

    keys = ["card_id", "kind", "case_number", "county", "year", "truth_status",
            "doc_path", "ratio", "display", "names", "status", "crop", "redacted"]
    with open(out / "cards.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    (out / "deck.json").write_text(json.dumps(deck, indent=1))
    with open(out / "gold.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["probe_id", "source_card", "true_label",
                                          "corruption"])
        w.writeheader()
        w.writerows(gold)
    for p in ("cards.csv", "deck.json", "gold.csv"):
        os.chmod(out / p, 0o600)

    print(f"disagreements available: {len(disagree)} of {len(yielded)} yielded",
          file=sys.stderr)
    print(f"status: {dict(Counter(r['status'] for r in results))}", file=sys.stderr)
    print(f"deck  : {len(deck)} cards ({len(gold_yes)} yes-gold, "
          f"{len(gold_no)} no-gold)", file=sys.stderr)
    print(f"out   : {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
