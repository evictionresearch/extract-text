# =============================================================================
# extracttext: extraction and comparison
# Author: Tim Thomas
# Created: 2026-08-18
# Reviewer:
# Updated:
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
#' Regular expressions and layout heuristics. No network, no API key, no model.
#' Every field returned carries the character span it was read from, so the
#' answer can be checked against the source without rerunning anything.
#'
#' @param text Document text as a single character string.
#' @return An `extracttext_extraction`: a list with `record`, `method`,
#'   `backend`, and `evidence`.
#' @export
#' @examples
#' \dontrun{
#' txt <- readLines("complaint.txt") |> paste(collapse = "\n")
#' rules <- extract_deterministic(txt)
#' rules$record$case_number
#' }
extract_deterministic <- function(text) {
  stopifnot("text must be a single string" = is.character(text) && length(text) == 1)
  as_extraction(engine()$extract_deterministic(text))
}

#' Extract a court record using a language model
#'
#' @param text Document text as a single character string.
#' @param backend `"local"` for a model on this machine, `"anthropic"` for the
#'   API. Defaults to `"local"`: court records name people and give their
#'   addresses, so the safe default keeps the text here.
#' @param ... Passed to the backend constructor, for example `model =` or
#'   `host =`.
#' @return An `extracttext_extraction`.
#' @export
extract_ai <- function(text, backend = c("local", "anthropic"), ...) {
  stopifnot("text must be a single string" = is.character(text) && length(text) == 1)
  backend <- match.arg(backend)
  as_extraction(engine()$extract_ai(text, backend = backend, ...))
}

#' Compare two extractions of the same document
#'
#' Disagreement is the useful output. It identifies the records a human should
#' look at, which is a far smaller set than all of them. Agreement is evidence,
#' not proof: two methods can be wrong the same way, particularly when the
#' document itself is wrong.
#'
#' @param a,b Results from [extract_deterministic()] or [extract_ai()].
#' @return A list with `agreement_rate`, `needs_review` (field paths worth a
#'   human look, most serious first), and `fields` (a tibble of every field with
#'   both values and a status of agree, disagree, only_a, only_b, or
#'   both_missing).
#' @importFrom tibble as_tibble
#' @export
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
#' For joining extraction output into a state pipeline. Party lists are
#' collapsed to semicolon-separated strings and counts, since a rectangular
#' frame cannot hold them otherwise.
#'
#' @param x A result from [extract_deterministic()] or [extract_ai()].
#' @return A one-row tibble.
#' @importFrom tibble as_tibble
#' @export
record_to_row <- function(x) {
  rec <- x$record
  names_of <- function(parties) {
    if (length(parties) == 0) return(NA_character_)
    paste(vapply(parties, function(p) p$name, character(1)), collapse = "; ")
  }
  as_date <- function(v) if (is.null(v)) as.Date(NA) else as.Date(v)

  as_tibble(data.frame(
    case_number      = rec$case_number %||% NA_character_,
    court_name       = rec$court_name %||% NA_character_,
    county           = rec$county %||% NA_character_,
    state            = rec$state %||% NA_character_,
    case_type        = rec$case_type %||% NA_character_,
    filing_date      = as_date(rec$filing_date),
    plaintiffs       = names_of(rec$plaintiffs),
    defendants       = names_of(rec$defendants),
    n_plaintiffs     = length(rec$plaintiffs),
    n_defendants     = length(rec$defendants),
    amount_claimed   = rec$amount_claimed %||% NA_real_,
    judgment_amount  = rec$judgment$amount %||% NA_real_,
    judgment_date    = as_date(rec$judgment$date),
    disposition      = rec$disposition %||% NA_character_,
    disposition_date = as_date(rec$disposition_date),
    method           = x$method,
    backend          = x$backend,
    n_ungrounded     = sum(!vapply(x$evidence, function(e) e$grounded, logical(1))),
    stringsAsFactors = FALSE
  ))
}

`%||%` <- function(x, y) if (is.null(x)) y else x
