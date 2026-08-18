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
