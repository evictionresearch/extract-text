# Fixtures are synthetic. Real court records never enter this repository.

synthetic <- paste(
  "IN THE SUPERIOR COURT OF THE STATE OF CALIFORNIA",
  "COUNTY OF ALAMEDA",
  "",
  "Case No. RG-24-108833",
  "",
  "ACME HOLDINGS LLC,",
  "                    Plaintiffs,",
  "v.",
  "JORDAN A. RIVERA,",
  "                    Defendants.",
  "",
  "COMPLAINT FOR UNLAWFUL DETAINER",
  "",
  "Date Filed: 03/14/2024",
  "Amount Claimed: $4,820.00",
  sep = "\n"
)

# The file fixtures live with the Python tests; present when running from a
# full clone of the repository, absent under R CMD check's isolated copy.
fixtures_dir <- testthat::test_path("..", "..", "..", "python", "tests", "fixtures")
have_fixture_files <- dir.exists(fixtures_dir)
have_system_tools <- all(nzchar(Sys.which(c("pdftotext", "pdfinfo", "pdftoppm"))))

test_that("deterministic extraction reads the caption and scalars", {
  skip_if_not(extracttext_available(), "Python engine not installed")

  out <- extract_deterministic(synthetic)

  expect_equal(out$record$case_number, "RG-24-108833")
  expect_equal(out$record$county, "ALAMEDA")
  expect_equal(out$method, "deterministic")
  expect_equal(out$record$plaintiffs[[1]]$name, "ACME HOLDINGS LLC")
  expect_true(out$record$plaintiffs[[1]]$is_business)
})

test_that("record_to_row returns one row with parsed dates", {
  skip_if_not(extracttext_available(), "Python engine not installed")

  row <- record_to_row(extract_deterministic(synthetic))

  expect_equal(nrow(row), 1L)
  expect_s3_class(row$filing_date, "Date")
  expect_equal(as.character(row$filing_date), "2024-03-14")
  expect_equal(row$amount_claimed, 4820)
  expect_equal(row$n_ungrounded, 0L)
})

test_that("comparing an extraction to itself agrees completely", {
  skip_if_not(extracttext_available(), "Python engine not installed")

  out <- extract_deterministic(synthetic)
  report <- compare_extractions(out, out)

  expect_equal(report$agreement_rate, 1)
  expect_length(report$needs_review, 0)
  expect_false(any(report$fields$status == "disagree"))
})

test_that("comparison rejects objects that are not extractions", {
  skip_if_not(extracttext_available(), "Python engine not installed")

  out <- extract_deterministic(synthetic)
  expect_error(compare_extractions(out, list(record = NULL)), "Expected a result")
})

test_that("a summons PDF extracts the address and attorney block", {
  skip_if_not(extracttext_available(), "Python engine not installed")
  skip_if_not(have_fixture_files, "fixture files not present (not a full clone)")
  skip_if_not(have_system_tools, "poppler not installed")

  out <- extract_deterministic(file.path(fixtures_dir, "synthetic_summons_efiled.pdf"))

  expect_equal(out$record$case_number, "25-2-00001-0")
  expect_equal(out$record$defendant_address$street, "1234 EXAMPLE AVE S APT 5")
  expect_equal(out$record$defendant_address$zip, "98100")
  expect_equal(out$record$attorney$firm, "EXAMPLE LAW GROUP PLLC")
  expect_equal(out$record$attorney$address$street, "100 MAIN ST STE 200")
  expect_length(out$flags, 0)
  expect_equal(out$evidence$defendant_address$anchor, "to_block")
})

test_that("scan_documents returns one tidy row per file and writes outputs", {
  skip_if_not(extracttext_available(), "Python engine not installed")
  skip_if_not(have_fixture_files, "fixture files not present (not a full clone)")
  skip_if_not(have_system_tools, "poppler not installed")

  out_dir <- file.path(tempdir(), "extracttext-test-scan")
  results <- scan_documents(
    file.path(fixtures_dir, "synthetic_summons_efiled.pdf"),
    out_dir = out_dir
  )

  expect_equal(nrow(results), 1L)
  expect_equal(results$case_number, "25-2-00001-0")
  expect_equal(results$defendant_street, "1234 EXAMPLE AVE S APT 5")
  expect_equal(results$defendant_zip, "98100")
  expect_equal(results$method, "deterministic")
  expect_true(file.exists(file.path(out_dir, "extracted.csv")))
  expect_true(file.exists(file.path(out_dir, "extracted.jsonl")))
  expect_identical(attr(results, "out_dir"), out_dir)
})

test_that("scan_documents with a progress bar returns the same rows", {
  skip_if_not(extracttext_available(), "Python engine not installed")
  skip_if_not(have_fixture_files, "fixture files not present (not a full clone)")
  skip_if_not(have_system_tools, "poppler not installed")

  files <- file.path(fixtures_dir, c("synthetic_summons_efiled.pdf", "synthetic_kc_efiled.pdf"))
  quiet <- scan_documents(files, out_dir = file.path(tempdir(), "et-quiet"), progress = FALSE)
  old <- options(cli.dynamic = TRUE)
  on.exit(options(old), add = TRUE)
  shown <- scan_documents(files, out_dir = file.path(tempdir(), "et-shown"), progress = TRUE)
  expect_equal(nrow(shown), 2L)
  expect_identical(shown$defendant_street, quiet$defendant_street)
})

test_that("scan results carry the review page's doc number and text flags", {
  skip_if_not(extracttext_available(), "Python engine not installed")
  skip_if_not(have_fixture_files, "fixture files not present (not a full clone)")
  skip_if_not(have_system_tools, "poppler not installed")

  files <- file.path(fixtures_dir, c("synthetic_summons_efiled.pdf", "synthetic_kc_efiled.pdf"))
  res <- scan_documents(files, out_dir = file.path(tempdir(), "et-doc"), progress = FALSE)
  expect_identical(res$doc, 1:2)
  expect_type(res$flags, "character")
  expect_type(res$n_pages, "integer")

  # a field no document has stays text, not an all-NA logical column
  no_unit <- scan_documents(file.path(fixtures_dir, "synthetic_kc_efiled.pdf"),
                            out_dir = file.path(tempdir(), "et-no-unit"), progress = FALSE)
  expect_identical(no_unit$defendant_unit, "")
})

test_that("review_documents looks, refuses to wait in a script, and score_documents scores", {
  skip_if_not(extracttext_available(), "Python engine not installed")
  skip_if_not(have_fixture_files, "fixture files not present (not a full clone)")
  skip_if_not(have_system_tools, "poppler not installed")

  out_dir <- file.path(tempdir(), "et-review")
  res <- scan_documents(file.path(fixtures_dir, "synthetic_summons_efiled.pdf"),
                        out_dir = out_dir, progress = FALSE)
  expect_identical(suppressMessages(review_documents(res, open = FALSE)), out_dir)
  expect_true(file.exists(file.path(out_dir, "review", "index.html")))
  expect_error(review_documents(res, correct = TRUE, open = FALSE), "interactive")

  # a random draw records every document on the page as drawn at random
  suppressMessages(review_documents(res, n = Inf, draw = "random", open = FALSE))
  drawn <- reticulate::import("json")$loads(
    readChar(file.path(out_dir, "review", "sample.json"), 1e6))
  expect_true(all(unlist(drawn) == "random"))

  empty <- suppressMessages(score_documents(res))
  expect_equal(nrow(empty), 0L)
  expect_named(empty, c("engine", "field", "checked", "right", "near", "blank",
                        "wrong", "checked_random", "right_random"))

  pl <- reticulate::import("extract_text.pipeline")
  cr <- reticulate::import("extract_text.corrections")
  scan <- pl$read_scan(out_dir)
  truth <- list(plaintiff = "EXAMPLE PROPERTY LLC",
                defendants = list("JANE Q. TENANT", "JON Q. TENANT"),
                street = "1234 EXAMPLE AVE S APT 5", unit = "APT 6", city = "SEATTLE",
                state = "WA", zip = "98100")
  saved <- cr$build_correction(1L, list(truth = truth), scan[[1]], scan[[2]], out_dir)
  writeLines(reticulate::import("json")$dumps(saved), file.path(out_dir, "corrections.jsonl"))

  report <- file.path(tempdir(), "et-score.txt")
  scored <- score_documents(res, save = report)
  expect_identical(attr(scored, "reviewed"), 1L)
  unit <- scored[scored$engine == "deterministic" & scored$field == "unit", ]
  expect_equal(unit$right, 0L)
  zip <- scored[scored$engine == "deterministic" & scored$field == "zip", ]
  expect_equal(zip$right, 1L)
  expect_false(any(grepl("EXAMPLE|TENANT", readLines(report))))
})
