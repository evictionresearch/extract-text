# ==========================================================================
# Getting started with extract-text in R: the deterministic engine
# Author: Tim Thomas
# Created: 2026-10-29
# Reviewer:
# Updated: 2026-11-17
#
# This script is the quick start script for the extract-text package using the
# rules engine only (no AI, no network). It installs the package, reads a
# made-up summons, scans a random 50 of your own documents, has you grade
# those 50 by hand, learns where your court's forms print each field from
# that grading, scans the whole folder, has you grade a second random 50
# from it, and builds the final table of cases, names, and addresses. The
# grading is not optional: until it is done, how often the scan is right on
# your documents is unknown (step 5 says why). Run it a line or a block at a
# time, not with source(), because step 2 restarts R partway through.
#
# The eight steps here are the eight steps of the Get started page,
# https://evictionresearch.net/extract-text/get-started.html, and of
# docs/start_here.md. Step 5 means the same thing in all three.
#
# Your documents, and every file this script writes from step 4 on, hold
# tenants' names and addresses. Keep them wherever your organization keeps
# the court documents themselves.
# ==========================================================================

# --------------------------------------------------------------------------
# Step 1. Install four free programs (once per computer)
# --------------------------------------------------------------------------
# extract-text cannot read a document without two free programs that R does
# not install: poppler opens PDFs, and tesseract reads scanned pages (OCR).
# Both Mac and Windows need them. Install them outside R, then open RStudio.
#
# Check first whether you have them: run `which pdftoppm tesseract` in
# Terminal (Mac, Linux) or `where.exe pdftoppm tesseract` in PowerShell
# (Windows). If both print a path, you have those two. On a Mac, brew install on
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
# or newer, and git, which the install in step 2 downloads the engine with.
# The Python that comes with a Mac is older than 3.10. Step 2 checks for
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
# Step 2. Install extract-text and check your setup
# --------------------------------------------------------------------------
# install_github() fetches the R package. extracttext_install() then builds
# the Python engine the package runs on, once per computer.
# install.packages(c("remotes", "dplyr")) # if you don't have them yet
# Only if you have an older version installed (it stops with an error on a
# computer that has never had the package):
# remove.packages("extracttext")
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
# (Cmd/Ctrl + Shift + 0), or quit and reopen R. The checkup below fails
# without this.

# Check your setup. The last line should read "Ready: the deterministic engine can run." The
# AI section reports Ollama as missing unless you set it up; the rules
# engine does not need it.
library(extracttext)
library(dplyr) # install.packages("dplyr")

extracttext_doctor()

# If it says "The Python engine is not installed yet", restart R and run the
# checkup again. If the message stays, the install above failed, most often
# because Python was missing or older than 3.10. Remove the half-built
# environment, then go back to the Python check at the top of this step and
# run from there:
# reticulate::virtualenv_remove("r-extracttext")
#
# The package points R at the engine's own Python environment each time it
# loads. If you have told R to use another Python (RETICULATE_PYTHON, or a
# reticulate::use_python() line), the engine will look uninstalled; this
# line, run before any other extract-text function, points R back:
# reticulate::use_virtualenv("r-extracttext", required = TRUE)

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
# instead of hours, and step 5 grades every document in it. Change n_sample
# as needed; step 5 explains how many is enough.
#
# To practice first. Steps 4 to 8 run on the package's made-up documents as
# well as on real ones, so you can learn the grading page before you open a
# court record. This block downloads the package's code (about 10 MB) into
# a folder in your home directory and points docs_dir and results at it.
# Run it, skip the docs_dir and results lines below, and go on from
# n_sample. The 15 documents are few and partly repeat one another, so the
# scores mean nothing; the practice is in the steps. Delete the folder when
# you are done.
# practice <- path.expand("~/extract_text_practice")
# dir.create(practice, showWarnings = FALSE)
# download.file(paste0("https://github.com/evictionresearch/extract-text/",
#                      "archive/refs/heads/main.zip"),
#               file.path(practice, "extract-text.zip"), mode = "wb")
# unzip(file.path(practice, "extract-text.zip"), exdir = practice)
# docs_dir <- file.path(practice, "extract-text-main", "python", "tests",
#                       "fixtures")
# results  <- file.path(practice, "results")
#
# What to put in the folder. The engine reads one document at a time and
# writes one row for every file it is given, whatever kind of document the
# file is. Its rules are built for the summons. If your folder holds whole
# case files (complaints, orders, returns of service), a case gets a row for
# each of them. When the file names say which documents are summonses, scan
# those alone by giving scan_documents() the list of files in place of
# docs_dir:
# summonses <- list.files(docs_dir, pattern = "summons", ignore.case = TRUE,
#                         recursive = TRUE, full.names = TRUE)
#
# Documents from outside Washington. The rules that read the city and the
# state expect "WA" or "Washington" after the city. On a made-up Oregon
# summons and a made-up Texas one, the engine read the street, the unit,
# and the ZIP, left the city and state blank, and raised no flag. Every
# document you grade carries your city and state in the final table; the
# others carry the street and ZIP alone. docs/changing_rules.md, "Documents
# from another state", shows the four-line change that makes the engine
# read your state, and how to measure it.
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
docs_dir <- "path/to/your/documents"
results  <- "path/to/your/results"
n_sample <- 50

sample_dir <- file.path(results, "sample")
all_dir    <- file.path(results, "all")

# seed = 1 draws the same documents every time you run it; another number
# draws a different sample
res <- scan_documents(docs_dir, engine = "deterministic", sample = n_sample,
                      seed = 1, out_dir = sample_dir)

# res is not ready to use yet. How often it is right on your documents is
# unknown until you grade the sample in step 5.

# Look at the results. Counts only, no names or addresses: whether the engine found a street,
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
# Step 5. Grade the sample by hand (required), then score the engine
# --------------------------------------------------------------------------
# The rules were written and measured on Washington filings. Another court's
# forms, scan quality, or decade can make them misread a field without
# raising a flag, and accuracy differs by field: on a random 50 King County
# summonses from 2017, the street was right about 85 percent of the time and
# the plaintiff about 40 percent (October 2026). Grading a random 50 puts
# the share right within about 10 points; grade 100 or more before
# publishing counts or sending anything to people (manual section 11).
# Your corrections do not change the engine's rules. They do three things.
# The score below tells you which fields to trust. Every document you
# grade carries your answer in the final table (step 8). And the boxes on
# the page image can teach the engine where your court's form prints each
# field (step 6).
#
# This opens a page in your browser with each document beside what the
# engine read. Check each field against the page, change only what is
# wrong, and leave a field blank when the document does not have it. Then
# look at the colored boxes on the page image, which show where the engine
# read each value. Where a box sits over the wrong place, drag it to the
# right one. Where a field has no box, press the field's button under the
# image and drag across the value. GRADING.md says what belongs in each
# field, and docs/grading_with_boxes.md covers the boxes. Save every
# document, even when the engine got everything right.
# Each save goes to corrections.jsonl in sample_dir. Press Esc in RStudio
# (Ctrl-C at a terminal) when done; running it again picks up where you
# left off.
review_documents(res, correct = TRUE, n = n_sample, draw = "random")

# Score the engine against your corrections. One row per field: how many
# documents you checked, and how many the engine got right, nearly right
# (the right content, written differently, such as Ave for Avenue), left
# blank, or got wrong. right_random / checked_random is the accuracy
# estimate for the whole folder.
#
# Reading it. Say the street row shows checked_random 50 and right_random
# 43. The engine read the street right on 43 of your 50 documents, 86
# percent. Fifty documents is a small sample, so the share for the whole
# folder is probably between about 76 and 96 percent. No score is right for
# everyone. Ask what the table is for: a count of filings by ZIP code can
# live with a street that is wrong one time in seven, and a mailing to
# tenants cannot. Look only at the fields you will use, and grade those
# with care. A field you leave as the engine filled it is counted as right.
#
# When a field you need is weak:
# - The engine looked in the wrong place (its box sat over the wrong part
#   of the page, or the field had no box). Step 6 can fix that for your
#   court's forms, with no code.
# - The box was in the right place and the value was still wrong. A rule
#   has to change. Check for a newer version of the package (rerun the
#   install in step 2): rule fixes reach you through package updates, made
#   by the Eviction Research Network from its own graded documents. Or tell
#   the Network what goes wrong, or change the rule on your own copy:
#   https://evictionresearch.net/extract-text/improve.html and
#   docs/changing_rules.md show how. Grading alone does not change a rule.
# - Whatever the score, every document you grade is right in the final
#   table. For a small folder, grading all of it is a sound plan.
score_documents(res)

# --------------------------------------------------------------------------
# Step 6. Teach the engine your forms (optional, no code)
# --------------------------------------------------------------------------
# The boxes from step 5 can improve how the engine reads your court's own
# forms, with no change to any code. learn_templates() groups the documents
# you graded by printed form. For each form with at least five graded
# documents it writes a template: the form's printed words, which identify
# it, and a region of a page for each field. A template holds no names or
# addresses.
#
# Expect templates only for the forms your court uses most. A random 50
# rarely holds five of a rare form. The report names every form that had too
# few, and the engine reads those with its rules alone. If your court uses
# many forms, a larger first sample (n_sample in step 4) covers more of them.
learn_templates(res)

# Opens a page showing each template's regions over a page it was learned
# from. Check that each region sits where the form prints that field.
review_templates(res)

# Approve each template whose regions are right, by the name on that page.
# Nothing learned is used until you approve it.
# approve_template("form-1", res)

# The templates and whether each is approved
list_templates(sample_dir)

# A template changes where the engine looks, not how it reads. The rules
# still do the reading inside each region. When a value is in the right
# place and still read wrong, a rule needs to change: check for a newer
# version of the package (rerun the install in step 2), or see
# docs/changing_rules.md. Its
# last chapter, "Teaching the engine a form, without code", is the full
# guide to templates.

# --------------------------------------------------------------------------
# Step 7. Scan the whole folder, then grade and score a second 50
# --------------------------------------------------------------------------
# The full run goes to its own folder, so the sample and its corrections
# stay as they are. At about 5 seconds a document, 4,000 documents take five
# or six hours; it needs no attention while it runs.
#
# The run uses the templates you approved in step 6, and the rules alone if
# you approved none.
templates_dir <- file.path(sample_dir, "templates")
use_templates <- dir.exists(templates_dir) &&
  any(list_templates(templates_dir)$approved)

res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir,
                          templates = if (use_templates) templates_dir)

# How many documents matched each template (blank means none)
count(res_all, template)

# Grade a second random sample, from the full run. The first sample told
# you whether to run everything. This one measures the
# run that becomes your table, templates included, and it can catch kinds of
# documents the first sample happened to miss. Grade it the same way as
# step 5. A document you already graded may come up again; grade it again,
# and the later answer is the one kept. The draw is seeded, so building the
# page again shows the same documents; give seed another value for a fresh
# draw.
review_documents(res_all, correct = TRUE, n = n_sample, draw = "random", seed = 1)

# Optional: also fix every document the engine flagged, so the table
# carries a person's answer wherever the engine was unsure.
# review_documents(res_all, correct = TRUE, n = sum(res_all$flags != ""),
#                  draw = "flagged")

# Score the full run. right_random / checked_random here is the accuracy of
# the full run, the figure to report with the table.
score_documents(res_all)

# --------------------------------------------------------------------------
# Step 8. Build the final table
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
# Later: scan again only after something changes
# --------------------------------------------------------------------------
# Grading does not change the rules engine: run it again on the same
# documents and it gives the same answers. Its readings change only when you
# update the package (rerun the install in step 2), which brings the fixes
# the Eviction Research Network makes from its own graded documents, or when
# you change the rules yourself (docs/changing_rules.md), or when you
# approve or withdraw a form template (step 6). Re-scan only then.
# Re-scanning the same documents into the same folder keeps your
# corrections, and scoring again shows what the change fixed or broke.
# res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir,
#                           templates = if (use_templates) templates_dir)
# score_documents(res_all)

# --------------------------------------------------------------------------
# Next
# --------------------------------------------------------------------------
# The manual (docs/manual.md) covers every output column (section 10), the
# flags and the address check against a list of real addresses (section 11),
# the experimental local AI engine (section 6), and documents from outside
# Washington (section 16).
