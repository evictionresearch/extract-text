# extract-text

Court records in, a case table out. This package reads eviction court
documents (e-filed PDFs, scanned PDFs, TIFFs) and extracts the fields housing
research and housing policy run on: party names on both sides, the defendant
household's service address, the plaintiff attorney block, case numbers, and
case-level details. It was built by the [Eviction Research
Network](https://evictionresearch.net), validated on more than a million
pages of Washington State filings, and designed to work anywhere court
documents follow American conventions.

There are **three** parts: two engines that read documents, and a card game
that lets people check the reading. The engines are only as good as what has
been measured about them, and the game is how that measurement happens.

Two independent engines do the reading, and you choose per run.

- **Deterministic.** Written rules plus page geometry. No AI of any kind, no
  network, same input always gives the same output, and every value records
  the exact rule and page region it came from. This is the engine for
  agencies whose policies do not permit AI tools, and it stands entirely on
  its own.
- **AI.** A vision-capable language model (qwen3.5 9B) running on your own
  machine through Ollama. It reads what rules and OCR cannot, handwriting
  above all. Nothing is sent to any cloud service.

Run both and the package compares them on every document, measuring address
agreement with the same similarity metric the validation work uses and
flagging every disagreement for human review. Anything either engine is
unsure about is flagged, never guessed.

And the third part:

- **Address Check** (`game/`). A phone-friendly card game that shows a picture
  of an address as printed on a filing next to the address an engine read, and
  asks a person whether they say the same thing. Answers become a labeled
  training set, broken down by county, year, anchor and text source, so a
  weakness local to one jurisdiction shows up instead of being averaged away.
  It is the only part of the package that produces ground truth, and it costs
  a rater about ten seconds a card.

**Privacy is the design constraint, not a feature.** With the default
engines, documents, page images, and extracted values never leave your
computer. There is no telemetry and nothing phones home; after installation
it runs with the network unplugged. This repository contains no personally
identifying information: every example and test document is synthetic, that
rule has no exceptions (`CONTRIBUTING.md`), and `python/scripts/pii_sweep.py`
verifies it against the working tree and the full git history.

## Quick start

Python:

```bash
pip install "extract-text @ git+https://github.com/evictionresearch/extract-text#subdirectory=python"
extract-text doctor        # checks your setup, says how to fix anything missing
```

```python
from extract_text import extract, scan

result = extract("summons.pdf")                     # rules only, no AI
result.record.defendant_address.street
result.flags                                        # empty means all checks passed

rows = scan("documents/", engine="both",            # whole folder, both engines,
            out_dir="results/")                     # disagreements flagged
```

R:

```r
remotes::install_github("evictionresearch/extract-text", subdir = "r")
library(extracttext)
extracttext_install()      # one time; then restart R
extracttext_doctor()

result <- extract_deterministic("summons.pdf")
result$record$defendant_address$street

results <- scan_documents("documents/", engine = "both",
                          out_dir = "results/", review = TRUE)
```

Command line, no programming:

```bash
extract-text scan documents/ --engine deterministic --out results/ --review
```

Batch runs write `extracted.csv` (and `.parquet` when available),
`extracted.jsonl` as the full audit trail, and a `review/index.html` page
showing each flagged document's image beside what was extracted from it.

**The manual.** [`docs/manual.md`](docs/manual.md) is the complete guide,
written for an everyday R or Python user with no OCR or AI background
assumed: installation on every platform, a column-by-column output
reference, the flag table and review workflow, how the engines work in plain
language, measured accuracy with its caveats, and adaptation to other
states.

## What to expect

On the July 2026 validation runs against 5,100+ hand-labeled Washington
addresses, the deterministic engine found an address on 83.5 to 100 percent
of documents depending on corpus and era, with mean similarity to the hand
labels of 0.87 to 0.92 and roughly 1.5 percent of extractions genuinely
wrong, the worst of them pre-flagged. The published 2024 pipeline scored
0.82 on the same truth data. The AI lane returned structured fields for all
300 pages of its bench corpus at about 17 seconds a page on a 16 GB laptop.
Details, provenance, and honest caveats are in the manual
([section 13](docs/manual.md#13-accuracy-measured-honestly)); the numbers
describe Washington documents, and a new jurisdiction deserves its own
scoring.

## Layout

```
schema/          Shared field contract (JSON Schema), generated from the Python models
python/          The engine, the CLI, tests, and synthetic fixtures
r/               The R package (full interface via reticulate)
game/            Address Check, for building a human-verified training set
docs/            The manual
MAINTENANCE.md   The improvement schedule: model reviews, benchmarks, release checklist
```

## Address Check: the human validation game

Every accuracy number in this package that is worth anything came from a
person looking at a page. `game/` is the tool that makes that cheap enough to
do at volume.

A card shows a cropped picture of the address as printed on the filing and the
address an engine read. The rater swipes: same, or not the same. Marking one
wrong opens an optional box to type what the picture actually says, and a
correction is worth more than a rejection because it says what the right
answer was. About ten seconds a card on a phone.

```bash
python3 game/make_demo_deck.py          # synthetic, no real data
cd game/demo && python3 -m http.server 8000
```

Then on a real corpus:

```bash
python3 python/scripts/build_card_deck.py --archive ARCHIVE --out DECK --n 700
```

**What comes out.** `score_ratings.py` weights each rater by their accuracy on
hidden cards whose answer is already known, drops anyone at chance, and writes
one row per card with a verdict, a confidence and the typed correction. It
also breaks accuracy down **by county, state, year, anchor and text source**,
which is the point: a rule that holds in one county can fail in the next, and
averaging hides it. The first round of real ratings showed a 19-point gap
between two Washington counties.

**Names are never shown.** They are painted over before the crop is taken, and
a card is withheld entirely unless a name was actually covered. Full reasoning
in `game/README.md`.

The design follows **braindr** by Anisha Keshavan, Jason D. Yeatman, and Ariel
Rokem, *Combining Citizen Science and Deep Learning to Amplify Expertise in
Neuroimaging*, Frontiers in Neuroinformatics 13:29 (2019),
<https://doi.org/10.3389/fninf.2019.00029>. Two ideas are taken directly: the
one-tap judgement on a single image, and weighting raters against known-answer
items rather than counting every vote equally.

The method is peer reviewed: Thomas, Ramiller, Ren, and Toomet (2024),
"Toward a National Eviction Data Collection Strategy Using Natural Language
Processing," *Cityscape* 26(1)
([HUD USER](https://www.huduser.gov/portal/periodicals/cityscape/vol26num1/article12.html)).
This package is the successor to that paper's pipeline, rebuilt around
word-coordinate zoning, which structurally removes the line-number-rail
errors the paper documents.

This package improves on a schedule rather than by accident: a monthly
automated review issue tracks whether a better local model exists, and
`MAINTENANCE.md` holds the procedure and the decision log.

## License and data

Code is AGPL-3.0-or-later (`LICENSE`). Commercial use is permitted; building
a closed-source product or hosted service on this code is not. The license
reaches the software, not the records you extract with it, so the terms that
matter for data are separate: `DATA-USE.md` governs datasets this project
supplies, and `ETHICS.md` states the uses this project will not support,
tenant screening and blacklists first among them.

## Authors

Cheng Ren (University at Albany, SUNY), Tim Thomas (Eviction Research
Network, UC Berkeley), Aaron Culich (UC Berkeley).

Citation metadata is in `CITATION.cff`. Contributions are welcome; read
`CONTRIBUTING.md` first, especially its one rule with no exceptions: no real
court records anywhere in this repository.
