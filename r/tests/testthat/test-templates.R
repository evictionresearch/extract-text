# Form templates: the R surface over extract_text.templates. The learning
# itself is tested on synthetic pages in python/tests/test_templates.py;
# these checks cover the plumbing a user touches from R.

fixtures_dir <- testthat::test_path("..", "..", "..", "python", "tests", "fixtures")
have_fixture_files <- dir.exists(fixtures_dir)
have_system_tools <- all(nzchar(Sys.which(c("pdftotext", "pdfinfo", "pdftoppm"))))

# A minimal template file written without a JSON package: twelve printed
# words at made-up positions and one region.
jsonlite_free_json <- function() {
  words <- paste0(
    '{"text": "W', 1:12, '", "x": 0.', 10 + 1:12, ', "y": 0.', 20 + 1:12, '}',
    collapse = ", "
  )
  paste0(
    '{"name": "form-1", "approved": false, "pages": 5, "match_threshold": 0.6, ',
    '"regions": {"address": {"box": [0.6, 0.4, 0.9, 0.46], "drawn": 5, "confirmed": 0, "dropped": 0}}, ',
    '"fingerprint": [', words, '], "learned_from": {"scan": "sample", "rows": [1, 2, 3, 4, 5]}}'
  )
}

test_that("an empty templates folder lists nothing and a missing name is refused", {
  skip_if_not(extracttext_available(), "Python engine not installed")

  tdir <- file.path(tempdir(), paste0("templates_", as.integer(Sys.time())))
  dir.create(tdir)
  listed <- list_templates(tdir)
  expect_s3_class(listed, "tbl_df")
  expect_equal(nrow(listed), 0L)
  expect_equal(names(listed), c("name", "approved", "pages", "words", "regions"))
  expect_error(approve_template("form-1", templates = tdir), "form-1")
  expect_error(approve_template("form-1"), "scan folder")
})

test_that("a scan refuses a templates folder with nothing approved", {
  skip_if_not(extracttext_available(), "Python engine not installed")
  skip_if_not(have_fixture_files && have_system_tools, "fixtures or system tools missing")

  tdir <- file.path(tempdir(), paste0("templates_", as.integer(Sys.time()), "b"))
  dir.create(tdir)
  # a well-formed, unapproved template file
  writeLines(jsonlite_free_json(), file.path(tdir, "form-1.json"))
  expect_equal(nrow(list_templates(tdir)), 1L)
  expect_false(list_templates(tdir)$approved)
  expect_error(
    scan_documents(file.path(fixtures_dir, "synthetic_summons_efiled.pdf"),
                   out_dir = file.path(tempdir(), "scan_t"), templates = tdir,
                   progress = FALSE),
    "no approved"
  )
})
