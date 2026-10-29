# =============================================================================
# extracttext: batch processing
# Author: Tim Thomas
# Created: 2026-08-18
# Reviewer:
# Updated: 2026-10-29
# =============================================================================

#' Extract a folder of court documents into a tibble
#'
#' The batch workhorse. Point it at files or folders of PDFs, TIFFs, or
#' images and get back one row per document, with the same columns the
#' Python pipeline writes to `extracted.csv`. The output directory also
#' receives `extracted.csv`, `extracted.jsonl` (the full audit trail), and
#' `extracted.parquet` when pyarrow is installed, so nothing is lost when
#' the R session ends.
#'
#' Engine choice is explicit and the engines never blend silently:
#' `"deterministic"` uses rules only (no model involved anywhere), `"ai"`
#' uses the local vision model only, and `"both"` runs the two, keeps the
#' rules in the main columns, puts the model's answers in `ai_*` columns,
#' and adds `address_similarity` plus disagreement flags.
#'
#' Real court records contain names and addresses, so choose `out_dir`
#' accordingly: a governed data location, never a code repository.
#'
#' @param paths Character vector of files and/or directories.
#' @param engine `"deterministic"` (default), `"ai"`, or `"both"`.
#' @param out_dir Where result files are written. Defaults to a fresh
#'   temporary directory; the path used is attached to the result as the
#'   `out_dir` attribute either way.
#' @param model AI model tag, when the AI lane runs. `NULL` uses the package
#'   default (qwen3.5:9b).
#' @param limit Process only the first `limit` documents (0 means all).
#' @param review Also build `review/index.html` in `out_dir`: page images
#'   beside extracted fields, flagged documents first, for human checking.
#' @param progress Show a progress bar while documents are read: documents
#'   done, time elapsed, and an estimate of the time left. On by default in
#'   an interactive session. It updates as each document starts and
#'   finishes, and never shows file or folder names, which in court
#'   collections can carry case numbers.
#' @return A tibble with one row per document. Its first column, `doc`, is
#'   the document's number on the review page (see [review_documents()]);
#'   the rest are the columns of `extracted.csv`. Attributes: `out_dir`.
#' @importFrom tibble as_tibble
#' @importFrom utils read.csv
#' @export
#' @examples
#' \dontrun{
#' results <- scan_documents("~/data/summonses/2026-07/", engine = "both",
#'                           out_dir = "~/data/extractions/2026-07/",
#'                           review = TRUE)
#' table(results$flags == "")
#' dplyr::filter(results, flags != "")
#' }
scan_documents <- function(paths, engine = c("deterministic", "ai", "both"),
                           out_dir = NULL, model = NULL, limit = 0,
                           review = FALSE, progress = interactive()) {
  engine <- match.arg(engine)
  if (is.null(out_dir)) {
    out_dir <- file.path(tempdir(), paste0("extracttext_", format(Sys.time(), "%H%M%S")))
  }
  pl <- pipeline_module()
  pl$scan(
    as.list(path.expand(paths)),
    engine = engine,
    out_dir = path.expand(out_dir),
    model = model,
    limit = as.integer(limit),
    progress = FALSE,
    on_progress = if (isTRUE(progress)) progress_reporter(environment())
  )
  if (review) {
    if (isTRUE(progress)) cli::cli_progress_step("Building the review page")
    pl$write_review(path.expand(out_dir))
  }
  # every column is read as text, so an empty one stays "" rather than
  # turning into all-NA logical when no document has that field; then the
  # columns that hold numbers or true/false are converted
  out <- read.csv(file.path(out_dir, "extracted.csv"), colClasses = "character",
                  na.strings = character(0), check.names = FALSE)
  blank_na <- function(x) replace(x, x == "", NA)
  for (col in intersect(scan_integer_cols, names(out))) out[[col]] <- as.integer(blank_na(out[[col]]))
  for (col in intersect(scan_double_cols, names(out))) out[[col]] <- as.numeric(blank_na(out[[col]]))
  for (col in intersect(scan_logical_cols, names(out))) out[[col]] <- as.logical(blank_na(out[[col]]))
  out <- as_tibble(out)
  # the document's number on the review page (#1, #2, ...), which follows
  # the order of extracted.csv
  out <- tibble::add_column(out, doc = seq_len(nrow(out)), .before = 1)
  attr(out, "out_dir") <- out_dir
  out
}

# extracted.csv columns that are not text
scan_integer_cols <- c("n_defendants", "n_ungrounded", "n_pages")
scan_double_cols <- c("amount_claimed", "judgment_amount", "ocr_mean_conf",
                      "address_similarity")
scan_logical_cols <- c("address_same_street", "case_number_agree")

# The engine calls this as each document starts and finishes, always from
# its main thread. The bar is created on the first call, once the engine
# has counted the documents, and belongs to the caller's frame so it closes
# when scan_documents() returns. Elapsed time and the estimate only move
# when a document starts or finishes.
progress_reporter <- function(envir) {
  bar <- NULL
  function(done, total, failed, current, what) {
    status <- if (failed > 0) paste0(failed, " failed") else ""
    if (is.null(bar)) {
      bar <<- cli::cli_progress_bar(
        total = total,
        format = paste(
          "{cli::pb_bar} {cli::pb_current}/{cli::pb_total} documents",
          "| {cli::pb_elapsed} elapsed | about {cli::pb_eta} left {cli::pb_status}"
        ),
        format_done = "Read {cli::pb_total} documents in {cli::pb_elapsed} {cli::pb_status}",
        clear = FALSE,
        .envir = envir
      )
    }
    cli::cli_progress_update(id = bar, set = done, status = status,
                             force = TRUE, .envir = envir)
    if (done >= total) cli::cli_progress_done(id = bar, .envir = envir)
    invisible(NULL)
  }
}
