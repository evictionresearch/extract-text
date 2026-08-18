# =============================================================================
# extracttext: Python engine binding
# Author: Tim Thomas
# Created: 2026-08-18
# Reviewer:
# Updated:
# =============================================================================

# Module handle, populated lazily on first use so that loading the package
# never requires a working Python environment.
.et <- new.env(parent = emptyenv())

.onLoad <- function(libname, pkgname) {
  .et$extract_text <- reticulate::import(
    "extract_text",
    delay_load = list(
      environment = "r-extracttext",
      on_error = function(e) NULL
    )
  )
}

engine <- function() {
  if (is.null(.et$extract_text) || !py_module_available("extract_text")) {
    stop(
      "The Python engine is not available. Run extracttext_install() once, ",
      "then restart R.",
      call. = FALSE
    )
  }
  .et$extract_text
}

#' Is the Python engine available
#'
#' @return `TRUE` when the `extract_text` Python module can be imported.
#' @importFrom reticulate py_module_available
#' @export
extracttext_available <- function() {
  isTRUE(py_module_available("extract_text"))
}

#' Install the Python engine
#'
#' Creates the `r-extracttext` virtual environment and installs the engine into
#' it. Run once per machine, then restart R.
#'
#' @param anthropic Install the Anthropic SDK as well. Leave `FALSE` for a
#'   local-only setup, which is the right default for records that must not
#'   leave the machine.
#' @param envname Virtual environment name.
#' @return Invisibly, the environment name.
#' @importFrom reticulate py_install
#' @export
extracttext_install <- function(anthropic = FALSE, envname = "r-extracttext") {
  spec <- if (anthropic) "extract-text[anthropic]" else "extract-text"
  py_install(spec, envname = envname, pip = TRUE)
  invisible(envname)
}
