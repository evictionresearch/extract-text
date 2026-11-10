# ==========================================================================
# Getting started with extract-text in R: the deterministic engine
# Author: Tim Thomas
# Created: 2026-10-29
# Reviewer:
# Updated: 2026-11-09
#
# This script is the quick start script for the extract-text package using the
# rules engine only (no AI, no network). It installs the package, reads a
# made-up summons, scans a random 50 of your own documents, has you grade
# those 50 by hand, scans the whole folder, has you grade a second random
# 50 from it, and builds the final table of cases, names, and addresses. The
# grading is not optional: until it is done, how often the scan is right on
# your documents is unknown (step 6 says why). Run it a line or a block at a
# time, not with source(), because step 1 ends by restarting R.
#
# Your documents, and every file this script writes from step 4 on, hold
# tenants' names and addresses. Keep them wherever your organization keeps
# the court documents themselves.
# ==========================================================================

# --------------------------------------------------------------------------
# Before you start: install poppler and tesseract (once per computer)
# --------------------------------------------------------------------------
# extract-text cannot read a document without two free programs that R does
# not install: poppler opens PDFs, and tesseract reads scanned pages (OCR).
# Both Mac and Windows need them. Install them outside R, then open RStudio.
#
# Check first whether you have them: run `which pdftoppm tesseract` in
# Terminal (Mac, Linux) or `where.exe pdftoppm tesseract` in PowerShell
# (Windows). If both print a path, skip to step 1. On a Mac, brew install on
# a program you already have upgrades it and everything that depends on it.
#
# Mac. Install Homebrew from https://brew.sh if you don't have it, then run
# this in Terminal:
#   brew install poppler tesseract
#
# Windows. Run these in PowerShell:
#   winget install oschwartz10612.Poppler
#   winget install UB-Mannheim.TesseractOCR
# winget puts poppler on your PATH, but the tesseract installer does not.
# Add its folder, by default C:\Program Files\Tesseract-OCR, through Start >
# "Edit environment variables for your account" > Path > Edit > New. Then
# restart RStudio. If your computer blocks installs, ask IT for these two
# programs.
#
# Linux (Debian or Ubuntu):
#   sudo apt install poppler-utils tesseract-ocr
#
# extracttext_doctor() in step 2 confirms that R can find both.
#
# The engine is written in Python, so the computer also needs Python 3.10
# or newer, and git, which the install in step 1 downloads the engine with.
# The Python that comes with a Mac is older than 3.10. Step 1 checks for
# both before it installs anything. If either is missing:
#
# Mac, in Terminal (Homebrew installs git with itself):
#   brew install python
#
# Windows, in PowerShell:
#   winget install Python.Python.3.12
#   winget install Git.Git
#
# Linux (Debian or Ubuntu):
#   sudo apt install python3 python3-venv git
#
# Then restart RStudio.

# --------------------------------------------------------------------------
# Step 1. Install extract-text
# --------------------------------------------------------------------------
# install_github() fetches the R package. extracttext_install() then builds
# the Python engine the package runs on, once per computer.
# install.packages(c("remotes", "dplyr")) # if you don't have them yet
remove.packages("extracttext") # if you have an older version installed
remotes::install_github("evictionresearch/extract-text", subdir = "r")
library(extracttext)

# The Python the engine will be built on, 3.10 or newer. NULL means R found
# none: install Python as "Before you start" says, restart RStudio, and run
# this line again before going on.
reticulate::virtualenv_starter(">=3.10")

# The path to git. An empty "" means git is missing; install it the same way.
Sys.which("git")

extracttext_install()

# Should print TRUE. FALSE means the install above stopped early; its last
# lines of output say why.
reticulate::virtualenv_exists("r-extracttext")

# Restart R so the package finds the engine: Session > Restart R in RStudio
# (Cmd/Ctrl + Shift + 0), or quit and reopen R. Step 2 fails without this.

# --------------------------------------------------------------------------
# Step 2. Check your setup
# --------------------------------------------------------------------------
# The last line should read "Ready: the deterministic engine can run." The
# AI section reports Ollama as missing unless you set it up; the rules
# engine does not need it.
library(extracttext)
library(dplyr) # install.packages("dplyr")

# Point R at the engine's own Python environment. Without this line, R picks
# up any other Python project it finds first (a ".venv" folder in your
# working directory, for one) and reports the engine as not installed. Run
# it at the start of every R session, before any other extract-text function.
reticulate::use_virtualenv("r-extracttext", required = TRUE)

extracttext_doctor()

# If it still says "The Python engine is not installed yet", restart R and
# run this step again from the top. If the message stays, step 1's install
# failed, most often because Python was missing or older than 3.10. Remove
# the half-built environment, then go back to step 1's Python check and run
# from there:
# reticulate::virtualenv_remove("r-extracttext")

# --------------------------------------------------------------------------
# Step 3. Read one example document
# --------------------------------------------------------------------------
# A made-up summons from the package's test files, scanned, so OCR reads it.
f <- file.path(tempdir(), "synthetic_summons_scanned.pdf")
download.file(paste0("https://raw.githubusercontent.com/evictionresearch/",
                     "extract-text/main/python/tests/fixtures/",
                     "synthetic_summons_scanned.pdf"),
              f, mode = "wb")

# Open the summons in your PDF viewer, to compare with what the engine reads
browseURL(f)

one <- extract_deterministic(f)

# Expect 1234 EXAMPLE AVE S APT 5, Seattle, WA 98100
one$record$defendant_address

# Problems the engine found; empty means none
one$flags

# Which rule found the address, and where on the page
one$evidence$defendant_address

# The same result as one row of the table a folder scan returns
glimpse(record_to_row(one))

# --------------------------------------------------------------------------
# Step 4. Scan a random 50 of your own documents
# --------------------------------------------------------------------------
# Start with a random sample rather than the whole folder: it takes minutes
# instead of hours, and step 6 grades every document in it. Change n_sample
# as needed; step 6 explains how many is enough.
#
# docs_dir holds the court documents (PDF or TIFF, subfolders included).
# If they come to you in a Google Drive folder, download that folder to
# your own computer first (Drive gives a zip; unzip it) and point docs_dir
# at the unzipped folder. Keep it, and results, out of any folder that
# syncs or is shared (not Dropbox, iCloud Drive, OneDrive, or a Google
# Drive folder that syncs to your computer): both hold tenants' names and
# addresses. Delete both when the round is over.
#
# results is where everything this script writes goes: the sample in
# results/sample, the full run in results/all, and the final table.
# Expect about 5 seconds a document when OCR is needed.
docs_dir <- "/Users/buffalo/data/evictionresearch/washington/court_images/King/2017"
results  <- "/Users/buffalo/data/evictionresearch/washington/ern_extract_text"
n_sample <- 50

sample_dir <- file.path(results, "sample")
all_dir    <- file.path(results, "all")

# seed = 1 draws the same documents every time you run it; another number
# draws a different sample
res <- scan_documents(docs_dir, engine = "deterministic", sample = n_sample,
                      seed = 1, out_dir = sample_dir)

# res is not ready to use yet. How often it is right on your documents is
# unknown until you grade the sample in step 6.

# --------------------------------------------------------------------------
# Step 5. Look at the results
# --------------------------------------------------------------------------
# Counts only, no names or addresses: whether the engine found a street,
# whether it flagged the document, and whether the PDF carried text
# (pdf_text_layer) or had to be read by OCR (pdf_ocr)
res %>%
	count(text_source,
	      found   = defendant_street != "",
	      flagged = flags != "")

# The values themselves. doc is the document's number on the review page.
View(select(res, doc, defendant_names, defendant_street, defendant_city,
            defendant_zip, flags))

# --------------------------------------------------------------------------
# Step 6. Grade the sample by hand (required)
# --------------------------------------------------------------------------
# The rules were written and measured on Washington filings. Another court's
# forms, scan quality, or decade can make them misread a field without
# raising a flag, and accuracy differs by field: on a random 50 King County
# summonses from 2017, the street was right about 85 percent of the time and
# the plaintiff about 40 percent (October 2026). Grading a random 50 puts
# the share right within about 10 points; grade 100 or more before
# publishing counts or sending anything to people (manual section 11).
# Your corrections do not change the engine. They tell you which fields to
# trust, and every document you grade carries your answer in the final
# table (step 13).
#
# This opens a page in your browser with each
# document beside what the engine read. Change only what is wrong, leave a
# field blank when the document does not have it, and save. Each save goes
# to corrections.jsonl in sample_dir. Press Esc in RStudio (Ctrl-C at a
# terminal) when done; running it again picks up where you left off.
review_documents(res, correct = TRUE, n = n_sample, draw = "random")

# --------------------------------------------------------------------------
# Step 7. Score the engine against your corrections
# --------------------------------------------------------------------------
# One row per field: how many documents you checked, and how many the engine
# got right, nearly right, left blank, or got wrong. right_random /
# checked_random is the accuracy estimate for the whole folder.
#
# Decide here whether the fields you need are accurate enough to scan
# everything. If they are not, check for a newer version of the package
# (rerun step 1): rule fixes reach you through package updates, made by the
# Eviction Research Network from its own graded documents. You can also
# change the rules on your own copy of the code: docs/changing_rules.md
# shows how, with a worked example. Grading alone does not change them.
score_documents(res)

# --------------------------------------------------------------------------
# Step 8. Scan the whole folder
# --------------------------------------------------------------------------
# The full run goes to its own folder, so the sample and its corrections
# stay as they are. At about 5 seconds a document, 4,000 documents take five
# or six hours; it needs no attention while it runs.
res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir)

# --------------------------------------------------------------------------
# Step 9. Grade a second random sample, from the full run
# --------------------------------------------------------------------------
# The first sample told you whether to run everything. This one measures the
# run that becomes your table, and it can catch kinds of documents the first
# sample happened to miss. Grade it the same way as step 6. A document you
# already graded may come up again; grade it again, and the later answer is
# the one kept. The draw is seeded, so building the page again shows the
# same documents; give seed another value for a fresh draw.
review_documents(res_all, correct = TRUE, n = n_sample, draw = "random", seed = 1)

# Optional: also fix every document the engine flagged, so the table
# carries a person's answer wherever the engine was unsure.
# review_documents(res_all, correct = TRUE, n = sum(res_all$flags != ""),
#                  draw = "flagged")

# --------------------------------------------------------------------------
# Step 10. Score the full run
# --------------------------------------------------------------------------
# right_random / checked_random here is the accuracy of the full run, the
# figure to report with the table.
score_documents(res_all)

# --------------------------------------------------------------------------
# Step 11. Teach the engine your forms (optional, no code)
# --------------------------------------------------------------------------
# Your graded documents can improve how the engine reads your own forms,
# with no change to any code. Where the engine's box on the review page was
# wrong or missing, you drew one (pick the field under the page, drag across
# the image, on whichever page the value is printed; a box can be moved,
# reshaped, deleted, or joined by another). learn_templates() groups the
# graded documents by printed form and writes, for each form with enough of
# them, a template: the form's printed words, which identify it, and a
# region of a page per field. It holds no names or addresses. Look at each
# template over a page it was learned from, approve the ones whose regions
# sit where the form prints those fields, and re-scan with the templates
# folder. The engine then looks there first on every document of that form,
# tagged "template:<name>" in defendant_anchor, and uses its own rules
# everywhere else. Nothing learned is used until you approve it.
#
# A template changes where the engine looks, not how it reads. The rules
# still do the reading inside each box. When a value is in the right box and
# still read wrong, a rule needs to change. Work with the Eviction Research
# Network on that (nothing from your records is sent; masked shapes from
# score_documents(res, save = ...) are enough), or change the rule on your
# own copy by docs/changing_rules.md. Ten to twenty graded documents per
# form is the figure the method comes from; the review page says when a
# template is thinner. The guide is "Teaching the engine a form, without
# code", the last chapter of docs/changing_rules.md.
# learn_templates(res_all)                      # writes results/all/templates/
# review_templates(res_all)                     # look, then approve the right ones
# approve_template("form-1", res_all)
# res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir,
#                           templates = file.path(all_dir, "templates"))
# score_documents(res_all)                      # what the templates fixed and broke

# --------------------------------------------------------------------------
# Step 12. Re-scan, only after the rules change
# --------------------------------------------------------------------------
# Grading does not change the rules engine: run it again on the same
# documents and it gives the same answers. The rules change only when you
# update the package (rerun step 1), which brings the fixes the Eviction
# Research Network makes from its own graded documents, or when you change
# them yourself (docs/changing_rules.md), or when you approve a form
# template (step 11). Re-scan only then. Re-scanning
# the same documents into the same folder keeps your corrections, and
# scoring again shows what the change fixed or broke.
# res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir)
# score_documents(res_all)

# --------------------------------------------------------------------------
# Step 13. Build the final table
# --------------------------------------------------------------------------
# One row per document: case number, plaintiff, defendants, and the
# defendants' address, with your graded answers (from both samples) in
# place of the engine's wherever you gave one. source says which each row
# carries. defendant_address_std is the address on one line in USPS form.
# The table holds names and addresses; keep it with the court documents.
cases <- case_table(res_all, graded = sample_dir,
                    save = file.path(results, "case_table.csv"))

# How many rows carry a graded answer, and how many the engine's reading
count(cases, source)

# The table is the input to the next stage of the pipeline: cleaning the
# names and addresses.

# --------------------------------------------------------------------------
# Next
# --------------------------------------------------------------------------
# The manual (docs/manual.md) covers every output column (section 10), the
# flags and the address check against a list of real addresses (section 11),
# the optional AI engine (section 6), and documents from outside Washington
# (section 16).
