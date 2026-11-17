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

# The engine's environment comes in two kinds. extracttext_install() builds a
# conda environment by default, inside the Miniforge that reticulate keeps
# for itself, because conda-forge supplies poppler and tesseract along with
# Python. method = "virtualenv" builds a plain Python environment for a
# computer that already has those programs. Both are named "r-extracttext".
own_conda <- function() {
  root <- reticulate::miniconda_path()
  exe <- if (.Platform$OS.type == "windows") {
    file.path(root, "condabin", "conda.bat")
  } else {
    file.path(root, "bin", "conda")
  }
  if (file.exists(exe)) exe else NULL
}

conda_env_path <- function(envname = "r-extracttext") {
  file.path(reticulate::miniconda_path(), "envs", envname)
}

conda_env_python <- function(envname = "r-extracttext") {
  env <- conda_env_path(envname)
  exe <- if (.Platform$OS.type == "windows") {
    file.path(env, "python.exe")
  } else {
    file.path(env, "bin", "python")
  }
  if (file.exists(exe)) exe else NULL
}

# Point reticulate at the engine's own Python environment before Python
# starts. Without this, reticulate prefers a ".venv" folder in the working
# directory (or any other Python project it finds first) over the package's
# environment, and the engine looks as if it were never installed. The conda
# environment is used when there is one, and the virtualenv otherwise. A
# Python the user chose is left alone: RETICULATE_PYTHON,
# RETICULATE_PYTHON_ENV, or options(extracttext.bind_python = FALSE) turn
# this off, and a reticulate::use_virtualenv() or use_python() call made
# after the package loads still wins.
bind_engine_python <- function(envname = "r-extracttext") {
  if (isFALSE(getOption("extracttext.bind_python", TRUE))) return(invisible(FALSE))
  if (nzchar(Sys.getenv("RETICULATE_PYTHON")) ||
      nzchar(Sys.getenv("RETICULATE_PYTHON_ENV"))) {
    return(invisible(FALSE))
  }
  if (reticulate::py_available()) return(invisible(FALSE))
  python <- conda_env_python(envname)
  if (!is.null(python)) {
    bound <- tryCatch({
      reticulate::use_python(python, required = TRUE)
      TRUE
    }, error = function(e) FALSE)
    return(invisible(bound))
  }
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

#' Install the Python engine, with poppler and tesseract
#'
#' Builds the `r-extracttext` environment the package runs on. Run once per
#' computer, then restart R. By default nothing else has to be installed
#' first: the environment comes from conda-forge and carries its own Python,
#' poppler (which opens PDFs), and tesseract (which reads scanned pages).
#' If the computer has no conda that reticulate manages, Miniforge is
#' downloaded into your user folder first; no administrator rights are
#' asked for. [extracttext_doctor()] then says what was found.
#'
#' Every download has an alternative, for an organization that blocks an
#' address or keeps its own copies. `channel` names where the conda packages
#' come from, `conda` a conda program already on the computer, `pip_index`
#' where the Python libraries come from, and `source` a copy of the engine's
#' code on disk. Each of the first three can also be set once for a computer
#' with an environment variable (`EXTRACTTEXT_CONDA_CHANNEL`,
#' `EXTRACTTEXT_CONDA`, `EXTRACTTEXT_PIP_INDEX`), so an IT department can
#' set them and users run `extracttext_install()` with no arguments.
#' `docs/it_checklist.md` in the repository walks through the choices.
#'
#' @param method `"conda"` (default) builds the environment from conda-forge,
#'   with Python, poppler, and tesseract inside it. `"virtualenv"` builds a
#'   plain Python environment instead, for a computer that already has
#'   Python 3.10 or newer, poppler, and tesseract.
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
#' @param channel Where the conda packages (Python, poppler, tesseract) come
#'   from. The default, `"conda-forge"`, is the community channel at
#'   conda.anaconda.org. Give a full address for a mirror of it, such as
#'   `"https://prefix.dev/conda-forge"`, or for your organization's own
#'   repository.
#' @param conda Path to a conda program already on the computer (Miniforge,
#'   Miniconda, or Anaconda, installed by you or your IT department). The
#'   default uses the Miniforge that reticulate keeps for itself and
#'   downloads it when absent. Whichever conda is used, the environment is
#'   built in your own user folder and from `channel` only.
#' @param pip_index Where the Python libraries come from: the address of a
#'   package index, such as your organization's mirror of PyPI. The default
#'   is PyPI itself.
#' @return Invisibly, the environment name.
#' @importFrom reticulate py_install
#' @export
extracttext_install <- function(method = c("conda", "virtualenv"),
                                anthropic = FALSE, parquet = TRUE,
                                source = NULL, envname = "r-extracttext",
                                ref = "main",
                                channel = Sys.getenv("EXTRACTTEXT_CONDA_CHANNEL", "conda-forge"),
                                conda = Sys.getenv("EXTRACTTEXT_CONDA", ""),
                                pip_index = Sys.getenv("EXTRACTTEXT_PIP_INDEX", "")) {
  method <- match.arg(method)
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
  pip_options <- if (nzchar(pip_index)) c("--index-url", pip_index) else character()
  # numpy is not used by the engine; reticulate wants it in any environment
  # it talks to, and installing it here silences that warning for users
  if (method == "virtualenv") {
    if (!is.null(conda_env_python(envname))) {
      message(
        "A conda environment named '", envname, "' is already on this computer, and the ",
        "package uses it first. To use the virtualenv built now, delete the folder ",
        conda_env_path(envname), "."
      )
    }
    py_install(c(spec, "numpy"), envname = envname, method = "virtualenv", pip = TRUE,
               pip_options = pip_options)
    return(invisible(envname))
  }

  if (nzchar(conda)) {
    if (!file.exists(conda)) {
      stop("No conda program at ", conda, ". Give the full path to conda (conda.bat on ",
           "Windows), or leave `conda` out to have Miniforge downloaded.", call. = FALSE)
    }
  } else {
    if (is.null(own_conda())) {
      root <- reticulate::miniconda_path()
      if (grepl(" ", root, fixed = TRUE)) {
        stop(
          "The install folder has a space in its name, which the installer cannot use:\n  ",
          root, "\nChoose a folder without a space that you can write to, tell R about it ",
          "with this line (change the folder to yours), and run extracttext_install() again:\n",
          "  Sys.setenv(RETICULATE_MINICONDA_PATH = \"C:/extracttext\")\n",
          "R forgets that line when it closes. docs/it_checklist.md (point 4 under ",
          "\"What can stop it\") says how to make R remember it.",
          call. = FALSE
        )
      }
      # a folder with no conda in it is what an install that was stopped
      # partway leaves behind; the installer refuses it unless told to start over
      leftover <- dir.exists(root)
      if (leftover) message("An earlier install stopped partway. Starting it again.")
      message("Downloading Miniforge (conda-forge's installer) into your user folder, once.")
      reticulate::install_miniconda(update = FALSE, force = leftover)
    }
    conda <- own_conda()
    if (is.null(conda)) {
      stop(
        "Miniforge did not install, so the environment cannot be built. The lines above ",
        "say why. If this computer blocks the download, see docs/it_checklist.md, or ",
        "install Python, poppler, and tesseract yourself and run ",
        "extracttext_install(method = \"virtualenv\").",
        call. = FALSE
      )
    }
  }
  # Many offices inspect web traffic with a certificate of their own, which
  # the computer trusts and conda's built-in list does not. Unless the user
  # has made a certificate setting, conda is told to use the computer's
  # certificate store, as pip does by default.
  if (!nzchar(Sys.getenv("CONDA_SSL_VERIFY")) && !nzchar(Sys.getenv("REQUESTS_CA_BUNDLE"))) {
    Sys.setenv(CONDA_SSL_VERIFY = "truststore")
    on.exit(Sys.unsetenv("CONDA_SSL_VERIFY"), add = TRUE)
  }
  programs <- c("poppler", "tesseract")
  # The environment is built by its folder, in the user's own space, so the
  # package finds it in one place whichever conda built it. Packages come
  # from `channel` only, whatever channels the computer's conda settings name.
  env <- conda_env_path(envname)
  if (is.null(conda_env_python(envname))) {
    dir.create(dirname(env), recursive = TRUE, showWarnings = FALSE)
    reticulate::conda_create(
      env, packages = c("python=3.12", programs), channel = channel,
      conda = conda, additional_create_args = "--override-channels"
    )
  } else {
    reticulate::conda_install(
      env, packages = programs, channel = channel,
      conda = conda, additional_install_args = "--override-channels"
    )
  }
  reticulate::conda_install(env, packages = c(spec, "numpy"), pip = TRUE,
                            pip_options = pip_options, conda = conda)
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
