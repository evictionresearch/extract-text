# =============================================================================
# extracttext: Python engine binding, install, and checkup
# Author: Tim Thomas
# Created: 2026-08-18
# Reviewer:
# Updated: 2026-11-17
# =============================================================================

# Module handle, populated lazily on first use so that loading the package
# never requires a working Python environment.
.et <- new.env(parent = emptyenv())

# Point reticulate at the engine's own Python environment before Python
# starts. Without this, reticulate prefers a ".venv" folder in the working
# directory (or any other Python project it finds first) over the package's
# environment, and the engine looks as if it were never installed. A Python
# the user chose is left alone: RETICULATE_PYTHON, RETICULATE_PYTHON_ENV, or
# options(extracttext.bind_python = FALSE) turn this off, and a
# reticulate::use_virtualenv() or use_python() call made after the package
# loads still wins.
bind_engine_python <- function(envname = "r-extracttext") {
  if (isFALSE(getOption("extracttext.bind_python", TRUE))) return(invisible(FALSE))
  if (nzchar(Sys.getenv("RETICULATE_PYTHON")) ||
      nzchar(Sys.getenv("RETICULATE_PYTHON_ENV"))) {
    return(invisible(FALSE))
  }
  if (reticulate::py_available()) return(invisible(FALSE))
  found <- tryCatch(reticulate::virtualenv_exists(envname), error = function(e) FALSE)
  if (!isTRUE(found)) return(invisible(FALSE))
  bound <- tryCatch({
    reticulate::use_virtualenv(envname, required = TRUE)
    TRUE
  }, error = function(e) FALSE)
  invisible(bound)
}

.onLoad <- function(libname, pkgname) {
  bind_engine_python()
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
  # the engine comes as GitHub's zip of the repository, so git is not needed
  spec <- if (is.null(source)) {
    paste0(
      "extract-text", extra_txt, " @ https://github.com/evictionresearch/",
      "extract-text/archive/", ref, ".zip#subdirectory=python"
    )
  } else {
    paste0(normalizePath(source), extra_txt)
  }
  # numpy is not used by the engine; reticulate wants it in any environment
  # it talks to, and installing it here silences that warning for users
  py_install(c(spec, "numpy"), envname = envname, pip = TRUE)
  message("Done. Restart R, then run extracttext_doctor().")
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
