# =============================================================================
# extracttext: checking extracted addresses against a list of real ones
# Author: Tim Thomas
# Created: 2026-10-29
# Reviewer:
# Updated: 2026-10-29
# =============================================================================

#' Check extracted addresses against a list of real addresses
#'
#' Looks up each document's standardized address (the `*_std` columns of
#' [scan_documents()]) in a list of the addresses that exist, such as a
#' county's address points, at the same house number in the same ZIP code or
#' city. Everything runs on this computer; the list is a file you supply.
#'
#' `address_check` is `"match"` (listed as read), `"near"` (not listed as
#' read, but the same house number is listed on a street spelled almost the
#' same, or on the same street under another ZIP code; the listed address is
#' in `address_suggested`), `"no_match"`, or `""` when there was nothing to
#' check. A suggestion is for a person to confirm and never replaces what
#' the engine read. A `"no_match"` can also mean the address no longer
#' exists: address lists are current, filings are not.
#'
#' @param x The tibble returned by [scan_documents()], or a scan's output
#'   folder.
#' @param reference Path to a CSV of real addresses.
#' @param preset The column names of a known list, such as
#'   `"king_county_wa"` for King County GIS's address points. Or give the
#'   columns yourself with `street`, `zip`, and `city`.
#' @param street,zip,city Column names in `reference`: house number and
#'   street, ZIP code, and city.
#' @param min_similarity How alike a listed street must be to the one read
#'   (0 to 1) to be suggested.
#' @return With a tibble, the same tibble with `address_check`,
#'   `address_suggested`, and `address_check_similarity` added. With a
#'   folder, a tibble of those columns and `doc`. The results are also saved
#'   to `address_check.csv` in the scan folder.
#' @importFrom tibble as_tibble
#' @export
#' @examples
#' \dontrun{
#' res <- scan_documents("summonses/", out_dir = "results/")
#' res <- check_addresses(res, "kc_address_points.csv", preset = "king_county_wa")
#' dplyr::count(res, address_check)
#' }
check_addresses <- function(x, reference, preset = NULL, street = NULL, zip = NULL,
                            city = NULL, min_similarity = 0.8) {
  out_dir <- scan_folder(x)
  reference <- path.expand(reference)
  if (!file.exists(reference)) cli::cli_abort("No file at {.file {reference}}.")
  if (is.null(preset) && is.null(street)) {
    cli::cli_abort("Give {.arg preset}, or {.arg street} (with {.arg zip} and {.arg city}) naming the list's columns.")
  }
  ac <- reticulate::import("extract_text.address_check")
  cli::cli_progress_step("Reading the address list")
  addresses <- if (!is.null(preset)) {
    ac$AddressList$from_preset(reference, preset)
  } else {
    ac$AddressList$from_csv(reference, street = street, zip = zip, city = city)
  }
  cli::cli_progress_step("Checking against {.val {addresses$n}} listed addresses")
  results <- ac$check_scan(out_dir, addresses, min_similarity = min_similarity)
  cli::cli_progress_done()
  cli::cli_inform(c("i" = ac$summary(results)))
  # with corrections saved, how the check did against them (counts only)
  report <- ac$evaluation(out_dir, results)
  if (!is.null(report)) cli::cli_verbatim(report)

  checked <- as_tibble(data.frame(
    doc = vapply(results, function(r) as.integer(r$doc), integer(1)),
    address_check = vapply(results, function(r) r$address_check, character(1)),
    address_suggested = vapply(results, function(r) r$address_suggested, character(1)),
    address_check_similarity = vapply(results, function(r) {
      s <- r$address_check_similarity
      if (is.numeric(s)) s else NA_real_
    }, numeric(1)),
    stringsAsFactors = FALSE
  ))
  if (!is.data.frame(x)) return(checked)
  keep <- setdiff(names(x), setdiff(names(checked), "doc"))
  joined <- merge(x[keep], checked, by = "doc", all.x = TRUE, sort = FALSE)
  joined <- as_tibble(joined[order(joined$doc), , drop = FALSE])
  attr(joined, "out_dir") <- out_dir
  joined
}
