#!/usr/bin/env python3
"""Turn exported ratings into a labeled training set.

Ratings are not counted equally. Each rater is scored against the attention
probes, which are cards whose correct answer is known because the address was
deliberately altered by one digit, and their votes are weighted by how well
they did. This follows braindr, which weighted citizen scientists by agreement
with an expert-labeled gold standard:

    Keshavan A, Yeatman JD, Rokem A (2019). "Combining Citizen Science and Deep
    Learning to Amplify Expertise in Neuroimaging." Frontiers in Neuroinformatics
    13:29. https://doi.org/10.3389/fninf.2019.00029

Usage:
    python3 game/score_ratings.py \
        --deck-dir ~/data/evictionresearch/washington/_training_2026-08-18 \
        --ratings ratings/*.json \
        --out ~/data/evictionresearch/washington/_training_2026-08-18/labels.csv
"""

import argparse
import csv
import glob
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Below this raw probe accuracy a rater's votes are dropped outright. A rater
# who is systematically wrong is worse than no rater at all.
DROP_BELOW = 0.5
# Agreement needed to call a card settled.
SETTLED = 0.70
# Laplace pseudo-counts used when estimating probe accuracy. At 8% probes a
# rater who does 120 cards sees only about 9 of them, and 6 right out of 9 is
# well within luck for someone swiping at random. Smoothing pulls small samples
# toward chance so that a high weight has to be earned over many probes rather
# than won on a short run.
PRIOR_HITS, PRIOR_MISSES = 1.0, 1.0


def rater_weight(hits, n_probes):
    """Map probe performance to a vote weight in 0..1.

    Chance is 50%, so accuracy is first rescaled to put chance at zero. Without
    that, a coin-flipping rater would carry half the weight of an expert. The
    exponent then widens the gap further, because on a task this easy for an
    attentive person, being merely mediocre is itself evidence of not reading.
    """
    if n_probes == 0:
        return 0.5                                   # neutral until measured
    raw = hits / n_probes
    if raw < DROP_BELOW:
        return 0.0
    smoothed = (hits + PRIOR_HITS) / (n_probes + PRIOR_HITS + PRIOR_MISSES)
    return round(max(0.0, 2 * smoothed - 1) ** 1.5, 3)


def load_ratings(patterns):
    files = []
    for p in patterns:
        files.extend(glob.glob(os.path.expanduser(p)))
    out = []
    for fp in sorted(files):
        try:
            d = json.load(open(fp))
        except Exception as e:                                # noqa: BLE001
            print(f"  skipping {fp}: {e}", file=sys.stderr)
            continue
        rater = d.get("rater") or Path(fp).stem
        for r in d.get("ratings", []):
            if r.get("id") and r.get("verdict"):
                out.append({"rater": rater, "id": r["id"], "verdict": r["verdict"],
                            "correction": (r.get("correction") or "").strip(),
                            "ms": r.get("ms", 0)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deck-dir", required=True)
    ap.add_argument("--ratings", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-votes", type=int, default=2,
                    help="votes needed before a card is labeled (default 2)")
    args = ap.parse_args()

    dd = Path(os.path.expanduser(args.deck_dir))
    cards = {r["card_id"]: r for r in csv.DictReader(open(dd / "cards.csv"))}
    for r in cards.values():
        r.setdefault("source", "rules")
    # vision cards (V####) carry a model's reading rather than the engine's;
    # they live in their own manifest so provenance is never mixed up
    vpath = dd / "vision_cards.csv"
    if vpath.exists():
        for r in csv.DictReader(open(vpath)):
            if r.get("status") == "ok":
                cards[r["card_id"]] = {
                    "card_id": r["card_id"], "county": r.get("county", ""),
                    "state": "WA", "year": r.get("year", ""),
                    "display": r.get("address", ""),
                    "anchor": "vision", "text_source": r.get("crop_kind", ""),
                    "flags": "", "source": r.get("source", "vision"),
                }
    gold = {r["probe_id"]: r for r in csv.DictReader(open(dd / "gold.csv"))}

    ratings = load_ratings(args.ratings)
    if not ratings:
        sys.exit("no ratings found")
    raters = sorted({r["rater"] for r in ratings})
    print(f"{len(ratings)} ratings from {len(raters)} raters", file=sys.stderr)

    # --- score each rater on the probes -----------------------------------
    stats = {}
    for who in raters:
        mine = [r for r in ratings if r["rater"] == who]
        probes = [r for r in mine if r["id"] in gold and r["verdict"] != "skip"]
        hit = sum(1 for r in probes
                  if r["verdict"] == gold[r["id"]]["true_label"])
        acc = hit / len(probes) if probes else None
        times = [r["ms"] for r in mine if r["ms"]]
        stats[who] = {
            "n": len(mine), "n_probe": len(probes), "acc": acc,
            "median_ms": statistics.median(times) if times else 0,
            "skips": sum(1 for r in mine if r["verdict"] == "skip"),
            "fixes": sum(1 for r in mine if r["correction"]),
        }
        stats[who]["weight"] = rater_weight(hit, len(probes))

    print("\nrater                     n  probes   acc  weight  med ms  fixes",
          file=sys.stderr)
    for who in raters:
        s = stats[who]
        a = f"{s['acc']:.0%}" if s["acc"] is not None else "  -"
        print(f"{who[:22]:22s} {s['n']:5d} {s['n_probe']:6d}  {a:>5s} "
              f"{s['weight']:6.2f} {s['median_ms']:7.0f} {s['fixes']:6d}",
              file=sys.stderr)

    dropped = [w for w in raters if stats[w]["weight"] == 0]
    if dropped:
        print(f"\ndropped (probe accuracy below {DROP_BELOW:.0%}): {dropped}",
              file=sys.stderr)

    # --- aggregate real cards ---------------------------------------------
    votes = defaultdict(lambda: {"yes": 0.0, "no": 0.0, "skip": 0,
                                 "n": 0, "fix": []})
    for r in ratings:
        if r["id"] in gold:
            continue                                   # probes are calibration only
        w = stats[r["rater"]]["weight"]
        v = votes[r["id"]]
        if r["verdict"] == "skip":
            v["skip"] += 1
            continue
        if w <= 0:
            continue
        v[r["verdict"]] += w
        v["n"] += 1
        if r["correction"]:
            v["fix"].append(r["correction"])

    rows = []
    for cid, v in sorted(votes.items()):
        card = cards.get(cid)
        if card is None:
            continue
        total = v["yes"] + v["no"]
        if total <= 0 or v["n"] < args.min_votes:
            label, conf = "unsettled", 0.0
        else:
            share = v["yes"] / total
            if share >= SETTLED:
                label, conf = "correct", share
            elif share <= 1 - SETTLED:
                label, conf = "incorrect", 1 - share
            else:
                label, conf = "disputed", max(share, 1 - share)
        fix = Counter(v["fix"]).most_common(1)
        rows.append({
            "card_id": cid,
            "source": card.get("source", "rules"),
            "county": card.get("county", ""),
            "state": card.get("state", "") or "WA",
            "year": card.get("year", ""),
            "engine_address": card.get("display", ""),
            "label": label,
            "confidence": round(conf, 3),
            "n_votes": v["n"],
            "n_skip": v["skip"],
            "weighted_yes": round(v["yes"], 3),
            "weighted_no": round(v["no"], 3),
            "correction": fix[0][0] if fix else "",
            "n_corrections": len(v["fix"]),
            "anchor": card.get("anchor", ""),
            "text_source": card.get("text_source", ""),
            "flags": card.get("flags", ""),
        })

    outp = Path(os.path.expanduser(args.out))
    with open(outp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    os.chmod(outp, 0o600)

    lab = Counter(r["label"] for r in rows)
    print(f"\nlabeled {len(rows)} cards: {dict(lab)}", file=sys.stderr)
    settled = [r for r in rows if r["label"] in ("correct", "incorrect")]
    if settled:
        acc = sum(1 for r in settled if r["label"] == "correct") / len(settled)
        print(f"engine accuracy on settled cards: {acc:.1%} "
              f"({len(settled)} cards)", file=sys.stderr)
    withfix = sum(1 for r in rows if r["correction"])
    print(f"cards with a typed correction: {withfix}", file=sys.stderr)

    # Accuracy is not one number. Counties use different forms, different
    # vendors and different scanning equipment, so a rule that holds in Pierce
    # can fail in Whatcom. Breaking the result down is how a pattern local to
    # one jurisdiction gets noticed instead of being averaged away, and it is
    # what makes the same deck useful when a new county or state is added.
    for key, label in (("source", "reader"), ("state", "state"),
                       ("county", "county"), ("year", "year")):
        groups = defaultdict(list)
        for r in rows:
            if r["label"] in ("correct", "incorrect"):
                groups[r[key] or "(unknown)"].append(r)
        if len(groups) < 2:
            continue
        print(f"\naccuracy by {label}:", file=sys.stderr)
        for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            ok = sum(1 for r in rs if r["label"] == "correct")
            fx = sum(1 for r in rs if r["correction"])
            print(f"   {g:14s} n={len(rs):4d}  correct {ok / len(rs):6.1%}"
                  f"   corrections {fx:3d}", file=sys.stderr)

    # the same split over anchors and text sources, which is where a fix
    # usually has to go once a weak county is identified
    for key, label in (("anchor", "anchor"), ("text_source", "text source")):
        groups = defaultdict(list)
        for r in rows:
            if r["label"] in ("correct", "incorrect"):
                groups[r[key] or "(none)"].append(r)
        if len(groups) < 2:
            continue
        print(f"\naccuracy by {label}:", file=sys.stderr)
        for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            ok = sum(1 for r in rs if r["label"] == "correct")
            print(f"   {g:20s} n={len(rs):4d}  correct {ok / len(rs):6.1%}",
                  file=sys.stderr)

    print(f"\nwrote {outp}", file=sys.stderr)


if __name__ == "__main__":
    main()
