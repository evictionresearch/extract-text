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
import sys
from pathlib import Path

from .deterministic import extract_from_document
from .documents import DOCUMENT_SUFFIXES, load_document, render_page
from .schema import Extraction
from .similarity import SAME_STREET_THRESHOLD, address_similarity

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
        case_agree = det_case.replace(" ", "") == ai_case.replace(" ", "")
        if case_agree is False:
            extra_flags.append("engines_disagree_case_number")

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


def scan(
    inputs,
    engine: str = "deterministic",
    out_dir=None,
    model: str | None = None,
    limit: int = 0,
    recursive: bool = True,
    write: bool = True,
    parquet: bool | None = None,
    progress: bool = True,
):
    """Extract every document under `inputs`. Returns the list of row dicts.

    `engine` is 'deterministic', 'ai', or 'both'. When `write` is true (the
    default) and `out_dir` is given, extracted.csv, extracted.jsonl, and the
    review inputs are written there; parquet too when pyarrow is installed
    (set `parquet=False` to skip it, `parquet=True` to require it).
    """
    if engine not in ("deterministic", "ai", "both"):
        raise ValueError("engine must be 'deterministic', 'ai', or 'both'")

    files = collect_inputs(inputs, recursive=recursive)
    if limit:
        files = files[:limit]
    if not files:
        raise FileNotFoundError(
            "No documents found. Supported types: " + ", ".join(DOCUMENT_SUFFIXES)
        )

    vision = None
    if engine in ("ai", "both"):
        from .ai.vision import DEFAULT_VISION_MODEL, LocalVisionBackend

        vision = LocalVisionBackend(model=model or DEFAULT_VISION_MODEL)

    rows, details, n_err = [], [], 0
    for i, path in enumerate(files, 1):
        try:
            det = ai = None
            doc_text = None
            if engine in ("deterministic", "both"):
                doc = load_document(path)
                det = extract_from_document(doc)
                doc_text = doc.text
            if vision is not None:
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
            rows.append({"file": path.name, "flags": f"scan_error:{type(e).__name__}"})
            details.append({"file": str(path),
                            "error": f"{type(e).__name__}: {e}"})
        if progress and (i % 25 == 0 or i == len(files)):
            print(f"  scanned {i}/{len(files)}", file=sys.stderr)

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


def write_review(out_dir, n=30, seed=SAMPLE_SEED, flagged_first=True):
    """Build review/index.html from a finished scan directory: page-1 image
    beside the extracted fields, flagged documents first, then a seeded
    sample of the rest. This is where a person checks the machine's work."""
    out = Path(out_dir)
    rev = out / "review"
    rev.mkdir(parents=True, exist_ok=True)
    with open(out / "extracted.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    details = {}
    with open(out / "extracted.jsonl") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                details[Path(d["file"]).name] = d

    flagged = [r for r in rows if r.get("flags")]
    clean = [r for r in rows if not r.get("flags")]
    rng = random.Random(seed)
    subset = flagged[:n] if flagged_first else []
    remaining = max(0, n - len(subset))
    if remaining and clean:
        subset += rng.sample(clean, min(remaining, len(clean)))

    cells = []
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;")
    for r in subset:
        d = details.get(r.get("file", ""), {})
        src = Path(d.get("file", ""))
        img_name = re.sub(r"[^\w.-]", "_", r.get("file", "doc")) + ".png"
        if src.exists():
            render_page(src, page=1, dpi=80, out_path=rev / img_name)
        ai_bits = ""
        if r.get("ai_defendant_address") or r.get("ai_backend"):
            ai_bits = (f"<p><b>AI address:</b> {esc(r.get('ai_defendant_address',''))} "
                       f"<i>[{esc(r.get('ai_backend',''))}]</i> "
                       f"similarity {esc(str(r.get('address_similarity','')))}</p>")
        cells.append(f"""
<div class="doc">
  <img src="{img_name}" loading="lazy">
  <div class="fields">
    <h3>{esc(r.get('file',''))} · {esc(r.get('case_number','')) or 'no case number'}</h3>
    <p><b>source:</b> {esc(r.get('text_source',''))} conf {esc(str(r.get('ocr_mean_conf','')))}</p>
    <p><b>defendants:</b> {esc(r.get('defendant_names',''))}</p>
    <p><b>address:</b> {esc(r.get('defendant_address_raw',''))}
       <i>[{esc(r.get('defendant_anchor',''))}]</i></p>
    <p><b>attorney:</b> {esc(r.get('attorney_firm',''))} —
       {esc(r.get('attorney_address_raw',''))}</p>
    {ai_bits}
    <p><b>flags:</b> {esc(r.get('flags','')) or 'none'}</p>
  </div>
</div>""")
    html = f"""<!doctype html><meta charset="utf-8"><title>extract-text review</title>
<style>
 body{{font-family:system-ui;margin:1rem;background:#f5f5f2}}
 .doc{{display:flex;gap:1rem;background:#fff;border:1px solid #ddd;
      margin-bottom:1rem;padding:1rem}}
 .doc img{{width:420px;height:auto;border:1px solid #ccc}}
 .fields{{font-size:14px;max-width:40rem}} h3{{margin:.2rem 0}}
</style>
<h1>Review: {len(subset)} of {len(rows)} documents
    ({len(flagged)} flagged in total; flagged shown first)</h1>
{''.join(cells)}"""
    (rev / "index.html").write_text(html)
    return rev / "index.html"
