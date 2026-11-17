# Run by the "install" job of the tests workflow, on a machine that has R and
# nothing else: no poppler, no tesseract, no Python set up for the package.
# It installs the engine the way a new user does and reads one made-up scan.
#
#   Rscript .github/scripts/install_check.R install   # builds the environment
#   Rscript .github/scripts/install_check.R use       # a fresh R session uses it
step <- commandArgs(trailingOnly = TRUE)[1]
library(extracttext)

if (step == "install") {
  extracttext_preflight()
  extracttext_install(source = "python")
}

if (step == "use") {
  ready <- extracttext_doctor()
  stopifnot("the checkup did not report the engine ready" = isTRUE(ready))
  documents <- reticulate::import("extract_text.documents")
  for (program in c("pdftotext", "pdftoppm", "pdfinfo", "tesseract")) {
    # the copy the engine runs is the one installed with the package
    stopifnot(isTRUE(documents$tool_is_own(program)))
  }
  one <- extract_deterministic("python/tests/fixtures/synthetic_summons_scanned.pdf")
  # the made-up scan is read by OCR, so this exercises poppler and tesseract
  stopifnot(one$record$defendant_address$street == "1234 EXAMPLE AVE S APT 5")
  stopifnot(one$record$defendant_address$zip == "98100")
  cat("Read the made-up scan with the copies installed with the package.\n")
}
