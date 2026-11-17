# ==========================================================================
# Getting started with extract-text in R: the rules engine
# Author: Tim Thomas
# Created: 2026-10-29
# Reviewer:
# Updated: 2026-11-17
#
# The eight steps of the Get started page, as code:
#   https://evictionresearch.net/extract-text/get-started.html
# That page and docs/start_here.md explain each step. This script holds the
# code and one-line notes. Run it a line or a block at a time (Cmd + Return
# on a Mac, Ctrl + Enter on Windows), not with source(): step 2 restarts R
# partway through.
#
# Your documents, and every file this script writes from step 4 on, hold
# tenants' names and addresses. Keep them where your organization keeps the
# court documents, and out of any folder that syncs or is shared.
# ==========================================================================

# --------------------------------------------------------------------------
# Step 1. Install three free programs (once per computer)
# --------------------------------------------------------------------------
# poppler, tesseract, and Python 3.10 or newer. They are installed outside
# R, in Terminal or PowerShell; the Get started page has the lines for Mac,
# Windows, and Linux.
#
# Update your computer first if it is old. On a Mac, Homebrew has poppler
# and tesseract ready-made only for macOS 15 (Sequoia) or later on an Apple
# chip. On a PC you need Windows 10 version 1809 or later. The page says how
# to check and how to update.

# --------------------------------------------------------------------------
# Step 2. Install extract-text and check your setup
# --------------------------------------------------------------------------
# install.packages(c("remotes", "dplyr")) # if you don't have them yet
remotes::install_github("evictionresearch/extract-text", subdir = "r")
library(extracttext)

# The Python the engine will be built on, 3.10 or newer. NULL means R found
# none: install Python (step 1), restart RStudio, and run this line again.
reticulate::virtualenv_starter(">=3.10")

# Installs the engine, once per computer. It is finished when the Console
# shows "Done. Restart R, then run extracttext_doctor()."
extracttext_install()

# Restart R (Session > Restart R), then carry on from here
library(extracttext)
library(dplyr)

# The last line should read "Ready: the deterministic engine can run."
extracttext_doctor()

# --------------------------------------------------------------------------
# Step 3. Read one example document
# --------------------------------------------------------------------------
# A made-up summons from the package's test files
f <- file.path(tempdir(), "synthetic_summons_scanned.pdf")
download.file(paste0("https://raw.githubusercontent.com/evictionresearch/",
                     "extract-text/main/python/tests/fixtures/",
                     "synthetic_summons_scanned.pdf"),
              f, mode = "wb")

# Open the summons, to compare with what the engine reads
browseURL(f)

one <- extract_deterministic(f)

# Expect 1234 EXAMPLE AVE S APT 5, Seattle, WA 98100
one$record$defendant_address

# Problems the engine found; empty means none
one$flags

# --------------------------------------------------------------------------
# Step 4. Scan a random 50 of your own documents
# --------------------------------------------------------------------------
# docs_dir holds your court documents (PDF or TIFF, subfolders included).
# results is a new folder where everything from here on is written. To
# practice on made-up documents first, see step 4 of the Get started page.
docs_dir <- "path/to/your/documents"
results  <- "path/to/your/results"
n_sample <- 50

sample_dir <- file.path(results, "sample")
all_dir    <- file.path(results, "all")

# seed = 1 draws the same documents every time
res <- scan_documents(docs_dir, engine = "deterministic", sample = n_sample,
                      seed = 1, out_dir = sample_dir)

# Counts only: whether the engine found a street and whether it raised a flag
res %>%
  count(text_source,
        found   = defendant_street != "",
        flagged = flags != "")

# --------------------------------------------------------------------------
# Step 5. Grade the sample by hand (required), then score the engine
# --------------------------------------------------------------------------
# Opens the review page in your browser. Check each field, fix the boxes,
# and save every document. Press Esc in RStudio when done; running the line
# again picks up where you left off. GRADING.md says what belongs in each
# field.
review_documents(res, correct = TRUE, n = n_sample, draw = "random")

# One row per field: how many you checked, and how many the engine got right
score_documents(res)

# --------------------------------------------------------------------------
# Step 6. Teach the engine your forms (optional, no code)
# --------------------------------------------------------------------------
# Writes a template for each printed form with at least five graded documents
learn_templates(res)

# Opens a page showing each template over a page it was learned from
review_templates(res)

# Approve each template whose regions are right, by the name on that page
# approve_template("form-1", res)

# The templates and whether each is approved
list_templates(sample_dir)

# --------------------------------------------------------------------------
# Step 7. Scan the whole folder, then grade and score a second 50
# --------------------------------------------------------------------------
# Uses the templates you approved in step 6, and the rules alone if none
templates_dir <- file.path(sample_dir, "templates")
use_templates <- dir.exists(templates_dir) &&
  any(list_templates(templates_dir)$approved)

res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir,
                          templates = if (use_templates) templates_dir)

# Grade a second random sample, from the full run, the same way as step 5
review_documents(res_all, correct = TRUE, n = n_sample, draw = "random", seed = 1)

# The accuracy of the full run, the figure to report with the table
score_documents(res_all)

# --------------------------------------------------------------------------
# Step 8. Build the final table
# --------------------------------------------------------------------------
# One row per document, with your graded answers in place of the engine's
cases <- case_table(res_all, graded = sample_dir,
                    save = file.path(results, "case_table.csv"))

# How many rows carry a graded answer, and how many the engine's reading
count(cases, source)

# --------------------------------------------------------------------------
# Later: scan again only after something changes
# --------------------------------------------------------------------------
# Grading does not change the engine. Scan again only after you update the
# package, change a rule, or approve a template (docs/start_here.md, "What
# grading does"). A scan into the same folder keeps your corrections.
# res_all <- scan_documents(docs_dir, engine = "deterministic", out_dir = all_dir,
#                           templates = if (use_templates) templates_dir)
# score_documents(res_all)
