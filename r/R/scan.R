# =============================================================================
# extracttext: batch processing
# Author: Tim Thomas
# Created: 2026-08-18
# Reviewer:
# Updated:
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
#' @return A tibble with one row per document. Attributes: `out_dir`.
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
                           review = FALSE) {
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
    progress = FALSE
  )
  if (review) {
    pl$write_review(path.expand(out_dir))
  }
  out <- as_tibble(read.csv(file.path(out_dir, "extracted.csv"),
                            stringsAsFactors = FALSE, check.names = FALSE,
                            colClasses = c(case_number = "character",
                                           defendant_zip = "character",
                                           attorney_zip = "character")))
  attr(out, "out_dir") <- out_dir
  out
}
