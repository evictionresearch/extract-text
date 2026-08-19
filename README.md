# extract-text

Court records in, a case table out. This package reads eviction court
documents (e-filed PDFs, scanned PDFs, TIFFs) and extracts the fields housing
research and housing policy run on: party names on both sides, the defendant
household's service address, the plaintiff attorney block, case numbers, and
case-level details. It was built by the [Eviction Research
Network](https://evictionresearch.net), validated on more than a million
pages of Washington State filings, and designed to work anywhere court
documents follow American conventions.

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
docs/            The manual
MAINTENANCE.md   The improvement schedule: model reviews, benchmarks, release checklist
```

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
