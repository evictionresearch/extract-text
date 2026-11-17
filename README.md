# extract-text

extract-text reads eviction court documents (e-filed PDFs, scanned PDFs, and TIFF images) and returns a table with one row per document: the plaintiffs, the defendants, the address where the defendants were served, the plaintiff's attorney, and the case number. It runs on your own computer, and your documents never leave it. The [Eviction Research Network](https://evictionresearch.net) built it for housing research and policy work. Thomas, Ramiller, Ren, and Toomet (2024) were the first to use this method on eviction case records, in "[Toward a National Eviction Data Collection Strategy Using Natural Language Processing](https://www.huduser.gov/portal/periodicals/cityscape/vol26num1/article12.html)," *Cityscape* 26(1). This package takes what that paper did and makes it available to the public.

**Status (version 0.4.2, under development).** The rules engine is the released tool, and every instruction here uses it. The local AI engine runs as an option, but its test against hand-labeled documents is not finished, so treat it as experimental. Accuracy has been measured only on Washington documents. Command options and output columns can still change between releases, so pin the version you build on. [`CHANGELOG.md`](CHANGELOG.md) lists every release.

## How it works

extract-text has two engines.

- **The rules engine** reads a document with written rules and the layout of the page. It uses no AI and no internet connection, and the same document always gives the same answer. It exists largely because some agencies do not allow AI on their computers, and they can run it alone. The code and the manual call it the deterministic engine.
- **The local AI engine (experimental)** is a language model that runs on your own computer and reads the page as an image. It can read what rules cannot, handwriting above all, and it sends nothing to any cloud service. It needs its own setup (manual, [section 6](docs/manual.md#6-setting-up-the-ai-engine-optional)). When both engines run, the package compares the two addresses on every document and flags each disagreement for a person to check.

A person checks the engine's work before anyone trusts it. You grade a random 50 of your own documents on a review page in your browser, and the score says how often each field was right. The rules were written and measured on Washington filings, and another court's forms can make them misread a field without raising a flag. On a random 50 King County summonses from 2017, the rules engine read the street right on about 85 percent and the plaintiff on about 40 percent (October 2026).

## Get started

The [Get started page](https://evictionresearch.net/extract-text/get-started.html) walks through the install and a first run in eight steps, in R, on Mac, Windows, or Linux.

1. **Install three free programs:** poppler, tesseract, and Python.
2. **Install extract-text** and run its checkup.
3. **Read one made-up summons** to see what the engine returns.
4. **Scan a random 50** of your own documents.
5. **Grade those 50** on a review page in your browser, then read the score.
6. **Teach the engine your court's forms** from the boxes you fixed while grading (optional, no code).
7. **Scan the whole folder** and grade a second random 50.
8. **Build the final table**, with your graded answers in place of the engine's.

The same eight steps, with the same numbers, are in [`getting_started_example_script.R`](getting_started_example_script.R), to open in RStudio and run a block at a time, and in [`docs/start_here.md`](docs/start_here.md), in plain words with the terminal command for each.

You can practice steps 4 to 8 on the package's made-up documents before you open a court record, and step 4 says what to expect from documents outside Washington.

## Where to read what

| You want to | Read |
|---|---|
| Install it and run it, step by step | [Get started](https://evictionresearch.net/extract-text/get-started.html), or [`getting_started_example_script.R`](getting_started_example_script.R) |
| See the whole procedure on one page, or use a terminal | [`docs/start_here.md`](docs/start_here.md) |
| Know what belongs in each field when you grade | [`GRADING.md`](GRADING.md) |
| Get the programs approved or installed on a computer your organization manages | [`docs/it_checklist.md`](docs/it_checklist.md) |
| Fix and draw the boxes on the review page | [`docs/grading_with_boxes.md`](docs/grading_with_boxes.md) |
| Learn how the engines read a page, and what was measured | [How it works](https://evictionresearch.net/extract-text/how-it-works.html), and manual sections [12](docs/manual.md#12-how-it-works-under-the-hood) and [13](docs/manual.md#13-accuracy-measured-honestly) |
| Look up an output column, a flag, or an error message | Manual sections [10](docs/manual.md#10-the-output-column-by-column), [11](docs/manual.md#11-flags-and-the-review-workflow), and [18](docs/manual.md#18-troubleshooting) |
| Use it on documents from another state | Manual [section 16](docs/manual.md#16-using-this-outside-washington), and ["Documents from another state"](docs/changing_rules.md#documents-from-another-state) |
| Make the engine read your documents better | [Improve it](https://evictionresearch.net/extract-text/improve.html), and [`docs/changing_rules.md`](docs/changing_rules.md) |
| Set up the experimental AI engine | Manual [section 6](docs/manual.md#6-setting-up-the-ai-engine-optional) |
| Run a grading round with several graders | Manual [section 11](docs/manual.md#11-flags-and-the-review-workflow), and [`docs/grading_round.md`](docs/grading_round.md) for the graders |
| Follow what changed, and why | [`CHANGELOG.md`](CHANGELOG.md) and [`MAINTENANCE.md`](MAINTENANCE.md) |

## Privacy

With the default engines, documents, page images, and extracted values never leave your computer. The package sends no usage data, and once installed it runs with the network unplugged. This repository holds no personal information. Every example and test document is synthetic (`CONTRIBUTING.md`), and `python/scripts/pii_sweep.py` checks the working tree and the full git history for real names and addresses.

## In this repository

```
getting_started_example_script.R   The eight steps, in R
docs/            Start here, the manual, and the guides to rules, templates, and grading
GRADING.md       What belongs in each field when you grade
python/          The engine, the command line, tests, and synthetic fixtures
r/               The R package (full interface via reticulate)
site/            The website, evictionresearch.net/extract-text
schema/          Shared field contract (JSON Schema), generated from the Python models
reports/         Grading-round reports (counts and masked shapes only)
game/            Address Check, an earlier card game for checking addresses (not in current use)
MAINTENANCE.md   The improvement schedule: model reviews, benchmarks, release checklist
```

Address Check produced the package's first human ratings, in August 2026, and borrows two ideas from braindr (Keshavan, Yeatman, and Rokem 2019). [`game/README.md`](game/README.md) describes it and gives the citation.

## Where the method comes from

The method is peer reviewed, in the *Cityscape* paper cited at the top of this page. This package is the successor to that paper's pipeline, rebuilt around word-coordinate zoning, which structurally removes the line-number-rail errors the paper documents.

This package improves on a schedule rather than by accident: a monthly automated review issue tracks whether a better local model exists, and `MAINTENANCE.md` holds the procedure and the decision log.

## License and data

Code is AGPL-3.0-or-later (`LICENSE`). Commercial use is permitted; building a closed-source product or hosted service on this code is not. The license reaches the software, not the records you extract with it, so the terms that matter for data are separate: `DATA-USE.md` governs datasets this project supplies, and `ETHICS.md` states the uses this project will not support, tenant screening and blacklists first among them.

## Authors

Cheng Ren (University at Albany, SUNY), Tim Thomas (Eviction Research Network, UC Berkeley), Aaron Culich (UC Berkeley).

Citation metadata is in `CITATION.cff`. Contributions are welcome; read `CONTRIBUTING.md` first, especially its one rule with no exceptions: no real court records anywhere in this repository.
