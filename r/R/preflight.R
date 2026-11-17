# =============================================================================
# extracttext: a check to run before installing, for a managed computer
# Author: Tim Thomas
# Created: 2026-11-17
# Reviewer:
# Updated: 2026-11-17
# =============================================================================

# The places extracttext_install() downloads from, with what each supplies,
# for the choices given: a channel by name is looked up at conda's channel
# address (conda.anaconda.org unless CONDA_CHANNEL_ALIAS names a mirror)
install_sources <- function(channel, conda, pip_index) {
  channel_url <- if (grepl("^https?://", channel)) {
    channel
  } else {
    alias <- Sys.getenv("CONDA_CHANNEL_ALIAS", "https://conda.anaconda.org")
    paste0(sub("/+$", "", alias), "/", channel)
  }
  index <- if (nzchar(pip_index)) sub("/+$", "", pip_index) else "https://pypi.org/simple"
  out <- c("the engine (GitHub)" =
             "https://github.com/evictionresearch/extract-text/archive/main.zip")
  if (!nzchar(conda) && is.null(own_conda())) {
    out <- c(out, "Miniforge installer (GitHub releases)" =
               "https://github.com/conda-forge/miniforge/releases/latest")
  }
  out <- c(out, stats::setNames(paste0(sub("/+$", "", channel_url), "/noarch/repodata.json"),
                                "Python, poppler, tesseract (conda packages)"))
  out <- c(out, stats::setNames(paste0(index, "/pydantic/"), "Python libraries (index)"))
  if (!nzchar(pip_index)) {
    out <- c(out, "Python libraries (PyPI files)" = "https://files.pythonhosted.org/")
  }
  out
}

# TRUE when the web server answered at all; a block or a timeout is FALSE
reachable <- function(url, seconds = 15) {
  old <- options(timeout = seconds)
  on.exit(options(old), add = TRUE)
  answered <- tryCatch({
    suppressWarnings(curlGetHeaders(url, redirect = TRUE, verify = TRUE))
    TRUE
  }, error = function(e) FALSE)
  isTRUE(answered)
}

#' Check a computer before installing, and say what would stop the install
#'
#' Run this first on a computer your organization manages. It installs
#' nothing and reads none of your documents. It reports the system, the
#' folder the install writes to and whether you can write there, the free
#' disk space, and whether R can reach each place [extracttext_install()]
#' downloads from. A line marked `PROBLEM` is one to take to your IT
#' department with `docs/it_checklist.md`. Give it the same `channel`,
#' `conda`, and `pip_index` you will give the install, and it checks those
#' places instead of the defaults.
#'
#' @inheritParams extracttext_install
#' @return Invisibly, `TRUE` when nothing in the report would stop the
#'   install.
#' @export
extracttext_preflight <- function(channel = Sys.getenv("EXTRACTTEXT_CONDA_CHANNEL", "conda-forge"),
                                  conda = Sys.getenv("EXTRACTTEXT_CONDA", ""),
                                  pip_index = Sys.getenv("EXTRACTTEXT_PIP_INDEX", "")) {
  ok <- TRUE
  line <- function(good, text) {
    if (!good) ok <<- FALSE
    cat(if (good) "  [ok ]     " else "  [PROBLEM] ", text, "\n", sep = "")
  }
  info <- Sys.info()
  cat("extract-text check before installing\n")
  cat("====================================\n")
  cat("System: ", info[["sysname"]], " ", info[["release"]], ", ", info[["machine"]],
      "; R ", as.character(getRversion()), "\n\n", sep = "")

  cat("Where the install goes (no administrator rights are asked for)\n")
  if (nzchar(conda)) {
    line(file.exists(conda), paste0("the conda program you named is there: ", conda))
  }
  target <- reticulate::miniconda_path()
  parent <- dirname(target)
  line(file.access(parent, 2) == 0,
       paste0("you can write to ", parent))
  # conda refuses or misbehaves in a folder whose path has a space
  line(!grepl(" ", target),
       paste0("the install folder has no space in its path: ", target))
  free <- tryCatch({
    if (.Platform$OS.type == "windows") {
      out <- system2("cmd", c("/c", "dir", "/-c", shQuote(parent)), stdout = TRUE, stderr = FALSE)
      as.numeric(sub("^.*?([0-9]+) bytes free.*$", "\\1", grep("bytes free", out, value = TRUE))) / 1e9
    } else {
      out <- system2("df", c("-k", shQuote(parent)), stdout = TRUE, stderr = FALSE)
      as.numeric(strsplit(trimws(out[length(out)]), " +")[[1]][4]) / 1e6
    }
  }, error = function(e) NA_real_)
  if (length(free) == 1 && !is.na(free)) {
    line(free >= 3, sprintf("%.0f GB free on that disk (the install takes about 1.5 GB)", free))
  } else {
    cat("  [ -- ]    free disk space could not be read; the install takes about 1.5 GB\n")
  }
  cat("\n")

  cat("What the install downloads, and whether R can reach it from here\n")
  sources <- install_sources(channel, conda, pip_index)
  for (i in seq_along(sources)) {
    line(reachable(sources[[i]]), paste0(names(sources)[i], ": ", sub("^(https://[^/]+).*$", "\\1", sources[[i]])))
  }
  cat("\n")
  if (ok) {
    cat("Nothing here would stop the install. Run extracttext_install().\n")
    cat("Two things this check cannot see: security software that stops programs from\n")
    cat("running out of your user folder, and web filtering that lets R through but\n")
    cat("not other programs. If the install fails, docs/it_checklist.md says what to ask for.\n")
  } else {
    cat("Take the PROBLEM lines to your IT department with docs/it_checklist.md.\n")
  }
  invisible(ok)
}
