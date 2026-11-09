"""The case table: one row per document of a scan, the end product of a run.

Wherever a person graded a document, on this scan's review page or on an
earlier scan of the same document (a sample drawn before the full run), the
graded answer replaces the engine's reading, and the row says so in
`source`. Every other row keeps the engine's reading. The address columns
come out in the same shape either way, street without the unit and the
unit apart, plus the whole address on one line in USPS Publication 28 form,
which is what a name and address cleaning step downstream starts from.

A graded answer is matched to a document by its full path and applied only
while the file is unchanged (its sha256 still matches the one saved with
the answer). Where a document was graded more than once, the latest save
wins.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .corrections import _sha256, load_corrections
from .pipeline import machine_reading, read_scan
from .standardize import standardize_address

COLUMNS = [
    "doc", "file", "case_number", "plaintiff", "defendant_names",
    "defendant_street", "defendant_unit", "defendant_city", "defendant_state",
    "defendant_zip", "defendant_address_std", "source", "flags", "text_source",
]


def _key(path) -> str:
    return str(Path(path).expanduser().resolve()) if path else ""


def graded_answers(folders) -> dict:
    """The latest graded answer for each document across scan folders,
    keyed by the document's resolved path."""
    answers = {}
    for folder in folders:
        _, details = read_scan(folder)
        for row_no, c in load_corrections(folder).items():
            path = c.get("file") or (
                details[row_no - 1].get("file", "") if 1 <= row_no <= len(details) else "")
            key = _key(path)
            if not key:
                continue
            kept = answers.get(key)
            if kept is None or c.get("saved_at", "") >= kept.get("saved_at", ""):
                answers[key] = c
    return answers


def case_table(out_dir, graded=(), save=None) -> list[dict]:
    """One row per document of the scan in `out_dir`, graded answers in
    place of the engine's readings. `graded` lists other scan folders whose
    answers apply too (the sample graded before the full run); this scan's
    own answers always apply. `save` writes the table to that CSV file.

    `source` is `graded` where a person's answer was used, `engine` where
    the engine's reading stands, and `unreadable` where a person marked the
    document unreadable (the engine's reading is kept, and should not be
    trusted)."""
    rows, details = read_scan(out_dir)
    answers = graded_answers([out_dir, *(graded or [])])
    table = []
    for doc, (row, detail) in enumerate(zip(rows, details), 1):
        path = detail.get("file") or row.get("file", "")
        c = answers.get(_key(path))
        if c is not None and c.get("sha256") and Path(path).exists() \
                and _sha256(Path(path)) != c["sha256"]:
            c = None  # the file changed after it was graded
        if c is not None and c.get("verdict") != "unreadable":
            t, source = c["truth"], "graded"
            names = t.get("defendants") or []
        else:
            t = machine_reading(row)
            source = "unreadable" if c is not None else "engine"
            names = t["defendants"]
        std = standardize_address(t.get("street", ""), t.get("unit", ""), t.get("city", ""),
                                  t.get("state", ""), t.get("zip", ""))
        table.append({
            "doc": doc,
            "file": str(path),
            "case_number": row.get("case_number", "") or "",
            "plaintiff": t.get("plaintiff", "") or "",
            "defendant_names": "; ".join(names),
            "defendant_street": t.get("street", "") or "",
            "defendant_unit": t.get("unit", "") or "",
            "defendant_city": t.get("city", "") or "",
            "defendant_state": t.get("state", "") or "",
            "defendant_zip": t.get("zip", "") or "",
            "defendant_address_std": std["address_std"],
            "source": source,
            "flags": row.get("flags", "") or "",
            "text_source": row.get("text_source", "") or "",
        })
    if save:
        save = Path(save).expanduser()
        save.parent.mkdir(parents=True, exist_ok=True)
        with open(save, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(table)
    return table
