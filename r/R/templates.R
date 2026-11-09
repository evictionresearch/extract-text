# =============================================================================
# extracttext: form templates, learned from graded documents' boxes
# Author: Tim Thomas
# Created: 2026-11-09
# Reviewer:
# Updated: 2026-11-09
# =============================================================================

#' Learn form templates from a scan's graded documents
#'
#' A form template tells the engine where a printed form puts each field,
#' so that a person can improve the engine on their own documents without
#' changing any code. It is learned from the boxes drawn on the review page
#' (pick a field, drag across the page where the value really is) and from
#' the engine's own boxes on documents a person confirmed. Documents that
#' share a printed form are grouped by the words of the form itself, and
#' each group with enough pages becomes one readable JSON file holding the
#' form's printed words with their positions (its fingerprint) and a region
#' of the page per field. Names, addresses, and case numbers are left out by
#' construction: they differ from page to page, and anything inside a
#' field's region is excluded.
#'
#' Nothing learned is used until a person approves it: look at the page
#' [review_templates()] builds, then [approve_template()] each template
#' whose regions sit where the form prints those fields. Then pass the
#' folder to [scan_documents()] as `templates`.
#'
#' @param out_dir The scan's output folder, or the tibble returned by
#'   [scan_documents()], holding `corrections.jsonl` from
#'   [review_documents()].
#' @param templates Where to write the templates. Default: a `templates`
#'   folder inside the scan folder.
#' @param min_pages Pages a form needs before a template is written.
#'   Default 5; ten to twenty is the figure from the method's source, and a
#'   template learned from fewer pages says so on the review page.
#' @param rows Learn from these documents only (their numbers on the review
#'   page). With `name`, they are treated as one form.
#' @param name With `rows`, the name to give the one template they make.
#' @return Invisibly, the templates folder. The report is printed: how many
#'   graded documents had a labeled position, how they grouped into forms,
#'   and for each template how many boxes each region came from.
#' @export
#' @examples
#' \dontrun{
#' res <- scan_documents("summonses/", out_dir = "results/sample")
#' review_documents(res, correct = TRUE, n = 50, draw = "random")
#' learn_templates(res)
#' review_templates(res)                 # look at each template over a page
#' approve_template("form-1", res)       # when its regions are right
#' res_all <- scan_documents("summonses/", out_dir = "results/all",
#'                           templates = file.path("results/sample", "templates"))
#' table(res_all$template)
#' }
learn_templates <- function(out_dir, templates = NULL, min_pages = 5, rows = NULL,
                            name = NULL) {
  out_dir <- scan_folder(out_dir)
  tdir <- templates_folder(templates, out_dir)
  tm <- templates_module()
  result <- tm$learn_templates(
    out_dir, templates_dir = tdir, min_pages = as.integer(min_pages),
    rows = if (!is.null(rows)) as.list(as.integer(rows)), name = name
  )
  cat(result[[2]], "\n", sep = "")
  if (length(result[[1]])) {
    page <- tm$write_templates_review(tdir, out_dir)
    cli::cli_inform(c(
      "i" = "Look at each template over a page it was learned from: {.code review_templates(\"{out_dir}\")}",
      " " = "Approve one with {.code approve_template(\"form-1\", \"{out_dir}\")}"
    ))
  }
  invisible(tdir)
}

#' Look at the form templates over the pages they were learned from
#'
#' Builds and opens a page showing each template's regions drawn over one
#' of the graded pages it was learned from, the printed words that identify
#' the form, how many boxes each region came from, and whether it is
#' approved. Check that each region sits over the right part of the form
#' and that no printed word sits on a name or an address, then
#' [approve_template()].
#'
#' The page renders a document's first page, so the `review` folder beside
#' the templates holds a page image and stays with the scan.
#'
#' @param out_dir The scan's output folder, or the tibble returned by
#'   [scan_documents()], that the templates were learned from.
#' @param templates The templates folder. Default: `templates` inside the
#'   scan folder.
#' @param open Open the page in the browser. Default `TRUE` in an
#'   interactive session.
#' @return Invisibly, the path of the page.
#' @export
review_templates <- function(out_dir, templates = NULL, open = interactive()) {
  out_dir <- scan_folder(out_dir)
  tdir <- templates_folder(templates, out_dir)
  page <- templates_module()$write_templates_review(tdir, out_dir)
  if (open) utils::browseURL(page)
  cli::cli_inform(c("i" = "Templates page: {.file {page}}"))
  invisible(page)
}

#' Approve a form template, so the engine uses it
#'
#' A template the engine may use carries the name of the person who approved
#' it and the date. Only a person does this; nothing learned is used until
#' they have. `approved = FALSE` takes the approval back.
#'
#' @param name The template's name, as the report and the review page show
#'   it (its file name without `.json`), or the path of its file.
#' @param out_dir The scan's output folder, or the tibble returned by
#'   [scan_documents()], that the templates were learned from; or `NULL`
#'   when `templates` names the folder.
#' @param templates The templates folder. Default: `templates` inside the
#'   scan folder.
#' @param approved `TRUE` to approve, `FALSE` to withdraw.
#' @return Invisibly, the path of the template file.
#' @export
approve_template <- function(name, out_dir = NULL, templates = NULL, approved = TRUE) {
  tdir <- if (is.null(templates) && is.null(out_dir)) {
    cli::cli_abort("Give the scan folder the templates were learned from, or {.arg templates}.")
  } else {
    templates_folder(templates, if (!is.null(out_dir)) scan_folder(out_dir))
  }
  path <- templates_module()$approve_template(name, tdir, approved = isTRUE(approved))
  cli::cli_inform(c("v" = "{if (isTRUE(approved)) 'Approved' else 'Withdrawn'}: {.file {path}}"))
  invisible(path)
}

#' The form templates in a folder
#'
#' @param templates The templates folder (or a scan's output folder, whose
#'   `templates` subfolder is used).
#' @return A tibble, one row per template: `name`, `approved`, `pages` it
#'   was learned from, `words` in its fingerprint, and `regions` (the fields
#'   it places, separated by "; ").
#' @importFrom tibble tibble
#' @export
list_templates <- function(templates) {
  tdir <- path.expand(templates)
  if (file.exists(file.path(tdir, "extracted.csv"))) tdir <- file.path(tdir, "templates")
  found <- templates_module()$load_templates(tdir, approved_only = FALSE)
  tibble(
    name = vapply(found, function(t) t$name, character(1)),
    approved = vapply(found, function(t) isTRUE(t$approved), logical(1)),
    pages = vapply(found, function(t) as.integer(t$pages), integer(1)),
    words = vapply(found, function(t) length(t$fingerprint), integer(1)),
    regions = vapply(found, function(t) paste(names(t$regions), collapse = "; "), character(1))
  )
}

templates_module <- function() {
  engine()
  reticulate::import("extract_text.templates")
}

# The templates folder: the one named, or `templates` inside the scan folder
templates_folder <- function(templates, out_dir) {
  if (!is.null(templates)) return(path.expand(templates))
  file.path(out_dir, "templates")
}
