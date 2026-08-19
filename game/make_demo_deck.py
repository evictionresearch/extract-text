#!/usr/bin/env python3
"""Generate a runnable demo deck from the synthetic fixtures.

The repo carries no card images. This builds a small deck from the invented
documents in `python/tests/fixtures/`, using exactly the same code path as a
real deck, so the game can be opened and played without touching a court
record and without adding binary files to git.

    python3 game/make_demo_deck.py
    cd game/demo && python3 -m http.server 8000

Real decks come from `python/scripts/build_card_deck.py`, which points at an
archive of real filings and writes outside the repo.
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))

FIXTURES = ROOT / "python" / "tests" / "fixtures"
OUT = Path(__file__).resolve().parent / "demo"

# Variants shown alongside the true extraction, so a first-time player sees
# both answers before rating anything real. Each wrong one fails the way this
# engine actually fails; see MAINTENANCE.md, "Known gaps in the address
# vocabulary".
VARIANTS = [
    ("correct", None),
    ("unit_dropped", lambda s: s.replace(" APT 5", "")),
    ("direction_wrong", lambda s: s.replace(" AVE S ", " AVE SE ")),
    ("digit_wrong", lambda s: s.replace("1234", "1243", 1)),
]


def main():
    from extract_text import documents
    from extract_text.cards import display_address, locate_address, name_tokens, render_card
    from extract_text.deterministic import extract_from_document

    src = FIXTURES / "synthetic_summons_efiled.pdf"
    if not src.exists():
        sys.exit(f"missing fixture: {src}\n"
                 "Run python/scripts/make_synthetic_fixtures.py first.")

    doc = documents.load_document(src)
    x = extract_from_document(doc, expected_case_number="25-2-00001-0")
    addr = x.record.defendant_address
    if addr is None or not addr.raw:
        sys.exit("the fixture produced no address; regenerate the fixtures")

    ev = x.evidence.get("defendant_address")
    page = getattr(ev, "page", None) or 1
    box = locate_address(doc, addr.raw, addr.street or "", page)
    if box is None:
        sys.exit("could not locate the address on the fixture page")

    crops = OUT / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    redact = name_tokens(x.record, addr.raw)
    png = render_card(src, page, box, crops / "demo.png",
                      words=doc.words, redact=redact)
    if png is None:
        sys.exit("render_card produced nothing")

    true_text = display_address(addr.street, addr.unit, addr.city,
                               addr.state, addr.zip)
    deck = []
    for i, (name, fn) in enumerate(VARIANTS, 1):
        guess = true_text if fn is None else fn(true_text)
        if fn is not None and guess == true_text:
            continue                      # variant did not apply to this text
        deck.append({"id": f"DEMO{i}", "img": "crops/demo.png", "guess": guess})

    (OUT / "deck.json").write_text(json.dumps(deck, indent=1))
    shutil.copy(Path(__file__).resolve().parent / "index.html", OUT / "index.html")

    print(f"demo deck: {OUT}")
    print(f"  true reading : {true_text}")
    print(f"  {len(deck)} cards, all synthetic ({len(VARIANTS) - 1} deliberately wrong)")
    print(f"  names covered: {sorted(redact) or '(none parsed)'}")
    print(f"\n  serve it:  cd {OUT} && python3 -m http.server 8000")


if __name__ == "__main__":
    main()
