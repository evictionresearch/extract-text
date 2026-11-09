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

# --------------------------------------------------------------------------
# Step 1. Install extract-text
# --------------------------------------------------------------------------
# install_github() fetches the R package. extracttext_install() then builds
# the Python engine the package runs on, once per computer.
# install.packages(c("remotes", "dplyr")) # if you don't have them yet
# remove.packages("extracttext") # if you have an older version installed
remotes::install_github("evictionresearch/extract-text", subdir = "r")
library(extracttext)
extracttext_install()

# Restart R so the package finds the engine: Session > Restart R in RStudio
# (Cmd/Ctrl + Shift + 0), or quit and reopen R.

# --------------------------------------------------------------------------
# Step 2. Check your setup
# --------------------------------------------------------------------------
# The last line should read "Ready: the deterministic engine can run." The
# AI section reports Ollama as missing unless you set it up; the rules
# engine does not need it.
library(extracttext)
library(dplyr)
extracttext_doctor()

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
# results is where everything this script writes goes: the sample in
# results/sample, the full run in results/all, and the final table.
# Expect about 5 seconds a document when OCR is needed.
docs_dir <- "path/to/your/documents"
results  <- "path/to/your/results"
n_sample <- 50

sample_dir <- file.path(results, "sample")
all_dir    <- file.path(results, "all")

# seed = 1 draws the same documents every time you run it
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
# table (step 12).
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
# the one kept.
review_documents(res_all, correct = TRUE, n = n_sample, draw = "random")

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
# Step 11. Re-scan, only after the rules change
# --------------------------------------------------------------------------
# Grading does not change the rules engine: run it again on the same
# documents and it gives the same answers. The rules change only when you
# update the package (rerun step 1), which brings the fixes the Eviction
# Research Network makes from its own graded documents, or when you change
# them yourself (docs/changing_rules.md). Re-scan only then. Re-scanning
# the same documents into the same folder keeps your corrections, and
# scoring again shows what the change fixed or broke.
# res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir)
# score_documents(res_all)

# --------------------------------------------------------------------------
# Step 12. Build the final table
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
