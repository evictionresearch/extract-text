"""Case files: what happened after the summons.

The engines read one document. A case is a folder of them, and the folder
holds the rest of the story: whether the tenant answered, whether the case
was dismissed or went to judgment, and what the sheriff reported back on the
writ. `extract-text cases DIR --out RESULTS` types every document in every
case folder, rolls each case up to those stages, and writes

- `cases.csv`, one row per case folder
- `case_documents.csv`, one row per document with its type, which joins to
  `extracted.csv` on the file name

The stage rules follow Cheng Ren's 2024 dissertation, "Not All Eviction Cases
are Alike" (UC Berkeley, https://escholarship.org/uc/item/7f36p8n6), which
coded 56,070 Pierce County cases this way:

- A document's type comes from its file name, because court systems name each
  file for the document it holds.
- A dismissal on file means dismissed and a judgment on file means judged. A
  motion for default judgment carries the word, so it counts as judged. A
  case holding both went to judgment: a plaintiff may move to dismiss and then
  carry on (p. 36).
- An answer or a notice of appearance means the tenant responded, and a motion
  for default means the tenant did not (p. 46).
- The sheriff's return on the writ says how the case ended, in one of five
  ways. "Ousted and ejected" and "peaceful possession" are evictions by the
  sheriff. Returned at the plaintiff's or the attorney's request, or expired,
  means the tenant was gone before the sheriff acted (pp. 35-36).

Two choices here are this package's and not the dissertation's. A writ or a
sheriff's return on file counts as a judgment even when the file name lacks
the word, because a writ only issues after one. And when a case holds several
sheriff's returns, an eviction on any of them decides the case; otherwise the
last return in name order does.

Everything is rules. Typing reads file names only. Reading a sheriff's return
opens its first page through the same text layer and OCR path the
deterministic engine uses, on this machine.

`cases.csv` carries folder names, which in a court collection are usually
case numbers, so it belongs on governed storage with the rest of the output.
The printed report is counts only and is safe to share.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .documents import load_document
from .pipeline import _Progress, collect_inputs

# First match wins, so the order is the rule. "Sheriff's return on writ of
# restitution" must be tried before the writ, "motion for default judgment"
# before the judgment, and "answer to complaint" before the complaint. A
# return of service is the summons being served, never the sheriff's return.
DOC_TYPE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("sheriff_return", re.compile(r"sheriff.*return|\breturn.*\b(?:writ|sheriff)")),
    ("writ", re.compile(r"\bwrit\b|restitution")),
    ("default_motion", re.compile(r"\bdefault")),
    ("dismissal", re.compile(r"dismiss")),
    ("judgment", re.compile(r"judge?ment")),
    ("answer", re.compile(r"\banswer|\bappearance")),
    ("summons", re.compile(r"summons")),
    ("complaint", re.compile(r"complaint")),
]
DOC_TYPES = tuple(t for t, _ in DOC_TYPE_RULES) + ("other",)

# The dissertation's five categories (pp. 35-36), as the return words them.
SHERIFF_RETURN_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ousted_ejected", re.compile(r"ousted and ejected")),
    ("peaceful_possession", re.compile(r"peaceful possession")),
    ("return_per_attorney",
     re.compile(r"at the request of the attorneys? for the plaintiffs?")),
    ("return_per_plaintiff", re.compile(r"at the request of the plaintiffs?")),
    ("expired", re.compile(r"writ of restitution has expired|restitution unsatisfied")),
]
SHERIFF_EVICTED = ("ousted_ejected", "peaceful_possession")

# Words counted in the file names the rules could not type. Only words on this
# list are ever printed, so the report can say what is going untyped without
# printing a file name, and file names can carry party names and case numbers.
LEGAL_WORDS = (
    "affidavit", "agreed", "amended", "bench", "calendar", "cause", "certificate",
    "confidential", "continuance", "cover", "declaration", "exhibit", "fee",
    "findings", "hearing", "information", "mailing", "minutes", "motion", "note",
    "notice", "order", "petition", "posting", "proposed", "receipt", "reply",
    "response", "return", "service", "sheet", "show", "stay", "stipulation",
    "vacate", "waiver",
)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def document_type(name: str) -> str:
    """The kind of court document a file holds, read from its file name."""
    title = _squash(re.sub(r"[_\-.]+", " ", Path(name).stem))
    for doc_type, pattern in DOC_TYPE_RULES:
        if pattern.search(title):
            return doc_type
    return "other"


def sheriff_return_status(text: str) -> str:
    """Which of the five outcomes a sheriff's return reports.

    Returns the category, `ambiguous` when the page words more than one, or
    `unread` when it words none (a poor scan, or a form the rules have not
    met). Neither is guessed at; both are flagged on the case.
    """
    squashed = _squash(text)
    found = [status for status, pattern in SHERIFF_RETURN_RULES
             if pattern.search(squashed)]
    if not found:
        return "unread"
    return found[0] if len(found) == 1 else "ambiguous"


@dataclass
class CaseSummary:
    """One case folder, rolled up to the stages it reached."""

    case_dir: str
    documents: list[tuple[str, str]] = field(default_factory=list)  # (file, type)
    sheriff_returns: list[str] = field(default_factory=list)  # statuses, name order

    def has(self, doc_type: str) -> bool:
        return any(t == doc_type for _, t in self.documents)

    @property
    def judged(self) -> bool:
        return any(self.has(t) for t in
                   ("judgment", "default_motion", "writ", "sheriff_return"))

    @property
    def outcome(self) -> str:
        if self.judged:
            return "judgment"
        return "dismissed" if self.has("dismissal") else "none_recorded"

    @property
    def sheriff_return_status(self) -> str:
        evictions = [s for s in self.sheriff_returns if s in SHERIFF_EVICTED]
        if evictions:
            return evictions[-1]
        return self.sheriff_returns[-1] if self.sheriff_returns else ""

    @property
    def sheriff_evicted(self) -> bool | None:
        status = self.sheriff_return_status
        if status in ("", "unread", "ambiguous"):
            return None
        return status in SHERIFF_EVICTED

    @property
    def flags(self) -> list[str]:
        flags = []
        if not self.has("summons"):
            flags.append("no_summons")
        if self.has("dismissal") and self.judged:
            flags.append("dismissal_and_judgment")
        if self.judged and not self.has("sheriff_return"):
            flags.append("judgment_no_sheriff_return")
        if self.sheriff_return_status in ("unread", "ambiguous"):
            flags.append(f"sheriff_return_{self.sheriff_return_status}")
        return flags

    def row(self) -> dict:
        evicted = self.sheriff_evicted
        return {
            "case_dir": self.case_dir,
            "n_documents": len(self.documents),
            "n_untyped": sum(1 for _, t in self.documents if t == "other"),
            **{f"has_{t}": self.has(t) for t in DOC_TYPES if t != "other"},
            "outcome": self.outcome,
            "n_sheriff_returns": sum(1 for _, t in self.documents
                                     if t == "sheriff_return"),
            "sheriff_return_status": self.sheriff_return_status,
            "sheriff_evicted": "" if evicted is None else evicted,
            "flags": ";".join(self.flags),
        }


def _read_return(path) -> str:
    try:
        return sheriff_return_status(load_document(path, pages=[1]).text)
    except Exception:
        # one unreadable return must not sink the run; the case is flagged
        return "unread"


def scan_cases(inputs, out_dir=None, read_returns: bool = True,
               recursive: bool = True, progress: bool = True) -> list[CaseSummary]:
    """Type every document under `inputs` and roll each case folder up.

    A case is a folder that directly holds documents. With `read_returns`
    (the default) each sheriff's return is opened and its outcome read;
    without it the pass reads file names only and takes seconds.
    """
    files = collect_inputs(inputs, recursive=recursive)
    if not files:
        raise FileNotFoundError("No documents found.")
    by_case: dict[Path, list[Path]] = defaultdict(list)
    for f in files:
        by_case[f.parent].append(f)

    typed = {f: document_type(f.name) for f in files}
    returns = [f for f in files if typed[f] == "sheriff_return"] if read_returns else []
    statuses = {}
    if returns:
        bar = _Progress(len(returns), enabled=progress)
        try:
            for i, f in enumerate(returns, 1):
                bar.status(i, "sheriff's return")
                statuses[f] = _read_return(f)
                bar.advance(statuses[f] == "unread")
        finally:
            bar.close()

    cases = []
    for case_dir in sorted(by_case):
        docs = by_case[case_dir]
        cases.append(CaseSummary(
            case_dir=case_dir.name,
            documents=[(f.name, typed[f]) for f in docs],
            sheriff_returns=[statuses[f] for f in docs if f in statuses],
        ))
    if out_dir is not None:
        write_cases(cases, out_dir)
    return cases


def write_cases(cases: list[CaseSummary], out_dir) -> Path:
    """Write cases.csv and case_documents.csv."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [c.row() for c in cases]
    with open(out / "cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["case_dir"])
        w.writeheader()
        w.writerows(rows)
    with open(out / "case_documents.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_dir", "file", "doc_type"])
        for c in cases:
            w.writerows([c.case_dir, name, doc_type] for name, doc_type in c.documents)
    return out


def report(cases: list[CaseSummary]) -> str:
    """The stage counts, as text. Counts only: no folder or file name."""
    n = len(cases)
    if not n:
        return "No cases."

    def line(label: str, count: int, of: int = n, indent: int = 2) -> str:
        share = f"{100 * count / of:5.1f}%" if of else "     -"
        return f"{' ' * indent}{label:<44}{count:>8}  {share}"

    def count(test) -> int:
        return sum(1 for c in cases if test(c))

    judged = count(lambda c: c.judged)
    returned = count(lambda c: c.has("sheriff_return"))
    out = [
        f"Cases: {n}",
        line("with a summons", count(lambda c: c.has("summons"))),
        line("with an answer or notice of appearance", count(lambda c: c.has("answer"))),
        line("with a motion for default", count(lambda c: c.has("default_motion"))),
        "Outcome",
        line("judgment", judged),
        line("dismissed", count(lambda c: c.outcome == "dismissed")),
        line("none recorded", count(lambda c: c.outcome == "none_recorded")),
        line("dismissal and judgment both on file",
             count(lambda c: "dismissal_and_judgment" in c.flags)),
        "After judgment",
        line("sheriff's return on file", returned, judged),
        line("no sheriff's return", judged - returned, judged),
    ]
    by_status = Counter(c.sheriff_return_status for c in cases if c.sheriff_returns)
    if by_status:
        read = sum(by_status.values())
        out.append("Sheriff's returns read")
        for status in [s for s, _ in SHERIFF_RETURN_RULES] + ["ambiguous", "unread"]:
            out.append(line(status.replace("_", " "), by_status.get(status, 0), read))
        out.append(line("evicted by the sheriff",
                        count(lambda c: c.sheriff_evicted is True), read))

    docs = [d for c in cases for d in c.documents]
    untyped = [name for name, t in docs if t == "other"]
    out.append(f"Documents: {len(docs)}")
    by_type = Counter(t for _, t in docs)
    for t in DOC_TYPES:
        out.append(line(t.replace("_", " "), by_type.get(t, 0), len(docs)))
    words = Counter(w for name in untyped
                    for w in set(re.findall(r"[a-z]+", name.lower()))
                    if w in LEGAL_WORDS)
    if words:
        out.append("Untyped documents, by legal word in the file name")
        for w, k in words.most_common():
            out.append(line(w, k, len(untyped)))
    return "\n".join(out)
