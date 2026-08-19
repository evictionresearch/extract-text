"""Environment checkup, in plain language.

`extract-text doctor` answers the setup questions in one pass: which helper
programs are installed, whether the local AI server is running, whether the
recommended model is pulled, and exactly what command fixes anything missing.
It never touches your documents and never uses the network beyond asking the
local Ollama server (a program on this machine) what models it has.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys

CHECKS_HEADER = "extract-text environment check"

_INSTALL_HINTS = {
    "Darwin": {
        "poppler": "brew install poppler",
        "tesseract": "brew install tesseract",
        "ollama": "brew install ollama   (or download from https://ollama.com)",
    },
    "Linux": {
        "poppler": "sudo apt install poppler-utils   (Debian/Ubuntu)",
        "tesseract": "sudo apt install tesseract-ocr",
        "ollama": "download from https://ollama.com",
    },
    "Windows": {
        "poppler": "download poppler for Windows and add its bin/ folder to PATH",
        "tesseract": "install tesseract from the UB Mannheim build and add it to PATH",
        "ollama": "download the installer from https://ollama.com",
    },
}


def _hint(tool: str) -> str:
    return _INSTALL_HINTS.get(platform.system(), _INSTALL_HINTS["Linux"]).get(tool, "")


def _version_of(cmd) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        line = (r.stdout or r.stderr).strip().splitlines()
        return line[0] if line else ""
    except Exception:
        return ""


def run_doctor(model: str | None = None, file=None) -> bool:
    """Print the checkup. Returns True when the deterministic engine can run.

    The deterministic engine needs poppler and tesseract. The AI engine
    additionally needs Ollama running with the model pulled. Neither needs
    the internet once installed.
    """
    from .ai.vision import DEFAULT_VISION_MODEL, available, pulled_models

    model = model or DEFAULT_VISION_MODEL
    out = file or sys.stdout
    say = lambda s="": print(s, file=out)
    ok = lambda cond: "ok " if cond else "MISSING"

    say(CHECKS_HEADER)
    say("=" * len(CHECKS_HEADER))
    say(f"Python {sys.version.split()[0]} on {platform.system()}")
    say()

    say("Deterministic engine (rules; needed for the default path)")
    det_ok = True
    for tool, binaries, purpose in (
        ("poppler", ("pdftotext", "pdftoppm", "pdfinfo"), "reads PDFs"),
        ("tesseract", ("tesseract",), "reads scanned pages (OCR)"),
    ):
        have_all = all(shutil.which(b) for b in binaries)
        det_ok = det_ok and have_all
        mark = ok(have_all)
        say(f"  [{mark}] {tool:10s} {purpose}")
        if have_all:
            v = _version_of([binaries[0], "-v" if tool == "poppler" else "--version"])
            if v:
                say(f"        {v}")
        else:
            say(f"        install with: {_hint(tool)}")
    try:
        import PIL  # noqa: F401

        say("  [ok ] Pillow      reads TIFF files (Python library)")
    except ImportError:
        det_ok = False
        say("  [MISSING] Pillow  reads TIFF files")
        say("        install with: pip install Pillow")
    say()

    say("AI engine (optional; local model through Ollama)")
    if not shutil.which("ollama"):
        say("  [MISSING] ollama  runs the local AI model")
        say(f"        install with: {_hint('ollama')}")
    else:
        say("  [ok ] ollama installed")
    if available():
        say("  [ok ] Ollama server is running")
        models = pulled_models()
        hit = [m for m in models if m == model or m.split(":")[0] == model.split(":")[0]]
        if model in models:
            say(f"  [ok ] model {model} is pulled")
        elif hit:
            say(f"  [note] {model} not pulled, but a related model is: {', '.join(hit)}")
            say(f"        either pass model='{hit[0]}' or run: ollama pull {model}")
        else:
            say(f"  [MISSING] model {model} is not pulled")
            say(f"        pull it once with: ollama pull {model}")
            say("        (about a 7 GB download; after that, no internet needed)")
    else:
        say("  [not running] start the Ollama app, or run: ollama serve")
    say()

    say("Optional extras")
    for mod, why, fix in (
        ("pyarrow", "parquet output", "pip install 'extract-text[parquet]'"),
        ("anthropic", "cloud API backend (sends text off this machine)",
         "pip install 'extract-text[anthropic]'"),
    ):
        try:
            __import__(mod)
            say(f"  [ok ] {mod:10s} {why}")
        except ImportError:
            say(f"  [ -- ] {mod:10s} {why}; enable with: {fix}")
    say()
    if det_ok:
        say("Ready: the deterministic engine can run.")
    else:
        say("Not ready yet: install the items marked MISSING above, then rerun "
            "'extract-text doctor'.")
    return det_ok
