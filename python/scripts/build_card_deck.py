#!/usr/bin/env python3
"""Build a validation card deck from an archive of court filings.

Samples documents, runs the deterministic engine, and writes one card per
document: a cropped picture of the address with names painted over, next to
the address the engine typed out. People rate the cards in `game/`, and their
answers become a human-verified training set.

No model is involved. The addresses come from the rules engine, so the
resulting labels say where the rules are right and where they are wrong.

Everything it writes is real record material and belongs outside the repo.
Point `--out` at governed storage.

    python3 python/scripts/build_card_deck.py \
        --archive ~/data/evictionresearch/washington/court_images \
        --out ~/data/evictionresearch/washington/development/extract_text_training/_training_2026-08-18 \
        --n 700

Archive layout expected: ARCHIVE/County/Year/CaseNumber/<documents>. County
folders holding an extra level (an "Archive" tree, say) are walked too.
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

SEED = 42
SUMMONS_RE = re.compile(r"summons|sumons|sumns", re.IGNORECASE)
DOC_EXT = (".pdf", ".tif", ".tiff", ".png", ".jpg", ".jpeg")


# ---------------------------------------------------------------------------
# picking documents
# ---------------------------------------------------------------------------

def pick_summons(case_dir: Path):
    """Preference order: plain summons, then summons+complaint, then by-mail,
    with clerk copies (csde_) last. Mirrors the validated Washington scanner."""
    cands = [p for p in sorted(case_dir.iterdir())
             if p.suffix.lower() in DOC_EXT and SUMMONS_RE.search(p.name)]
    if not cands:
        return None, ""
    def rank(p):
        n = p.name.lower()
        return (n.startswith("csde_"), "by_mail" in n or "by mail" in n,
                "complaint" in n, len(n), n)
    best = sorted(cands, key=rank)[0]
    n = best.name.lower()
    variant = ("summons_by_mail" if ("by_mail" in n or "by mail" in n)
               else "summons_complaint" if "complaint" in n else "summons")
    return best, variant


def year_dirs(archive: Path, counties=None):
    out = []
    for county_dir in sorted(archive.iterdir()):
        if not county_dir.is_dir() or county_dir.name.startswith("_"):
            continue
        county = county_dir.name
        if counties and county not in counties:
            continue
        for sub in sorted(county_dir.iterdir()):
            if not sub.is_dir():
                continue
            if re.fullmatch(r"(19|20)\d{2}", sub.name):
                out.append((county, sub))
            else:
                for inner in sorted(sub.iterdir()):
                    if inner.is_dir() and re.fullmatch(r"(19|20)\d{2}", inner.name):
                        out.append((county, inner))
    return out


def sample(archive, n_total, take_all=(), counties=None, seed=SEED):
    """Counties in `take_all` are exhausted; the rest are stratified by year.

    Stratifying by year matters more than it looks. Court form layouts change
    over time, and layout variety is what a training set needs, so spreading
    thinly across many years beats concentrating on recent ones.
    """
    rng = random.Random(seed)
    ydirs = year_dirs(Path(archive), counties)
    picked, seen = [], set()

    def take(county, ydir, quota):
        got = 0
        cases = [p for p in ydir.iterdir() if p.is_dir()]
        rng.shuffle(cases)
        for case_dir in cases:
            if got >= quota:
                break
            if (county, case_dir.name) in seen:
                continue
            doc, variant = pick_summons(case_dir)
            if doc is None:
                continue
            seen.add((county, case_dir.name))
            picked.append({"county": county, "year": ydir.name,
                           "case_number": case_dir.name,
                           "doc_variant": variant, "doc_path": str(doc)})
            got += 1

    for county, yd in [(c, y) for c, y in ydirs if c in take_all]:
        take(county, yd, 10 ** 9)
    rest = [(c, y) for c, y in ydirs if c not in take_all]
    rng.shuffle(rest)
    per_year = max(1, (n_total - len(picked)) // max(1, len(rest)))
    for county, yd in rest:
        if len(picked) >= n_total:
            break
        take(county, yd, per_year)
    return picked


# ---------------------------------------------------------------------------
# one card
# ---------------------------------------------------------------------------

def build_card(item, out_dir):
    from extract_text import documents
    from extract_text.cards import (
        display_address,
        locate_address,
        name_tokens,
        render_card,
        safe_to_show,
    )
    from extract_text.deterministic import extract_from_document

    cid = item["card_id"]
    rec = dict(item, status="", address_guess="", display="", street="", unit="",
               city="", state="", zip="", anchor="", page="", flags="",
               text_source="", ocr_conf="", crop="", redacted="")
    try:
        doc = documents.load_document(item["doc_path"])
        x = extract_from_document(doc, expected_case_number=item["case_number"])
    except Exception as e:                                    # noqa: BLE001
        rec["status"] = f"error:{type(e).__name__}"
        return rec

    rec["flags"] = ";".join(x.flags)
    rec["text_source"] = x.document.text_source if x.document else ""
    rec["ocr_conf"] = (x.document.ocr_mean_conf
                       if x.document and x.document.ocr_mean_conf is not None else "")

    addr = x.record.defendant_address
    if addr is None or not addr.raw:
        rec["status"] = "no_address"
        # A document the reader failed on is worth keeping when it failed
        # because it was written by hand: those are the hardest addresses in
        # the archive and they never reach the data any other way. They become
        # transcription cards, which show no guess and ask for one.
        if not item.get("want_unreadable"):
            return rec
        from extract_text.cards import locate_service_band
        band = locate_service_band(doc, 1)
        if band is None:
            rec["status"] = "no_service_band"
            return rec
        png = render_card(item["doc_path"], 1, band,
                          Path(out_dir) / "crops" / f"{cid}.png",
                          words=doc.words, redact=name_tokens(x.record, ""),
                          blank_first_row=True)
        if png is None:
            rec["status"] = "crop_failed"
            return rec
        rec["crop"] = f"crops/{cid}.png"
        rec["status"] = "transcribe_review"
        return rec

    ev = x.evidence.get("defendant_address")
    page = getattr(ev, "page", None) or 1
    rec.update(address_guess=addr.raw, street=addr.street or "", unit=addr.unit or "",
               city=addr.city or "", state=addr.state or "", zip=addr.zip or "",
               anchor=getattr(ev, "anchor", "") or "", page=page,
               display=display_address(addr.street, addr.unit, addr.city,
                                       addr.state, addr.zip))

    redact = name_tokens(x.record, addr.raw)
    rec["redacted"] = ";".join(sorted(redact))
    ok, why = safe_to_show(redact)
    if not ok:
        rec["status"] = f"withheld:{why}"
        return rec

    box = locate_address(doc, addr.raw, addr.street or "", page)
    if box is None:
        rec["status"] = "no_crop"
        return rec
    png = render_card(item["doc_path"], page, box,
                      Path(out_dir) / "crops" / f"{cid}.png",
                      words=doc.words, redact=redact)
    if png is None:
        rec["status"] = "crop_failed"
        return rec
    rec["crop"] = f"crops/{cid}.png"
    rec["status"] = "ok"
    return rec


# ---------------------------------------------------------------------------
# attention probes
# ---------------------------------------------------------------------------

def corrupt(display, rng):
    """Change exactly one digit, so the correct answer is always "no".

    Only numeric corruptions are used. Flipping a direction or dropping a unit
    can accidentally *correct* a guess that was already wrong, which would
    label the probe "no" when "yes" is the honest answer. Richer probes become
    safe once a first round yields confirmed-correct cards to build them from.
    """
    options = []
    m = re.match(r"^(\d{1,6})\b", display)
    if m:
        d = list(m.group(1))
        j = rng.randrange(len(d))
        d[j] = str((int(d[j]) + rng.randint(1, 8)) % 10)
        out = "".join(d) + display[m.end(1):]
        if out != display:
            options.append((out, "house_number"))
    m = re.search(r"\b(\d{5})\b(?!.*\b\d{5}\b)", display)
    if m:
        z = m.group(1)
        out = (display[:m.start(1)] + z[:3] + str((int(z[3]) + 3) % 10) + z[4]
               + display[m.end(1):])
        if out != display:
            options.append((out, "zip"))
    m = re.search(r"(#|APT\.?|STE\.?|SUITE|UNIT)\s?#?\s?([\w-]+)", display, re.IGNORECASE)
    if m:
        tail = m.group(2)
        alt = "".join(str((int(c) + 4) % 10) if c.isdigit() else c for c in tail)
        if alt != tail:
            options.append((display[:m.start(2)] + alt + display[m.end(2):],
                            "unit_number"))
    if not options:
        return None, ""
    # Pick at random rather than always taking the first. When every probe
    # altered the house number, a rater learned to check the leading digits and
    # nothing else, and the probes stopped measuring general attention. Varying
    # which part changes keeps them honest about the whole string.
    return rng.choice(options)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=700)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--take-all", default="King",
                    help="comma-separated counties to exhaust rather than sample")
    ap.add_argument("--counties", default="", help="restrict to these counties")
    ap.add_argument("--probes", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--include-unreadable", action="store_true",
                    help="also build transcription cards from documents the "
                         "reader failed on (handwritten filings). Written to a "
                         "separate deck that needs human review before use.")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "crops").mkdir(parents=True, exist_ok=True)
    take_all = tuple(c for c in args.take_all.split(",") if c)
    counties = tuple(c for c in args.counties.split(",") if c) or None

    items = sample(args.archive, args.n, take_all, counties, args.seed)
    for k, it in enumerate(items, 1):
        it["card_id"] = f"C{k:04d}"
        it["want_unreadable"] = args.include_unreadable
    print(f"sampled {len(items)}: {dict(Counter(i['county'] for i in items))}",
          file=sys.stderr)

    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(build_card, it, str(out)): it for it in items}
        for k, f in enumerate(as_completed(futs), 1):
            try:
                rows.append(f.result())
            except Exception as e:                            # noqa: BLE001
                rows.append(dict(futs[f], status=f"worker:{type(e).__name__}"))
            if k % 50 == 0:
                print(f"  {k}/{len(items)}", file=sys.stderr)

    rows.sort(key=lambda r: r.get("card_id", ""))
    keys = ["card_id", "county", "year", "case_number", "doc_variant", "doc_path",
            "status", "address_guess", "display", "street", "unit", "city",
            "state", "zip", "anchor", "page", "flags", "text_source", "ocr_conf",
            "crop", "redacted"]
    with open(out / "cards.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.chmod(out / "cards.csv", 0o600)

    ok = [r for r in rows if r["status"] == "ok"]
    deck = [{"id": r["card_id"], "img": r["crop"], "guess": r["display"]} for r in ok]

    rng = random.Random(args.seed + 1)
    gold = []
    for r in rng.sample(ok, min(max(1, int(len(ok) * args.probes)), len(ok))):
        bad, kind = corrupt(r["display"], rng)
        if not bad:
            continue
        pid = "P" + r["card_id"][1:]
        deck.append({"id": pid, "img": r["crop"], "guess": bad})
        gold.append({"probe_id": pid, "source_card": r["card_id"],
                     "true_label": "no", "corruption": kind})
    rng.shuffle(deck)

    (out / "deck.json").write_text(json.dumps(deck, indent=1))
    os.chmod(out / "deck.json", 0o600)

    # Transcription cards go in their own file, never merged into deck.json.
    # Their crops are cut from a printed "TO:" label with no OCR output beneath
    # it, so whether the defendant's name is inside the box is unknown. A
    # person has to look before these are shown to anyone.
    tr = [r for r in rows if r["status"] == "transcribe_review"]
    if tr:
        (out / "deck_transcribe_REVIEW.json").write_text(json.dumps(
            [{"id": r["card_id"], "img": r["crop"], "mode": "transcribe"}
             for r in tr], indent=1))
        os.chmod(out / "deck_transcribe_REVIEW.json", 0o600)
    with open(out / "gold.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["probe_id", "source_card", "true_label",
                                          "corruption"])
        w.writeheader()
        w.writerows(gold)
    os.chmod(out / "gold.csv", 0o600)

    st = Counter(r["status"] for r in rows)
    print(f"\nstatus     : {dict(st)}", file=sys.stderr)
    print(f"cards      : {len(ok)}", file=sys.stderr)
    print(f"withheld   : {sum(v for k, v in st.items() if k.startswith('withheld'))}"
          "  (no name could be covered, so the card is not shown)", file=sys.stderr)
    print(f"probes     : {len(gold)}", file=sys.stderr)
    print(f"deck       : {out / 'deck.json'} ({len(deck)} cards)", file=sys.stderr)
    print(f"\nServe it:  cp game/index.html {out}/ && cd {out} && "
          "python3 -m http.server 8000", file=sys.stderr)


if __name__ == "__main__":
    main()
