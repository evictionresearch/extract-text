# For your IT department

This page is for the person who manages the computer extract-text will run on. It says what the install puts on the computer, where, and from which web addresses, so the install can be approved, or done for the user, without reading the code.

extract-text reads court documents on the user's own computer. After the install it uses no network. It runs no service, opens no port to other computers, and sends no usage data.

## What the user installs

1. **R**, and usually **RStudio**. R installs for one user without administrator rights (into the user's Program Files folder on Windows). RStudio's installer may ask for them.
2. **The extract-text R package**, from GitHub, into the user's R library.
3. **The engine's environment**, built by one R command, `extracttext_install()`. This is the part to look at.

## What `extracttext_install()` does

- It downloads **Miniforge**, the conda-forge project's installer, and runs it for the current user only. On Windows the installer runs silently with `/InstallationType=JustMe /AddToPath=0 /RegisterPython=0 /NoRegistry=1`: no administrator rights, no change to PATH, no registry entries.
- It creates one conda environment named `r-extracttext`, from the conda-forge channel only, holding Python 3.12, **poppler** (opens PDF files), and **tesseract** (reads scanned pages, with its language data).
- It installs the engine's Python code and a handful of Python libraries with pip: pydantic, Pillow, numpy, pyarrow, and what they depend on.

Nothing is installed outside one folder:

| System | Folder |
|---|---|
| Windows | `r-miniconda` under the user's local application data folder (`%LOCALAPPDATA%`) |
| Mac | `~/Library/r-miniconda-arm64` (Apple chip) or `~/Library/r-miniconda` (Intel) |
| Linux | `r-miniconda` under the user's data folder (`~/.local/share`) |

`extracttext_preflight()` in R prints the exact folder on a given computer. The folder takes about 1.5 GB, most of it a download cache. To put it somewhere else, set the environment variable `RETICULATE_MINICONDA_PATH` to a folder the user can write to, before the install and in every R session after.

To remove everything, delete that folder and run `remove.packages("extracttext")` in R.

## Your choices

Every download has an alternative. Each choice is an argument to `extracttext_install()`, and the first three can be set once for a computer as an environment variable, so users run the install with no arguments.

| What | Default | Your choice | Argument, and environment variable |
|---|---|---|---|
| Where Python, poppler, and tesseract come from | The conda-forge channel at `conda.anaconda.org` | A mirror of conda-forge, such as `https://prefix.dev/conda-forge`, or your organization's own conda repository | `channel`, `EXTRACTTEXT_CONDA_CHANNEL` |
| Which conda builds the environment | Miniforge, downloaded from GitHub into the user's folder | A conda you installed (Miniforge, Miniconda, or Anaconda): give the path to `conda`, or `conda.bat` on Windows | `conda`, `EXTRACTTEXT_CONDA` |
| Where the Python libraries come from | PyPI | Your organization's package index | `pip_index`, `EXTRACTTEXT_PIP_INDEX` |
| Where the engine's code comes from | GitHub's zip of the repository | A copy on disk: download the repository yourself and give its `python` folder | `source` |
| Where the environment is built | The folder in the table above | Any folder the user can write to | `RETICULATE_MINICONDA_PATH` (environment variable only) |

Whichever conda does the work, the environment is built in the user's own folder and from the one channel named, never from Anaconda's "defaults" channel.

For example, with a mirror, a conda IT installed, and an internal package index:

```r
extracttext_install(channel   = "https://prefix.dev/conda-forge",
                    conda     = "C:/ProgramData/miniforge3/condabin/conda.bat",
                    pip_index = "https://packages.example.org/simple")
```

`extracttext_preflight()` takes the same three arguments and checks those places in place of the defaults.

Two more routes need no download by the user at all.

- **You build the environment, the user points at it.** Build a conda environment anywhere with Python 3.12, poppler, tesseract, and the engine (`pip install` of the repository's `python` folder), by whatever means you use. The user sets the environment variable `RETICULATE_PYTHON` to that environment's Python, and the package uses it as it is.
- **You install the programs, the package installs only the engine.** See "If you would rather install the programs yourself" below.

## The web addresses it needs, once

| Address | What comes from it |
|---|---|
| `cran.r-project.org`, or the CRAN mirror R is set to use | R packages the R package depends on |
| `github.com`, `api.github.com`, `codeload.github.com` | The R package and the engine's code; the Miniforge installer (GitHub release files are served from a `githubusercontent.com` address) |
| `conda.anaconda.org` | The conda-forge packages: Python, poppler, tesseract |
| `pypi.org`, `files.pythonhosted.org` | The Python libraries |

These are the defaults. Each row but the first two changes with the choices above.

`conda.anaconda.org` is run by Anaconda, Inc., but the install uses the community conda-forge channel only, never Anaconda's own "defaults" channel, whose terms some organizations must license. If your organization blocks that address, the same packages are served by the mirror at `prefix.dev`: `extracttext_install(channel = "https://prefix.dev/conda-forge")`.

## What can stop it on a managed computer

1. **Web filtering.** Any address above that is blocked stops the install. `extracttext_preflight()` tries each from R and marks the ones it cannot reach.
2. **Traffic inspection.** Where the organization inspects encrypted traffic with its own certificate, R and pip use the computer's certificate store and work. The install tells conda to use the computer's certificate store too (`CONDA_SSL_VERIFY=truststore`), unless that variable or `REQUESTS_CA_BUNDLE` is already set. If the install still fails with a certificate error, point `REQUESTS_CA_BUNDLE` at your organization's certificate file.
3. **Rules that stop programs from running out of a user's folder** (application allowlisting, such as AppLocker or App Control for Business). The engine runs `python.exe`, `pdftoppm.exe`, `pdftotext.exe`, `pdfinfo.exe`, and `tesseract.exe` from the folder above. Either allow that folder, or set `RETICULATE_MINICONDA_PATH` to a folder where programs are allowed to run.
4. **A user folder with a space in its path** (a Windows account named with two words). conda does not install reliably into such a path. Set `RETICULATE_MINICONDA_PATH` to a folder without one, such as `C:\extracttext`.
5. **Antivirus scanning** can slow the install, which writes many small files. It does not stop it.

## If you would rather install the programs yourself

Install Python 3.10 or newer, poppler, and tesseract by your usual means, with poppler's and tesseract's folders on PATH. The user then runs `extracttext_install(method = "virtualenv")`, which builds a plain Python environment and downloads only the engine's code and the Python libraries (GitHub and PyPI). `extracttext_doctor()` reports what it found and what is missing.

## What we have and have not tested

The install was built and run by hand on one Mac (macOS 26, Apple chip), with Homebrew taken off the search path: with its defaults; with the `prefix.dev` mirror, a conda already on the computer, and a named package index together; and with an environment built elsewhere and named by `RETICULATE_PYTHON`. The repository also runs the install as a test, on machines that have R and nothing else: Windows Server 2025 and 2022, macOS 14, macOS 15 on an Intel chip, the current macOS, and Ubuntu. The results of each run are on the repository's Actions page. Those machines have administrator rights and open internet access, so the five points above are not tested there, and no test has run on a locked-down office computer. If the install fails on your computers, write to evictions@berkeley.edu with the last lines of the install's output and the report from `extracttext_preflight()`. Neither holds anything from court documents.
