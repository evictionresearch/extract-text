# =============================================================================
# extracttext: Python engine binding, install, and checkup
# Author: Tim Thomas
# Created: 2026-08-18
# Reviewer:
# Updated: 2026-08-18
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

pipeline_module <- function() {
  engine() # fail with the friendly message first if nothing is available
  reticulate::import("extract_text.pipeline")
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
#' Creates the `r-extracttext` Python environment and installs the engine
#' into it, straight from the project repository. Run once per machine, then
#' restart R. This installs Python code only; the two helper programs the
#' engine shells out to (poppler for PDFs, tesseract for scanned pages) come
#' from your system package manager, and [extracttext_doctor()] tells you
#' exactly what to install if they are missing.
#'
#' @param anthropic Also install the SDK for the cloud API backend. Leave
#'   `FALSE` for a local-only setup, which is the right default for records
#'   that must not leave the machine.
#' @param parquet Also install pyarrow so batch runs write `.parquet` files
#'   alongside the CSV. Default `TRUE`.
#' @param source Path to a local clone's `python/` directory, to install
#'   from disk instead of from GitHub. Default `NULL` installs from GitHub.
#' @param envname Python environment name.
#' @param ref Git branch, tag, or commit to install when installing from
#'   GitHub. Default `"main"`.
#' @return Invisibly, the environment name.
#' @importFrom reticulate py_install
#' @export
extracttext_install <- function(anthropic = FALSE, parquet = TRUE,
                                source = NULL, envname = "r-extracttext",
                                ref = "main") {
  extras <- c(if (anthropic) "anthropic", if (parquet) "parquet")
  extra_txt <- if (length(extras)) paste0("[", paste(extras, collapse = ","), "]") else ""
  spec <- if (is.null(source)) {
    paste0(
      "extract-text", extra_txt, " @ git+https://github.com/evictionresearch/",
      "extract-text@", ref, "#subdirectory=python"
    )
  } else {
    paste0(normalizePath(source), extra_txt)
  }
  # numpy is not used by the engine; reticulate wants it in any environment
  # it talks to, and installing it here silences that warning for users
  py_install(c(spec, "numpy"), envname = envname, pip = TRUE)
  invisible(envname)
}

#' Check the whole setup and say how to fix what is missing
#'
#' Prints one report covering the Python engine, the helper programs
#' (poppler, tesseract), the local AI server (Ollama), and whether the
#' recommended model is pulled, with the exact install command for anything
#' missing. Nothing here reads your documents or uses the internet.
#'
#' @param model AI model tag to check for. `NULL` checks for the package
#'   default.
#' @return Invisibly, `TRUE` when the deterministic engine is ready to run.
#' @export
extracttext_doctor <- function(model = NULL) {
  if (!extracttext_available()) {
    cat(
      "The Python engine is not installed yet.\n",
      "  1. install.packages('reticulate') if needed\n",
      "  2. extracttext_install()\n",
      "  3. restart R and run extracttext_doctor() again\n",
      sep = ""
    )
    return(invisible(FALSE))
  }
  doctor <- reticulate::import("extract_text.doctor")
  ready <- reticulate::py_capture_output(res <- doctor$run_doctor(model = model))
  cat(ready)
  invisible(isTRUE(res))
}
