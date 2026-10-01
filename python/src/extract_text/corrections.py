"""Human corrections from the review page, saved beside the scan.

`extract-text review --out DIR --serve` builds the review page and serves it
from this computer only (127.0.0.1, never the network). Each Save on the page
appends one line to `DIR/corrections.jsonl` and rewrites `DIR/corrections.csv`
with the latest answer per document.

A correction is a labeled example, and the file is built to be used as one:

- `truth` is what the reviewer says the page prints (plaintiff, defendants,
  and the defendant's address in parts)
- `machine` is what the main columns said, and `ai` what the AI engine said
  in a both-engine run, each with the fields where it differs from the truth
  (`changed_fields`, `ai.changed_fields`), so either engine can be scored
- `used_ai_fill` says the reviewer started from the AI engine's reading
  (the page's "Use AI engine's reading" button) before saving
- `verdict` is `confirmed` (nothing changed), `corrected` (with the fields
  in `changed_fields`), or `unreadable` (the page does not settle it)
- `sampled_as` records whether the document was shown because it was
  flagged or drawn at random. Only the random ones estimate accuracy for a
  whole corpus; the flagged ones are the hard cases, which is what a rule fix
  or a model evaluation needs most.
- `sha256` identifies the document itself, so a label survives the file
  being moved or renamed.

The file holds whatever the documents hold, names and addresses included.
It lives in the scan directory, which must be governed storage.
"""

from __future__ import annotations

import csv
import datetime as _dt
import getpass
import hashlib
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .pipeline import ai_reading, machine_reading, read_scan

TRUTH_FIELDS = ("plaintiff", "street", "unit", "city", "state", "zip")
MAX_BODY = 64 * 1024
DOCUMENT_TYPES = {".pdf": "application/pdf", ".tif": "image/tiff", ".tiff": "image/tiff"}
MAX_FIELD = 300

CSV_COLUMNS = [
    "row", "file", "sha256", "sampled_as", "verdict", "changed_fields",
    "plaintiff", "defendants", "street", "unit", "city", "state", "zip", "note",
    "machine_method", "machine_plaintiff", "machine_defendants", "machine_street",
    "machine_unit", "machine_city", "machine_state", "machine_zip",
    "ai_plaintiff", "ai_defendant_names", "ai_defendant_address", "ai_changed_fields",
    "used_ai_fill", "flags", "reviewer", "reviewer_email", "saved_at",
]


def _same(a: str, b: str) -> bool:
    squash = lambda s: re.sub(r"\s+", " ", (s or "").strip()).casefold()
    return squash(a) == squash(b)


def _text(value) -> str:
    return str(value or "").strip()[:MAX_FIELD]


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _changed(truth: dict, reading: dict) -> list:
    """The fields where a reading differs from the reviewer's answer."""
    changed = [k for k in TRUTH_FIELDS if not _same(truth[k], reading.get(k, ""))]
    if ([n.casefold() for n in truth["defendants"]]
            != [n.casefold() for n in reading.get("defendants", [])]):
        changed.insert(1, "defendants")
    return changed


def _sampled_as(out: Path, row_no: int, row: dict) -> str:
    """How the review page came to show this row: `random` for a random
    draw, `flagged` for the flagged-first pile. Read from the page's own
    sample record; a page built before that record existed falls back to
    the row's flags."""
    try:
        drawn = json.loads((out / "review" / "sample.json").read_text())
        return drawn[str(row_no)]
    except (OSError, ValueError, KeyError):
        return "flagged" if row.get("flags") else "random"


def build_correction(row_no: int, body: dict, rows: list, details: list,
                     out_dir=None) -> dict:
    """One saved correction, assembled from the reviewer's answer and the
    scan's own record of that document. Only the answer comes from the page;
    the file, the machine's reading, and the flags come from the scan."""
    row, detail = rows[row_no - 1], details[row_no - 1]
    given = body.get("truth") or {}
    truth = {k: _text(given.get(k)) for k in TRUTH_FIELDS}
    names = given.get("defendants") or []
    if not isinstance(names, list):
        raise ValueError("defendants must be a list")
    truth["defendants"] = [_text(n) for n in names if _text(n)][:20]

    machine = machine_reading(row)
    changed = _changed(truth, machine)
    if body.get("verdict") == "unreadable":
        verdict = "unreadable"
    else:
        verdict = "corrected" if changed else "confirmed"

    ai = ai_reading(detail)
    if ai is not None:
        ai = {**ai, "backend": row.get("ai_backend", ""),
              "defendant_address": row.get("ai_defendant_address", ""),
              "changed_fields": _changed(truth, ai)}
    src = Path(detail.get("file", ""))
    return {
        "row": row_no,
        "file": str(src),
        "sha256": _sha256(src),
        "sampled_as": _sampled_as(Path(out_dir or "."), row_no, row),
        "verdict": verdict,
        "changed_fields": changed,
        "truth": truth,
        "note": _text(body.get("note")),
        # the reviewer filled the form from the AI engine before saving. The
        # answer is still the reviewer's, but scoring the AI engine on rows
        # where its own reading was the starting point flatters it, so the
        # record keeps the difference
        "used_ai_fill": bool(body.get("used_ai_fill")),
        "machine": {"method": row.get("method", ""), **machine},
        "ai": ai,
        "flags": row.get("flags", ""),
        # the graders' page sends a name and email with every save; a lone
        # reviewer on the plain page is recorded by their login name
        "reviewer": _text(body.get("reviewer")) or getpass.getuser(),
        "reviewer_email": _text(body.get("reviewer_email")),
        "saved_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def load_corrections(out_dir) -> dict:
    """The latest saved correction for each row, keyed by row number."""
    path = Path(out_dir) / "corrections.jsonl"
    latest = {}
    if path.exists():
        with open(path) as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    latest[c["row"]] = c
    return latest


def write_corrections_csv(out_dir) -> Path:
    """Flatten the latest correction per row into corrections.csv."""
    out = Path(out_dir)
    path = out / "corrections.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for _, c in sorted(load_corrections(out).items()):
            t, m, ai = c["truth"], c["machine"], c.get("ai") or {}
            w.writerow({
                "row": c["row"], "file": c["file"], "sha256": c["sha256"],
                "sampled_as": c["sampled_as"], "verdict": c["verdict"],
                "changed_fields": ";".join(c["changed_fields"]),
                **{k: t[k] for k in TRUTH_FIELDS},
                "defendants": "; ".join(t["defendants"]),
                "note": c["note"],
                "machine_method": m.get("method", ""),
                **{f"machine_{k}": m[k] for k in TRUTH_FIELDS},
                "machine_defendants": "; ".join(m["defendants"]),
                "ai_plaintiff": ai.get("plaintiff", ""),
                # records saved before 2026-09-30's AI fill carry names as one string
                "ai_defendant_names": (
                    "; ".join(ai["defendants"]) if "defendants" in ai
                    else ai.get("defendant_names", "")),
                "ai_defendant_address": ai.get("defendant_address", ""),
                "ai_changed_fields": ";".join(ai.get("changed_fields", [])),
                "used_ai_fill": c.get("used_ai_fill", False),
                "flags": c["flags"], "reviewer": c["reviewer"],
                "reviewer_email": c.get("reviewer_email", ""), "saved_at": c["saved_at"],
            })
    return path


def make_review_server(out_dir, port=8765):
    """A server for the review folder, plus /api/corrections for saving and
    /doc/N for opening document N in full.

    Bound to 127.0.0.1, so nothing is reachable from another machine. It
    serves the review folder (page images and the page) and the scanned
    documents by row number, never the scan tables beside them."""
    out = Path(out_dir)
    rev = out / "review"
    rows, details = read_scan(out)
    lock = threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(rev), **kwargs)

        def log_message(self, *args):
            pass  # request lines would scroll the terminal with page-image names

        def _json(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _refuse(self, status, message):
            data = message.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/corrections":
                with lock:
                    saved = load_corrections(out)
                return self._json(200, {str(k): v for k, v in saved.items()})
            if path.startswith("/doc/"):
                return self._document(path[len("/doc/"):])
            return super().do_GET()

        def _document(self, number):
            # the original file, all pages, for the browser's own viewer.
            # Looked up by row number from the scan's record, so the page
            # can only ask for documents the scan read, never a path.
            if not number.isdigit() or not 1 <= int(number) <= len(rows):
                return self._refuse(404, "no such document")
            src = Path(details[int(number) - 1].get("file", ""))
            kind = DOCUMENT_TYPES.get(src.suffix.lower())
            if not kind or not src.is_file():
                return self._refuse(404, "document not available")
            data = src.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Disposition", "inline")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path.split("?")[0] != "/api/corrections":
                return self._refuse(404, "not found")
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BODY:
                return self._refuse(413, "empty or too large")
            try:
                body = json.loads(self.rfile.read(length))
                row_no = int(body.get("row"))
                if not 1 <= row_no <= len(rows):
                    raise ValueError(f"no document numbered {row_no}")
                correction = build_correction(row_no, body, rows, details, out)
            except (ValueError, TypeError, AttributeError) as e:
                return self._refuse(400, f"bad correction: {e}")
            with lock:
                with open(out / "corrections.jsonl", "a") as f:
                    f.write(json.dumps(correction) + "\n")
                write_corrections_csv(out)
            return self._json(200, correction)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_review(out_dir, port=8765, open_browser=True):
    """Serve the review page until Ctrl-C, saving corrections as they come."""
    import sys
    import webbrowser

    try:
        server = make_review_server(out_dir, port)
    except OSError:
        server = make_review_server(out_dir, 0)  # port taken; any free one
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Review page: {url}\nCorrections save to {Path(out_dir) / 'corrections.jsonl'}"
          "\nPress Ctrl-C here when finished.", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    saved = load_corrections(out_dir)
    print(f"\n{len(saved)} documents reviewed so far, in corrections.csv.", file=sys.stderr)
