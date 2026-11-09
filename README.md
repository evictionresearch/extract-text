# extract-text

extract-text is a court document reader (e-filed PDFs, scanned PDFs, and TIFF images) trained on eviction court records. It returns a table with one row per document. Each row holds the names of the plaintiffs and defendants, the address where the defendants were served, the plaintiff's attorney, the case number, and other details of the case. The [Eviction Research Network](https://evictionresearch.net) built it for housing research and policy work and validated it on more than a million pages of Washington State filings. It was designed to work on any court documents that follow American conventions.

**Status.** extract-text is under development; [`CHANGELOG.md`](CHANGELOG.md) lists every release and what changed. ERN is checking both engines against hand-labeled Washington filings, and command options, output fields, and the default AI model can still change between releases. Accuracy has been measured only on Washington documents, and the head-to-head test of the AI engine against the labeled sets is not finished. Versions below 1.0 promise no stable interface, so pin the version you build on.

The package has two engines that read documents, and you choose one or both on each run.

- **Deterministic.** Written rules and the layout of the page, with no AI of any kind and no network connection. The same document always gives the same output, and every value records the rule and the region of the page it came from. It needs nothing from the AI engine, so agencies whose policies do not permit AI tools can use it alone.
- **AI.** A language model that reads page images (qwen3.5 9B), running on your own computer through Ollama. It reads what rules and OCR cannot, handwriting above all, and it sends nothing to any cloud service.

When you run both, the package compares the two addresses on every document, using the similarity measure from the validation work, and flags each disagreement for a person to review. Either engine also flags a value it is unsure of instead of guessing.

A third part, **Address Check** (`game/`), is a card game for phones that measures how often the engines are right. Each card shows an address as printed on a filing beside the address an engine read, and the player says whether they match, in about ten seconds a card. The answers become labeled data, broken down by county, year, the rule that found the address, and whether the text came from the PDF or from OCR, so a weakness in one county shows up instead of being averaged away. It is the only part of the package that produces ground truth.

**Privacy.** With the default engines, documents, page images, and extracted values never leave your computer. The package sends no usage data, and once installed it runs with the network unplugged. This repository holds no personal information. Every example and test document is synthetic (`CONTRIBUTING.md`), and `python/scripts/pii_sweep.py` checks the working tree and the full git history for real names and addresses.

## Quick start

**First, on Mac and Windows alike, install poppler and tesseract.** extract-text cannot read a document without these two free programs: poppler opens PDFs, and tesseract reads scanned pages (OCR). Neither R nor pip installs them.

Before you install:

- **Check whether you already have them.** Run `which pdftoppm tesseract` in Terminal on a Mac or Linux, or `where.exe pdftoppm tesseract` in PowerShell on Windows. If both print a path, skip the commands below. On a Mac, `brew install` on a program you already have upgrades it and every Homebrew program that depends on it, which can mean gigabytes of downloads.
- **English is the only language data extract-text uses.** Homebrew's tesseract includes English, so you do not need the `tesseract-lang` package it mentions.
- **You need Python 3.10 or newer** on the computer (from [python.org](https://www.python.org/downloads/) if you have none), for R as well as Python, because the engine is written in Python.
- **You need the internet only to install.** After that, extract-text runs with the network unplugged.
- **The rules engine needs no AI setup.** `doctor` will report Ollama as missing, and that is fine. The AI engine is optional and needs about 16 GB of memory (manual section 3).
- **On a work computer, installs may need IT.** If your computer blocks them, ask IT for poppler, tesseract, and Python.

On a Mac, install [Homebrew](https://brew.sh) if you don't have it, then run in Terminal:

```bash
brew install poppler tesseract
```

On Windows, run in PowerShell:

```powershell
winget install oschwartz10612.Poppler
winget install UB-Mannheim.TesseractOCR
```

winget puts poppler on your PATH, but the tesseract installer does not. Add its folder (by default `C:\Program Files\Tesseract-OCR`) through Start, "Edit environment variables for your account", Path, Edit, New, and then restart R, RStudio, or the terminal. On Debian or Ubuntu, run `sudo apt install poppler-utils tesseract-ocr`. The `doctor` check below confirms that both were found.

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

[`getting_started_example_script.R`](getting_started_example_script.R) takes these steps one at a time with the rules engine: a made-up summons; a random 50 of your own documents, which you grade by hand and score; the whole folder; a second random 50 graded from it; and a final table with one row per document (`case_table()`), your graded answers in place of the engine's wherever you gave one.

Command line, no programming:

```bash
extract-text scan documents/ --engine deterministic --out results/ --review
```

Batch runs write `extracted.csv` (and `.parquet` when available), `extracted.jsonl` as the full audit trail, and a `review/index.html` page showing each flagged document's image beside what was extracted from it.

**Grade a random 50 before you trust a run.** The rules were written and measured on Washington filings, and another court's forms, scan quality, or decade can make them misread a field without raising a flag. Accuracy also differs by field: on a random 50 King County summonses from 2017, the rules engine read the street right on about 85 percent and the plaintiff on about 40 percent (October 2026). So scan a random 50 of your documents first, grade them on the review page (`review_documents(res, correct = TRUE, n = 50, draw = "random")` in R), score the engine against your corrections (`score_documents(res)`), and scan the whole folder only when the fields you need are accurate enough. The getting-started script takes these steps in order. Fifty random documents put the share right within about 10 points; check 100 or more before publishing counts or sending anything to people. Your corrections do not change the engine. They tell you which fields to trust, and every graded document carries your answer in the final table; fixes to the rules themselves reach you through package updates. Manual section 11 has the full protocol.

The manual, [`docs/manual.md`](docs/manual.md), is written for someone who uses R or Python and knows nothing about OCR or AI. It covers installation on every platform, each output column, the flags and how to review them, how the engines work, measured accuracy and its limits, and how to adapt the rules to another state. [`docs/changing_rules.md`](docs/changing_rules.md) shows how to change a rule on your own copy, measure the change against your graded documents, and keep it through package updates. Its last chapter shows the way that needs no code: a form template, learned from the boxes drawn while grading, that tells the engine where your court's form prints each field. A template changes where the engine looks, not how it reads; when the rules themselves need to change, work with the Eviction Research Network or follow the guide on your own copy.

To grade the engines, people correct a folder of results on a review page served from their own computer. `extract-text review --graders` builds the page, `extract-text agree` reports how often graders agree, and `extract-text score` reports how often each engine is right. The organizer's guide is "Running a grading round" in section 11 of the manual, and the graders' guide is [`GRADING.md`](GRADING.md). The answers hold names and addresses, so they stay in the project's protected storage, and only the masked reports in `reports/` are kept in this repository.

## What to expect

The deterministic engine found an address on 83.5 to 100 percent of documents, depending on corpus and era, in the July 2026 validation runs against 5,100+ hand-labeled Washington addresses. Its addresses had a mean similarity to the hand labels of 0.87 to 0.92, and roughly 1.5 percent were wrong, the worst of them flagged in advance. The published 2024 pipeline scored 0.82 on the same truth data. An August 2026 improvement pass, measured on the full 5,168-case truth set, raised address yield to 92.4 and 95.6 percent on the two large King County sets with mean similarity 0.91 to 0.93; `MAINTENANCE.md` holds the change-by-change evidence. The AI lane returned structured fields for all 300 pages of its bench corpus at about 17 seconds a page on a 16 GB laptop. Section 13 of the manual ([Accuracy](docs/manual.md#13-accuracy-measured-honestly)) gives the details, where each number came from, and its limits. The numbers describe Washington documents, and a new jurisdiction should be scored on its own documents.

## Layout

```
schema/          Shared field contract (JSON Schema), generated from the Python models
python/          The engine, the CLI, tests, and synthetic fixtures
r/               The R package (full interface via reticulate)
game/            Address Check, for building a human-verified training set
docs/            The manual
reports/         Grading-round reports (counts and masked shapes only)
GRADING.md       Instructions for graders
MAINTENANCE.md   The improvement schedule: model reviews, benchmarks, release checklist
```

## Address Check: the human validation game

Every accuracy number in this package that is worth anything came from a person looking at a page. `game/` is the tool that makes that cheap enough to do at volume.

A card shows a cropped picture of the address as printed on the filing and the address an engine read. The rater swipes: same, or not the same. Marking one wrong opens an optional box to type what the picture actually says, and a correction is worth more than a rejection because it says what the right answer was. About ten seconds a card on a phone.

```bash
python3 game/make_demo_deck.py          # synthetic, no real data
cd game/demo && python3 -m http.server 8000
```

Then on a real corpus:

```bash
python3 python/scripts/build_card_deck.py --archive ARCHIVE --out DECK --n 700
```

**What comes out.** `score_ratings.py` weights each rater by their accuracy on hidden cards whose answer is already known, drops anyone at chance, and writes one row per card with a verdict, a confidence and the typed correction. It also breaks accuracy down **by county, state, year, anchor and text source**, which is the point: a rule that holds in one county can fail in the next, and averaging hides it. The first round of real ratings showed a 19-point gap between two Washington counties.

**Names are never shown.** They are painted over before the crop is taken, and a card is withheld entirely unless a name was actually covered. Full reasoning in `game/README.md`.

The design follows **braindr** by Anisha Keshavan, Jason D. Yeatman, and Ariel Rokem, *Combining Citizen Science and Deep Learning to Amplify Expertise in Neuroimaging*, Frontiers in Neuroinformatics 13:29 (2019), <https://doi.org/10.3389/fninf.2019.00029>. Two ideas are taken directly: the one-tap judgement on a single image, and weighting raters against known-answer items rather than counting every vote equally.

The method is peer reviewed: Thomas, Ramiller, Ren, and Toomet (2024), "Toward a National Eviction Data Collection Strategy Using Natural Language Processing," *Cityscape* 26(1) ([HUD USER](https://www.huduser.gov/portal/periodicals/cityscape/vol26num1/article12.html)). This package is the successor to that paper's pipeline, rebuilt around word-coordinate zoning, which structurally removes the line-number-rail errors the paper documents.

This package improves on a schedule rather than by accident: a monthly automated review issue tracks whether a better local model exists, and `MAINTENANCE.md` holds the procedure and the decision log.

## License and data

Code is AGPL-3.0-or-later (`LICENSE`). Commercial use is permitted; building a closed-source product or hosted service on this code is not. The license reaches the software, not the records you extract with it, so the terms that matter for data are separate: `DATA-USE.md` governs datasets this project supplies, and `ETHICS.md` states the uses this project will not support, tenant screening and blacklists first among them.

## Authors

Cheng Ren (University at Albany, SUNY), Tim Thomas (Eviction Research Network, UC Berkeley), Aaron Culich (UC Berkeley).

Citation metadata is in `CITATION.cff`. Contributions are welcome; read `CONTRIBUTING.md` first, especially its one rule with no exceptions: no real court records anywhere in this repository.
