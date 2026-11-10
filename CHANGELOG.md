# Changelog

Every user-facing change to extract-text is recorded here, newest first. A change goes under "Unreleased" when it is made, and moves under a version number when that version is released. The evidence behind each change (measurements, before-and-after counts, decisions) is in `MAINTENANCE.md`. Versions below 1.0 make no promise of a stable interface, so pin the version you build on (see "Installing a specific version" below).

## Unreleased

Nothing yet.

## 0.4.0 (2026-11-09)

- The plaintiff's caption description is dropped when the state's name is capitalized (", a Washington limited liability company") and when no comma precedes it ("INC a Washington corporation"); before, the name kept the description.
- The review page turns pages. A document's other pages are rendered on first request when the page is served, and `--pages N` renders more when building the graders' page. The engine's boxes appear on the page each value came from, and a reviewer can move any box, reshape it at the corners, or delete it, the engine's own included, draw a box on any page, and add another for the same field. Boxes are saved with their page (`{"page": N, "box": [...]}`), and answers saved before this read as page-1 boxes.
- A saved answer applies only to the document it was given for. A folder scanned again with a different draw puts other documents at the same row numbers; the earlier answers stay in `corrections.jsonl` but are no longer shown, scored, or learned from, and the scan, the review page, and `scan_documents()` say how many.
- Form templates. The engine can learn where a printed form puts each field, on any page, from the boxes drawn and confirmed while grading, with no change to the code. The rules still do the reading inside each region. `learn_templates()`, `review_templates()`, `approve_template()`, and `list_templates()` in R, `extract-text templates` at a terminal, and a `templates` argument to `scan_documents()`, `extract-text scan`, and `rules_eval.py`. A template is one readable JSON file per form holding the form's printed words with positions and regions per field, no names or addresses. Nothing learned is used until a person approves it. Matched documents show the form in a new `template` column and `template:<name>` in `defendant_anchor`. The guide is "Teaching the engine a form, without code" in `docs/changing_rules.md`.

## 0.3.0 (2026-11-09)

The first tagged release. It collects everything built since the package began on 2026-08-18.

### Deterministic engine

- Reads e-filed PDFs, scanned PDFs (through tesseract OCR), and TIFF images, and returns one row per document: case number, plaintiffs, defendants, the defendants' service address, the plaintiff's attorney, and other case details. Every value records the rule and the region of the page it came from, and a document that fails a check is flagged rather than guessed.
- Finds the defendants' address by four rules tried in order: the TO: service block, "premises located at", a street line over a city line, and the case caption.
- Rule passes measured against hand-labeled Washington filings on 2026-08-20, 2026-09-30, 2026-10-29 (debris in defendant names, split ordinals such as "12 th"), and 2026-11-03 (plaintiff names that wrap across lines, "ATTORNEY AT LAW" read as a title rather than a firm, street repairs), and 2026-11-09 ("unknown occupants" dropped from defendant names, as "all other occupants" already was).
- Standardized address columns in USPS Publication 28 form: `defendant_house_number`, `defendant_street_std`, `defendant_unit_std`, `defendant_address_std`.
- An address check against a list of real addresses: `check_addresses()` in R, `extract-text check-addresses` at a terminal, with a preset for King County's public address points.
- The field contract, `schema/court_record.schema.json`, includes each value's box on the page.
- A first slice of case context from a whole case file: `extract-text cases` reads document types from file names, case stages, and the sheriff's return.

### AI engine

- A vision language model (qwen3.5:9b by default) running on your own computer through Ollama; nothing is sent to any cloud service.
- The graders'-format prompt is the default since 2026-10-21; the original stays available as `--prompt v1`.
- Run both engines and the package compares their addresses on every document and flags each disagreement.

### Checking the engines

- A review page shows each document's first page beside what the engine read, with boxes drawn where each value was found; a reviewer can correct any field and redraw a wrong box, and every save is written to `corrections.jsonl` on the reviewer's own computer.
- Grading rounds: `extract-text review --graders` builds a page for several graders, `extract-text agree` measures how often they agree, and `extract-text score` measures how often each engine is right. Graders can work without a terminal, opening the page as a file and downloading their answers for `extract-text import`.
- `python/scripts/rules_eval.py` measures a rule change: what it fixed and what it broke, field by field, on graded documents.
- Address Check (`game/`), a card game for phones that produces human-verified address labels.

### R package

- Install from GitHub with `remotes::install_github()` and `extracttext_install()`; `extracttext_doctor()` checks the setup and names anything missing.
- `scan_documents()` shows a progress bar, and takes `sample`, `seed`, and `exclude` to scan a random draw of a folder that leaves out documents already scanned.
- `review_documents()` and `score_documents()` check and score a scan from R, and `case_table()` builds the final table: one row per document, with graded answers in place of the engine's readings wherever a person gave one.

### Documentation

- The README lists what to install first (poppler and tesseract, on Mac and Windows) and why every run needs a graded random sample.
- `getting_started_example_script.R` takes an R user from a test document through a sample, two rounds of grading, a full run, and the final table.
- `docs/manual.md` is the complete guide; `docs/changing_rules.md` shows how to change a rule on your own copy, measure it, and keep it through updates; `GRADING.md` is the graders' guide.

### Privacy

- The repository holds no real court records: every example and test document is synthetic, and `python/scripts/pii_sweep.py` checks the working tree and the full git history. The history was rewritten before the repository went public on 2026-10-20.

### Known limits

- Accuracy has been measured only on Washington filings, and King County's only through 2017.
- The head-to-head test of the AI engine against the labeled sets is not finished.

## Installing a specific version

In R, give the version tag to both install steps, so the R package and the engine match:

```r
remotes::install_github("evictionresearch/extract-text@v0.4.0", subdir = "r")
extracttext::extracttext_install(ref = "v0.4.0")
```

In Python:

```bash
pip install "extract-text @ git+https://github.com/evictionresearch/extract-text@v0.4.0#subdirectory=python"
```
