# ==========================================================================
# Demo walk through of extract-text: the deterministic engine, from R
# Author: Tim Thomas
# Created: 2026-10-29
# Reviewer:
# Updated: 2026-10-29
#
# What this does. Installs the package the way a new user (King County DCHS
# is the example) would get it from GitHub, checks the machine, reads one
# synthetic summons, then reads a sample of real King County summonses with
# the rules engine only, so a person can check the results by hand.
#
# Run it a line or a block at a time, not with source(): step 2 restarts R.
#
# Privacy. Steps 1 to 4 touch only a synthetic document. From step 5 on, the
# documents and every output file hold tenants' names and addresses. Keep
# all of it on governed storage (out_dir below), never in this repository.
# ==========================================================================

# --------------------------------------------------------------------------
# Step 1. Clean up prior versions
# --------------------------------------------------------------------------
# The R package runs a Python engine inside a private Python environment
# named "r-extracttext" (stored in ~/.virtualenvs). Removing it means the
# install below starts from nothing, exactly as on a new machine. It asks
# you to confirm. Skip this on a machine that never had the package.
reticulate::virtualenv_remove("r-extracttext")

# --------------------------------------------------------------------------
# Step 2. Install
# --------------------------------------------------------------------------
# Two things get installed. remotes::install_github() fetches the R package
# (the functions you call). extracttext_install() builds the private Python
# environment and puts the engine in it; this happens once per machine and
# took about 20 seconds in testing.
#
# Not installed by either: poppler (opens PDFs) and tesseract (reads scanned
# pages, OCR). They come from the system, e.g. `brew install poppler
# tesseract` on a Mac. On a county Windows machine this is usually the
# hardest step; extracttext_doctor() in step 3 names anything missing.
# install.packages("remotes") # uncomment if remotes is not installed yet
remotes::install_github("evictionresearch/extract-text", subdir = "r")
library(extracttext)
extracttext_install()

# Restart R so the package finds the new Python environment. In RStudio,
# Session > Restart R (Cmd/Ctrl + Shift + 0) does it without closing
# anything. quit() ends the session; reopen R and carry on from step 3.
quit(save = "no")

# --------------------------------------------------------------------------
# Step 3. Check the machine
# --------------------------------------------------------------------------
# The checkup reads none of your documents and uses no network. The line
# that matters is the last one: "Ready: the deterministic engine can run."
# The AI section can be ignored for a rules-only setup; on a machine where
# AI is not allowed it will show ollama as missing, which is fine.
library(extracttext)
# install.packages("tidyverse") # uncomment if you haven't installed tidyverse
library(tidyverse)
extracttext_doctor()

# --------------------------------------------------------------------------
# Step 4. Read one synthetic document
# --------------------------------------------------------------------------
# A made-up King County style summons from the repository (no real person
# in it): a printed form that was scanned, so OCR has to read it. It goes
# to R's temporary folder, which is emptied when R closes.
f <- file.path(tempdir(), "synthetic_kc_printed_scanned.pdf")
download.file(
	paste0(
		"https://raw.githubusercontent.com/evictionresearch/extract-text/",
		"main/python/tests/fixtures/synthetic_kc_printed_scanned.pdf"),
	f,
	mode = "wb")

# extract_deterministic() reads one file with the rules engine. The result
# is a list: $record holds the fields, $flags any problems found (empty is
# good), $evidence where each field came from.
one <- extract_deterministic(f)

# Expect 1234-EXAMPLE AVE. NE BLDG ZZ Apt # 102, Sampleton, WA 98100
one$record$defendant_address

# Which rule found the address, and where on the page (the audit trail)
one$evidence$defendant_address

# The same result as one row, with the columns a batch run writes
record_to_row(one) %>% glimpse()

# --------------------------------------------------------------------------
# Step 5. Pick real documents
# --------------------------------------------------------------------------
# docs_dir is where the court PDFs live. Here it is ERN's 2017 King County
# folder (the newest King year on disk, so the closest to today's filings):
# one folder per case, named for the case number, each holding the summons.
# A county user points docs_dir at its own folder instead.
docs_dir <- path.expand("~/data/evictionresearch/washington/court_images/King/2017")

# out_dir is where results go: governed storage, one dated folder per run.
train   <- path.expand("~/data/evictionresearch/washington/development/extract_text_training")
out_dir <- file.path(train, "_kc_walkthrough_50_2026-10-29")

# Every PDF under docs_dir, case folders included (4,091 for 2017)
pdfs <- list.files(docs_dir, pattern = "\\.pdf$", recursive = TRUE,
                   full.names = TRUE, ignore.case = TRUE)
length(pdfs)

# ERN only (a county user skips this block). Leave out the documents already
# in grading rounds 1 and 2. Round 2's random 200 are the held-out test set
# for tuning the rules, so they must not be looked at now. Matching is by
# full path: in this collection the case number is the folder name and the
# file names repeat (the 2017 folder has only 9 distinct file names), so
# matching on file name alone drops nearly every document. Each scan's
# extracted.jsonl records the full path in its "file" field.
rounds <- c("_grading_round_1_2026-09-30", "_grading_round_2_random_2026-10-26",
            "_grading_round_2_hard_2026-10-26")
graded <- map(rounds, function(d) {
	lines <- read_lines(file.path(train, d, "extracted.jsonl"))
	map_chr(lines, function(l) jsonlite::parse_json(l)$file)
}) %>% unlist()
pdfs <- pdfs[!normalizePath(pdfs) %in% normalizePath(graded, mustWork = FALSE)]

# 3,959 left for 2017 (132 were in a grading round)
length(pdfs)

# A reproducible random draw of 50, the calibration batch. The same seed
# always picks the same documents, and the first 25 of these 50 are the 25
# this seed gave before.
set.seed(20261029)
pick <- sample(pdfs, 50)

# --------------------------------------------------------------------------
# Step 6. Run the rules engine
# --------------------------------------------------------------------------
# scan_documents() reads every file in `pick` and returns one row per
# document. engine = "deterministic" is rules only: no AI, no network.
#
# A progress bar shows documents done, time elapsed, and an estimate of the
# time left. About 5 seconds a document when OCR is needed, so about four
# minutes for 50.
#
# Written to out_dir: extracted.csv (the table), extracted.jsonl (every
# field's evidence), and extracted.parquet. The first column of res, doc,
# is each document's number on the review page in step 8 (#1, #2, ...).
res <- scan_documents(pick, engine = "deterministic", out_dir = out_dir)

# --------------------------------------------------------------------------
# Step 7. Read the results
# --------------------------------------------------------------------------
# found: the engine returned a street. flagged: it raised at least one
# warning. text_source: pdf_text_layer means the PDF carried digital text;
# pdf_ocr means tesseract had to read a picture of the page.
#
# This count table holds no names or addresses; it is safe to share.
res %>%
	mutate(found   = defendant_street != "",
	       flagged = flags != "") %>%
	count(text_source, found, flagged)

# The flags raised, and how often
res %>%
	filter(flags != "") %>%
	separate_longer_delim(flags, ";") %>%
	count(flags, sort = TRUE)

# The values themselves, for your eyes only. defendant_anchor names the rule
# that found the address. Note that defendant_unit repeats what is already
# inside defendant_street; use street alone for the full street line.
look <- res %>%
	select(doc, defendant_names, defendant_street, defendant_unit,
	       defendant_city, defendant_zip, defendant_anchor, flags)

# In RStudio this opens the data viewer. In R at a terminal, View() needs
# X11, so the table prints in the console instead, every row and column.
if (.Platform$GUI == "RStudio") View(look) else print(look, n = Inf, width = Inf)

# For a spreadsheet view anywhere, open the run's full table in the
# computer's default app for CSV files (Excel or Numbers, say). It holds
# every column, names and addresses included.
# browseURL(file.path(out_dir, "extracted.csv"))

# --------------------------------------------------------------------------
# Step 8. Check the results against the page images
# --------------------------------------------------------------------------
# The review page shows each document's first page beside what the engine
# read, flagged documents first, numbered to match res$doc.
#
# To look only (nothing is saved):
review_documents(res, correct = TRUE)

# To correct the calibration batch: all 50, drawn at random (draw =
# "random"), so the share right is a fair estimate. The page is served from
# this computer only and every save is
# written at once to corrections.jsonl in out_dir. On each document, change
# only what the engine got wrong and save; when it got everything right,
# save as it is. Leave a field blank when the document does not have it.
# R waits while you work: press Esc in RStudio, or Ctrl-C at a terminal,
# when finished. Running it again picks up where you left off.
#
# Without draw = "random" the page puts flagged documents first, which
# finds failures faster but understates accuracy.
review_documents(res, correct = TRUE, n = 50, draw = "random")

# --------------------------------------------------------------------------
# Step 9. Score the engine against your corrections
# --------------------------------------------------------------------------
# One row per field: documents checked, right, near (nearly right, such as
# a spelling difference), blank (the engine found nothing where the
# document had a value), and wrong. Flagged documents are the hard ones and
# come first on the page, so right / checked understates accuracy for the
# whole scan; right_random / checked_random covers the randomly drawn
# documents alone.
#
# save writes the full report with every value masked (letters become A/a,
# digits 9), so it can be shared and brought back to a working session.
score <- score_documents(res, save = path.expand(
	"~/offline/evictionresearch/extract-text/notes/2026-10-29_score_kc_walkthrough.txt"))
score

# --------------------------------------------------------------------------
# Next steps
# --------------------------------------------------------------------------
# 1. Bring back the step 7 count tables and the step 9 table or saved
#    report (counts and masked values only).
# 2. Rule fixes are made and tested on the synthetic documents, then this
#    run is repeated on the same 25 (same seed) to see what changed.
# 3. A county running this on current filings should report the same two
#    count tables; ERN's King documents run 2004 to 2017.
