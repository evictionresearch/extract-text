# For your IT department

This page is for the person who manages the computer extract-text will run on. It lists the programs the user needs, where each comes from, what the rest of the install does, and the web addresses it uses, so the install can be approved, or done for the user, without reading the code.

extract-text reads court documents on the user's own computer. After the install it uses no network. It runs no service, opens no port to other computers, and sends no usage data.

## What has to be on the computer

| Program | What it is for | Where it comes from |
|---|---|---|
| R, and usually RStudio | The user works in these | [cran.r-project.org](https://cran.r-project.org/) and [posit.co](https://posit.co/download/rstudio-desktop/) |
| poppler | Opens PDF files | Mac: Homebrew (`brew install poppler`). Windows: `winget install oschwartz10612.Poppler`, a build of poppler for Windows. Linux: the `poppler-utils` package |
| tesseract | Reads scanned pages (OCR) | Mac: Homebrew (`brew install tesseract`). Windows: `winget install UB-Mannheim.TesseractOCR`, the University of Mannheim's build. Linux: the `tesseract-ocr` package |
| Python 3.10 or newer | Runs the engine | Mac: Homebrew (`brew install python`). Windows: `winget install Python.Python.3.12`, or the installer from [python.org](https://www.python.org/downloads/). Linux: `python3` and `python3-venv` |

All are free and open source. You can install them by these means or by your own (a software center, a package you build), as long as the folders that hold `pdftoppm`, `pdftotext`, `pdfinfo`, and `tesseract` are on the user's PATH. On Windows the tesseract installer does not add its folder (by default `C:\Program Files\Tesseract-OCR`) to PATH; add it. Some of these installers may ask for administrator rights.

Which systems: on a Mac, Homebrew has ready-made copies of these programs for macOS 15 and later on Apple chips only. On Windows, `winget` needs Windows 10 version 1809 or later.

## What the user then runs in R

Two commands, neither of which asks for administrator rights.

1. `remotes::install_github("evictionresearch/extract-text", subdir = "r")` installs the R package into the user's R library.
2. `extracttext_install()` makes a Python virtual environment named `r-extracttext` in the user's own folder (the folder R prints for `reticulate::virtualenv_root()`, by default `.virtualenvs` in the user's home folder). It installs into it, with pip, the engine's Python code and the Python libraries it needs: pydantic, Pillow, numpy, pyarrow, and what they depend on.

Nothing is added to PATH, and nothing is written outside the R library and that folder. To remove it, run `reticulate::virtualenv_remove("r-extracttext")` and `remove.packages("extracttext")` in R.

`extracttext_doctor()` in R then reports what it found: each helper program and the folder it is in, the engine, and what is missing.

## The web addresses the R commands need, once

| Address | What comes from it |
|---|---|
| `cran.r-project.org`, or the CRAN mirror R is set to use | R packages the R package depends on |
| `github.com`, `api.github.com`, `codeload.github.com` | The R package, and the engine's code as a zip |
| `pypi.org`, `files.pythonhosted.org` | The Python libraries |

The programs in the first table come from wherever you install them from.

## What can stop it on a managed computer

1. **The three programs.** If users cannot install programs, poppler, tesseract, and Python are yours to install. This is the step most likely to need you.
2. **Web filtering.** Any address in the table above that is blocked stops the R commands. If your organization keeps its own Python package index, pip uses it when the environment variable `PIP_INDEX_URL` names it.
3. **Traffic inspection.** Where the organization inspects encrypted traffic with its own certificate, R and current versions of pip use the computer's certificate store. If pip fails with a certificate error, point the environment variable `PIP_CERT` at your organization's certificate file.
4. **Rules that stop programs from running out of a user's folder** (application allowlisting). The engine runs the Python inside the virtual environment folder above. Allow that folder, or set the environment variable `WORKON_HOME` to a folder where programs are allowed to run, before the install and in every R session after.

## What we have and have not tested

The R commands were run on a Mac (macOS 26, Apple chip) with the programs from Homebrew. The repository's tests check the R package and the engine on Ubuntu on every change. The install has not been tested by us on Windows, or on a locked-down office computer. If it fails on your computers, write to evictions@berkeley.edu with the last lines of the install's output and what `extracttext_doctor()` prints. Neither holds anything from court documents.
