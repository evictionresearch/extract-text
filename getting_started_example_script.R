# ==========================================================================
# Getting started with extract-text in R: the deterministic engine
# Author: Tim Thomas
# Created: 2026-10-29
# Reviewer:
# Updated: 2026-11-09
#
# This script is the quick start script for the extract-text package using the
# rules engine only (no AI, no network). It installs the package, reads a
# made-up summons, reads a folder of your own documents, and checks the
# results by hand. Run it a line or a block at a time, not with source(),
# because step 1 ends by restarting R.
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
# Step 4. Read a folder of your own documents
# --------------------------------------------------------------------------
# docs_dir holds the court documents (PDF or TIFF, subfolders included).
# out_dir receives the results: extracted.csv, extracted.jsonl (the
# evidence behind every value), and the review page used in step 6.
# Expect about 5 seconds a document when OCR is needed.
docs_dir <- "path/to/your/documents"
out_dir  <- "path/to/your/results"

res <- scan_documents(docs_dir, engine = "deterministic", out_dir = out_dir)

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
# Step 6. Check a random 50 by hand
# --------------------------------------------------------------------------
# How accurate the engine is on your documents is unknown until a person
# checks a random sample. This opens a page in your browser with each
# document beside what the engine read. Change only what is wrong, leave a
# field blank when the document does not have it, and save. Each save goes
# to corrections.jsonl in out_dir. Press Esc in RStudio (Ctrl-C at a
# terminal) when done; running it again picks up where you left off.
review_documents(res, correct = TRUE, n = 50, draw = "random")

# --------------------------------------------------------------------------
# Step 7. Score the engine against your corrections
# --------------------------------------------------------------------------
# One row per field: how many documents you checked, and how many the engine
# got right, nearly right, left blank, or got wrong. right_random /
# checked_random is the accuracy estimate for the whole folder.
score_documents(res)

# --------------------------------------------------------------------------
# Next
# --------------------------------------------------------------------------
# The manual (docs/manual.md) covers every output column (section 10), the
# flags and the address check against a list of real addresses (section 11),
# the optional AI engine (section 6), and documents from outside Washington
# (section 16).
