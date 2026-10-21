# The extract-text manual

This manual explains how to install and use extract-text, a free, open-source
tool that reads eviction court documents and turns them into a spreadsheet-style
table of names, addresses, and case details. It is written for someone
comfortable with either R or Python at an everyday level. It does not assume
you know anything about PDF internals, optical character recognition, or
artificial intelligence, and it explains each of those in plain terms at the
point where they matter.

Everything in this manual that shows example data uses invented documents. No
real case, person, or address appears anywhere in this project, and the
project's rules require it to stay that way.

## Contents

1. [What this tool does](#1-what-this-tool-does)
2. [The two engines, and which to use](#2-the-two-engines-and-which-to-use)
3. [What you need before installing](#3-what-you-need-before-installing)
4. [Installation for Python users](#4-installation-for-python-users)
5. [Installation for R users](#5-installation-for-r-users)
6. [Setting up the AI engine (optional)](#6-setting-up-the-ai-engine-optional)
7. [Checking your setup](#7-checking-your-setup)
8. [Your first document](#8-your-first-document)
9. [Processing a folder of documents](#9-processing-a-folder-of-documents)
10. [The output, column by column](#10-the-output-column-by-column)
11. [Flags and the review workflow](#11-flags-and-the-review-workflow)
12. [How it works under the hood](#12-how-it-works-under-the-hood)
13. [Accuracy, measured honestly](#13-accuracy-measured-honestly)
14. [Privacy and security](#14-privacy-and-security)
15. [Settings you may want to change](#15-settings-you-may-want-to-change)
16. [Using this outside Washington](#16-using-this-outside-washington)
17. [Speed and hardware](#17-speed-and-hardware)
18. [Troubleshooting](#18-troubleshooting)
19. [Glossary](#19-glossary)
20. [References and how to cite](#20-references-and-how-to-cite)
21. [Getting help](#21-getting-help)

---

## 1. What this tool does

Eviction case files arrive as images of paper. A county archive typically
holds a mix of three formats. Some documents are e-filed PDFs, where the text
is digitally embedded and can be selected with a cursor. Some are scans, where
the PDF is only a photograph of a page. Older archives often use TIFF image
files, another photograph format. None of the three is a spreadsheet, and the
information researchers and agencies need, who was filed against, where they
live, who filed, is buried inside page images at a scale no person can read
through.

extract-text reads those files and produces a table with one row per document.
The fields it is built to find, in order of how much they matter for housing
research, are

- the defendant's service address (the tenant household's address, which is
  what mapping and neighborhood analysis are built on)
- the names of the defendants and the plaintiff, as printed
- the plaintiff attorney's firm, address, phone, and bar number
- the case number, and general fields where documents carry them (court,
  county, case type, filing date, judgment amounts and dates)

Two independent engines can do the reading. One follows written rules and
never involves any artificial intelligence. The other uses an AI model that
runs entirely on your own computer. You choose one, the other, or both, every
time you run the tool. Anything either engine is unsure about is flagged for a
person to check rather than guessed at.

The tool was built by the Eviction Research Network and validated on more than
a million pages of Washington State court filings from four counties. The
method behind it is peer reviewed (see [section 20](#20-references-and-how-to-cite)).
It works anywhere court documents look broadly like American court documents,
with the honest caveats in [section 16](#16-using-this-outside-washington).

## 2. The two engines, and which to use

**The deterministic engine** reads the document with written rules. It looks
for the address in the places summonses put it, uses the geometry of the page
to tell the tenant's address apart from the attorney's, and records, for every
value it returns, exactly which rule found it and where on the page. It is
called deterministic because the same input always produces the same output,
which matters when results have to be reproducible, auditable, or defensible.
It involves no AI of any kind, no model files, and no network activity, so it
is the engine for agencies whose policies do not yet permit AI tools. Its
limitation is coverage. Rules read the documents they were written for, and a
document layout the rules have never seen, or handwriting, produces a flag
instead of an answer.

**The AI engine** shows a picture of the page to a language model running on
your own computer and asks it, with a carefully designed request, to return
the same fields. It reads layouts the rules were not written for and, notably,
handwriting, which no conventional text-recognition software handles well. Its
limitation is trust. A language model can produce a confident, fluent, wrong
answer, so this engine's output is verified where possible (see grounding, in
[section 12](#12-how-it-works-under-the-hood)) and is best used alongside the
deterministic engine rather than alone.

**Running both** is the recommended mode when you are allowed to use both. The
deterministic answer fills the main columns, the AI answer lands in columns
beside it, and every disagreement is measured and flagged. Agreement between
two independent methods is good evidence a value is right. Disagreement tells
you exactly which documents deserve a person's attention, and that is a far
smaller pile than all of them.

A plain decision guide, in one table.

| Your situation | Use |
|---|---|
| Policy does not permit AI tools | `deterministic` |
| You want maximum confidence and can use AI | `both` |
| Your documents include handwriting or unusual layouts | `both` (the AI columns cover what rules miss) |
| Quick exploration of a new corpus | `deterministic` first, look at flags, then decide |

The engines never blend silently. A value in a deterministic column always
came from rules; AI answers are always labeled as such.

## 3. What you need before installing

**A computer.** Any reasonably modern laptop or desktop on macOS, Linux, or
Windows. The deterministic engine is light. The AI engine needs about 16 GB of
memory to run comfortably.

**Three helper programs**, all free and open source, installed once from your
system's package manager.

- **poppler** opens PDF files. It provides the small programs extract-text
  uses to pull digital text out of e-filed PDFs and to turn scanned pages
  into images.
- **tesseract** performs optical character recognition, OCR for short. OCR is
  software that looks at a picture of a page and works out what characters
  are printed on it. It is what makes scanned documents readable at all, and
  it is only used when a document has no digital text of its own.
- **ollama** (optional, only for the AI engine) is a program that downloads
  and runs AI models on your own machine, the way a music app plays files it
  has downloaded. Nothing you process is sent anywhere; ollama is a local
  program listening only to your own computer.

**An internet connection during installation only.** Once the software and,
optionally, the AI model are downloaded, everything runs with the network
cable unplugged. That is a design requirement of this project, not an
accident, and [section 14](#14-privacy-and-security) spells it out.

Install commands for the helper programs, by operating system.

| | poppler | tesseract | ollama |
|---|---|---|---|
| macOS (Homebrew) | `brew install poppler` | `brew install tesseract` | `brew install ollama`, or the installer at ollama.com |
| Debian/Ubuntu | `sudo apt install poppler-utils` | `sudo apt install tesseract-ocr` | installer at ollama.com |
| Windows | poppler for Windows build, added to PATH | UB Mannheim tesseract installer, added to PATH | installer at ollama.com |

If any of that sounds unfamiliar, install what you can, then run the checkup
in [section 7](#7-checking-your-setup). It looks at your machine and prints
the exact command for anything missing.

## 4. Installation for Python users

You need Python 3.10 or newer. In a terminal,

```bash
pip install "extract-text @ git+https://github.com/evictionresearch/extract-text#subdirectory=python"
```

That installs the package and its two Python dependencies (pydantic, which
enforces the data structure, and Pillow, which reads TIFF files). Two optional
extras exist.

```bash
# adds .parquet output files alongside the CSV
pip install "extract-text[parquet] @ git+https://github.com/evictionresearch/extract-text#subdirectory=python"

# adds the cloud API backend. Read section 14 before considering this.
pip install "extract-text[anthropic] @ git+https://github.com/evictionresearch/extract-text#subdirectory=python"
```

If you cloned the repository, `pip install -e "python[parquet]"` from the
repository root does the same from your local copy.

Installing the Python package also installs the `extract-text` command for
your terminal, which can run everything with no Python code at all.

## 5. Installation for R users

You need R 4.1 or newer. The R package is a complete interface to the same
engine; R users are not second-class here, and every capability in this
manual has an R form.

```r
install.packages("remotes")
remotes::install_github("evictionresearch/extract-text", subdir = "r")

library(extracttext)
extracttext_install()   # one time: sets up the Python engine behind the scenes
```

`extracttext_install()` creates a private Python environment named
`r-extracttext` and installs the engine into it. You do not need to know
Python or manage it afterward; the reticulate package carries R calls across
to the engine automatically. Restart R after the install, then run
`extracttext_doctor()` to confirm everything is in place.

The helper programs in [section 3](#3-what-you-need-before-installing) are
still needed, because the engine calls them no matter which language you work
from.

## 6. Setting up the AI engine (optional)

Skip this section entirely if you will only use the deterministic engine.
Nothing else in the tool depends on it.

1. Install ollama (table in [section 3](#3-what-you-need-before-installing))
   and start it. On macOS and Windows it runs as an app; on Linux,
   `ollama serve` in a terminal.
2. Download the model, once:

   ```bash
   ollama pull qwen3.5:9b
   ```

   This is about a 7 GB download. After it completes, the model lives on your
   disk and no further downloads happen. If you already have `qwen3.5:latest`
   and it points at the same 9B model, this command adds the exact tag name
   without downloading anything again.

The model, qwen3.5 9B, is the one this project currently recommends and tests
against. In plain terms it is a vision-capable language model, a program that
can look at an image and answer questions about it, with roughly nine billion
internal parameters, which is small enough to run on an ordinary 16 GB
workstation and large enough to read court documents well. It is released
under the Apache 2.0 license, a permissive open-source license, which matters
to agencies that must account for every component they run. The project
re-evaluates this choice on a schedule (see `MAINTENANCE.md` in the
repository) and the default will move when something better runs on the same
class of hardware.

If you pulled a different tag of the same model family (for example
`ollama pull qwen3.5`, which gives `qwen3.5:latest`), extract-text will use it
and print a note saying so. The output always records exactly which model
produced it.

## 7. Checking your setup

One command examines your machine and reports what is ready, what is missing,
and the exact command that fixes each missing piece.

Terminal:

```bash
extract-text doctor
```

R:

```r
extracttext_doctor()
```

The report covers the helper programs, the Python engine, whether ollama is
running, and whether the model is pulled. It reads none of your documents and
touches no network beyond asking the ollama program on your own machine what
models it has. When the last line says the deterministic engine can run, you
are ready.

## 8. Your first document

The repository ships synthetic example documents in
`python/tests/fixtures/`, generated by a script and containing no real
information. `synthetic_summons_efiled.pdf` is a one-page Washington-style
summons for an invented case. These examples are the right way to learn the
tool before any real record is involved.

Python:

```python
from extract_text import extract

result = extract("synthetic_summons_efiled.pdf")

result.record.case_number             # '25-2-00001-0'
result.record.defendant_address.raw   # '... 1234 EXAMPLE AVE S APT 5 SEATTLE, WA 98100'
result.record.defendant_address.zip   # '98100'
[d.name for d in result.record.defendants]
                                      # ['JANE Q. TENANT', 'JON Q. TENANT']
result.record.attorney.firm           # 'EXAMPLE LAW GROUP PLLC'
result.flags                          # []  (empty means every check passed)
```

R:

```r
library(extracttext)

result <- extract_deterministic("synthetic_summons_efiled.pdf")

result$record$case_number
result$record$defendant_address$street
result$record$attorney$firm
result$flags

record_to_row(result)   # the same thing as a one-row tibble
```

Terminal, no programming at all:

```bash
extract-text extract synthetic_summons_efiled.pdf
```

To run both engines on the same document and see where they agree,

```python
both = extract("synthetic_summons_efiled.pdf", engine="both")
both.record.defendant_address.street     # the deterministic answer
both.ai.record.defendant_address.raw     # the AI answer, kept separate
both.comparison.needs_review             # fields a person should look at
```

```r
rules <- extract_deterministic("synthetic_summons_efiled.pdf")
model <- extract_ai("synthetic_summons_efiled.pdf")
compare_extractions(rules, model)$needs_review
```

Every extracted value carries its evidence. `result$evidence` (R) or
`result.evidence` (Python) maps each field to where it came from, including
the named rule that produced it, such as `to_block` for the service-address
rule. That audit trail is what lets a reviewer trace any cell in the final
table back to a spot on the original page.

## 9. Processing a folder of documents

Point the batch runner at files or folders. It finds every PDF, TIFF, PNG,
and JPEG underneath, processes them in a fixed order, and writes results as
it goes.

Terminal:

```bash
extract-text scan ~/data/summonses/2026-07/ --engine both \
    --out ~/data/extractions/2026-07/ --review
```

Python:

```python
from extract_text import scan

rows = scan("~/data/summonses/2026-07/", engine="both",
            out_dir="~/data/extractions/2026-07/")
```

R:

```r
results <- scan_documents("~/data/summonses/2026-07/", engine = "both",
                          out_dir = "~/data/extractions/2026-07/",
                          review = TRUE)
```

The output directory receives

- `extracted.csv`, one row per document, openable in anything
- `extracted.parquet`, the same table in a faster format, written when the
  parquet extra is installed
- `extracted.jsonl`, the full detail per document (every field, its evidence,
  its flags), one JSON object per line; this is the audit trail behind the CSV
- `review/index.html`, when review is requested, described in
  [section 11](#11-flags-and-the-review-workflow)

Choose the output directory the way you would choose a filing cabinet for
paper court records. These files contain whatever the documents contain,
names and addresses included. Keep them on governed storage, never inside a
code repository, and never anywhere publicly served. The repository's
`DATA-USE.md` states the terms that travel with data extracted by the
project's own team, and it is a sensible template for anyone else's practice.

### Case folders: what happened after the summons

The engines read one document, and the summons is the document they are
built for. A case is a folder of documents, and the folder holds the rest of
the story. When your collection keeps one folder per case, with each file
named for the document it holds, a second command rolls every case up to the
stages it reached.

```bash
extract-text cases ~/data/court_images/ --out ~/data/extractions/cases/
```

It types each document from its file name (summons, complaint, answer or
notice of appearance, motion for default, dismissal, judgment, writ,
sheriff's return), opens the first page of each sheriff's return to read how
the writ came back, and writes two tables.

`cases.csv` has one row per case folder.

| Column | Meaning |
|---|---|
| `case_dir` | The folder's name, which in most court collections is the case number |
| `n_documents`, `n_untyped` | Documents in the folder, and how many the file-name rules could not type |
| `has_summons`, `has_complaint`, `has_answer`, `has_default_motion`, `has_dismissal`, `has_judgment`, `has_writ`, `has_sheriff_return` | Whether a document of that type is on file |
| `outcome` | `judgment`, `dismissed`, or `none_recorded` |
| `n_sheriff_returns`, `sheriff_return_status` | How many returns are on file and what the deciding one reports: `ousted_ejected`, `peaceful_possession`, `return_per_attorney`, `return_per_plaintiff`, `expired`, or `unread` and `ambiguous` when the rules could not tell |
| `sheriff_evicted` | True for `ousted_ejected` and `peaceful_possession`, False for the other three, empty when there is no return or it could not be read |
| `flags` | `no_summons`, `dismissal_and_judgment`, `judgment_no_sheriff_return`, `sheriff_return_unread`, `sheriff_return_ambiguous` |

`case_documents.csv` has one row per document (`case_dir`, `file`,
`doc_type`) and joins to `extracted.csv` on `file`.

The rules are the ones Cheng Ren used to code 56,070 Pierce County cases in
his 2024 dissertation ([section 20](#20-references-and-how-to-cite)). A case
with a dismissal on file was dismissed. A case with a judgment on file, a
motion for default judgment included, went to judgment, and a case with both
counts as a judgment, because a plaintiff can move to dismiss and then carry
on. An answer or notice of appearance means the tenant responded. The
sheriff's return decides whether the sheriff carried out the eviction. This
package adds two choices of its own. A writ or a sheriff's return counts as a
judgment even when no file is named for one, and when a case holds several
returns, an eviction on any of them decides the case.

The command prints a report of counts and percentages, and `--save FILE`
writes the same report to a file. The report holds no folder name and no file
name. For documents the rules could not type, it counts words from a fixed
list of legal terms (declaration, order, notice, and so on) so that you can
see what is going untyped without a name being printed. `--names-only` skips
the sheriff's returns and finishes quickly, which is the sensible first run
on a new collection.

What this does not do yet. It does not read judgment amounts, filing and
judgment dates, or the content of a tenant's answer. It types documents by
file name only, so a collection whose files are named by number needs a title
reader that has not been written. And none of it has been measured against
hand labels. The dissertation's own figures for Pierce County, 2004 to 2022
(30 percent of cases with a summons answered, 76.8 percent to judgment, 71.7
percent on to the sheriff; pp. 46 to 47) are the first thing a Pierce County
run should be compared with.

## 10. The output, column by column

The main columns of `extracted.csv`, in the order they appear. The R
functions return the same columns, from the same code, so the two can never
drift apart.

| Column | Meaning |
|---|---|
| `file` | Document file name |
| `case_number` | Case number read from the document itself |
| `plaintiffs` | Plaintiff name(s) as printed, separated by semicolons |
| `defendant_names` | Defendant name(s) as printed, separated by semicolons |
| `n_defendants` | How many defendants were named |
| `defendant_address_raw` | The service address exactly as captured, one line |
| `defendant_street` | House number and street, including any unit designator that is part of the street line |
| `defendant_unit` | Apartment, unit, or suite on its own, when printed. This repeats what is already inside `defendant_street`; see the note below the table |
| `defendant_city`, `defendant_state`, `defendant_zip` | The rest of the address, split out |
| `defendant_anchor` | Which rule found the address (the audit trail; see section 12) |
| `attorney_names`, `attorney_firm` | Plaintiff counsel, as printed |
| `attorney_address_raw`, `attorney_street`, `attorney_unit`, `attorney_city`, `attorney_state`, `attorney_zip` | The attorney's address, kept firmly separate from the defendant's. `attorney_unit` repeats what is inside `attorney_street`, as above |
| `attorney_phone`, `attorney_bar_numbers` | Contact and bar registration (WSBA numbers in Washington) |
| `court_name`, `county`, `state`, `case_type` | Case-level fields as written on the document |
| `filing_date`, `amount_claimed`, `judgment_amount`, `judgment_date`, `disposition`, `disposition_date` | Present when the document type carries them |
| `n_ungrounded` | For AI output, how many values could not be verified against the document text (0 for deterministic output) |
| `n_pages` | Pages in the file |
| `text_source` | How the text was obtained. `pdf_text_layer` means digital text, no OCR involved. `pdf_ocr`, `tiff_ocr`, and `image_ocr` mean OCR read the page images |
| `ocr_mean_conf` | OCR's own confidence in what it read, 0 to 100, only when OCR ran. Low values usually mean a poor scan |
| `method`, `backend` | Which engine produced the row's main columns, and exactly which rules or model |
| `flags` | Review flags, semicolon separated. Empty means every check passed |

One thing to watch in the address columns. The `unit` column repeats
information that is already contained in the `street` column, rather than
holding a piece removed from it. If a summons prints "1234 Example Ave S Apt
5", then `defendant_street` is the whole of "1234 Example Ave S Apt 5" and
`defendant_unit` is "Apt 5". Pasting the two columns together therefore
produces "1234 Example Ave S Apt 5 Apt 5". Use `street` on its own when you
want the full street line, `address_raw` when you want the address as
captured, and `unit` only when you need the unit by itself, for example to
count multi-unit buildings. The same applies to `attorney_street` and
`attorney_unit`.

When the engine is `both`, these additional columns appear.

| Column | Meaning |
|---|---|
| `ai_case_number`, `ai_plaintiff`, `ai_defendant_names`, `ai_defendant_address`, `ai_law_firm`, `ai_law_firm_address` | The AI engine's answers, never blended into the main columns |
| `ai_backend` | Exactly which model produced them |
| `ai_flags` | Flags raised by the AI lane itself |
| `address_similarity` | How alike the two engines' addresses are, 0 to 1, using the same similarity measure as the validation work |
| `address_same_street` | Whether that similarity clears the 0.7 threshold the validation work counts as a same-street match |
| `case_number_agree` | Whether both engines read the same case number |

## 11. Flags and the review workflow

The design principle is flagged, never guessed. A document that fails any
check gets a named flag and keeps moving; nothing invents an answer to keep a
row looking complete. The flags and what to do about them.

| Flag | What it means | What to do |
|---|---|---|
| `no_defendant_address` | No rule found a service address | Review the document; often handwriting or an unusual layout. In `both` mode, check the AI columns |
| `defendant_address_incomplete` | A street was found but no city or ZIP | Usually recoverable by a person in seconds |
| `defendant_block_low_conf` | OCR read the address block with low confidence | Poor scan or handwriting; verify against the page image |
| `low_ocr_conf` | The whole page read poorly | Consider a better scan if one exists |
| `no_text` | Nothing readable at all | Corrupt file or blank page |
| `house_number_repaired` | OCR confused characters in the house number (a common example is reading 1234 as L234) and a documented repair was applied | Informational; spot-check a sample |
| `street_no_suffix` | The street had no type word (Ave, St, and kin) and was accepted because a city line directly confirmed it | Informational; this rule is newer than the validated original, so spot-check these as a class |
| `pro_se_plaintiff` | The plaintiff appears self-represented | Informational; no attorney block is expected |
| `no_attorney_block` | No attorney block was found and the plaintiff is not marked self-represented | Review |
| `defendant_equals_attorney` | The two addresses came out identical, the classic wrong-address failure | Always review; the row is untrustworthy |
| `case_number_mismatch` | The number on the document disagrees with the number the file was supposed to be | Filing or download mix-up; review |
| `scan_error:*` | The file could not be processed at all | Check the file |
| `engines_disagree_address` (both mode) | The two engines found different addresses | Review; one of them is wrong |
| `only_ai_found_address` / `only_rules_found_address` (both mode) | One engine found an address, the other did not | Review the finder's answer against the page |
| `vision_json_fallback` / `vision_no_fields` (AI lane) | The model's reply needed repair, or contained nothing | Treat that row's AI columns skeptically |
| `defendant_matches_plaintiff` | A name read as a defendant is also the name read as the plaintiff. The AI engine removes it from the defendants; the deterministic engine keeps it and flags the row | Review both names against the page |
| `deterministic_defendant_is_ai_plaintiff` (both mode) | A deterministic-engine defendant matches the plaintiff the AI engine read | Review; the deterministic engine's defendant list likely holds the landlord |
| `vision_defendant_group_term` (AI lane) | The model returned a trailing group term ("ALL OTHER OCCUPANTS", "et al.") with the defendants and it was stripped in code | Informational; the named defendants are kept |

The review page turns this into a workflow. `extract-text review --out DIR`
(or `review = TRUE` in R, `--review` on the scan command) builds
`review/index.html`, a single page showing each document's first-page image
beside everything extracted from it, flagged documents first. A person scrolls
and compares. No software is installed to view it; it is a plain HTML file.

To correct what the machine got wrong, open the page with saving turned on.

```bash
extract-text review --out ~/data/extractions/2026-07/ --serve
```

This opens the page in your browser from a small server running on your own
computer (it answers only at 127.0.0.1, so nothing is reachable from the
network), and prints where corrections go. Each document has a form that
starts with the machine's reading: plaintiff, defendants (one per line), the
defendant's address in parts, street without the unit, and, when the page
is built with `--attorneys N`, the plaintiff's attorney on N documents drawn
at random (names one per line, firm, and the address on one line; `all` asks
on every document). Fix what is wrong,
clear what the page does not show, and press Save. Saving a form you did not
change records that the machine was right, which is as useful as a
correction. "Can't tell from the page" records that the page does not settle
it. Saving again replaces your earlier answer, and reopening the page later
shows what you already saved. Press Ctrl-C in the terminal when finished.

In a both-engine scan each document says whether the two engines agree. A
shaded line above the table names the fields where they differ (for the
address, which parts: street, unit, city, ZIP), and those rows of the table
are shaded and marked ≠. The comparison ignores case, punctuation,
abbreviations such as Ave and Avenue, and legal-form words such as LLC, so
only a real difference in content shows. It is stricter than the
`engines_disagree_address` flag, which follows the validation's forgiving
same-street measure and lets a dropped unit pass.

In a both-engine scan each form also has a "Use AI engine's reading" button.
It fills the form with the AI engine's answer, which is quicker when that
answer is right or nearly so. Check it against the page, fix what is wrong,
and save. Every save is scored against both engines, so a field you fix
after filling from the AI is recorded as the AI engine's error, and teaches
as much about the AI engine as about the deterministic one. The message
after saving says which fields each engine got wrong. The record also notes
that you started from the AI's reading, because a field accepted unchanged
is easier to agree with than to find, and that tilts a score of the AI
engine in its own favor.

Click a page image to enlarge it, and click again to shrink it. Enlarged,
the page takes most of the window and the comparison and form stay to its
right, moving down the screen with you as you scroll the page, so the
answer and the page stay side by side. When the page is served, each document also has an "Open
the full document" link, which opens the original file, every page, in the
browser's own viewer, where it can be zoomed.

Answers land beside the scan, in `corrections.jsonl` (every save, in order)
and `corrections.csv` (the latest answer per document). Each one records the
right answer, what the machine said, what the AI engine said in a
both-engine run, which fields changed, and whether the document was shown
because it was flagged or drawn at random. That makes the file a labeled
set: it scores either engine, and it tells a rule fix exactly which
documents it must get right. The random draws estimate accuracy for the whole
scan; the flagged ones are the hard cases. These files hold names and
addresses, so the scan folder must be governed storage.

### Running a grading round

A grading round puts several people on one scan folder and turns their
answers into scores. The steps, in order:

1. **Draw the documents.** `extract-text scan COLLECTION --out DIR --engine
   both --sample 300` scans 300 documents drawn at random (seeded, so the
   draw repeats) from a whole collection. Both engines are worth running,
   because the page then shows where they disagree.
2. **Choose the order.** `extract-text review --out DIR --graders --serve`
   builds the graders' page. Every document goes on it; each grader types a
   name and email at the top, chooses a batch of 10, 30, or 100, and sees
   only that many ungraded documents. Name and email are saved with every
   answer. By default the documents most in need of a person come first (a
   distrusted address, then a field the engines disagree on, then any other
   flag). That finds broken rules fastest, but the graded share leans toward
   hard documents and understates accuracy. `--order random` serves them in
   random order instead, a different one for each grader, so whatever share
   gets graded is a fair sample of the folder; every answer is then recorded
   as a random draw, and the score report's bracketed figures are the
   accuracy estimate.
3. **Add a shared set.** `--overlap N` puts the same N documents, drawn at
   random, first for every grader, in one order, before each grader's own
   order takes over. Graders are not told which documents are shared and
   each works from a separate copy of the folder, so the second answer is
   blind. Thirty is enough to see which fields people read differently.
   To have a chosen set graded again (say, the documents you graded
   yourself), leave your answers out of the copy you share and give the
   graders `--rows` with those document numbers alongside `--graders`. That
   page holds just those documents, records each grader's name, and shows no
   other answer, so `agree` compares the graders with you.
4. **Ask for the attorney on some documents.** `--attorneys N` adds the
   plaintiff attorney's box (attorneys and firm together, one per line, and
   the address on one line) to N documents drawn at random, the same ones
   for every grader;
   `all` asks on every document, and without the option no document has it.
   A few dozen answers measure the attorney block, and asking on every
   document slows the whole round.
5. **Hand out the folder.** Zip the scan folder and share it through
   restricted storage, by name. Anything already graded in it is hidden from
   the graders and shown with its answer, so remove `corrections.jsonl` and
   `corrections.csv` from the copy you share unless you mean graders to skip
   those documents. For an accuracy round this matters: leftover answers on
   hard documents would leave an easier remainder. `GRADING.md` at the
   repository root is the graders' own step-by-step.
6. **Bring the answers back.** Each grader returns their
   `corrections.jsonl`, renamed `corrections_NAME.jsonl`, through the same
   restricted storage; the reports are made from it. Put the
   files in the scan folder, then run
   `extract-text agree --out DIR DIR/corrections_A.jsonl DIR/corrections_B.jsonl`.
   It reports, field by field, how often each pair of graders gave the same
   answer on the documents they shared, and lists each disagreement by
   document number with the answers masked.
7. **Merge, then settle.** The same command with `--merge` copies every
   grader's answers into the scan's `corrections.jsonl` and keeps both
   answers where two graders did the same document (a plain copy would keep
   only the last, silently). The report ends with
   `extract-text review --out DIR --rows 12,57 --serve`, which opens just
   the documents to settle, with every grader's answers side by side above
   each form and the fields where they differ highlighted. The form starts
   empty: **Keep this one** fills it from one grader's answer, to save as it
   is or edit first. The answer saved there is the one that counts, and
   `agree` run again leaves it out of the graders' figures and lists only
   the documents still to settle. The attorney box appears only where a
   grader answered it. A later answer to a document keeps the draw it came
   from, so settling never turns a random draw into a flagged one.
8. **Score.** `extract-text score --out DIR --shapes`, described next.

Answers saved before 2026-10-07 carry no attorney block, and neither does an
answer to a document without the attorney box; the score report counts only
the answers that have one on its three attorney lines. The AI engine is not
scored on attorney names, which it does not read by design. Answers from the
second round on hold attorneys and firm in one list, with no firm of its own:
an engine's names and firm together are checked against that list
(`attorneys`), and its firm alone is right when it is one of the lines
(`attorney_firm`).

**Keep a test set apart from the fix set.** Answers are used two ways: their
failure shapes show which rule to fix, and their scores say how accurate the
engines are. Measured on the same documents a fix was written from, a score
flatters the fix. To know how the engine does on documents it has not seen,
score a random-order round before any rule change drawn from it, and take
rule fixes only from worst-first answers or from an earlier round, or score
the fixed engine on a fresh draw (`scan ... --sample 300 --seed 2`).

Two more commands go with corrections. `extract-text review --out DIR --random
100` builds the page from 100 documents drawn at random from the whole scan,
flagged or not. Only a random draw can say how accurate the engines are on
the whole; the flagged-first page is for finding failures, and it
over-represents them. Corrections already saved are kept whichever page is
built. And `extract-text score --out DIR` reads the corrections and prints,
for each engine, the share of each field it got right (with the random rows
alone in brackets), what kind of wrong the rest were (blank, extra, or
different), and the flags carried by the rows it got wrong. Add `--shapes`
to see each wrong value in masked form, letters as A, digits as 9, so the
pattern of a failure is visible without the record. The report holds no
names, addresses, case numbers, or file names, so it can be sent to whoever
maintains the rules.

How much review to expect depends entirely on your documents. As one
reference point, in the July 2026 Washington validation work ([section
13](#13-accuracy-measured-honestly)) roughly 84 to 100 percent of documents
yielded an address depending on the era and format of the corpus, and the
genuinely wrong addresses among extractions were about 1.5 percent,
concentrated in rows that were already flagged. The August 2026 improvement
pass raised the yields on the two large King County truth sets to 92.4 and
95.6 percent (section 13 has the full table). Plan for a person to look at
the flagged minority, plus a small random sample of unflagged rows as a
standing habit.

## 12. How it works under the hood

You do not need this section to use the tool. It is here because
understanding the mechanism makes the flags and the failure modes make sense,
and because this project believes tools used on court records should be
explainable to the people affected by them.

**Reading the file.** An e-filed PDF carries its text digitally, with the
position of every word on the page, so the tool reads that directly and
perfectly; OCR never runs. A scanned PDF or TIFF is only a picture, so the
tool renders each needed page at 300 dots per inch and hands it to
tesseract, the OCR program, which returns its best guess at every word, that
word's position, and a confidence score. Either way, the result is the same
thing, a list of words with page coordinates. The engine only reads the
pages it needs (the first two and the last, where summons fields live), and
reads deeper when a document turns out to be a combined bundle or when the
first pass produced a suspect answer, one that collides with the attorney's
street or lacks both city and ZIP, since either is the signature of the true
service block living on an interior page.

**Why positions matter.** Court pleading paper prints a rail of line
numbers, 1 through 26, down the left margin of every page. To OCR, those
digits are just more text, and naive extraction interleaves them into
whatever sits beside them, so an address like 123 4th Street S, Seattle
comes out as 123 4th Street S 17 18 Seattle. This exact failure is
documented in the project's 2024 paper. Because every word here carries its
position, the rail is identified geometrically, digits in the margin band,
and deleted before any text is assembled. The same cleaning drops
implausibly tall OCR boxes, which are the pleading paper's vertical rule
misread as letters. A single such smear used to seed a merged "line" that
swallowed entire service blocks, and mining the full truth set found it to
be the engine's single largest cause of missed addresses before the August
2026 fix. The same positional information is what tells a bottom-right
attorney block apart from a mid-page service block, which no amount of
text-only pattern matching can do reliably.

**The anchor ladder.** The defendant's address is searched for by four named
rules in a fixed order, and the first to succeed wins. `to_block` finds the
mid-page service block that begins TO: or TO DEFENDANT. `premises_prose`
finds sentences of the form "premises located at ...". `address_stack` finds
a bare street line with a city line under it in the body of older summonses.
`caption_cell` finds an address printed inside the caption's defendant cell.
Every extracted address records which anchor produced it, in the
`defendant_anchor` column, so systematic problems can be traced to a specific
rule and fixed.

Selection among candidates follows rules that were each added in response to
a measured failure. A street with no type word at all ("1949 S. Sprague", a
form common in Tacoma) can be accepted when a city line directly confirms
it, and every such acceptance is flagged `street_no_suffix`. A strict match
outranks a confirmed no-suffix match from any anchor, and a candidate with a
city or ZIP outranks a fragment with neither, even one found on an earlier
page. When the winning street turns out to be the plaintiff attorney's, the
first non-colliding candidate on the audit trail takes over, and the
collision flag still fires when no alternative exists. Some blocks are
refused outright because their address belongs to someone else: a process
server's declaration, the "deliver your answer to:" instruction (that
address is plaintiff counsel's), and prose captures such as a "city" of
Residing or a firm name standing where a city should be.

**The attorney block.** Found geometrically in the bottom-right region,
scored on whether it contains a firm-like name, a street, a city line, and a
phone number, with form-publisher footers explicitly vetoed. It is extracted
partly for its own value and partly as a defense, because knowing where the
attorney's address is stops it from being mistaken for the tenant's. If the
two ever come out identical the row is flagged `defendant_equals_attorney`
rather than passed through.

**The AI engine.** A language model is a program trained on enormous amounts
of text to predict what comes next, which in practice makes it able to
answer questions about content it is shown. A vision model is one that can
also look at images. The AI engine renders page one of the document as an
image, sends it to the qwen3.5 model running inside ollama on your machine,
and asks one fixed, carefully worded question requesting six fields back in
a rigid format, with instructions to say NA rather than guess. The question
is the one benchmarked by Cheng Ren, with two recorded deviations: a
case-number field was appended, and the law-firm item now says it wants the
firm itself rather than the attorney who signed for it, a fix measured
across six local models in August 2026. The reply is parsed strictly, with
two documented fallback parsers for near-miss replies, and mapped into the
same fields the deterministic engine produces. One repair happens in code
rather than by instruction: trailing group terms such as "ALL OTHER
OCCUPANTS" or "et al." are stripped from the defendant line and flagged
`vision_defendant_group_term`, because a term left in place used to split
into a phantom second defendant named for the group.

**Grounding, the defense against confident nonsense.** Language models
sometimes produce fluent answers that the document does not support. Where
document text is available (always, in `both` mode), each AI answer is
checked for whether it actually appears in the document, allowing for line
wrapping. Answers that cannot be found are marked unverified, counted in
`n_ungrounded`, and listed for review. The model is deliberately never asked
to rate its own confidence, because that rating would be generated by the
same process that generated any error.

**Reproducibility.** The deterministic engine is reproducible by
construction, with pinned OCR settings and ordered rules. The AI engine is
pinned as far as an AI engine can be, temperature zero and a fixed seed, but
a model update or different hardware can still change its output, which is
one more reason the two engines stay separate and labeled.

## 13. Accuracy, measured honestly

Two generations of numbers are given here. The July 2026 validation runs
scored the Washington scanner that this package's deterministic engine began
as a port of, against more than 5,100 hand-labeled addresses from real
Washington cases. On 2026-08-20 the packaged engine itself, carrying every
measured improvement shipped since the port, was re-scored against the same
labeled sets with the validation kit's own scoring code. (The labeled data
lives in the network's governed research archive, not in this repository.)
Similarity is a normalized edit-distance measure between the extracted
address and the hand label, where 1.0 is identical; 0.7 or above corresponds
to the same street and is the threshold the 2024 paper used.

**July 2026: the ported original, on the July samples.**

| Truth set | n | Address found | Mean similarity | Same street (at least 0.7) | ZIP agreement |
|---|---|---|---|---|---|
| King County 2013 scans (dissertation labels) | 200 | 83.5% | 0.867 | 94.0% | 90.7% |
| King County 2017 e-filed (legal-aid intake labels) | 100 | 90.0% | 0.886 | 90.0% | 94.3% |
| Pierce County, hand-swiped labels | 11 | 100% | 0.922 | 100% | 90.9% |
| Pierce County, manual labels (includes handwritten forms) | 6 | 66.7% | 0.897 | 100% | 100% |

**August 2026: this engine, on the full truth sets.** The re-score began by
rerunning the July samples on the same documents, where the engine came back
equal or better on every column of every set, and then ran the 5,168 labeled
cases (of 5,171) whose documents are on the archive volume in one pass. The
same-street rate is counted two ways, among documents where an address was
found, and among all documents, where a missing address counts as a miss.

| Truth set | n | Address found | Mean similarity | At least 0.7, of extractions | At least 0.7, of all | ZIP agreement |
|---|---|---|---|---|---|---|
| King County 2013 scans, full set | 4,254 | 92.4% | 0.907 | 98.3% | 90.8% | 96.3% |
| King County 2017 e-filed, full set | 877 | 95.6% | 0.926 | 99.5% | 95.1% | 95.1% |
| Hand-swiped labels, four counties | 27 | 88.9% | 0.913 | 91.7% | 81.5% | 95.7% |
| Manual labels, three counties | 10 | 70.0% | 0.967 | 100% | 70.0% | 100% |

**What the improvement pass cost, and where.** The last round of fixes
refuses a doubtful answer rather than emitting it, and that trade is visible
in the table rather than hidden by it. On the two large King sets it pays
for itself. Same-street-of-all rose from 89.1 to 90.8 percent and from 90.4
to 95.1 percent, against a yield drop of one to two points. On the 27-case
hand-swiped set it does not pay. Yield fell from 100 to 88.9 percent and
same-street-of-all from 92.6 to 81.5 percent, because three addresses the
earlier stage of the same pass had extracted correctly became outright
refusals and a fourth fell from 0.90 to 0.57. Every one of the four carries
a flag. Mean similarity rose on all four sets, so what survives is more
accurate and there is less of it. On 27 cases a four-document swing is
small-n volatility as much as a finding, but it is a real regression on that
set and worth watching on the next run rather than rounding away.

For context, the pipeline published in the 2024 paper scored a 0.82 mean
similarity on the same truth data; the July 2026 original ran 0.87 to 0.92,
and this engine now runs 0.91 to 0.93 on the two large sets. What moved the
numbers is documented change by change in `MAINTENANCE.md`: the
failure-mining pass of 2026-08-20 classified every miss on the full set,
read the dominant classes as page images, and fixed eight mechanisms, the
largest being an OCR smear of the pleading rule that merged lines and
swallowed service blocks. E-filed documents are the easiest and most
reliable format. The misses in the Pierce manual set are handwritten forms,
which is precisely the case the AI lane exists for; in bench testing the AI
engine returned structured fields for all 300 pages of a Pierce County test
set and recovered a handwritten service address that OCR returned as noise.

Read the table with these cautions.

- The numbers describe Washington documents from specific counties and eras.
  They are evidence of how the method behaves, not a promise about your
  corpus. Different jurisdictions will differ.
- The AI lane is spot-validated and has been benched on a synthetic
  24-document corpus (which tightened its prompt), but it is not yet
  formally scored against the same labeled sets. That head-to-head is the
  project's next validation milestone, and `MAINTENANCE.md` tracks it.
- Part of the sub-0.7 residue in the table is the metric, not the extraction;
  for example, extractions that included unit numbers the hand labels
  omitted score low despite being more complete than the label.
- This engine now deviates from the validated original in several
  documented ways: direction and unit vocabulary, a rail-number guard, the
  no-suffix parser, phantom-city vetoes, and the selection rules in
  section 12. Each was measured on real documents before shipping. The
  2026-08-20 re-score reproduced or beat the July samples on every column,
  and improved every column of the two large full sets, at the cost noted
  above on the smallest one; the evidence trail for each change is in
  `MAINTENANCE.md`.

If you need numbers for your own jurisdiction, the path is the one this
project used. Have people hand-label a few hundred documents, run the tool,
and score the two against each other with the similarity functions shipped in
`extract_text.similarity`. [Section 16](#16-using-this-outside-washington)
says more.

## 14. Privacy and security

Court records name real people at the worst moments of their housing lives.
This project treats that as a design constraint, and the constraint is
simple to state. With the default engines, no document, no page image, no
extracted value, and no fragment of any of them leaves your computer, ever.

What backs that claim.

- The deterministic engine is rules running in-process, plus two local
  programs (poppler, tesseract) that read files on disk. There is no network
  code in that path at all.
- The AI engine talks only to ollama, which is a program on your own machine
  serving a model from your own disk. The address it uses is localhost, which
  is computer-speak for "this machine and nowhere else."
- The tool contains no telemetry, no usage reporting, no update checks, and
  no cloud anything. After installation it runs fully offline.
- The code is open source under a license (AGPL-3.0) that requires anyone who
  modifies and serves it to publish their modifications. You, or your
  security team, can read every line and verify each statement above, and
  the project considers that checkability part of the security story.

One exception exists and is opt-in three times over. A backend for Anthropic's
cloud API ships in the package for corpora that are already cleared for
third-party processing. It is never a default, it requires installing a
separate extra, it requires an API key, and its own documentation repeats
this warning. If your records must stay local, simply never type
`backend="anthropic"`, and nothing will ever leave.

Two practices this project follows and recommends.

- **Code and data live apart.** The repository holds code and synthetic
  examples only. Outputs, which contain names and addresses, go to governed
  storage. The repository's rules (`CONTRIBUTING.md`) forbid real records in
  code, tests, fixtures, and documentation, and `python/scripts/pii_sweep.py`
  checks the repository, including its git history, for anything shaped like
  a real case number or address. Run it before sharing any fork.
- **Treat outputs as what they are.** A table of names and addresses
  extracted from court records identifies people. Store it with the same
  access controls you would give the source documents, and read `ETHICS.md`
  and `DATA-USE.md`, which state the uses this project supports and refuses.

## 15. Settings you may want to change

Everything below has a sensible default, and the defaults are the tested
configuration. Change them knowingly.

| Setting | Where | Default | Why change it |
|---|---|---|---|
| `engine` | every entry point | `deterministic` | `ai` or `both`, per section 2 |
| `model` | AI calls, `--model` | `qwen3.5:9b` | A newer recommended model, or a larger one if you have the memory |
| `prompt_format` | AI calls, `--prompt` | `lists` | `v1`, the original prompt, to reproduce a run made before 2026-10-21 |
| `host` | AI backends, or the `OLLAMA_HOST` environment variable | `http://localhost:11434` | Ollama running on another port, or a shared machine inside your own network |
| `temperature` | AI backends | `0.0` | Higher values make the model more variable; there is no good reason for that here |
| `seed` | AI backends | `42` | Reproducibility bookkeeping |
| `dpi` | vision rendering | `150` | Raise if page images are unusually dense |
| `page` | vision backend | `1` | Extract from a different page of the file |
| `expected_case_number` | deterministic calls | none | Enables the mismatch flag when you already know which case a file should be |
| `limit` | scan | all | Trial runs on the first N documents |
| `parquet` | scan | write if available | Force on (error if pyarrow missing) or off |

The OCR settings, engine choice inside tesseract, 300 dpi rasterization, and
page selection, are deliberately pinned rather than exposed, because they are
part of what was validated. They live in one place in the source
(`documents.py`) if a fork truly needs different ones.

## 16. Using this outside Washington

The package was trained and validated on Washington unlawful detainer
documents. What transfers, and what to check, if your documents come from
somewhere else.

**What transfers as-is.** The file handling (e-filed, scanned, TIFF), the
line-number rail removal (pleading paper is near-universal in American
courts), the general field patterns (case numbers, dates, amounts, captions),
the service-block and premises anchors (TO: blocks and "premises located at"
phrasing are standard summons furniture), the attorney-block geometry
(bottom-right placement is convention), the AI engine (nothing about it is
Washington-specific), and the whole flag-and-review design.

**What is Washington-tuned.** Three things in
`python/src/extract_text/deterministic/summons.py`, each marked at its
definition. The city-state-ZIP patterns, strict and no-suffix both, expect
WA or Washington as the state token. The strict case-number format
(##-2-#####-#) is the Washington superior court convention; elsewhere, the
generic case-number patterns still apply. Bar numbers are recognized by the
WSBA label. Adapting these for another state is a contained, reviewable
change, and the project welcomes such contributions as pull requests (see
`CONTRIBUTING.md`; note the rule that examples must be synthetic).

**How to validate in a new place.** Do not trust transferred rules blind, and
do not trust the AI lane blind either. Sample a few hundred documents, have
people record the true address for each, run the tool, and score with
`extract_text.similarity.address_similarity`. That is the same procedure the
Washington numbers come from, and it turns "it seems to work" into a number
you can put in a methods section.

## 17. Speed and hardware

Measured behavior, so you can plan capacity.

- The deterministic engine runs at roughly 5 seconds per document on an
  ordinary laptop CPU when OCR is involved, and much faster on e-filed PDFs,
  which skip OCR entirely.
- The AI engine benchmarked 300 summons pages in 83 minutes on ordinary
  hardware, roughly 17 seconds per page, and matched that rate on the
  machine this package was built on.
- Memory: the deterministic engine is light; the AI engine wants about 16 GB
  of system memory with the 9B model.
- Marginal cost: zero. No per-page fees, no cloud bill, no license cost
  anywhere in the stack.

Worked example. A county receiving about 700 filings a month can expect the
deterministic pass over a month's summonses to take on the order of an hour
on one workstation, and an AI pass over the same documents to run overnight.
At a 90 percent address yield, the flagged review pile is about 70 documents
a month, which is an hour or two of a person's time with the review page.

## 18. Troubleshooting

Each entry pairs the message you will actually see with the fix.

**"The program 'pdftotext' is needed to read text out of PDF files and is
not installed."** Install poppler (table in section 3), then rerun
`extract-text doctor` to confirm.

**"The program 'tesseract' is needed to read scanned pages (OCR) and is not
installed."** Install tesseract. Only scanned documents need it; e-filed
PDFs work without it.

**"No local model server at http://localhost:11434."** Ollama is not
running. Start the ollama app, or run `ollama serve` in a terminal, and
leave it running while you work.

**"The model 'qwen3.5:9b' is not pulled on this machine."** Run
`ollama pull qwen3.5:9b` once and retry.

**"note: model 'qwen3.5:9b' is not pulled; using 'qwen3.5:latest' from the
same family."** Not an error. You have a same-family model and it was used;
the output records which. As of August 2026 `qwen3.5:latest` points at the
same 9B model as `qwen3.5:9b`, so in that case nothing differs but the name.
Run `ollama pull qwen3.5:9b` if you want the pinned tag present, which costs
nothing when the weights are already on disk.

**"The Python engine is not available. Run extracttext_install() once, then
restart R."** Exactly that. If it persists after a restart, run
`reticulate::py_config()` and check that the `r-extracttext` environment is
the one selected.

**Rows full of `no_text` or very low `ocr_mean_conf`.** Your scans are poor.
If re-scanning at 300 dpi is possible, do that; if not, the AI lane reads
bad pages better than OCR does, and the review page shows you the worst.

**A defendant address that is obviously the law firm's.** That is the
failure this tool was built to prevent, so treat it seriously. Check whether
the row is flagged `defendant_equals_attorney` (it should be). If you can
share the document layout with the maintainers with a synthetic mock-up, not
the real page, it helps the next release.

**Windows notes.** All three helper programs have Windows builds, and the
paths must be on PATH (the doctor checks). Everything else is identical.

## 19. Glossary

- **anchor** A named extraction rule tied to a place or phrasing on the
  page. Recorded with every value it produces.
- **deterministic** Producing the same output for the same input, every
  time. Rules are deterministic; AI models are not.
- **e-filed PDF** A PDF whose text is digital, selectable, and exact. The
  best input this tool can receive.
- **grounding** Verifying an AI answer by finding it in the document text.
  Ungrounded answers are labeled unverified, never quietly kept.
- **OCR (optical character recognition)** Software that reads pictures of
  text into machine text. Necessary for scans, imperfect by nature, and
  the source of the confidence scores in the output.
- **language model** A program trained on very large amounts of text to
  continue or answer text. A **vision model** additionally accepts images.
- **local model** A language model whose files sit on your own disk and
  whose computation runs on your own processor. The opposite of a cloud API.
- **Ollama** The open-source program this project uses to run local models.
- **parquet** A compressed columnar file format for tables, faster and
  smaller than CSV, readable by R (arrow), Python (pandas or polars), and
  most databases.
- **pleading paper** Court stationery with numbered lines down the margin.
  The source of the rail digits this tool strips.
- **service address** The address at which a defendant is served notice,
  printed on the summons. For research purposes, the tenant household's
  address.
- **similarity (edit distance)** A 0-to-1 measure of how alike two strings
  are, based on how many single-character changes turn one into the other.
  The validation metric of this project; 0.7 or above means same street in
  practice.
- **summons** The document notifying a defendant of the case against them.
  Page one carries most of what this tool extracts.

## 20. References and how to cite

The method this package implements is described in

> Thomas, Tim, Alex Ramiller, Cheng Ren, and Ott Toomet. 2024. "Toward a
> National Eviction Data Collection Strategy Using Natural Language
> Processing." *Cityscape* 26(1). U.S. Department of Housing and Urban
> Development.
> https://www.huduser.gov/portal/periodicals/cityscape/vol26num1/article12.html
> (also on JSTOR: https://www.jstor.org/stable/48766080)

The case-folder rules in [section 9](#9-processing-a-folder-of-documents)
follow

> Ren, Cheng. 2024. "Not All Eviction Cases are Alike: How Do Contextual and
> Individual Characteristics Matter? A Computational Analysis of a Decade of
> Court Cases from Pierce County, Washington." PhD dissertation, University
> of California, Berkeley. https://escholarship.org/uc/item/7f36p8n6

To cite the software itself, use the metadata in `CITATION.cff` at the
repository root, which citation managers and GitHub read directly.

The default AI model, qwen3.5 9B, is an open-weights model released under
the Apache License 2.0 and run through Ollama.

## 21. Getting help

- Setup problems: run the doctor first; it answers most of them.
- Bugs and feature requests: open an issue at
  https://github.com/evictionresearch/extract-text/issues. Never paste a
  real document, a real name, a real address, or a real case number into an
  issue; reproduce problems with the synthetic fixtures or a synthetic
  mock-up of your layout.
- Security or privacy problems: do not open a public issue; write to
  timthomas@berkeley.edu.
- Collaboration, validation partnerships, and data questions: same address,
  and see `ETHICS.md` for what this project will and will not support.
