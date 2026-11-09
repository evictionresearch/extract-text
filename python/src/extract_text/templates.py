"""Form templates: where a form prints each field, learned from a person's
boxes and read by the rules engine before its own anchors.

The rules engine finds the defendants' address by an anchor ladder written
in code (`deterministic/summons.py`). Changing that code takes a programmer.
A form template needs none: a person grades documents on the review page
and, where the engine's box is wrong or missing, draws the box where the
value really is, on whichever page it is printed. Documents that share a
printed form are grouped, and for each field and page the drawn boxes (and
the engine's own boxes on documents a person confirmed) are joined into a
region. The result is one readable JSON file per form, in the user's
results folder, that holds:

- a **fingerprint**: the words of the printed form's first page, with their
  positions, which identify the form on a new document. A word belongs to
  the fingerprint when it is on nearly every learned page at the same
  place; the values (names, addresses, case numbers) differ from page to
  page and so never qualify, and anything inside a field's region is left
  out as well
- **regions** per field (plaintiff, defendants, address, attorney, case),
  each on a page, as fractions of the page width and height from the top
  left, so a scan's resolution does not matter, with the count of boxes it
  was learned from. A field can have several regions: the attorney block
  repeats in every page's footer, and an address can sit on page 3 of a
  bundle

When the engine reads a document, it first tries every approved template on
page 1: a page matches when enough of the fingerprint's words are found at
their positions (a small shift of the whole page, as a scanner adds, is
measured and allowed for). On a match the engine reads each field from its
regions first, reading pages it would otherwise skip when a region needs
them, and that reading is tagged `template:<name>` in `defendant_anchor`
and in the evidence, so what templates fix and break is measurable with
`scripts/rules_eval.py`. Where a region is empty on a document, or holds
nothing that parses, the engine's own anchors run as before for that field
alone: the rules still do the reading inside a region, a template only says
where to look. No template is used until a person has looked at it and
approved it.

Everything here is arithmetic on positions and exact text matching: the same
document with the same templates always gives the same answer, and no model
is involved. This is the deterministic form of the per-form layout learning
in Cheng Ren's dissertation (ten to twenty labeled pages per form).

A template holds the printed form's words and coordinates only; the values
are excluded by construction. Inspect a generated file before sharing it all
the same. The review page beside the templates (`templates/review/`) renders
learned pages as images, so that folder is governed, like the scan.
"""

from __future__ import annotations

import datetime as _dt
import getpass
import html
import json
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from .layout import Line, cluster_lines

TEMPLATE_FIELDS = ("plaintiff", "defendants", "address", "attorney", "case")
DEFAULT_DIR = "templates"

#: a page matches a template when at least this share of the fingerprint's
#: words are found at their positions
MATCH_THRESHOLD = 0.6
#: a fingerprint word is found when the text agrees and the word's centre is
#: within these distances (fractions of the page) of the learned position
POS_TOL_X = 0.02
POS_TOL_Y = 0.012
#: the whole page may have shifted (a scanner's margin); a shift is measured
#: from loose matches within these distances and then allowed for
SHIFT_TOL_X = 0.06
SHIFT_TOL_Y = 0.04
SHIFT_MIN_MATCHES = 8
#: two pages share a form when this share of the smaller page's words are
#: found on the other at the same positions
SAME_FORM_THRESHOLD = 0.5
#: a word belongs to a form's fingerprint when it is on this share of the
#: learned pages
FIXED_SHARE = 0.8
#: fewer fingerprint words than this cannot identify a form
MIN_FINGERPRINT = 12
#: pages a form needs before a template is written (Cheng Ren's figure is
#: ten to twenty; whether fewer suffice is measured, not assumed)
MIN_PAGES = 5
#: a box whose centre is farther than this from the others' is a slip of the
#: mouse, not a position, and is left out of the region
OUTLIER_DISTANCE = 0.12
REGION_PAD = 0.005
#: words closer than this on a printed line belong together; a caption's
#: column divider is wider (the caption reader uses 0.06)
WORD_GAP = 0.025

# what the review page calls each region, and its colour
FIELD_LABELS = {"plaintiff": "Plaintiff", "defendants": "Defendants", "address": "Address",
                "attorney": "Attorney", "case": "Case number"}
FIELD_COLOURS = {"plaintiff": "#2a7", "defendants": "#27b", "address": "#d33",
                 "attorney": "#a5a", "case": "#c80"}

# value shapes that never belong in a fingerprint even when a word happens to
# repeat: a case number, a ZIP code, a phone number's parts
_VALUE_SHAPE_RE = re.compile(r"^(?:\d{2}2\d{5}\d|\d{5}(?:\d{4})?|\d{3}|\d{4}|\d{7,})$")
# a printed label at the head of a block ("TO:", "Served upon:", "Defendant(s):")
_LABEL_RE = re.compile(r"^\s*[A-Za-z()./'\s-]{2,40}?:\s*(.*)$")


# ---------------------------------------------------------------------------
# words with positions
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    """A word as the fingerprint stores it: capitals and digits only."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _edit1(a: str, b: str) -> bool:
    """True when `a` and `b` differ by at most one character: one OCR slip."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i, j = i + 1, j + 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(a) > len(b):
            i += 1
        elif len(b) > len(a):
            j += 1
        else:
            i, j = i + 1, j + 1
    return edits + (len(a) - i) + (len(b) - j) <= 1


def _alike(a: str, b: str) -> bool:
    """The same printed word, allowing one OCR slip in a word of five or
    more characters; short words must agree exactly."""
    if a == b:
        return True
    return len(a) >= 5 and len(b) >= 5 and _edit1(a, b)


def page_words(lines, page: int = 1) -> list[tuple[str, float, float]]:
    """(normalized text, centre x, centre y) for every word on `page`, from
    the engine's rail-stripped lines, so page furniture is already gone."""
    out = []
    for ln in lines:
        if ln.page != page:
            continue
        for w in ln.words:
            t = _norm(w.text)
            if len(t) >= 2:
                out.append((t, round((w.x0 + w.x1) / 2, 4), round((w.y0 + w.y1) / 2, 4)))
    return out


class _PageIndex:
    """A page's words, searchable by position band."""

    def __init__(self, words):
        self.items = sorted(words, key=lambda t: t[2])
        self.ys = [t[2] for t in self.items]

    def find(self, text, x, y, tol_x=POS_TOL_X, tol_y=POS_TOL_Y, exact=False):
        lo = bisect_left(self.ys, y - tol_y)
        hi = bisect_right(self.ys, y + tol_y)
        best = None
        for t in self.items[lo:hi]:
            if abs(t[1] - x) > tol_x:
                continue
            if (t[0] == text) if exact else _alike(text, t[0]):
                d = abs(t[1] - x) + abs(t[2] - y)
                if best is None or d < best[0]:
                    best = (d, t)
        return best[1] if best else None


def _shift(index: _PageIndex, words) -> tuple[float, float]:
    """How far the page sits from where `words` expect it: the median offset
    of exact-text matches found within the loose tolerance, or no shift when
    too few are found to trust."""
    dx, dy = [], []
    for text, x, y in words:
        hit = index.find(text, x, y, SHIFT_TOL_X, SHIFT_TOL_Y, exact=True)
        if hit:
            dx.append(hit[1] - x)
            dy.append(hit[2] - y)
    if len(dx) < SHIFT_MIN_MATCHES:
        return 0.0, 0.0
    return round(median(dx), 4), round(median(dy), 4)


def _matches(index: _PageIndex, words, shift=(0.0, 0.0)) -> list:
    """The words of `words` found on the indexed page, shifted, as
    (word, hit) pairs."""
    found = []
    for text, x, y in words:
        hit = index.find(text, x + shift[0], y + shift[1])
        if hit:
            found.append(((text, x, y), hit))
    return found


def page_similarity(a, b) -> float:
    """The share of the smaller page's words found on the other at the same
    position, after allowing for a shift: 1.0 for the same printed form with
    different values, near 0 for different forms."""
    if not a or not b:
        return 0.0
    index = _PageIndex(b)
    found = _matches(index, a, _shift(index, a))
    return len(found) / min(len(a), len(b))


# ---------------------------------------------------------------------------
# the template file
# ---------------------------------------------------------------------------


@dataclass
class Region:
    box: list  # x0, y0, x1, y1 as fractions of the page from the top left
    page: int = 1
    drawn: int = 0
    confirmed: int = 0
    dropped: int = 0

    def to_json(self):
        return {"page": self.page, "box": [round(v, 4) for v in self.box], "drawn": self.drawn,
                "confirmed": self.confirmed, "dropped": self.dropped}

    @classmethod
    def from_json(cls, d):
        box = [float(v) for v in d["box"]]
        if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
            raise ValueError(f"region box out of range: {box}")
        page = int(d.get("page", 1))
        if page < 1:
            raise ValueError(f"region page out of range: {page}")
        return cls(box, page, int(d.get("drawn", 0)), int(d.get("confirmed", 0)),
                   int(d.get("dropped", 0)))


def _regions_from_json(value) -> list[Region]:
    # a template written before 2026-11-10 holds one region per field, a dict
    items = [value] if isinstance(value, dict) else list(value or [])
    return sorted((Region.from_json(d) for d in items), key=lambda r: r.page)


@dataclass
class Template:
    name: str
    fingerprint: list  # of {"text", "x", "y"}
    regions: dict  # field -> [Region, ...] in page order
    pages: int = 0
    label: str = ""
    approved: bool = False
    approved_by: str = ""
    approved_at: str = ""
    created: str = ""
    extract_text_version: str = ""
    match_threshold: float = MATCH_THRESHOLD
    learned_from: dict = field(default_factory=dict)
    path: Path | None = None

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "approved": self.approved,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "created": self.created,
            "extract_text_version": self.extract_text_version,
            "pages": self.pages,
            "match_threshold": self.match_threshold,
            "regions": {k: [r.to_json() for r in self.regions[k]]
                        for k in TEMPLATE_FIELDS if k in self.regions},
            "fingerprint": [{"text": w["text"], "x": round(w["x"], 4), "y": round(w["y"], 4)}
                            for w in self.fingerprint],
            "learned_from": self.learned_from,
        }

    @classmethod
    def from_json(cls, d: dict, path=None) -> "Template":
        if not d.get("name"):
            raise ValueError("a template needs a name")
        regions = {k: rs for k, v in (d.get("regions") or {}).items()
                   if k in TEMPLATE_FIELDS and (rs := _regions_from_json(v))}
        fp = [{"text": _norm(w["text"]), "x": float(w["x"]), "y": float(w["y"])}
              for w in d.get("fingerprint") or []]
        fp = [w for w in fp if len(w["text"]) >= 2]
        return cls(
            name=str(d["name"]), fingerprint=fp, regions=regions,
            pages=int(d.get("pages", 0)), label=str(d.get("label", "")),
            approved=bool(d.get("approved", False)),
            approved_by=str(d.get("approved_by", "")), approved_at=str(d.get("approved_at", "")),
            created=str(d.get("created", "")),
            extract_text_version=str(d.get("extract_text_version", "")),
            match_threshold=float(d.get("match_threshold", MATCH_THRESHOLD)),
            learned_from=dict(d.get("learned_from") or {}), path=Path(path) if path else None,
        )

    def save(self, directory) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{self.name}.json"
        self.path.write_text(json.dumps(self.to_json(), indent=2) + "\n")
        return self.path

    def fingerprint_words(self):
        return [(w["text"], w["x"], w["y"]) for w in self.fingerprint]

    def region_pages(self) -> set[int]:
        return {r.page for rs in self.regions.values() for r in rs}


def load_templates(directory, approved_only: bool = True) -> list[Template]:
    """Every template in `directory`, by name; with `approved_only`, those a
    person has approved. A folder that does not exist holds none."""
    directory = Path(directory)
    out = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            t = Template.from_json(json.loads(path.read_text()), path)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            raise ValueError(f"{path.name} is not a template file: {e}") from e
        if approved_only and not t.approved:
            continue
        out.append(t)
    return out


def resolve_templates(templates) -> list[Template]:
    """`templates` as the engine takes it: a folder of template files, a list
    of templates, or nothing."""
    if not templates:
        return []
    if isinstance(templates, (str, Path)):
        return load_templates(templates)
    return [t for t in templates if isinstance(t, Template)]


def approve_template(name, directory, approved: bool = True, by: str | None = None) -> Path:
    """Mark the template called `name` (or at this path) approved, so the
    engine uses it. Only a person does this; nothing learned is used until
    they have. `approved=False` withdraws it again."""
    path = Path(name)
    if not path.suffix == ".json" or not path.is_file():
        path = Path(directory) / f"{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no template called {name!r} in {directory}")
    d = json.loads(path.read_text())
    Template.from_json(d, path)  # a malformed file is refused, not approved
    d["approved"] = bool(approved)
    d["approved_by"] = (by or getpass.getuser()) if approved else ""
    d["approved_at"] = _dt.datetime.now().astimezone().isoformat(timespec="seconds") if approved else ""
    path.write_text(json.dumps(d, indent=2) + "\n")
    return path


# ---------------------------------------------------------------------------
# learning
# ---------------------------------------------------------------------------

# which scored fields must be unchanged for the engine's own box of a field
# to count as confirmed by the reviewer
_CONFIRMS = {
    "plaintiff": ("plaintiff",),
    "defendants": ("defendants",),
    "address": ("street", "unit", "city", "state", "zip"),
    "attorney": ("attorneys", "attorney_firm", "attorney_address"),
}
# the engine's evidence keys that place each field on the page
_EVIDENCE_KEYS = {"plaintiff": "plaintiffs.", "defendants": "defendants.", "address": "defendant_address",
                  "attorney": "attorney", "case": "case_number"}


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _engine_boxes(detail: dict) -> dict:
    """Each field's boxes from the engine's evidence of a scanned document,
    one per page it placed the field on, several defendants or plaintiffs
    on a page joined into one: {field: {page: box}}."""
    evidence = ((detail or {}).get("deterministic") or {}).get("evidence") or {}
    out: dict = {}
    for fld, prefix in _EVIDENCE_KEYS.items():
        by_page: dict = {}
        for key, ev in evidence.items():
            if key != prefix and not (prefix.endswith(".") and key.startswith(prefix)):
                continue
            if ev.get("box") and ev.get("page"):
                by_page.setdefault(int(ev["page"]), []).append([float(v) for v in ev["box"]])
        if by_page:
            out[fld] = {p: _union(bs) for p, bs in by_page.items()}
    return out


def labeled_boxes(correction: dict, detail: dict) -> dict:
    """The positions a correction labels: the boxes the reviewer drew, and
    for a field they left as the engine read it (no change in that field),
    the engine's own boxes, which their answer confirms. Returns
    {field: [(page, box, "drawn" | "confirmed"), ...]}. An unreadable
    verdict labels nothing; a drawn "not in this document" removes the
    field."""
    from .corrections import box_list

    out: dict = {}
    if correction.get("verdict") == "unreadable":
        return out
    drawn = correction.get("boxes") or {}
    truth, changed = correction.get("truth") or {}, set(correction.get("changed_fields") or [])
    engine = _engine_boxes(detail)
    for fld in TEMPLATE_FIELDS:
        if fld in drawn:
            if drawn[fld] is not None:
                boxes = [(page, box, "drawn") for page, box in box_list(drawn[fld])]
                if boxes:
                    out[fld] = boxes
            continue
        if fld not in _CONFIRMS or fld not in engine:
            continue
        if any(k in changed for k in _CONFIRMS[fld]):
            continue
        # a confirmed blank is no position; the attorney counts only when
        # the reviewer was asked about it
        has_value = {
            "plaintiff": bool(truth.get("plaintiff")),
            "defendants": bool(truth.get("defendants")),
            "address": bool(truth.get("street")),
            "attorney": "attorneys" in truth and bool(truth.get("attorneys") or truth.get("attorney_firm")),
        }[fld]
        if has_value:
            out[fld] = [(page, box, "confirmed") for page, box in sorted(engine[fld].items())]
    return out


def region_from_boxes(boxes: list, page: int = 1) -> Region | None:
    """One region from several boxes for the same field on the same page:
    their union, after leaving out any box whose centre sits far from the
    others' (a slip). `boxes` holds (box, kind) pairs."""
    kept = [b for b, _ in boxes]
    if not kept:
        return None
    cx = median((b[0] + b[2]) / 2 for b in kept)
    cy = median((b[1] + b[3]) / 2 for b in kept)
    inliers = [(b, kind) for b, kind in boxes
               if abs((b[0] + b[2]) / 2 - cx) <= OUTLIER_DISTANCE
               and abs((b[1] + b[3]) / 2 - cy) <= OUTLIER_DISTANCE]
    if not inliers:
        inliers = boxes
    box = _union([b for b, _ in inliers])
    box = [max(0.0, box[0] - REGION_PAD), max(0.0, box[1] - REGION_PAD),
           min(1.0, box[2] + REGION_PAD), min(1.0, box[3] + REGION_PAD)]
    return Region(box, page, drawn=sum(k == "drawn" for _, k in inliers),
                  confirmed=sum(k == "confirmed" for _, k in inliers),
                  dropped=len(boxes) - len(inliers))


def _inside(x, y, box) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def learn_fingerprint(pages: list[list], regions: dict) -> list[dict]:
    """The words common to the first pages at the same positions, outside
    every page-1 region: the printed form. Positions are averaged over the
    pages. `regions` maps field to a Region or a list of them."""
    if not pages:
        return []
    page1 = [r for rs in regions.values() for r in (rs if isinstance(rs, list) else [rs])
             if r.page == 1]
    # the reference page: the one whose word count is nearest the median,
    # so a page with bad OCR does not set the standard
    counts = sorted(len(p) for p in pages)
    mid = counts[len(counts) // 2]
    ref = min(pages, key=lambda p: (abs(len(p) - mid), pages.index(p)))
    others = []
    for p in pages:
        if p is ref:
            continue
        idx = _PageIndex(p)
        others.append((idx, _shift(idx, ref)))
    out = []
    for text, x, y in ref:
        if _VALUE_SHAPE_RE.match(text):
            continue
        if any(_inside(x, y, r.box) for r in page1):
            continue
        hits = [idx.find(text, x + s[0], y + s[1]) for idx, s in others]
        hits = [(h, s) for h, s in zip(hits, (s for _, s in others)) if h]
        if others and len(hits) / len(others) < FIXED_SHARE:
            continue
        xs = [x] + [h[1] - s[0] for h, s in hits]
        ys = [y] + [h[2] - s[1] for h, s in hits]
        out.append({"text": text, "x": sum(xs) / len(xs), "y": sum(ys) / len(ys)})
    return out


def group_pages(pages: list[list], threshold: float = SAME_FORM_THRESHOLD) -> list[list[int]]:
    """Indexes of `pages` grouped by printed form: a page joins the group
    whose first page it resembles most, if enough, or starts one. The order
    is fixed by the input, so the grouping is reproducible."""
    groups: list[list[int]] = []
    for i, words in enumerate(pages):
        best, best_sim = None, 0.0
        for g in groups:
            sim = page_similarity(words, pages[g[0]])
            if sim > best_sim:
                best, best_sim = g, sim
        if best is not None and best_sim >= threshold:
            best.append(i)
        else:
            groups.append([i])
    return groups


def learn_templates(out_dir, templates_dir=None, min_pages: int = MIN_PAGES,
                    rows=None, name: str | None = None, cache=None) -> tuple[list[Template], str]:
    """Learn templates from the graded documents of a scan and write one file
    per form into `templates_dir` (default: `templates/` in the scan folder),
    unapproved. Returns the templates and a report in counts.

    Each graded document with a labeled position is read again (its text is
    cached beside the scan, as `rules_eval.py` does), the documents are
    grouped by the printed form of their first page, and a group of at least
    `min_pages` becomes a template. `rows` limits the learning to some rows
    of the scan, and `name` names the one template they make (for a form a
    person has sorted out by hand). Templates with a name already in the
    folder are replaced; their approval does not carry over, since the
    regions changed."""
    from . import __version__
    from .corrections import _sha256, load_corrections
    from .documents import cached_document
    from .pipeline import read_scan

    out = Path(out_dir)
    tdir = Path(templates_dir) if templates_dir else out / DEFAULT_DIR
    cache = Path(cache) if cache else out / "_rules_eval_cache"
    latest = load_corrections(out)
    rows_all, details = read_scan(out)

    labeled, pages, skipped = [], [], {}
    for row_no, c in sorted(latest.items()):
        if rows is not None and row_no not in set(rows):
            continue
        if not 1 <= row_no <= len(rows_all):
            skipped["row not in scan"] = skipped.get("row not in scan", 0) + 1
            continue
        boxes = labeled_boxes(c, details[row_no - 1])
        if not boxes:
            continue
        src = Path(details[row_no - 1].get("file", ""))
        if c.get("sha256") and _sha256(src) != c["sha256"]:
            skipped["document changed since graded"] = skipped.get("document changed since graded", 0) + 1
            continue
        try:
            doc = cached_document(src, cache)
        except Exception as exc:  # one unreadable file must not stop the run
            key = f"error: {type(exc).__name__}"
            skipped[key] = skipped.get(key, 0) + 1
            continue
        labeled.append((row_no, boxes))
        pages.append(page_words(doc.lines, 1))

    groups = group_pages(pages) if name is None else [list(range(len(pages)))]
    groups.sort(key=lambda g: (-len(g), g[0] if g else 0))
    lines = [f"{len(labeled)} graded documents with a labeled position, "
             f"in {len(groups)} printed form{'s' if len(groups) != 1 else ''}."]
    if skipped:
        lines.append("Not used: " + ", ".join(f"{n} {k}" for k, n in sorted(skipped.items())))
    written = []
    n_written = 0
    for g in groups:
        if len(g) < min_pages:
            lines.append(f"  a form on {len(g)} document{'s' if len(g) != 1 else ''} "
                         f"(rows {' '.join(f'#{labeled[i][0]}' for i in g)}): fewer than "
                         f"{min_pages}, no template written")
            continue
        by_field: dict = {}
        for i in g:
            for fld, items in labeled[i][1].items():
                for page, box, kind in items:
                    by_field.setdefault(fld, {}).setdefault(page, []).append((box, kind))
        regions = {}
        for fld, by_page in by_field.items():
            rs = [r for page, boxes in sorted(by_page.items())
                  if (r := region_from_boxes(boxes, page)) is not None]
            if rs:
                regions[fld] = rs
        fp = learn_fingerprint([pages[i] for i in g], regions)
        n_written += 1
        tname = name if name is not None else f"form-{n_written}"
        t = Template(
            name=tname, fingerprint=fp, regions=regions, pages=len(g),
            created=_dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            extract_text_version=__version__,
            learned_from={"scan": out.resolve().name, "rows": [labeled[i][0] for i in g]},
        )
        desc = ", ".join(
            f"{fld}" + (f" p{r.page}" if r.page != 1 or len(regions[fld]) > 1 else "")
            + f" ({r.drawn} drawn, {r.confirmed} confirmed"
            + (f", {r.dropped} left out" if r.dropped else "") + ")"
            for fld in TEMPLATE_FIELDS if fld in regions for r in regions[fld])
        if len(fp) < MIN_FINGERPRINT:
            lines.append(f"  {tname}: {len(g)} documents, but only {len(fp)} words identify the form "
                         f"(fewer than {MIN_FINGERPRINT}); no template written")
            continue
        path = t.save(tdir)
        written.append(t)
        lines.append(f"  {tname}: {len(g)} documents, {len(fp)} words identify the form; "
                     f"regions: {desc or 'none'}; written to {path.name}")
    if written:
        lines += ["", "No template is used until a person approves it: look at the review "
                      "page, then approve each one that is right.",
                  f"  templates folder: {tdir}"]
    return written, "\n".join(lines)


# ---------------------------------------------------------------------------
# matching and reading
# ---------------------------------------------------------------------------


@dataclass
class Match:
    """A document recognized as a form: the template, how far page 1 is
    shifted from the learned positions, and the share of the fingerprint
    found."""

    template: Template
    shift: tuple
    score: float

    @property
    def tag(self) -> str:
        return f"template:{self.template.name}"

    def regions(self, fld: str, page: int | None = None) -> list[Region]:
        rs = self.template.regions.get(fld) or []
        return [r for r in rs if page is None or r.page == page]

    def pages_needed(self) -> set[int]:
        return self.template.region_pages()

    def region_lines(self, lines, region: Region) -> list[Line]:
        """The words of the region's page that fall in it, as lines of their
        own. The shift measured on page 1 is applied to every page.

        A line counts when a word's centre falls in the region, and it is
        then followed along the printed line in both directions until a
        column-sized gap: a region is the union of the boxes it was learned
        from, and a value longer than any of them (a unit after a long
        street) would otherwise lose its tail. The gap stops the growth at
        a two-column caption's divider, so the other column stays out."""
        box = [region.box[0] + self.shift[0], region.box[1] + self.shift[1],
               region.box[2] + self.shift[0], region.box[3] + self.shift[1]]
        words = []
        for ln in lines:
            if ln.page != region.page:
                continue
            ws = sorted(ln.words, key=lambda w: w.x0)
            inside = [k for k, w in enumerate(ws)
                      if _inside((w.x0 + w.x1) / 2, (w.y0 + w.y1) / 2, box)]
            if not inside:
                continue
            lo, hi = min(inside), max(inside)
            while lo > 0 and ws[lo].x0 - ws[lo - 1].x1 <= WORD_GAP:
                lo -= 1
            while hi < len(ws) - 1 and ws[hi + 1].x0 - ws[hi].x1 <= WORD_GAP:
                hi += 1
            words += ws[lo:hi + 1]
        return cluster_lines(words) if words else []

    def _names_from_region(self, lines, page):
        """Defendant names from a defendants region on `page`, or on page 1
        when that page has none; [] when the template has no such region."""
        from .deterministic import summons as S

        regions = self.regions("defendants", page) or self.regions("defendants", 1)
        names = []
        for region in regions:
            for ln in self.region_lines(lines, region):
                clean = S.OCCUPANT_NOISE_RE.sub("", ln.text).strip(" ,;")
                if clean and S.looks_like_name_line(clean) and not S.BUILDING_LINE_RE.search(clean):
                    names.append(clean)
        return names

    def defendant_anchor(self):
        """An anchor for the ladder (`fn(lines, pg) -> (parsed, tag)`) that
        reads the address regions on that page, and the defendants region
        for the names when the template has one."""
        from .deterministic import summons as S

        def anchor(lines, pg):
            for region in self.regions("address", pg):
                rows = []
                for ln in self.region_lines(lines, region):
                    t = ln.text.strip()
                    if S.PROSE_STOP_RE.search(t):
                        break
                    if not rows:
                        # the form's own label on the first row ("TO:", "Served
                        # upon:") is not a name; what follows the colon is
                        t = S.TO_ANCHOR_RE.sub("", t) if S.TO_ANCHOR_RE.match(t) else t
                        t = S.ADDRESS_LABEL_RE.sub("", t).strip()
                        m = _LABEL_RE.match(t)
                        if m and not any(ch.isdigit() for ch in t[: m.start(1)]):
                            t = m.group(1).strip()
                    if t:
                        rows.append((t, ln.conf))
                    if len(rows) > 8:
                        break
                if not rows:
                    continue
                names, addr_parts, started = [], [], False
                for t, _ in rows:
                    clean = S.OCCUPANT_NOISE_RE.sub("", t).strip(" ,;")
                    if not started and clean and (S.looks_like_name_line(clean)
                                                  or not any(ch.isdigit() for ch in clean)):
                        names.append(clean)
                        continue
                    started = True
                    addr_parts.append(t)
                if len(names) > 1:
                    names = names[:1] + [n for n in names[1:] if not S.BUILDING_LINE_RE.search(n)]
                joined = " ".join(addr_parts)
                sm0 = S._first_street_match(joined)
                if sm0 and sm0.start() > 0:
                    head = S.OCCUPANT_NOISE_RE.sub("", joined[:sm0.start()]).strip(" ,;:")
                    if re.search(r"[A-Za-z]{2}", head) and not S.ADDRESS_LABEL_RE.match(head):
                        names.append(head)
                    joined = joined[sm0.start():]
                parsed = S.parse_address(joined) if addr_parts else None
                if not parsed and addr_parts:
                    parsed = S.parse_address_nosuffix(joined)
                if not parsed:
                    continue
                from_region = self._names_from_region(lines, pg)
                if from_region:
                    names = from_region
                parsed["defendant_names"] = "; ".join(n for n in names if n)[:200]
                parsed["block_conf"] = round(sum(c for _, c in rows) / len(rows), 1)
                return parsed, self.tag
            return None, None

        return anchor

    def plaintiff(self, lines):
        """Plaintiff names from the first plaintiff region that holds any:
        the rows above the 'Plaintiff,' or 'vs.' label, the court's header
        left out."""
        from .deterministic import summons as S

        for region in self.regions("plaintiff"):
            rows = [ln.text.strip() for ln in self.region_lines(lines, region)]
            kept = []
            for row in rows:
                if S._PLAINTIFF_LABEL_RE.match(row) or S._VS_LINE_RE.match(row):
                    break
                if S._CAPTION_NOISE_RE.search(row) or S.STREET_RE.search(row) or re.search(r"\d{3}", row):
                    continue
                kept.append(row)
            names = S.plaintiff_names_from_rows(kept) if kept else []
            if names:
                return names, self.tag
        return [], ""

    def attorney(self, lines):
        """The plaintiff attorney's block from the first of its regions that
        holds a firm word or a street, parsed as the engine parses the block
        it finds itself; None when none does."""
        from .deterministic import summons as S

        for region in self.regions("attorney"):
            zlines = [ln for ln in self.region_lines(lines, region)
                      if not S.FORM_PUBLISHER_RE.search(ln.text)]
            if not zlines:
                continue
            joined = " ".join(ln.text for ln in zlines)
            if not (S.FIRM_KEYWORDS.search(joined) or S.STREET_RE.search(joined)):
                continue
            out = S.attorney_fields(zlines, lines, region.page)
            out["attorney_anchor"] = self.tag
            return out
        return None

    def case_text(self, lines) -> str:
        return " ".join(ln.text for region in self.regions("case")
                        for ln in self.region_lines(lines, region))


def match_page(lines, templates, page: int = 1) -> Match | None:
    """The template this document is a form of, by its page `page`, or None.
    Every template is scored; the highest share of fingerprint words found
    wins, and it must reach the template's threshold. Ties go to the
    template named first."""
    templates = resolve_templates(templates)
    if not templates:
        return None
    words = page_words(lines, page)
    if not words:
        return None
    index = _PageIndex(words)
    best = None
    for t in sorted(templates, key=lambda t: t.name):
        fp = t.fingerprint_words()
        if len(fp) < MIN_FINGERPRINT:
            continue
        shift = _shift(index, fp)
        score = len(_matches(index, fp, shift)) / len(fp)
        if score >= t.match_threshold and (best is None or score > best.score):
            best = Match(t, shift, round(score, 3))
    return best


# ---------------------------------------------------------------------------
# the review page
# ---------------------------------------------------------------------------


def write_templates_review(templates_dir, scan_dir=None, dpi: int = 100) -> Path:
    """`review/index.html` beside the templates: each template's regions and
    fingerprint words drawn over the pages of one of the documents it was
    learned from (when the scan it came from is given and the file is still
    there; blank pages otherwise), with its counts and the approval command.
    The page images are real documents, so the review folder is governed
    like the scan."""
    from .documents import render_page

    tdir = Path(templates_dir)
    rev = tdir / "review"
    rev.mkdir(parents=True, exist_ok=True)
    details = None
    if scan_dir is not None:
        from .pipeline import read_scan

        try:
            _, details = read_scan(scan_dir)
        except (OSError, ValueError):
            details = None
    cards = []
    for t in load_templates(tdir, approved_only=False):
        rows = t.learned_from.get("rows") or []
        src = None
        if details is not None:
            for row_no in rows:
                if 1 <= int(row_no) <= len(details):
                    cand = Path(details[int(row_no) - 1].get("file", ""))
                    if cand.is_file():
                        src = cand
                        break
        shown_pages = sorted({1} | t.region_pages())
        panels = []
        for page in shown_pages:
            image = ""
            if src is not None:
                png = render_page(src, page, dpi=dpi, out_path=rev / f"{t.name}_p{page}.png")
                if png is not None:
                    image = png.name
            regions = "".join(
                f'<div class="region" style="left:{r.box[0] * 100:.2f}%;top:{r.box[1] * 100:.2f}%;'
                f'width:{(r.box[2] - r.box[0]) * 100:.2f}%;height:{(r.box[3] - r.box[1]) * 100:.2f}%;'
                f'border-color:{FIELD_COLOURS[k]}"><span style="background:{FIELD_COLOURS[k]}">'
                f'{FIELD_LABELS[k]}</span></div>'
                for k, rs in t.regions.items() for r in rs if r.page == page)
            dots = "".join(
                f'<i class="fp" style="left:{w["x"] * 100:.2f}%;top:{w["y"] * 100:.2f}%" '
                f'title="{html.escape(w["text"])}"></i>' for w in t.fingerprint) if page == 1 else ""
            panels.append(
                f'<div class="panel"><p class="pno">Page {page}</p><div class="page">'
                f'{f"<img src={chr(34)}{image}{chr(34)} alt={chr(34)}{chr(34)}>" if image else "<div class=blank></div>"}'
                f'{regions}{dots}</div></div>')
        counts = "".join(
            f"<li><b style=\"color:{FIELD_COLOURS[k]}\">{FIELD_LABELS[k]}</b>"
            + (f" (page {r.page})" if r.page != 1 or len(rs) > 1 else "")
            + f": learned from {r.drawn} drawn box{'es' if r.drawn != 1 else ''} and {r.confirmed} confirmed "
            f"reading{'s' if r.confirmed != 1 else ''}"
            + (f"; {r.dropped} box{'es' if r.dropped != 1 else ''} far from the rest left out" if r.dropped else "")
            + "</li>"
            for k, rs in t.regions.items() for r in rs)
        status = (f'<p class="ok">Approved by {html.escape(t.approved_by)} on {html.escape(t.approved_at[:10])}.</p>'
                  if t.approved else
                  '<p class="todo">Not approved: the engine does not use it yet. If every region sits '
                  'where that field is printed on this form, approve it:</p>'
                  f'<pre>approve_template("{html.escape(t.name)}", "{html.escape(str(tdir))}")</pre>'
                  f'<pre>extract-text templates approve {html.escape(t.name)} --templates "{html.escape(str(tdir))}"</pre>')
        thin = (f'<p class="todo">Learned from {t.pages} documents. Fewer than 10 is thin: a region may '
                'be narrower than the form allows. Grade and box more documents of this form, then learn again.</p>'
                if t.pages < 10 else "")
        cards.append(f"""
<section class="card">
  <h2>{html.escape(t.name)}{(' <small>' + html.escape(t.label) + '</small>') if t.label else ''}</h2>
  <div class="pages">{''.join(panels)}</div>
  <div class="facts">
    <p>Learned from {t.pages} document{'s' if t.pages != 1 else ''} (rows {html.escape(' '.join(f'#{r}' for r in rows))}
       of the scan <code>{html.escape(str(t.learned_from.get('scan', '')))}</code>), {len(t.fingerprint)} printed
       words on page 1 identify the form (the small dots); a document is this form when at least
       {t.match_threshold:.0%} of them are found where they belong.</p>
    <ul>{counts}</ul>
    {thin}{status}
    <p class="file">File: <code>{html.escape(t.path.name if t.path else '')}</code>. The label and the threshold can be edited there.</p>
  </div>
</section>""")
    body = "".join(cards) or "<p>No templates in this folder yet.</p>"
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Form templates</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #222; max-width: 1200px; }}
.card {{ display: grid; grid-template-columns: minmax(280px, 45%) 1fr; gap: 1.5rem; margin-bottom: 2.5rem;
        border-top: 1px solid #ccc; padding-top: 1rem; }}
h2 {{ grid-column: 1 / -1; margin: 0; }} h2 small {{ font-weight: normal; color: #666; margin-left: .75em; }}
.pages {{ display: flex; flex-direction: column; gap: .8rem; }}
.pno {{ margin: 0 0 .2rem; font-size: .85rem; color: #666; }}
.page {{ position: relative; aspect-ratio: 612 / 792; background: #fff; border: 1px solid #bbb; overflow: hidden; }}
.page img, .page .blank {{ display: block; width: 100%; height: 100%; object-fit: fill; }}
.region {{ position: absolute; border: 2px solid; box-sizing: border-box; }}
.region span {{ position: absolute; left: -2px; top: -1.3em; color: #fff; font-size: .72rem; padding: 0 .3em; }}
.fp {{ position: absolute; width: 5px; height: 5px; margin: -2px 0 0 -2px; background: rgba(0,0,0,.35); border-radius: 50%; }}
.facts p {{ margin: .3rem 0; }} .ok {{ color: #170; }} .todo {{ color: #a40; }}
pre {{ background: #f4f4f4; padding: .5rem; overflow-x: auto; }}
.file {{ color: #666; font-size: .9rem; }}
</style></head><body>
<h1>Form templates</h1>
<p>Each box is where the engine will look for a field on documents that match this form, learned from the
boxes drawn and confirmed on graded documents; the engine's own rules still do the reading inside it.
Check that each box sits over the right part of the form, and that the printed form's words (dots) do not
sit on a name or an address. A template holds those words and these coordinates only. This review folder
also holds page images, so it stays with the scan.</p>
{body}
</body></html>
"""
    out = rev / "index.html"
    out.write_text(page)
    return out
