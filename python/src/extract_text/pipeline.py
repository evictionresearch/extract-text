"""Batch processing: a folder of documents in, a case table out.

This is the harness the two engines run under. Point it at files or folders
and it produces:

- `extracted.csv` — one row per document, flat columns, ready for a
  spreadsheet, R, or a database load
- `extracted.jsonl` — the full detail per document (every field, its
  evidence, its flags), the audit trail behind the CSV
- `extracted.parquet` — the same rows as the CSV, written when the pyarrow
  library is installed
- `review/index.html` — a contact sheet of flagged and sampled documents,
  page image beside extracted fields, for human review

Engine choice is explicit and the two never blend silently:

- `engine="deterministic"` — rules only. No model involved anywhere.
- `engine="ai"` — the local vision model only.
- `engine="both"` — rules fill the main columns, the model's answers land in
  `ai_*` columns beside them, and disagreement is measured and flagged. The
  main columns are never overwritten by the model.

Outputs contain whatever the documents contain, which for real court records
means names and addresses. Write them somewhere governed (not into a code
repository), and see DATA-USE.md.
"""

from __future__ import annotations

import csv
import json
import random
import re
import shutil
import sys
import threading
import time
import warnings
from pathlib import Path

from .deterministic import extract_from_document
from .documents import DOCUMENT_SUFFIXES, load_document, render_page
from .parties import _party_key, drop_plaintiff_matches
from .schema import Extraction
from .similarity import SAME_STREET_THRESHOLD, address_similarity, norm

SAMPLE_SEED = 42

# Filename preference when a case folder holds several documents and only the
# summons is wanted (ported from wa_doc_scan.pick_summons): plain summons >
# summons+complaint > by-mail > archive copies last.
SUMMONS_NAME_RE = re.compile(r"summons", re.IGNORECASE)


def choose_summons(case_dir):
    """Choose the summons document for a case directory, deterministically.

    Returns (path, variant) or (None, "")."""
    case_dir = Path(case_dir)
    cands = [p for p in sorted(case_dir.iterdir())
             if p.suffix.lower() in (".pdf", ".tif", ".tiff")
             and SUMMONS_NAME_RE.search(p.name)]
    if not cands:
        return None, ""

    def rank(p):
        n = p.name.lower()
        return (
            n.startswith("csde_"),
            "by_mail" in n or "by mail" in n,
            "complaint" in n,
            len(n),
            n,
        )

    best = sorted(cands, key=rank)[0]
    n = best.name.lower()
    variant = ("summons_by_mail" if ("by_mail" in n or "by mail" in n)
               else "summons_complaint" if "complaint" in n else "summons")
    return best, variant


def _content_hash(path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _excluded_documents(exclude) -> tuple[set, set]:
    """The resolved paths and content hashes of every document in the scans
    listed in `exclude`, so a new draw can leave them out."""
    paths, shas = set(), set()
    for folder in exclude or []:
        _, details = read_scan(folder)
        for detail in details:
            src = detail.get("file") or ""
            if not src:
                continue
            path = Path(src)
            paths.add(path.resolve())
            try:
                shas.add(_content_hash(path))
            except OSError:
                # the earlier scan's file is gone; its path still excludes it
                pass
    return paths, shas


def collect_inputs(inputs, recursive=True):
    """Expand files and directories into a sorted document list."""
    if isinstance(inputs, (str, Path)):
        inputs = [inputs]
    files = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            files += [f for f in it
                      if f.is_file() and f.suffix.lower() in DOCUMENT_SUFFIXES]
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(f"No such file or directory: {p}")
    # sorted, deduplicated: same input, same order, every run
    return sorted(dict.fromkeys(f.resolve() for f in files))


# ---------------------------------------------------------------------------
# flattening an Extraction into one tidy row
# ---------------------------------------------------------------------------


def _names(parties) -> str:
    return "; ".join(p.name for p in parties)


def _addr_cols(prefix, addr) -> dict:
    a = addr or None
    return {
        f"{prefix}_address_raw": a.raw if a else "",
        f"{prefix}_street": (a.street or "") if a else "",
        f"{prefix}_unit": (a.unit or "") if a else "",
        f"{prefix}_city": (a.city or "") if a else "",
        f"{prefix}_state": (a.state or "") if a else "",
        f"{prefix}_zip": (a.zip or "") if a else "",
    }


def flatten_extraction(x: Extraction) -> dict:
    """One flat row per document. Lists join with '; '."""
    rec = x.record
    att = rec.attorney
    doc = x.document
    anchor = ""
    ev = x.evidence.get("defendant_address")
    if ev is not None and ev.anchor:
        anchor = ev.anchor
    row = {
        "file": (doc.file if doc else "") or "",
        "case_number": rec.case_number or "",
        "plaintiffs": _names(rec.plaintiffs),
        "defendant_names": _names(rec.defendants),
        "n_defendants": len(rec.defendants),
        **_addr_cols("defendant", rec.defendant_address),
        "defendant_anchor": anchor,
        "attorney_names": (att.names or "") if att else "",
        "attorney_firm": (att.firm or "") if att else "",
        **_addr_cols("attorney", att.address if att else None),
        "attorney_phone": (att.phone or "") if att else "",
        "attorney_bar_numbers": (att.bar_numbers or "") if att else "",
        "court_name": rec.court_name or "",
        "county": rec.county or "",
        "state": rec.state or "",
        "case_type": rec.case_type or "",
        "filing_date": rec.filing_date.isoformat() if rec.filing_date else "",
        "amount_claimed": rec.amount_claimed if rec.amount_claimed is not None else "",
        "judgment_amount": (rec.judgment.amount
                            if rec.judgment and rec.judgment.amount is not None else ""),
        "judgment_date": (rec.judgment.date.isoformat()
                          if rec.judgment and rec.judgment.date else ""),
        "disposition": rec.disposition or "",
        "disposition_date": (rec.disposition_date.isoformat()
                             if rec.disposition_date else ""),
        "n_ungrounded": len(x.ungrounded_fields()),
        "n_pages": (doc.n_pages if doc else "") or "",
        "text_source": (doc.text_source if doc else "") or "",
        "ocr_mean_conf": doc.ocr_mean_conf if doc and doc.ocr_mean_conf is not None else "",
        "method": x.method,
        "backend": x.backend,
        "flags": ";".join(x.flags),
    }
    return row


def _ai_columns(ai: Extraction | None) -> dict:
    """Advisory columns for the AI lane in engine='both' runs."""
    if ai is None:
        return {
            "ai_case_number": "", "ai_plaintiff": "", "ai_defendant_names": "",
            "ai_defendant_address": "", "ai_law_firm": "", "ai_law_firm_address": "",
            "ai_backend": "", "ai_flags": "",
        }
    rec = ai.record
    return {
        "ai_case_number": rec.case_number or "",
        "ai_plaintiff": _names(rec.plaintiffs),
        "ai_defendant_names": _names(rec.defendants),
        "ai_defendant_address": rec.defendant_address.raw if rec.defendant_address else "",
        "ai_law_firm": (rec.attorney.firm or "") if rec.attorney else "",
        "ai_law_firm_address": (rec.attorney.address.raw
                                if rec.attorney and rec.attorney.address else ""),
        "ai_backend": ai.backend,
        "ai_flags": ";".join(ai.flags),
    }


def case_key(case_number: str | None) -> str:
    """A case number for comparison: no spaces, and without the county code
    a page prints after it ("... SEA"), which the AI engine reads and the
    rules engine does not."""
    key = re.sub(r"\s+", "", case_number or "").upper()
    return re.sub(r"(?<=\d)[-.]?[A-Z]{2,4}$", "", key)


def _cross_check(row: dict, det: Extraction, ai: Extraction) -> dict:
    """Compare the two engines' answers and add agreement columns + flags."""
    det_addr = det.record.defendant_address.raw if det.record.defendant_address else None
    ai_addr = ai.record.defendant_address.raw if ai.record.defendant_address else None
    sim = address_similarity(det_addr, ai_addr)
    extra_flags = []
    if det_addr and ai_addr:
        if sim is not None and sim < SAME_STREET_THRESHOLD:
            extra_flags.append("engines_disagree_address")
    elif ai_addr and not det_addr:
        extra_flags.append("only_ai_found_address")
    elif det_addr and not ai_addr:
        extra_flags.append("only_rules_found_address")

    det_case = det.record.case_number
    ai_case = ai.record.case_number
    case_agree = ""
    if det_case and ai_case:
        case_agree = case_key(det_case) == case_key(ai_case)
        if case_agree is False:
            extra_flags.append("engines_disagree_case_number")

    # the AI engine read the caption's plaintiff; a deterministic defendant carrying
    # that name is a misread even when the deterministic engine read no plaintiff.
    # Flagged only: the model never edits the main columns.
    _, crossed = drop_plaintiff_matches([p.name for p in det.record.defendants],
                                        [p.name for p in ai.record.plaintiffs])
    if crossed:
        extra_flags.append("deterministic_defendant_is_ai_plaintiff")

    out = {
        "address_similarity": "" if sim is None else sim,
        "address_same_street": "" if sim is None else sim >= SAME_STREET_THRESHOLD,
        "case_number_agree": case_agree,
    }
    if extra_flags:
        out["flags"] = ";".join(filter(None, [row.get("flags", ""), *extra_flags]))
    return out


# ---------------------------------------------------------------------------
# the scan itself
# ---------------------------------------------------------------------------


def _clock(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class _Progress:
    """The scan's progress line on stderr: a bar, documents done, elapsed
    time, an estimate of the time left, and which engine is working now.

    In a terminal the line redraws in place and ticks once a second, so a
    slow AI page never looks like a hang. Elsewhere (a log file, a pipe) it
    falls back to a plain line every 25 documents. It never shows file or
    folder names: in court collections those can carry case numbers, and
    terminal output is what gets pasted into issues and chats.

    `callback`, when given, is called as callback(done, total, failed,
    current, what) each time a document starts or finishes, whether or not
    the line itself is shown. The R package draws its own bar from it. It is
    only ever called from the scanning thread, never from the ticker, since
    R cannot be called from another thread; and like the line it carries
    counts, never names. A callback that raises is dropped with a warning,
    so a display problem can never stop a scan."""

    WIDTH = 24

    def __init__(self, total: int, enabled: bool = True, stream=None, callback=None):
        self.total = total
        self.enabled = enabled
        self.callback = callback
        self.stream = stream or sys.stderr
        self.live = enabled and self.stream.isatty()
        self.start = time.monotonic()
        self.done = self.failed = self.current = 0
        self.last_done_at = 0.0
        self.what = ""
        self._lock = threading.Lock()
        self._stop = threading.Event()
        if self.live:
            self._draw()
            threading.Thread(target=self._tick, daemon=True).start()

    def status(self, i: int, what: str):
        with self._lock:
            self.current, self.what = i, what
        if self.live:
            self._draw()
        self._report()

    def advance(self, failed: bool = False):
        with self._lock:
            self.done += 1
            self.failed += failed
            self.last_done_at = time.monotonic() - self.start
            self.what = ""
        if self.live:
            self._draw()
        elif self.enabled and (self.done % 25 == 0 or self.done == self.total):
            print(f"  scanned {self.done}/{self.total}", file=self.stream)
        self._report()

    def _report(self):
        if self.callback is None:
            return
        try:
            self.callback(self.done, self.total, self.failed, self.current, self.what)
        except Exception as e:
            self.callback = None
            warnings.warn(f"progress display stopped: {type(e).__name__}: {e}", stacklevel=2)

    def close(self):
        self._stop.set()
        if self.live:
            self._draw()
            self.stream.write("\n")
            self.stream.flush()

    def _tick(self):
        while not self._stop.wait(1.0):
            self._draw()

    def _draw(self):
        with self._lock:
            elapsed = time.monotonic() - self.start
            filled = self.WIDTH * self.done // self.total
            parts = [f"[{'#' * filled}{'-' * (self.WIDTH - filled)}]",
                     f"{self.done}/{self.total} documents",
                     f"{_clock(elapsed)} elapsed"]
            if 0 < self.done < self.total:
                # pace from finished documents only, counting down while the
                # current one runs, so the estimate does not creep upward
                per_doc = self.last_done_at / self.done
                left = per_doc * (self.total - self.done)
                left = max(0.0, left - (elapsed - self.last_done_at))
                parts.append(f"about {_clock(left)} left")
            if self.failed:
                parts.append(f"{self.failed} failed")
            if self.what and self.done < self.total:
                parts.append(f"document {self.current}: {self.what}")
            cols = shutil.get_terminal_size((100, 20)).columns - 1
            self.stream.write("\r" + "  ".join(parts)[:cols].ljust(cols))
            self.stream.flush()


def scan(
    inputs,
    engine: str = "deterministic",
    out_dir=None,
    model: str | None = None,
    prompt_format: str = "lists",
    limit: int = 0,
    sample: int = 0,
    seed: int = SAMPLE_SEED,
    recursive: bool = True,
    write: bool = True,
    parquet: bool | None = None,
    progress: bool = True,
    exclude=None,
    on_progress=None,
):
    """Extract every document under `inputs`. Returns the list of row dicts.

    `exclude` lists earlier scan folders whose documents must not be drawn
    again, matched by path and by content, so a second grading round never
    repeats a document of the first even where the same filing sits under
    two names. With `sample`, the draw walks a seeded shuffle and skips
    those, so it differs from the draw the same seed gives without
    `exclude`.

    `engine` is 'deterministic', 'ai', or 'both'. `prompt_format` picks the
    AI engine's prompt: 'lists' (the default) or 'v1', the original. When `write` is true (the
    default) and `out_dir` is given, extracted.csv, extracted.jsonl, and the
    review inputs are written there; parquet too when pyarrow is installed
    (set `parquet=False` to skip it, `parquet=True` to require it).

    `progress` shows the progress line on stderr. `on_progress`, a function
    of (done, total, failed, current, what), is called as each document
    starts and finishes, for callers that draw their own (see _Progress).
    """
    if engine not in ("deterministic", "ai", "both"):
        raise ValueError("engine must be 'deterministic', 'ai', or 'both'")

    files = collect_inputs(inputs, recursive=recursive)
    if limit:
        files = files[:limit]
    skip_paths, skip_shas = _excluded_documents(exclude)
    if skip_paths:
        files = [p for p in files if p.resolve() not in skip_paths]
    if sample and sample < len(files) and skip_shas:
        # a seeded shuffle, taking the first `sample` documents whose
        # content is not in an earlier scan; only the drawn ones are hashed
        order = list(files)
        random.Random(seed).shuffle(order)
        drawn = []
        for path in order:
            if _content_hash(path) in skip_shas:
                continue
            drawn.append(path)
            if len(drawn) == sample:
                break
        files = sorted(drawn)
    elif sample and sample < len(files):
        # a seeded random draw across the whole collection, so a grading
        # round is not the first N paths in sort order (one county, one year)
        files = sorted(random.Random(seed).sample(files, sample))
    elif skip_shas:
        files = [p for p in files if _content_hash(p) not in skip_shas]
    if not files:
        raise FileNotFoundError(
            "No documents found. Supported types: " + ", ".join(DOCUMENT_SUFFIXES)
        )

    vision = None
    if engine in ("ai", "both"):
        from .ai.vision import DEFAULT_VISION_MODEL, LocalVisionBackend

        vision = LocalVisionBackend(model=model or DEFAULT_VISION_MODEL,
                                    prompt_format=prompt_format)

    rows, details, n_err = [], [], 0
    bar = _Progress(len(files), enabled=progress, callback=on_progress)
    try:
        for i, path in enumerate(files, 1):
            failed = False
            try:
                det = ai = None
                doc_text = None
                if engine in ("deterministic", "both"):
                    bar.status(i, "deterministic engine")
                    doc = load_document(path)
                    det = extract_from_document(doc)
                    doc_text = doc.text
                if vision is not None:
                    bar.status(i, "AI engine")
                    ai = vision.extract_file(path, source_text=doc_text)

                primary = det if det is not None else ai
                row = flatten_extraction(primary)
                row["file"] = path.name
                if engine == "both":
                    row.update(_ai_columns(ai))
                    if det is not None and ai is not None:
                        row.update(_cross_check(row, det, ai))
                rows.append(row)
                details.append({
                    "file": str(path),
                    "row": row,
                    "deterministic": det.model_dump(mode="json") if det else None,
                    "ai": ai.model_dump(mode="json") if ai else None,
                })
            except Exception as e:
                n_err += 1
                failed = True
                rows.append({"file": path.name, "flags": f"scan_error:{type(e).__name__}"})
                details.append({"file": str(path),
                                "error": f"{type(e).__name__}: {e}"})
            bar.advance(failed)
    finally:
        bar.close()

    if write and out_dir is not None:
        write_outputs(rows, details, out_dir, parquet=parquet)
    return rows


def write_outputs(rows, details, out_dir, parquet=None):
    """Write extracted.csv, extracted.jsonl, and optionally parquet."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fieldnames = []
    for r in rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    cpath = out / "extracted.csv"
    with open(cpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    with open(out / "extracted.jsonl", "w") as jf:
        jf.writelines(json.dumps(d) + "\n" for d in details)

    if parquet is not False:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            # column-wise, with consistent types: empty cells become null; a
            # column stays numeric only when every present value is numeric
            columns = {}
            for fn in fieldnames:
                vals = [r.get(fn) for r in rows]
                vals = [None if v in ("", None) else v for v in vals]
                present = [v for v in vals if v is not None]
                if present and all(isinstance(v, (int, float, bool)) for v in present):
                    columns[fn] = vals
                else:
                    columns[fn] = [None if v is None else str(v) for v in vals]
            pq.write_table(pa.table(columns), out / "extracted.parquet")
        except ImportError:
            if parquet is True:
                raise RuntimeError(
                    "Parquet output needs pyarrow: pip install 'extract-text[parquet]'"
                )
    return out


# ---------------------------------------------------------------------------
# the review contact sheet
# ---------------------------------------------------------------------------


GRADER_PANEL = """
<div id="grader">
  <label>Your name <input id="gname" placeholder="required to save"></label>
  <label>Email <input id="gemail" type="email"></label>
  <label>How many to grade
    <select id="gcount"><option>10</option><option>30</option><option>100</option>
      <option value="all">all</option></select></label>
  <button type="button" id="gmore">Grade another batch</button>
  <span id="gnote"></span>
</div>
<div id="keep" hidden>
  <p><b>Your answers are kept in this web browser, on this computer.</b>
    Use this browser each time you grade. When you stop for the day, press
    <b>Download my answers</b> and upload the file to the Drive folder the
    zip came from. Each download holds every answer so far, so the newest
    file is the only one Tim needs.</p>
  <div class="buttons">
    <button type="button" id="kdown">Download my answers</button>
    <label class="quiet">Bring back answers from a downloaded file
      <input type="file" id="kload" accept=".jsonl"></label>
    <span id="knote"></span>
  </div>
</div>"""

WORST_FLAGS = ("no_defendant_address", "defendant_equals_attorney", "engines_disagree_address",
               "only_ai_found_address", "only_rules_found_address", "no_text", "scan_error")


def review_tier(row: dict, detail: dict) -> int:
    """How badly a document needs a person, for the graders' page order:
    3 for an address the scan itself distrusts, 2 for a field the two
    engines disagree on, 1 for any other flag, 0 for a clean row."""
    flags = row.get("flags", "") or ""
    if any(f in flags for f in WORST_FLAGS):
        return 3
    ai = ai_reading(detail)
    if ai and engine_differences(row, ai):
        return 2
    return 1 if flags else 0


def write_review(out_dir, n=30, seed=SAMPLE_SEED, flagged_first=True, graders=False,
                 attorneys=0, order="worst", overlap=0, rows=None):
    """Build review/index.html from a finished scan directory: page-1 image
    beside the extracted fields, flagged documents first, then a seeded
    sample of the rest. This is where a person checks the machine's work.

    Each document carries a correction form. Opened as a plain file the page
    is read-only; served by `extract-text review --serve` the form saves to
    `corrections.jsonl` in the scan directory (see corrections.py).

    `attorneys` puts the plaintiff attorney's box on that many documents,
    drawn at random from the whole scan with the same seed every time, so
    every grader of a folder sees it on the same documents (`"all"` for
    every one, 0 for none). A few dozen answers measure the attorney block;
    asking on every document would slow the whole round.

    `order` sets the graders' page order: "worst" puts the documents most in
    need of a person first, which finds failures fastest but makes any
    accuracy figure pessimistic; "random" serves every document in an order
    unrelated to its content, so whatever share gets graded is a fair sample
    of the folder, and each answer is recorded as a random draw.

    `overlap` puts that many documents, drawn at random with a fixed seed,
    first in the same order for every grader, so each of them is answered
    more than once and `extract-text agree` can measure how often graders
    agree. `rows` builds a page of just those document numbers, for
    settling the documents graders disagreed on; it shows every answer saved
    so far and leaves the page's sample record alone. With `graders` too it
    is a graders' page of just those documents instead: each save records
    the grader's name, and no other answer is shown, so a chosen set (say,
    the documents one person has already graded) can be graded again
    blind."""
    out = Path(out_dir)
    rev = out / "review"
    rev.mkdir(parents=True, exist_ok=True)
    rows_scan, details = read_scan(out)
    numbered = list(enumerate(rows_scan, 1))
    if order not in ("worst", "random"):
        raise ValueError(f"order must be 'worst' or 'random', not {order!r}")
    random_order = graders and order == "random"
    # in random order every document sits in one tier, so the page's
    # per-grader shuffle is the whole order
    tiers = ({i: 0 if random_order else review_tier(r, details[i - 1]) for i, r in numbered}
             if graders else {})

    flagged = [(i, r) for i, r in numbered if r.get("flags")]
    clean = [(i, r) for i, r in numbered if not r.get("flags")]
    rng = random.Random(seed)
    subset = flagged[:n] if flagged_first else []
    remaining = max(0, n - len(subset))
    # flagged-first fills the rest from the unflagged rows; a plain random
    # page draws from every row, flagged or not, which is what an accuracy
    # estimate for the whole scan needs
    pool = clean if flagged_first else numbered
    if remaining and pool:
        subset += sorted(rng.sample(pool, min(remaining, len(pool))))
    # how each row came to be on the page, for the corrections record: only
    # the randomly drawn rows estimate accuracy for the whole scan
    drawn = {i: "flagged" for i, _ in flagged[:n]} if flagged_first else {}
    drawn.update({i: "random" for i, _ in subset if i not in drawn})
    # the shared set: its own seeded draw, listed in the order every grader
    # meets it
    shared = (random.Random(f"overlap-{seed}").sample(
        [i for i, _ in numbered], min(int(overlap or 0), len(numbered))) if graders else [])
    shared_at = {i: k for k, i in enumerate(shared)}
    if graders:
        # every document goes on the page, worst first; the page shows each
        # grader a batch of the size they choose and hides the rest
        subset = sorted(numbered, key=lambda ir: (-tiers[ir[0]], ir[0]))
        drawn = {i: ("flagged" if tiers[i] else "random") for i, _ in subset}
        if random_order:
            drawn = {i: "random" for i, _ in subset}
        drawn.update({i: "random" for i in shared})
    if rows:
        wanted = sorted({int(i) for i in rows})
        missing = [i for i in wanted if not 1 <= i <= len(numbered)]
        if missing:
            raise ValueError(f"no document numbered {missing[0]} in this scan")
        subset = [numbered[i - 1] for i in wanted]
    else:
        (rev / "sample.json").write_text(
            json.dumps({str(i): how for i, how in sorted(drawn.items())}))
    # its own seeded draw, so turning it on never changes which documents
    # the page shows
    if attorneys == "all":
        ask_attorney = {i for i, _ in numbered}
    else:
        ask_attorney = set(random.Random(f"attorneys-{seed}").sample(
            [i for i, _ in numbered], min(int(attorneys or 0), len(numbered))))
    # the settling page asks for the attorney block wherever a grader
    # answered it; without the box a settled answer would drop that block
    # It also marks, on each document, the fields where the graders differ
    # and how, with a tally across the page, so patterns in the
    # disagreements show
    differ_by_row, settle_summary = {}, ""
    hint = ("Boxes start with the machine's reading; fix what is wrong, clear what is "
            "not there, then save.")
    if rows and not graders:
        hint = ("Press Keep this one above to fill these boxes from a grader's answer, "
                "fix anything wrong, then save.")
        from collections import Counter

        from .agree import field_differences
        from .corrections import load_answers
        answers = load_answers(out)
        ask_attorney |= {row for row, a in answers.items()
                         if any("attorneys" in c.get("truth", {}) for c in a.values())}
        differ_by_row = field_differences({i: answers[i] for i, _ in subset if i in answers})
        totals = {}
        for found in differ_by_row.values():
            for field, how in found.items():
                totals.setdefault(field, Counter())[how] += 1
        if totals:
            settle_summary = (
                f'<p class="others">Where the graders differ, by field, across these '
                f'{len(subset)} documents: '
                + "; ".join(f"{field} {sum(c.values())} ("
                            + ", ".join(f"{n} {how}" for how, n in c.most_common()) + ")"
                            for field, c in sorted(totals.items(), key=lambda fc: -sum(fc[1].values())))
                + ".</p>")

    cells = []
    esc = lambda s: ((s or "").replace("&", "&amp;").replace("<", "&lt;")
                     .replace('"', "&quot;"))
    for i, r in subset:
        src = Path(details[i - 1].get("file", ""))
        # numbered, not named after the file: same-named files would
        # overwrite each other, and file names can carry case numbers
        img_name = f"doc_{i:04d}.png"
        if src.exists():
            # rendered sharp enough to read when enlarged; shown small until clicked
            render_page(src, page=1, dpi=150, out_path=rev / img_name)
        both = bool(r.get("ai_backend"))
        both_parts = lambda *parts: ", ".join(x for x in parts if x)
        ai_col = (lambda v: f"<td>{esc(v)}</td>") if both else (lambda v: "")
        sim = r.get("address_similarity", "")
        start = review_prefill(r, details[i - 1])
        ai_answer = ai_reading(details[i - 1])
        differ = engine_differences(r, ai_answer) if ai_answer else {}
        mark = lambda field: ' class="differ"' if field in differ else ""
        if not ai_answer:
            verdict = ""
        elif differ:
            verdict = ('<p class="disagree">The engines disagree on '
                       + ", ".join(f"{k} ({v})" if v else k for k, v in differ.items())
                       + ".</p>")
        else:
            verdict = '<p class="agree">The engines agree on every field below.</p>'
        # attorneys and firm share one box (from round 2): graders could not
        # always tell a lawyer from the firm, nor did they need to
        att_lines = [*start['attorneys'], *([start['attorney_firm']] if start['attorney_firm'] else [])]
        att_box = f"""<fieldset class="att"><legend>Plaintiff's attorney</legend>
        <label>Attorneys and firm, one per line, as printed <textarea name="attorneys" rows="2">{esc(chr(10).join(att_lines))}</textarea></label>
        <label>Address, on one line as printed <input name="attorney_address" value="{esc(start['attorney_address'])}"></label>
      </fieldset>""" if i in ask_attorney else ""
        ai_button = ('<button type="button" class="quiet use-ai">Use AI engine\'s reading</button>'
                     if ai_answer else "")
        cells.append(f"""
<div class="doc" id="doc{i}" data-tier="{tiers.get(i, 0)}"{f' data-shared="{shared_at[i]}"' if i in shared_at else ''}>
  <div class="page">
    <img src="{img_name}" loading="lazy" alt="page 1 of document {i}"
         title="Click to enlarge">
    <p class="pagelinks">Click the page to enlarge it.
      <a class="full" href="doc/{i}" target="_blank" hidden>Open the full document</a></p>
  </div>
  <div class="fields">
    <h3>#{i} · {esc(r.get('file',''))} · {esc(r.get('case_number','')) or 'no case number'}</h3>
    <p class="meta">flags: {esc(r.get('flags','')) or 'none'} · source: {esc(r.get('text_source',''))}
       conf {esc(str(r.get('ocr_mean_conf','')))}</p>
    {verdict}
    <table class="read">
      <tr><th></th><th>{'Deterministic engine' if r.get('method') != 'ai' else 'AI engine'}</th>{'<th>AI engine</th>' if both else ''}</tr>
      <tr{mark('plaintiff')}><th>Plaintiff</th><td>{esc(r.get('plaintiffs',''))}</td>{ai_col(r.get('ai_plaintiff',''))}</tr>
      <tr{mark('defendants')}><th>Defendants</th><td>{esc(r.get('defendant_names',''))}</td>{ai_col(r.get('ai_defendant_names',''))}</tr>
      <tr{mark('address')}><th>Address</th><td>{esc(r.get('defendant_address_raw',''))}
          <i>{esc(r.get('defendant_anchor',''))}</i></td>{ai_col(r.get('ai_defendant_address','') + (f'  (similarity {sim})' if sim != '' else ''))}</tr>
      <tr{mark('attorney firm')}><th>Attorney</th><td>{esc(both_parts(r.get('attorney_names'), r.get('attorney_firm'), r.get('attorney_address_raw')))}</td>{ai_col(both_parts('; '.join((ai_answer or {}).get('attorneys', [])), r.get('ai_law_firm'), r.get('ai_law_firm_address')))}</tr>
    </table>
    <form class="fix" data-row="{i}" data-ai="{esc(json.dumps(ai_answer)) if ai_answer else ''}"
          data-differ="{esc(json.dumps(differ_by_row.get(i, {})))}">
      <p class="hint">The right answer, as printed on the page. {hint}</p>
      <label>Plaintiff, the name only (several plaintiffs, one per line) <textarea name="plaintiff" rows="1">{esc(start['plaintiff'])}</textarea></label>
      <label>Defendants, one per line <textarea name="defendants" rows="2">{esc(chr(10).join(start['defendants']))}</textarea></label>
      <div class="addr">
        <label class="street">Street <input name="street" value="{esc(start['street'])}"></label>
        <label class="unit">Unit <input name="unit" value="{esc(start['unit'])}"></label>
        <label>City <input name="city" value="{esc(start['city'])}"></label>
        <label class="short">State <input name="state" value="{esc(start['state'])}"></label>
        <label class="short">ZIP <input name="zip" value="{esc(start['zip'])}"></label>
      </div>
      {att_box}
      <label>Note <input name="note" placeholder="optional"></label>
      <div class="buttons">
        <button type="submit" value="checked">Save</button>
        {ai_button}
        <button type="submit" value="unreadable" class="quiet">Can't tell from the page</button>
        <span class="status"></span>
      </div>
    </form>
  </div>
</div>""")
    html = f"""<!doctype html><meta charset="utf-8"><title>extract-text review</title>
<style>
 body{{font-family:system-ui;margin:1rem;background:#f5f5f2;color:#222}}
 header{{padding:.4rem 0}}
 #grader{{display:flex;flex-wrap:wrap;gap:1rem;align-items:end;background:#e8eef6;
      border:1px solid #c5d2e3;padding:.6rem .8rem;margin:.4rem 0}}
 #grader label{{font-size:14px;color:#333}} #grader input,#grader select{{display:block;font:inherit;padding:.25rem .35rem}}
 #gnote{{align-self:center;color:#2e4a6b}}
 #banner{{background:#fff3cd;border:1px solid #e0c870;padding:.6rem;margin:.5rem 0}}
 #keep{{background:#eef7ee;border:1px solid #b9dbb9;padding:.2rem .8rem .6rem;margin:.4rem 0}}
 #keep p{{margin:.4rem 0;max-width:60rem}} #keep label{{font-size:14px;color:#333}}
 #knote.warn{{color:#a02020;font-weight:600}}
 .doc{{display:flex;gap:1rem;background:#fff;border:1px solid #ddd;
      margin-bottom:1rem;padding:1rem}}
 /* display:flex above would otherwise override the hidden attribute, and the
    graders' page would show every document instead of the chosen batch */
 .doc[hidden]{{display:none}}
 .page{{flex:0 0 460px;align-self:flex-start}}
 .fields{{align-self:flex-start}}
 .page img{{width:100%;height:auto;border:1px solid #ccc;cursor:zoom-in;display:block}}
 .pagelinks{{font-size:13px;color:#555;margin:.3rem 0}}
 .doc{{scroll-margin-top:.5rem}}
 /* enlarged: the page takes the room, and the table and form stay beside
    it, riding down the screen while the page scrolls past */
 .doc.big .page{{flex:1 1 auto;min-width:0}}
 .doc.big .fields{{flex:0 0 36rem;position:sticky;top:.5rem;
      max-height:calc(100vh - 1rem);overflow-y:auto}}
 .doc.big .page img{{cursor:zoom-out}}
 .fields{{font-size:14px;flex:1;max-width:46rem}} h3{{margin:.2rem 0}}
 .meta{{color:#555;margin:.2rem 0 .6rem}}
 table.read{{border-collapse:collapse;width:100%;margin-bottom:.8rem}}
 table.read th,table.read td{{border-bottom:1px solid #eee;padding:.25rem .4rem;
      text-align:left;vertical-align:top}}
 table.read th{{white-space:nowrap;color:#555;font-weight:600}}
 table.read tr.differ td,table.read tr.differ th{{background:#fff1d6}}
 table.read tr.differ th::after{{content:" ≠";color:#b06000}}
 .disagree{{background:#fff1d6;border-left:4px solid #e0a030;padding:.35rem .6rem;margin:.3rem 0 .5rem}}
 .agree{{background:#eef7ee;border-left:4px solid #7cb87c;padding:.35rem .6rem;margin:.3rem 0 .5rem}}
 form.fix{{background:#f7f9fc;border:1px solid #d8e0ea;padding:.7rem}}
 form.fix.saved{{background:#f1f8f1;border-color:#b9dbb9}}
 form.fix label{{display:block;margin:.3rem 0;color:#444}}
 form.fix input,form.fix textarea{{display:block;width:100%;box-sizing:border-box;
      font:inherit;padding:.25rem .35rem;border:1px solid #bbb;border-radius:3px}}
 /* boxes grow with what is in them (see grow), so a long list shows whole */
 form.fix textarea{{resize:vertical;overflow-y:auto}}
 .addr{{display:flex;flex-wrap:wrap;gap:.5rem}}
 .addr label{{flex:1 1 7rem}} .addr label.street{{flex:3 1 16rem}}
 .addr label.unit{{flex:2 1 10rem}}
 .addr label.short{{flex:0 1 5rem}}
 fieldset.att{{border:1px solid #d8e0ea;margin:.6rem 0 .3rem;padding:.2rem .6rem .4rem}}
 fieldset.att legend{{color:#444;padding:0 .3rem}}
 .hint{{margin:0 0 .4rem;color:#555}}
 .others{{background:#fbf7ec;border:1px solid #e6dcc0;padding:.3rem .6rem;margin-bottom:.5rem;font-size:13px}}
 .others p{{margin:.2rem 0}}
 .others table{{border-collapse:collapse;margin:.3rem 0}}
 .others th,.others td{{border:1px solid #e6dcc0;padding:.15rem .4rem;text-align:left;
      vertical-align:top;white-space:pre-line}}
 .others tr.differ{{background:#ffd27a}} .others tr.fmt{{background:#fff0c2}}
 .others td.na{{color:#999;font-style:italic}}
 .others .chosen{{box-shadow:inset 0 0 0 2px #2e6b2e;font-weight:600}}
 .others th.chosen{{background:#2e6b2e;color:#fff}}
 .others p.kept{{color:#2e6b2e;font-weight:600}}
 button.keep.on{{background:#2e6b2e;color:#fff;border-color:#2e6b2e}}
 input,textarea{{transition:background .8s}}
 input.flash,textarea.flash{{background:#ffe27a}}
 .buttons{{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;margin-top:.5rem}}
 button{{font:inherit;padding:.3rem .9rem;cursor:pointer;white-space:nowrap}}
 button.quiet{{background:none;border:1px solid #bbb}}
 .status.ok{{color:#2e6b2e}} .status.err{{color:#a02020}}
</style>
<header>
<h1>Review: {len(subset)} of {len(rows_scan)} documents
    ({len(flagged)} flagged in total; {('in random order' if random_order else 'worst first') if graders else 'flagged shown first' if flagged_first else 'a random draw'})</h1>
<p id="count"></p>
{settle_summary}
{GRADER_PANEL if graders else ''}
<div id="banner" hidden>This page was opened as a file, so corrections cannot be saved.
  To save them, start it with <code>extract-text review --out YOUR_SCAN_FOLDER --serve</code>,
  or in R with <code>review_documents("YOUR_SCAN_FOLDER", correct = TRUE)</code>.</div>
</header>
{''.join(cells)}
<script>
const GRADERS = {'true' if graders else 'false'};
const SETTLE = {'true' if rows and not graders else 'false'};
// the scan folder the page was built from; every answer carries it, so
// `extract-text import` can refuse answers from another folder's page
const PAGE = {json.dumps(out.resolve().name)};
// the graders' page opened as a plain file, with no server behind it: each
// Save is kept in the browser, and the grader downloads the answers to send
const LOCAL = GRADERS && !location.protocol.startsWith("http");
const STORE = "extract-text answers " + PAGE;
const FIELDS = ["plaintiff", "street", "unit", "city", "state", "zip",
                "attorney_firm", "attorney_address", "note"];
const LISTS = ["defendants", "attorneys"];
const forms = [...document.querySelectorAll("form.fix")];
const count = document.getElementById("count");

function setStatus(f, text, cls) {{
  const s = f.querySelector(".status");
  s.textContent = text;
  s.className = "status " + (cls || "");
}}
// a box as tall as what is in it; a box on a hidden card measures nothing
// and keeps its rows
function grow(t) {{
  t.style.height = "auto";
  if (t.scrollHeight) t.style.height = t.scrollHeight + 2 + "px";
}}
function fill(f, c) {{
  // answers saved before the attorney boxes existed leave those boxes as read
  for (const k of FIELDS) {{
    if (k === "note") f.elements.note.value = c.note || "";
    else if (f.elements[k] && k in c.truth) f.elements[k].value = c.truth[k] || "";
  }}
  for (const k of LISTS) if (f.elements[k] && k in c.truth) f.elements[k].value = (c.truth[k] || []).join("\\n");
  // an answer saved with a separate firm box brings its firm into the
  // attorney box as one more line
  if (f.elements.attorneys && !f.elements.attorney_firm && c.truth.attorney_firm)
    f.elements.attorneys.value = [f.elements.attorneys.value, c.truth.attorney_firm].filter(Boolean).join("\\n");
  f.dataset.usedAi = c.used_ai_fill ? "1" : "";
  f.querySelectorAll("textarea").forEach(grow);
}}
function mark(f, c) {{
  f.classList.add("saved");
  if (c.verdict === "unreadable") return setStatus(f, "Saved: can't tell from the page", "ok");
  const missed = fields => fields.length ? "wrong on " + fields.join(", ") : "all right";
  let what = "Saved. Deterministic engine " + missed(c.changed_fields);
  if (c.ai && c.ai.changed_fields) what += "; AI engine " + missed(c.ai.changed_fields);
  setStatus(f, what + ".", "ok");
}}
// the settling page: an unsettled card's boxes start empty, so nothing is
// chosen until Keep is pressed
function clear(f) {{
  for (const k of [...FIELDS, ...LISTS]) if (f.elements[k]) f.elements[k].value = "";
  f.dataset.usedAi = "";
  f.querySelectorAll("textarea").forEach(grow);
}}
// the settling page: whose answer was kept, marked on the answers table
// (its column and its button), and a line under the table saying where
// the card stands
function showChosen(f) {{
  const box = f.previousElementSibling;
  if (!box || !box.classList.contains("others")) return;
  const who = f.dataset.from, edited = f.dataset.edited === "1", dirty = f.dataset.dirty === "1";
  for (const el of box.querySelectorAll("[data-who]")) el.classList.toggle("chosen", el.dataset.who === who);
  for (const b of box.querySelectorAll("button.keep")) {{
    const on = b.dataset.who === who;
    b.classList.toggle("on", on);
    b.textContent = on ? "\\u2713 Kept" : "Keep this one";
  }}
  const kept = who === undefined ? "" : who + "'s answer" + (edited ? ", with your changes" : "");
  box.querySelector("p.kept").textContent =
    f.classList.contains("saved") && !dirty
      ? "Saved" + (kept ? ": " + kept : "") + ". To change it, edit the boxes or keep another answer, then Save again."
    : kept ? "You kept " + kept + ". Check the boxes below against the page, then Save."
    : dirty ? "Your own answer, typed in. Save when it matches the page."
    : "Press Keep this one under the answer that matches the page. It fills the boxes below, "
      + "where you can fix anything before you Save.";
}}
function tally() {{
  const done = forms.filter(f => f.classList.contains("saved")).length;
  count.textContent = done + " of " + forms.length + " on this page reviewed";
}}

for (const img of document.querySelectorAll(".page img")) {{
  img.addEventListener("click", () => {{
    const card = img.closest(".doc");
    card.classList.toggle("big");
    card.scrollIntoView({{block: "start"}});
    img.title = card.classList.contains("big") ? "Click to shrink" : "Click to enlarge";
  }});
}}

// answers kept in this browser, {{row: what Save sent}}; null when the
// browser refuses storage to a page opened as a file
function kept() {{
  try {{ return JSON.parse(localStorage.getItem(STORE) || "{{}}"); }} catch (e) {{ return null; }}
}}
function markKept(f, c) {{
  f.classList.add("saved");
  setStatus(f, c.verdict === "unreadable" ? "Saved in this browser: can't tell from the page"
                                          : "Saved in this browser.", "ok");
}}
// how many answers are kept, and how many are newer than the last download;
// those are the ones closing the page would put at risk
function unsent() {{
  let since = "";
  try {{ since = localStorage.getItem(STORE + " downloaded") || ""; }} catch (e) {{}}
  const all = Object.values(kept() || {{}});
  return [all.length, all.filter(c => c.saved_at > since).length];
}}
const answers = n => n + (n === 1 ? " answer" : " answers");
function keepNote() {{
  const [n, waiting] = unsent();
  const note = document.getElementById("knote");
  note.textContent = answers(n) + " kept in this browser"
    + (waiting ? "; " + waiting + " not yet downloaded." : n ? ", all downloaded." : ".");
  note.className = waiting ? "warn" : "";
}}
function showKept() {{
  const all = kept() || {{}};
  for (const f of forms) {{
    const c = all[f.dataset.row];
    if (c) {{ fill(f, c); markKept(f, c); }}
  }}
  tally();
  arrange();
  keepNote();
}}
function downloadKept() {{
  const all = Object.values(kept() || {{}}).sort((a, b) => a.row - b.row);
  const who = (grader.name.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_")
               .replace(/^_+|_+$/g, "")) || "grader";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([all.map(c => JSON.stringify(c) + "\\n").join("")],
                                        {{type: "application/json"}}));
  a.download = "answers_" + who + "_" + PAGE.replace(/^_+/, "") + ".jsonl";
  document.body.appendChild(a);
  a.click();
  a.remove();
  try {{ localStorage.setItem(STORE + " downloaded", new Date().toISOString()); }} catch (e) {{}}
  keepNote();
}}
// a downloaded file brought back, for a browser whose storage was cleared;
// for each document the newer of the two answers stays, and one this browser
// already holds is counted apart so a grader testing the button does not read
// "0 brought back" as a failure
async function restoreKept(file) {{
  const all = kept() || {{}};
  let added = 0, held = 0, other = 0;
  for (const line of (await file.text()).split("\\n")) {{
    if (!line.trim()) continue;
    const c = JSON.parse(line);
    if (c.page !== PAGE) {{ other++; continue; }}
    if (!all[c.row] || all[c.row].saved_at < c.saved_at) {{ all[c.row] = c; added++; }}
    else held++;
  }}
  try {{ localStorage.setItem(STORE, JSON.stringify(all)); }} catch (e) {{}}
  showKept();
  const said = [answers(added) + " brought back"];
  if (held) said.push(answers(held) + " already kept in this browser");
  if (other) said.push(other + " from another folder's page, left out");
  document.getElementById("knote").textContent = said.join("; ") + ".";
}}

if (LOCAL) {{
  if (kept() === null) {{
    const b = document.getElementById("banner");
    b.textContent = "This browser will not keep answers for a page opened from a file. "
      + "Open the page in Google Chrome instead, or tell Tim.";
    b.hidden = false;
    forms.forEach(f => f.querySelectorAll("button").forEach(b => b.disabled = true));
  }} else {{
    document.getElementById("keep").hidden = false;
    document.getElementById("kdown").addEventListener("click", downloadKept);
    document.getElementById("kload").addEventListener("change", e => {{
      if (e.target.files[0]) restoreKept(e.target.files[0]);
      e.target.value = "";
    }});
    // closing the tab with answers not yet downloaded asks first
    addEventListener("beforeunload", e => {{
      if (unsent()[1]) {{ e.preventDefault(); e.returnValue = ""; }}
    }});
    setTimeout(showKept);
  }}
}} else if (!location.protocol.startsWith("http")) {{
  document.getElementById("banner").hidden = false;
  forms.forEach(f => f.querySelectorAll("button").forEach(b => b.disabled = true));
}} else {{
  document.querySelectorAll("a.full").forEach(a => a.hidden = false);
  fetch("api/corrections").then(r => r.json()).then(saved => {{
    for (const f of forms) {{
      const c = saved[f.dataset.row];
      // on the settling page a card counts as done only once it is settled
      // there; until then its boxes are empty, waiting for a Keep
      if (SETTLE && !(c && c.settled)) clear(f);
      else if (c) {{ fill(f, c); mark(f, c); }}
      if (SETTLE) showChosen(f);
    }}
    tally();
    if (GRADERS) arrange();
  }});
  // the settling page: the graders' answers side by side above each form,
  // one row per field, the rows where they differ highlighted
  if (SETTLE) fetch("api/answers").then(r => r.json()).then(all => {{
    const COLS = ["plaintiff", "defendants", "street", "unit", "city", "state", "zip",
                  "attorneys", "attorney_firm", "attorney_address"];
    const cell = (tr, tag, text, cls) => {{
      const c = document.createElement(tag);
      c.textContent = text;
      if (cls) c.className = cls;
      tr.appendChild(c);
      return c;
    }};
    for (const f of forms) {{
      // an answer saved here is the settlement, already in the form
      const answers = Object.entries(all[f.dataset.row] || {{}}).filter(([, a]) => !a.settled);
      if (!answers.length) continue;
      const differ = JSON.parse(f.dataset.differ || "{{}}");
      const box = document.createElement("div");
      box.className = "others";
      const what = Object.entries(differ).map(([k, how]) => k + " (" + how + ")");
      cell(box, "p", "Graders' answers. Keep one, edit it if neither is right, then Save. "
        + (what.length ? "They differ on " + what.join(", ") + "." : "Their answers match."));
      const table = document.createElement("table");
      const top = table.insertRow();
      cell(top, "th", "");
      for (const [who] of answers) cell(top, "th", who).dataset.who = who;
      for (const k of COLS.filter(k => answers.some(([, a]) => k in a.truth))) {{
        const tr = table.insertRow();
        if (k in differ) tr.className = differ[k] === "formatting only" ? "fmt" : "differ";
        cell(tr, "th", k);
        for (const [who, a] of answers) {{
          const v = a.truth[k];
          const td = a.verdict === "unreadable" ? cell(tr, "td", "can't tell from the page", "na")
            : !(k in a.truth) ? cell(tr, "td", "not asked", "na")
            // a bullet starts each name, so a long name wrapping onto a
            // second line is not mistaken for a second name
            : cell(tr, "td", (Array.isArray(v) ? v.map(n => "\\u2022 " + n).join("\\n") : v) || "(empty)");
          td.dataset.who = who;
        }}
      }}
      const bottom = table.insertRow();
      cell(bottom, "th", "");
      for (const [who, a] of answers) {{
        const td = cell(bottom, "td", "");
        if (a.verdict === "unreadable") continue;
        // fills the form from this answer, to save as it is or edit first
        const keep = cell(td, "button", "Keep this one", "quiet keep");
        keep.type = "button";
        keep.dataset.who = who;
        keep.addEventListener("click", () => {{
          const was = [...f.elements].map(el => [el, el.value]);
          fill(f, a);
          // a grader who was not asked about the attorney block leaves those
          // boxes to a grader who was, rather than saving them empty
          const asked = answers.find(([, b]) => b.verdict !== "unreadable" && "attorneys" in b.truth);
          if (!("attorneys" in a.truth) && asked) fill(f, {{truth: Object.fromEntries(
            ["attorneys", "attorney_firm", "attorney_address"].map(k => [k, asked[1].truth[k]]))}});
          f.dataset.from = who;
          f.dataset.dirty = "1";
          delete f.dataset.edited;
          showChosen(f);
          // the boxes this choice changed flash, since often only one does
          for (const [el, v] of was) if (el.value !== v) {{
            el.classList.add("flash");
            setTimeout(() => el.classList.remove("flash"), 1200);
          }}
          setStatus(f, "Filled from " + who + "'s answer. Check it against the page, "
            + "edit anything wrong, then Save", "");
        }});
      }}
      box.appendChild(table);
      cell(box, "p", "", "kept");
      f.before(box);
      showChosen(f);
    }}
  }});
}}

for (const b of document.querySelectorAll("button.use-ai")) {{
  b.addEventListener("click", () => {{
    const f = b.closest("form");
    const a = JSON.parse(f.dataset.ai);
    for (const k of FIELDS) if (k !== "note" && f.elements[k]) f.elements[k].value = a[k] || "";
    // a field the AI engine does not read (attorneys) keeps what is there
    for (const k of LISTS) if (f.elements[k] && k in a) f.elements[k].value = (a[k] || []).join("\\n");
    // the one attorney box takes the AI engine's firm, the only part of the
    // block it reads; the attorneys' names are left to the grader
    if (f.elements.attorneys && !f.elements.attorney_firm)
      f.elements.attorneys.value = [...(a.attorneys || []), a.attorney_firm].filter(Boolean).join("\\n");
    f.querySelectorAll("textarea").forEach(grow);
    f.dataset.usedAi = "1";
    setStatus(f, a.address_unsplit
      ? "Filled from the AI engine. Its address is all in Street; split it into the boxes, check against the page, then Save"
      : "Filled from the AI engine. Check it against the page, then Save", "");
  }});
}}

for (const f of forms) {{
  f.querySelectorAll("textarea").forEach(grow);
  f.addEventListener("input", e => {{
    if (e.target.tagName === "TEXTAREA") grow(e.target);
    if (f.dataset.from !== undefined) f.dataset.edited = "1";
    f.dataset.dirty = "1";
    if (SETTLE) showChosen(f);
    if (f.classList.contains("saved")) setStatus(f, "Changed since saved; press Save again", "");
  }});
  f.addEventListener("submit", async e => {{
    e.preventDefault();
    const truth = {{}};
    // a document without the attorney box sends no attorney answer, and is
    // not scored on the attorney block
    for (const k of FIELDS) if (k !== "note" && f.elements[k]) truth[k] = f.elements[k].value.trim();
    // several plaintiffs, typed one per line, are saved as one name list
    truth.plaintiff = truth.plaintiff.split("\\n").map(s => s.trim()).filter(Boolean).join("; ");
    for (const k of LISTS) if (f.elements[k])
      truth[k] = f.elements[k].value.split("\\n").map(s => s.trim()).filter(Boolean);
    const body = {{
      row: Number(f.dataset.row),
      verdict: e.submitter ? e.submitter.value : "checked",
      truth, note: f.elements.note.value.trim(),
      used_ai_fill: f.dataset.usedAi === "1",
      reviewer: GRADERS ? grader.name.value.trim() : "",
      reviewer_email: GRADERS ? grader.email.value.trim() : "",
      settled: SETTLE,
    }};
    if (GRADERS && !body.reviewer) {{
      setStatus(f, "Not saved: put your name at the top of the page first", "err");
      return;
    }}
    if (SETTLE && body.verdict === "checked"
        && !Object.values(truth).some(v => Array.isArray(v) ? v.length : v)) {{
      setStatus(f, "Not saved: press Keep this one above, or type the answer in", "err");
      return;
    }}
    if (LOCAL) {{
      body.page = PAGE;
      body.saved_at = new Date().toISOString();
      const all = kept() || {{}};
      all[body.row] = body;
      try {{
        localStorage.setItem(STORE, JSON.stringify(all));
      }} catch (err) {{
        setStatus(f, "Not saved: this browser would not keep it (" + err.message + "). "
          + "Download your answers now and tell Tim", "err");
        return;
      }}
      markKept(f, body);
      delete f.dataset.dirty;
      tally();
      keepNote();
      return;
    }}
    setStatus(f, "Saving...", "");
    try {{
      const r = await fetch("api/corrections", {{
        method: "POST", headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify(body),
      }});
      if (!r.ok) throw new Error(await r.text());
      mark(f, await r.json());
      delete f.dataset.dirty;
      if (SETTLE) showChosen(f);
      tally();
    }} catch (err) {{
      setStatus(f, "Not saved: " + err.message, "err");
    }}
  }});
}}
// the graders' page: name and email on every save, a batch of the chosen
// size drawn from the documents nobody has graded yet, worst first, with
// the order within a tier shuffled by the grader's name so two people
// grading the same folder at once mostly get different documents (in
// random order there is one tier, and the shuffle is the whole order)
const grader = GRADERS ? {{
  name: document.getElementById("gname"), email: document.getElementById("gemail"),
  count: document.getElementById("gcount"), note: document.getElementById("gnote"),
}} : null;
let batch = [];
function hash(s) {{
  let h = 2166136261;
  for (const ch of s) {{ h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; }}
  return h;
}}
// the shared set comes first, in one order for everyone (Infinity - Infinity
// is NaN, which falls through to the next key)
const sharedAt = c => c.dataset.shared === undefined ? Infinity : Number(c.dataset.shared);
function arrange() {{
  const want = grader.count.value === "all" ? Infinity : Number(grader.count.value);
  const salt = grader.name.value.trim().toLowerCase();
  const cards = [...document.querySelectorAll(".doc")];
  const todo = cards.filter(c => !c.querySelector("form.fix").classList.contains("saved"))
    .sort((a, b) => (sharedAt(a) - sharedAt(b))
                 || (Number(b.dataset.tier) - Number(a.dataset.tier))
                 || (hash(salt + a.id) - hash(salt + b.id)));
  batch = todo.slice(0, want);
  for (const c of cards) c.hidden = !batch.includes(c);
  // boxes on cards that were hidden measured nothing until now
  for (const c of batch) c.querySelectorAll("textarea").forEach(grow);
  progress();
}}
function progress() {{
  if (!GRADERS) return;
  const done = batch.filter(c => c.querySelector("form.fix").classList.contains("saved")).length;
  grader.note.textContent = batch.length
    ? `${{done}} of ${{batch.length}} in this batch saved`
      + (done === batch.length ? ". Press \u201cGrade another batch\u201d for more." : "")
    : "Nothing left to grade in this folder.";
}}
if (GRADERS) {{
  try {{
    grader.name.value = localStorage.getItem("grader.name") || "";
    grader.email.value = localStorage.getItem("grader.email") || "";
    grader.count.value = localStorage.getItem("grader.count") || "10";
  }} catch (e) {{}}
  const remember = () => {{
    try {{
      localStorage.setItem("grader.name", grader.name.value);
      localStorage.setItem("grader.email", grader.email.value);
      localStorage.setItem("grader.count", grader.count.value);
    }} catch (e) {{}}
  }};
  grader.name.addEventListener("change", () => {{ remember(); arrange(); }});
  grader.email.addEventListener("change", remember);
  grader.count.addEventListener("change", () => {{ remember(); arrange(); }});
  document.getElementById("gmore").addEventListener("click", arrange);
  for (const f of forms) f.addEventListener("submit", () => setTimeout(progress, 300));
}}

tally();
</script>"""
    (rev / "index.html").write_text(html)
    return rev / "index.html"


def read_scan(out_dir):
    """The scan's table rows and their full-detail records, paired.

    Rows and details pair by position: the scan writes both files in the
    same order, one line per document. Pairing by file name breaks on court
    collections, where every case folder can hold a file of the same name,
    and sent every same-named row to one document's page image."""
    out = Path(out_dir)
    with open(out / "extracted.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    with open(out / "extracted.jsonl") as f:
        details = [json.loads(line) for line in f if line.strip()]
    if len(details) != len(rows):
        raise ValueError(
            f"{out} holds {len(rows)} rows in extracted.csv but "
            f"{len(details)} in extracted.jsonl; re-run the scan")
    return rows, details


def _split_names(joined: str) -> list[str]:
    return [n.strip() for n in (joined or "").split(";") if n.strip()]


def _street_without_unit(street: str, unit: str) -> str:
    street, unit = (street or "").strip(), (unit or "").strip()
    if unit and street.upper().endswith(" " + unit.upper()):
        return street[: -len(unit)].rstrip(" ,#")
    return street


def _one_line(text: str) -> str:
    return " ".join((text or "").split())


def machine_reading(row: dict) -> dict:
    """What the main columns say, in the shape a correction takes. The
    engine's street column carries the unit on its end and the unit column
    repeats it; a correction keeps them apart, street without unit."""
    return {
        "plaintiff": row.get("plaintiffs", "") or "",
        "defendants": _split_names(row.get("defendant_names", "")),
        "street": _street_without_unit(row.get("defendant_street", ""),
                                       row.get("defendant_unit", "")),
        "unit": row.get("defendant_unit", "") or "",
        "city": row.get("defendant_city", "") or "",
        "state": row.get("defendant_state", "") or "",
        "zip": row.get("defendant_zip", "") or "",
        "attorneys": _split_names(row.get("attorney_names", "")),
        "attorney_firm": row.get("attorney_firm", "") or "",
        "attorney_address": _attorney_address_line(row),
    }


def _attorney_address_line(row: dict) -> str:
    """The attorney's address as one line from its parsed parts, as a grader
    types it; the raw block (firm name, phone and all) only when the parts
    were not found, since a block can never equal a typed address."""
    street = (row.get("attorney_street") or "").strip()
    if not street:
        return _one_line(row.get("attorney_address_raw", ""))
    unit = (row.get("attorney_unit") or "").strip()
    if unit and not street.upper().endswith(" " + unit.upper()):
        street = f"{street} {unit}"
    city = (row.get("attorney_city") or "").strip()
    state_zip = " ".join(x for x in ((row.get("attorney_state") or "").strip(),
                                     (row.get("attorney_zip") or "").strip()) if x)
    tail = ", ".join(x for x in (city, state_zip) if x)
    return f"{street}, {tail}" if tail else street


def ai_reading(detail: dict) -> dict | None:
    """The AI engine's answer in the shape a correction takes, or None when
    the scan did not run the AI engine. When the model's address could not be
    split into parts, the whole address sits in `street` and
    `address_unsplit` is set, so a reviewer knows to split it."""
    ai = ((detail or {}).get("ai") or {}).get("record")
    if not ai:
        return None
    addr = ai.get("defendant_address") or {}
    att = ai.get("attorney") or {}
    unit = addr.get("unit") or ""
    reading = {
        "plaintiff": "; ".join(p.get("name", "") for p in ai.get("plaintiffs") or []),
        "defendants": [p.get("name", "") for p in ai.get("defendants") or []],
        "street": _street_without_unit(addr.get("street") or "", unit),
        "unit": unit,
        "city": addr.get("city") or "",
        "state": addr.get("state") or "",
        "zip": addr.get("zip") or "",
        "attorney_firm": att.get("firm") or "",
        "attorney_address": _one_line((att.get("address") or {}).get("raw") or ""),
        "address_unsplit": False,
    }
    if att.get("names"):
        # the graders'-format prompt reads the attorneys' names; the original
        # asks for the firm and its address only, so its readings carry none
        reading["attorneys"] = _split_names(att["names"])
    if not reading["street"] and addr.get("raw"):
        reading["street"] = addr["raw"]
        reading["address_unsplit"] = True
    return reading


def review_prefill(row: dict, detail: dict) -> dict:
    """The correction form's starting values: the main columns, with the
    AI engine's reading filling a field the main columns left empty (both
    mode only). A reviewer who accepts an AI-filled value has corrected the
    main columns, and the saved record says so."""
    start = machine_reading(row)
    ai = ai_reading(detail)
    if not ai:
        return start
    if not start["plaintiff"]:
        start["plaintiff"] = ai["plaintiff"]
    if not start["defendants"]:
        start["defendants"] = ai["defendants"]
    if not start["street"] and ai["street"] and not ai["address_unsplit"]:
        for k in ("street", "unit", "city", "state", "zip"):
            start[k] = ai[k]
    for k in ("attorneys", "attorney_firm", "attorney_address"):
        if not start[k] and ai.get(k):
            start[k] = ai[k]
    return start


def _name_tokens(text: str) -> list[str]:
    """Names as a word sequence: case, punctuation, and the separators
    between names ignored, so "A B; C D" and "A B C D" compare equal."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()


def _unit_key(unit: str) -> str:
    unit = re.sub(r"\b(apt|apartment|unit|no|number)\b", "", (unit or "").lower())
    return re.sub(r"[^a-z0-9]", "", unit)


def engine_differences(row: dict, ai: dict) -> dict:
    """Where the two engines' readings differ, for the review page.

    Keys are the fields that differ, in page order; a value names the parts
    of the address that differ. Stricter than the scan's own address flag,
    which uses the paper's forgiving same-street threshold: a dropped unit
    passes that threshold and is exactly what a reviewer should see. One
    engine reading a field the other left blank counts as a difference."""
    out = {}
    if _party_key(row.get("plaintiffs", "")) != _party_key(ai["plaintiff"]):
        out["plaintiff"] = ""
    if _name_tokens(row.get("defendant_names", "")) != _name_tokens(" ".join(ai["defendants"])):
        out["defendants"] = ""
    det = machine_reading(row)
    if ai["address_unsplit"]:
        if norm(row.get("defendant_address_raw", "")) != norm(ai["street"]):
            out["address"] = ""
    else:
        parts = [
            ("street", norm(det["street"]) != norm(ai["street"])),
            ("unit", _unit_key(det["unit"]) != _unit_key(ai["unit"])),
            ("city", det["city"].casefold() != ai["city"].casefold()),
            ("ZIP", det["zip"][:5] != ai["zip"][:5]),
        ]
        differing = [name for name, d in parts if d]
        if differing:
            out["address"] = ", ".join(differing)
    if _party_key(row.get("attorney_firm", "")) != _party_key(row.get("ai_law_firm", "")):
        out["attorney firm"] = ""
    return out
