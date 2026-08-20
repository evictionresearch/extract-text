#!/usr/bin/env python3
"""Turn vision-model readings into validation cards for the game.

The deterministic engine fails on some documents. A vision reader (Claude
reading page images, or the local qwen lane) can often still read the address.
Those readings must NOT go straight into a training set: a model's reading is
a proposal, not ground truth. This script turns each reading into a game card
so that a person confirms or rejects it by swiping, exactly like the
deterministic cards. Only confirmed cards graduate to truth.

Input: a readings CSV with columns
    card_id, doc_path, case_number, county, year, page,
    address        the full address as the reader saw it (street, city, ZIP)
    names          party names the reader saw, ';'-separated — these are the
                   redaction targets, so read them carefully
    source         which reader produced it (e.g. "claude-vision", "qwen3.5")

Cards land in OUT/crops and OUT/vision_cards.csv, plus deck entries in
OUT/deck_vision.json. Every card keeps the safety rule: no card is emitted
unless at least one name was actually painted over, and crops fall back to a
first-row-blanked service band when the reading's tokens cannot be located in
the OCR words (which is common — OCR failing is often why the engine failed).

    python3 python/scripts/build_vision_cards.py \
        --readings READINGS.csv --out DECKDIR
"""

import argparse
import csv
import json
import os
import re
import sys
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _toks(s):
    return [t for t in re.split(r"[^A-Za-z0-9#]+", (s or "").upper()) if t]


def build_one(row, out_dir):
    from extract_text import documents
    from extract_text.cards import (NEVER_REDACT, locate_address,
                                    locate_service_band, render_card,
                                    safe_to_show)

    cid = row["card_id"]
    rec = dict(row, status="", crop="", redacted="", crop_kind="")
    try:
        page = int(row.get("page") or 1)
        doc = documents.load_document(row["doc_path"], pages=[page])
    except Exception as e:                                    # noqa: BLE001
        rec["status"] = f"error:{type(e).__name__}"
        return rec

    # redaction targets come from the reader's own name field, filtered by the
    # same rules the deterministic cards use
    redact = set()
    for name in (row.get("names") or "").split(";"):
        for t in _toks(name):
            if len(t) >= 3 and t.isalpha():
                redact.add(t)
    redact -= set(_toks(row["address"]))
    redact -= NEVER_REDACT
    rec["redacted"] = ";".join(sorted(redact))
    ok, why = safe_to_show(redact)
    if not ok:
        rec["status"] = f"withheld:{why}"
        return rec

    out_png = Path(out_dir) / "crops" / f"{cid}.png"
    box = locate_address(doc, row["address"], "", page)
    if box is not None:
        png = render_card(row["doc_path"], page, box, out_png,
                          words=doc.words, redact=redact)
        rec["crop_kind"] = "located"
    else:
        # OCR could not place the reader's tokens — cut the service band and
        # blank the name row; refuse rather than show a name (render_card
        # returns None when the row cannot be isolated)
        band = locate_service_band(doc, page)
        if band is None:
            rec["status"] = "no_crop_anchor"
            return rec
        png = render_card(row["doc_path"], page, band, out_png,
                          words=doc.words, redact=redact, blank_first_row=True)
        rec["crop_kind"] = "service_band"
    if png is None:
        rec["status"] = "crop_failed"
        return rec
    rec["crop"] = f"crops/{cid}.png"
    rec["status"] = "ok"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(os.path.expanduser(args.out))
    (out / "crops").mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.expanduser(args.readings))))
    results = [build_one(r, out) for r in rows]

    keys = ["card_id", "county", "year", "case_number", "doc_path", "page",
            "address", "names", "source", "status", "crop", "crop_kind",
            "redacted"]
    with open(out / "vision_cards.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    os.chmod(out / "vision_cards.csv", 0o600)

    ok = [r for r in results if r["status"] == "ok"]
    deck = [{"id": r["card_id"], "img": r["crop"], "guess": r["address"],
             "src": r.get("source", "vision")} for r in ok]
    (out / "deck_vision.json").write_text(json.dumps(deck, indent=1))
    os.chmod(out / "deck_vision.json", 0o600)

    print(f"readings : {len(rows)}", file=sys.stderr)
    print(f"status   : {dict(Counter(r['status'] for r in results))}", file=sys.stderr)
    print(f"crop kind: {dict(Counter(r['crop_kind'] for r in ok))}", file=sys.stderr)
    print(f"deck     : {out / 'deck_vision.json'} ({len(deck)} cards)", file=sys.stderr)


if __name__ == "__main__":
    main()
