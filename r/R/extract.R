# =============================================================================
# extracttext: extraction and comparison
# Author: Tim Thomas
# Created: 2026-08-18
# Reviewer:
# Updated: 2026-08-18
# =============================================================================

# Python objects are kept on an attribute rather than discarded, so that a
# result can be handed straight back to compare_extractions() without a
# lossy round trip through R.
as_extraction <- function(py_obj) {
  out <- py_obj$model_dump(mode = "json")
  attr(out, "py") <- py_obj
  class(out) <- c("extracttext_extraction", "list")
  out
}

py_handle <- function(x) {
  handle <- attr(x, "py")
  if (is.null(handle)) {
    stop(
      "Expected a result from extract_deterministic() or extract_ai().",
      call. = FALSE
    )
  }
  handle
}

#' Extract a court record using rules alone
#'
#' Regular expressions and positional layout rules. No network, no model, no
#' API key, and the same input always gives the same output. Every field
#' returned carries the evidence it was read from, so the answer can be
#' checked against the source without rerunning anything.
#'
#' @param source A path to a document file (PDF, TIFF, PNG, JPEG), or the
#'   document text as a single character string. The file is the better
#'   input: page positions switch on the address and attorney rules and the
#'   scan-quality flags.
#' @param expected_case_number Optionally, the case number this document is
#'   supposed to belong to (from a docket list or folder name). It is never
#'   used to fill the field; it only powers the `case_number_mismatch` flag.
#' @return An `extracttext_extraction`: a list with `record`, `method`,
#'   `backend`, `evidence`, `flags`, and `document`.
#' @export
#' @examples
#' \dontrun{
#' rules <- extract_deterministic("summons.pdf")
#' rules$record$defendant_address$street
#' rules$flags
#' }
extract_deterministic <- function(source, expected_case_number = NULL) {
  stopifnot("source must be a single string" = is.character(source) && length(source) == 1)
  as_extraction(engine()$extract_deterministic(source, expected_case_number))
}

#' Extract a court record using a language model
#'
#' The AI engine. With the default local backend, a file path goes to a
#' vision model that reads the page image (which is what handles handwriting
#' OCR cannot read), and plain text goes to a text model. Either way the
#' model runs on this machine through Ollama; the document never leaves it.
#'
#' @param source A path to a document file, or document text as a single
#'   character string.
#' @param backend `"local"` for a model on this machine (the default, and
#'   the only backend that keeps the text here), or `"anthropic"` for the
#'   cloud API, which sends text off this machine and is only appropriate
#'   for records cleared for third-party processing.
#' @param ... Passed to the backend, for example `model = "qwen3.5:9b"`,
#'   `host =`, or `temperature =`.
#' @return An `extracttext_extraction`.
#' @export
#' @examples
#' \dontrun{
#' model <- extract_ai("summons.pdf")
#' model$record$defendant_address$raw
#' }
extract_ai <- function(source, backend = c("local", "anthropic"), ...) {
  stopifnot("source must be a single string" = is.character(source) && length(source) == 1)
  backend <- match.arg(backend)
  as_extraction(engine()$extract_ai(source, backend = backend, ...))
}

#' Compare two extractions of the same document
#'
#' Disagreement is the useful output. It identifies the records a human
#' should look at, which is a far smaller set than all of them. Agreement is
#' evidence, not proof: two methods can be wrong the same way, particularly
#' when the document itself is wrong.
#'
#' @param a,b Results from [extract_deterministic()] or [extract_ai()].
#' @return A list with `agreement_rate`, `needs_review` (field paths worth a
#'   human look, most serious first), and `fields` (a tibble of every field
#'   with both values and a status of agree, disagree, only_a, only_b, or
#'   both_missing).
#' @importFrom tibble as_tibble
#' @export
#' @examples
#' \dontrun{
#' rules <- extract_deterministic("summons.pdf")
#' model <- extract_ai("summons.pdf")
#' report <- compare_extractions(rules, model)
#' report$needs_review
#' }
compare_extractions <- function(a, b) {
  report <- engine()$compare(py_handle(a), py_handle(b))$to_dict()

  rows <- do.call(rbind, lapply(report$fields, function(f) {
    data.frame(
      path   = f$path,
      a      = if (is.null(f$a)) NA_character_ else as.character(f$a),
      b      = if (is.null(f$b)) NA_character_ else as.character(f$b),
      status = f$status,
      stringsAsFactors = FALSE
    )
  }))

  list(
    agreement_rate = report$agreement_rate,
    needs_review   = unlist(report$needs_review) %||% character(0),
    fields         = as_tibble(rows)
  )
}

#' Flatten a record into a one-row tibble
#'
#' For joining extraction output into a state pipeline. The columns are
#' identical to the ones batch runs write to `extracted.csv`, because both
#' come from the same Python function; the two can never drift apart.
#'
#' @param x A result from [extract_deterministic()] or [extract_ai()].
#' @return A one-row tibble.
#' @importFrom tibble as_tibble
#' @export
record_to_row <- function(x) {
  row <- pipeline_module()$flatten_extraction(py_handle(x))
  row <- lapply(row, function(v) {
    if (is.null(v) || (is.character(v) && !nzchar(v))) NA else v
  })
  for (col in c("filing_date", "judgment_date", "disposition_date")) {
    row[[col]] <- as.Date(if (is.na(row[[col]])) NA else row[[col]])
  }
  for (col in c("amount_claimed", "judgment_amount", "ocr_mean_conf")) {
    row[[col]] <- as.numeric(row[[col]])
  }
  as_tibble(row)
}

`%||%` <- function(x, y) if (is.null(x)) y else x
