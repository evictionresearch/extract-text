# =============================================================================
# extracttext: checking a scan by hand, and scoring the engine against it
# Author: Tim Thomas
# Created: 2026-10-29
# Reviewer:
# Updated: 2026-11-10
# =============================================================================

#' Check a scan's readings against the page images
#'
#' Opens the review page in your browser: each document's first page beside
#' what the engine read, flagged documents first. Each document is numbered
#' on the page (#1, #2, ...) to match the `doc` column of
#' [scan_documents()].
#'
#' With `correct = FALSE` (the default) the page opens read-only, to look.
#' With `correct = TRUE` it is served from this computer only (address
#' 127.0.0.1, unreachable from anywhere else) and every correction you save
#' is written at once to `corrections.jsonl` in `out_dir`. R waits while you
#' work; press Esc in RStudio, or Ctrl-C at a terminal, when finished.
#' Nothing saved is lost by stopping, and running it again shows what you
#' saved before. Then [score_documents()] measures the engine against your
#' corrections.
#'
#' On a correction form, change only what the engine got wrong and save;
#' when it got everything right, save as it is. Leave a field blank when the
#' document does not have it. Coloured boxes on the page image show where
#' the engine read each value; where one is wrong or missing, pick the field
#' under the image and drag across the page where the value really is, on
#' whichever page it is printed (the arrows under the image turn the
#' pages). A box can be moved, reshaped at its corners, deleted, or joined
#' by another for the same field. The boxes are saved with the answer and
#' are what [learn_templates()] learns from.
#'
#' @param out_dir The scan's output folder, or the tibble returned by
#'   [scan_documents()].
#' @param correct `FALSE` to look only; `TRUE` to save corrections.
#' @param n How many documents the page shows, up to `n` in all. `Inf`
#'   shows every document. Giving `n` or `draw` rebuilds the page.
#' @param draw How the page chooses documents. `"flagged"` (the default)
#'   puts every flagged document first, then fills with a random draw of the
#'   rest: the quickest way to find what the rules get wrong, but a
#'   pessimistic accuracy figure, because flagged documents are the hard
#'   ones. `"random"` draws all `n` at random, flagged or not, so the share
#'   right is a fair estimate for the whole scan: the calibration batch to
#'   correct before trusting a run (50 is a sensible minimum).
#' @param pages How many pages of each document to render when the page is
#'   built (default 1). With `correct = TRUE` the page is served, and any
#'   other page is rendered the moment you turn to it, so the default is
#'   enough; a page opened to look only can show only the rendered pages.
#' @param rebuild Rebuild the page even when one exists. The page is built
#'   on first use and kept, since building it renders an image of every
#'   document shown.
#' @param open Open the page in the browser. Default `TRUE` in an
#'   interactive session.
#' @return Invisibly, `out_dir`, so the call can sit in a pipe ahead of
#'   [score_documents()].
#' @export
#' @examples
#' \dontrun{
#' res <- scan_documents("summonses/", out_dir = "results/")
#' review_documents(res)                    # look
#' review_documents(res, correct = TRUE)    # correct, then Esc or Ctrl-C
#' # the calibration batch: 50 drawn at random, for a fair accuracy figure
#' review_documents(res, correct = TRUE, n = 50, draw = "random")
#' score_documents(res)
#' }
review_documents <- function(out_dir, correct = FALSE, n = 30,
                             draw = c("flagged", "random"), pages = 1,
                             rebuild = FALSE, open = interactive()) {
  out_dir <- scan_folder(out_dir)
  page <- file.path(out_dir, "review", "index.html")
  if (rebuild || !missing(n) || !missing(draw) || !missing(pages) || !file.exists(page)) {
    draw <- match.arg(draw)
    n <- if (is.infinite(n)) .Machine$integer.max else as.integer(n)
    cli::cli_progress_step("Building the review page")
    pipeline_module()$write_review(out_dir, n = n, flagged_first = draw == "flagged",
                                   pages = as.integer(pages))
    cli::cli_progress_done()
  }

  if (!isTRUE(correct)) {
    if (open) utils::browseURL(page)
    cli::cli_inform(c(
      "i" = "Opened the review page to look only; nothing can be saved from it.",
      " " = "To save corrections: {.code review_documents(out_dir, correct = TRUE)}"
    ))
    return(invisible(out_dir))
  }

  if (!interactive()) {
    cli::cli_abort(c(
      "{.code correct = TRUE} needs an interactive R session.",
      "i" = "It waits for you to finish correcting, which a script cannot do."
    ))
  }
  stop_key <- if (.Platform$GUI == "RStudio") "Esc" else "Ctrl-C"
  ready <- function(url) {
    cli::cli_inform(c(
      "i" = "Review page: {.url {url}}",
      " " = "Corrections save as you go, to {.file corrections.jsonl} in the scan folder.",
      " " = "Press {stop_key} here when finished."
    ))
    if (open) utils::browseURL(url)
    invisible(NULL)
  }
  reticulate::import("extract_text.corrections")$serve_review(
    out_dir, port = 0L, open_browser = FALSE, quiet = TRUE, on_ready = ready
  )
  saved <- length(reticulate::import("extract_text.corrections")$load_corrections(out_dir))
  cli::cli_inform(c(
    "v" = "{saved} document{?s} corrected so far.",
    " " = "Next: {.code score_documents(out_dir)}"
  ))
  invisible(out_dir)
}

#' Score the engine against your corrections
#'
#' Compares what the engine read with the corrections saved through
#' [review_documents()], field by field. The table holds counts only, never
#' a name or an address.
#'
#' Flagged documents go on the review page first, and they are the hard
#' ones, so `right / checked` understates accuracy for the whole scan.
#' `right_random / checked_random` covers only the documents drawn at
#' random, which is the fair estimate when there are enough of them.
#'
#' @param out_dir The scan's output folder, or the tibble returned by
#'   [scan_documents()].
#' @param save Optionally, a file to write the full report to. Every value
#'   in it is masked (letters become A or a, digits 9), so it can be shared
#'   without exposing anyone's name or address.
#' @return A tibble, one row per engine and field: `checked` (documents
#'   scored on that field), `right`, `near` (nearly right, such as a
#'   spelling difference), `blank` (the engine returned nothing where the
#'   document had a value), `wrong` (anything else), and `checked_random`
#'   and `right_random` for the randomly drawn documents alone. Attribute
#'   `reviewed`: documents with a saved correction.
#' @importFrom tibble as_tibble
#' @export
#' @examples
#' \dontrun{
#' score_documents("results/")
#' score_documents("results/", save = "score_report.txt")
#' }
score_documents <- function(out_dir, save = NULL) {
  out_dir <- scan_folder(out_dir)
  score <- reticulate::import("extract_text.score")
  rows <- score$score_rows(out_dir)
  cols <- c("engine", "field", "checked", "right", "near", "blank", "wrong",
            "checked_random", "right_random")
  out <- if (length(rows)) {
    as_tibble(do.call(rbind, lapply(rows, as.data.frame, stringsAsFactors = FALSE)))
  } else {
    as_tibble(stats::setNames(
      list(character(), character(), integer(), integer(), integer(), integer(),
           integer(), integer(), integer()),
      cols
    ))
  }
  out <- out[, cols]
  reviewed <- length(reticulate::import("extract_text.corrections")$load_corrections(out_dir))
  attr(out, "reviewed") <- reviewed
  if (!is.null(save)) {
    writeLines(score$report(out_dir, shapes = TRUE), path.expand(save))
  }
  if (reviewed == 0) {
    cli::cli_inform(c(
      "!" = "No corrections saved in this scan folder yet.",
      " " = "Make some with {.code review_documents(out_dir, correct = TRUE)}"
    ))
  }
  out
}

#' The final table: one row per document, graded answers applied
#'
#' The end product of a run. Every document of the scan gets one row: case
#' number, plaintiff, defendants, and the defendants' address. Wherever a
#' person graded the document, on this scan's review page or on an earlier
#' scan of the same document (the sample graded before the full run), the
#' graded answer replaces the engine's reading. `source` says which one each
#' row carries. The address comes as street (without the unit), unit, city,
#' state, and ZIP, and as one line in USPS Publication 28 form
#' (`defendant_address_std`), ready for a name and address cleaning step.
#'
#' A graded answer is matched to its document by full path and used only
#' while the file is unchanged. Where a document was graded more than once,
#' the latest save wins.
#'
#' The table holds names and addresses: save it with the court documents,
#' never in a code repository.
#'
#' @param out_dir The scan's output folder, or the tibble returned by
#'   [scan_documents()]: normally the full run.
#' @param graded Other scans whose graded answers apply too, as output
#'   folders or tibbles: normally the sample graded before the full run.
#' @param save Optionally, a CSV file to write the table to.
#' @return A tibble, one row per document: `doc`, `file`, `case_number`,
#'   `plaintiff`, `defendant_names` (separated by "; "), `defendant_street`,
#'   `defendant_unit`, `defendant_city`, `defendant_state`, `defendant_zip`,
#'   `defendant_address_std`, `source` (`graded`, `engine`, or `unreadable`,
#'   which keeps the engine's reading of a page a person could not read),
#'   `flags`, and `text_source`.
#' @export
#' @examples
#' \dontrun{
#' sample50 <- scan_documents("summonses/", sample = 50, out_dir = "results/sample")
#' review_documents(sample50, correct = TRUE, n = 50, draw = "random")
#' all <- scan_documents("summonses/", out_dir = "results/all")
#' review_documents(all, correct = TRUE, n = 50, draw = "random")
#' cases <- case_table(all, graded = sample50, save = "results/case_table.csv")
#' dplyr::count(cases, source)
#' }
case_table <- function(out_dir, graded = NULL, save = NULL) {
  out_dir <- scan_folder(out_dir)
  if (is.data.frame(graded)) graded <- list(graded)
  graded <- as.list(vapply(as.list(graded), scan_folder, character(1)))
  rows <- reticulate::import("extract_text.casetable")$case_table(
    out_dir, graded = graded, save = if (!is.null(save)) path.expand(save)
  )
  cols <- reticulate::import("extract_text.casetable")$COLUMNS
  if (!length(rows)) {
    return(as_tibble(stats::setNames(rep(list(character()), length(cols)), cols)))
  }
  out <- lapply(cols, function(k) vapply(rows, function(r) as.character(r[[k]]), character(1)))
  out <- as_tibble(stats::setNames(out, cols))
  out$doc <- as.integer(out$doc)
  out
}


# A scan folder from either a path or scan_documents() output
scan_folder <- function(x) {
  if (is.data.frame(x)) x <- attr(x, "out_dir")
  if (!is.character(x) || length(x) != 1 || !nzchar(x)) {
    cli::cli_abort("Give a scan's output folder, or the result of {.fn scan_documents}.")
  }
  x <- path.expand(x)
  if (!file.exists(file.path(x, "extracted.csv"))) {
    cli::cli_abort("No scan in {.file {x}}: {.file extracted.csv} is missing.")
  }
  x
}
