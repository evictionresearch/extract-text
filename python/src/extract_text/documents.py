"""Turning a court document file into positioned words.

Three kinds of file arrive from county archives, and each is read differently:

- **PDF with a digital text layer** (e-filed documents): the text is already
  in the file, with positions. Read it directly with poppler's
  `pdftotext -bbox`. No OCR runs at all, so there are no recognition errors
  to worry about.
- **Image-only PDF** (a scan saved as PDF): rasterize the needed pages at
  300 dpi with `pdftoppm`, then run tesseract OCR to get words with
  positions and per-word confidence.
- **TIFF** (older archives): split frames with Pillow, OCR each needed page.

All three paths produce the same thing, a list of `layout.Word`, so every
rule downstream is format-blind. Settings are pinned (tesseract LSTM engine,
300 dpi, TSV output) so the same file always produces the same words.

Nothing here touches the network. The system programs used, poppler and
tesseract, are ordinary open-source tools installed from your package
manager; `extract-text doctor` checks for them and says how to install
what is missing.

Ported from the ERN Washington scanner (`wa_doc_scan.py`).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .layout import Line, Word, cluster_lines, page_text, strip_line_number_rail

OCR_DPI = 300  # tesseract input resolution for rasterized PDFs
MIN_NATIVE_WORDS = 40  # fewer than this on p.1 → treat PDF as image-only
FALLBACK_MAX_PAGE = 9  # bound the fallback pass on long combined bundles

PDF_SUFFIXES = (".pdf",)
TIFF_SUFFIXES = (".tif", ".tiff")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
DOCUMENT_SUFFIXES = PDF_SUFFIXES + TIFF_SUFFIXES + IMAGE_SUFFIXES


class MissingDependencyError(RuntimeError):
    """A required system program is not installed. The message says which."""


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def have(binary: str) -> bool:
    return shutil.which(binary) is not None


def _require(binary: str, purpose: str) -> None:
    if not have(binary):
        raise MissingDependencyError(
            f"The program '{binary}' is needed to {purpose} and is not "
            "installed. Run 'extract-text doctor' for install instructions "
            "for your operating system."
        )


# ---------------------------------------------------------------------------
# word acquisition: native PDF text layer, OCR for scans
# ---------------------------------------------------------------------------

BBOX_PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">')
BBOX_WORD_RE = re.compile(
    r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>'
)


def pdf_native_words(pdf, first, last):
    """Word boxes from the embedded text layer via `pdftotext -bbox`."""
    _require("pdftotext", "read text out of PDF files")
    r = run(["pdftotext", "-f", str(first), "-l", str(last), "-bbox", str(pdf), "-"])
    if r.returncode != 0:
        return []
    words, page_no = [], first - 1
    W = H = None
    for chunk in r.stdout.splitlines():
        m = BBOX_PAGE_RE.search(chunk)
        if m:
            page_no += 1
            W, H = float(m.group(1)), float(m.group(2))
            continue
        for m in BBOX_WORD_RE.finditer(chunk):
            x0, y0, x1, y1, txt = m.groups()
            txt = (
                txt.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&#34;", '"').replace("&#39;", "'")
            ).strip()
            if txt and W and H:
                words.append(Word(page_no, float(x0) / W, float(y0) / H,
                                  float(x1) / W, float(y1) / H, txt))
    return words


def ocr_image_words(png, page_no):
    """Word boxes from tesseract TSV (LSTM engine, default psm, fixed DPI)."""
    _require("tesseract", "read scanned pages (OCR)")
    r = run(["tesseract", str(png), "stdout", "--oem", "1", "--dpi", str(OCR_DPI), "tsv"])
    if r.returncode != 0:
        return []
    words = []
    try:
        from PIL import Image

        with Image.open(png) as im:
            W, H = im.size
    except Exception:
        return []
    for row in r.stdout.splitlines()[1:]:
        f = row.split("\t")
        if len(f) != 12 or f[0] != "5":  # level 5 = word
            continue
        txt = f[11].strip()
        conf = float(f[10])
        if not txt or conf < 0:
            continue
        left, top, w, h = int(f[6]), int(f[7]), int(f[8]), int(f[9])
        words.append(Word(page_no, left / W, top / H, (left + w) / W, (top + h) / H, txt, conf))
    return words


def pdf_page_count(pdf):
    _require("pdfinfo", "count PDF pages")
    r = run(["pdfinfo", str(pdf)])
    m = re.search(r"Pages:\s+(\d+)", r.stdout)
    return int(m.group(1)) if m else 1


def tiff_frame_count(tif):
    from PIL import Image

    with Image.open(tif) as im:
        n = 0
        try:
            while True:
                im.seek(n)
                n += 1
        except EOFError:
            pass
    return n


def pages_to_read(n_pages):
    """Defendant block lives on p.1; the attorney footer repeats, but the
    signature block is on the last page. Read 1, 2, and last first; the
    fallback pass adds interior pages when the primary pages yield nothing."""
    want = {1, 2, n_pages}
    return sorted(p for p in want if 1 <= p <= n_pages)


def doc_pages(doc_path):
    doc_path = Path(doc_path)
    suffix = doc_path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return pdf_page_count(doc_path)
    if suffix in TIFF_SUFFIXES:
        return tiff_frame_count(doc_path)
    return 1


def acquire_words(doc_path, workdir, pages, source_hint=None):
    """Word boxes for the given pages of a PDF, TIFF, or image document.
    Returns (words, source)."""
    doc_path = Path(doc_path)
    suffix = doc_path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        if source_hint != "pdf_ocr":
            words = pdf_native_words(doc_path, pages[0], pages[0])
            if len(words) >= MIN_NATIVE_WORDS or source_hint == "pdf_text_layer":
                for p in pages[1:]:
                    words += pdf_native_words(doc_path, p, p)
                return words, "pdf_text_layer"
        # image-only PDF → rasterize the pages we need, then OCR
        _require("pdftoppm", "turn PDF pages into images for OCR")
        words = []
        for p in pages:
            stem = workdir / f"p{p}"
            run(["pdftoppm", "-png", "-gray", "-r", str(OCR_DPI),
                 "-f", str(p), "-l", str(p), str(doc_path), str(stem)])
            outs = sorted(workdir.glob(f"p{p}-*.png")) or sorted(workdir.glob(f"p{p}*.png"))
            if outs:
                words += ocr_image_words(outs[0], p)
                for o in outs:
                    o.unlink(missing_ok=True)
        return words, "pdf_ocr"
    if suffix in TIFF_SUFFIXES:
        from PIL import Image

        words = []
        with Image.open(doc_path) as im:
            for p in pages:
                im.seek(p - 1)
                png = workdir / f"t{p}.png"
                frame = im.convert("L")
                frame.save(png)
                words += ocr_image_words(png, p)
                png.unlink(missing_ok=True)
        return words, "tiff_ocr"
    if suffix in IMAGE_SUFFIXES:
        return ocr_image_words(doc_path, 1), "image_ocr"
    raise ValueError(
        f"Unsupported file type: {doc_path}. Supported: PDF, TIFF, PNG, JPEG, "
        "or plain text passed as a string."
    )


def render_page(doc_path, page=1, dpi=150, out_path=None):
    """Render one page to a PNG, for the AI vision lane and review sheets.

    Returns the PNG path, or None if rendering failed. `out_path` names the
    output; when omitted a file is created beside a temporary directory the
    caller owns.
    """
    doc_path = Path(doc_path)
    suffix = doc_path.suffix.lower()
    if out_path is None:
        out_path = Path(tempfile.mkdtemp(prefix="extract_text_")) / "page.png"
    out_path = Path(out_path)
    if suffix in PDF_SUFFIXES:
        _require("pdftoppm", "turn PDF pages into images")
        stem = out_path.with_suffix("")
        run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
             str(doc_path), str(stem)])
        outs = sorted(out_path.parent.glob(stem.name + "*.png"))
        if not outs:
            return None
        outs[0].rename(out_path)
        return out_path
    if suffix in TIFF_SUFFIXES:
        from PIL import Image

        with Image.open(doc_path) as im:
            im.seek(page - 1)
            im.convert("L").save(out_path)
        return out_path
    if suffix in IMAGE_SUFFIXES:
        return doc_path
    return None


# ---------------------------------------------------------------------------
# the Document bundle
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """A loaded document: positioned words, clustered lines, assembled text.

    `text` is the rail-stripped, line-clustered text of the pages read, which
    is what the generic text rules and the grounding check run against.
    """

    path: Path
    n_pages: int
    pages_read: list[int]
    words: list[Word]
    lines: list[Line] = field(default_factory=list)
    source: str = "pdf_text_layer"

    @property
    def text(self) -> str:
        return page_text(self.lines)

    @property
    def ocr_mean_conf(self) -> float:
        if not self.words:
            return 0.0
        return round(sum(w.conf for w in self.words) / len(self.words), 1)

    def extend(self, more_words: list[Word]) -> None:
        """Add words from fallback pages and recluster."""
        self.words = self.words + more_words
        self.lines = cluster_lines(strip_line_number_rail(self.words))


def load_document(path, pages=None) -> Document:
    """Read a document file into positioned words and clustered lines.

    By default reads pages 1, 2, and the last page, which carry every field
    the extractors look for on a summons. Pass an explicit `pages` list to
    override.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")
    n_pages = doc_pages(path)
    wanted = pages or pages_to_read(n_pages)
    with tempfile.TemporaryDirectory(prefix="extract_text_") as td:
        words, source = acquire_words(path, Path(td), wanted)
    doc = Document(path=path, n_pages=n_pages, pages_read=list(wanted),
                   words=words, source=source)
    doc.lines = cluster_lines(strip_line_number_rail(words))
    return doc


def load_fallback_pages(doc: Document) -> list[int]:
    """Read interior pages 3..9 into the document (combined summons+complaint
    bundles can bury the service block there). Returns the pages added."""
    extra = [p for p in range(3, min(doc.n_pages, FALLBACK_MAX_PAGE) + 1)
             if p not in doc.pages_read]
    if not extra:
        return []
    with tempfile.TemporaryDirectory(prefix="extract_text_") as td:
        more, _ = acquire_words(doc.path, Path(td), extra, source_hint=doc.source)
    doc.extend(more)
    doc.pages_read += extra
    return extra
