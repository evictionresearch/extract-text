"""Agreement between graders who answered the same documents.

`extract-text agree --out DIR FILE ...` reads the answers already in
`DIR/corrections.jsonl` and each grader's returned `corrections_NAME.jsonl`,
finds the documents more than one grader answered (the shared set that
`review --graders --overlap N` puts first), and reports, field by field, how
often each pair of graders gave the same answer. Where they differ it prints
the document number, the field, and each grader's answer in masked form,
so the report holds counts, grader names, and shapes, never a record value.

With `--merge` the graders' answers are appended to `DIR/corrections.jsonl`,
every one of them, so nothing is lost when two graders answered the same
document. Scoring uses the latest answer per document, which after a merge
is whichever file came last; the documents graders disagreed on are settled
by opening them with `extract-text review --out DIR --rows ...` and saving
the right answer, which then becomes the latest.
"""

from __future__ import annotations

import json
from collections import Counter
from itertools import combinations
from pathlib import Path

from .corrections import write_corrections_csv
from .score import FIELDS, compare, mask

# how one grader's answer differs from another's, in words that do not
# assume either is right (the scorer's kinds are machine-against-truth)
KINDS = {"near": "formatting only", "blank": "one left it empty",
         "extra": "one left it empty", "extra names": "different number of names",
         "missing names": "different number of names", "different": "different"}


def read_answers(paths) -> list[dict]:
    """Every saved answer in the given files, in file order."""
    records = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        with open(path) as f:
            records += [json.loads(line) for line in f if line.strip()]
    return records


def _key(c: dict) -> tuple:
    return (c["row"], c.get("reviewer", ""), c.get("saved_at", ""))


def latest_by_grader(records) -> dict:
    """{row: {reviewer: latest answer}}."""
    answers = {}
    for c in records:
        answers.setdefault(c["row"], {})[c.get("reviewer", "")] = c
    return answers


def agreement(records) -> dict:
    by_row = latest_by_grader(records)
    shared = {row: a for row, a in by_row.items() if len(a) > 1}
    fields = {f: {"pairs": 0, "same": 0, "near": 0, "kinds": Counter()} for f in FIELDS}
    verdicts = {"pairs": 0, "both": 0}
    disagreements = []          # (row, field, kind, [(who, masked value), ...])
    for row, answers in sorted(shared.items()):
        for a, b in combinations(sorted(answers), 2):
            ca, cb = answers[a], answers[b]
            unreadable = [c["verdict"] == "unreadable" for c in (ca, cb)]
            if any(unreadable):
                verdicts["pairs"] += 1
                if all(unreadable):
                    verdicts["both"] += 1
                else:
                    disagreements.append((row, "can't tell", "one could not tell",
                                          [(a, ""), (b, "")]))
                continue
            ta, tb = ca["truth"], cb["truth"]
            wrong = compare(ta, tb)
            for field in FIELDS:
                # the attorney box is only on some documents, and only in
                # answers saved after 2026-10-07
                if field.startswith("attorney") and not ("attorneys" in ta and "attorneys" in tb):
                    continue
                f = fields[field]
                f["pairs"] += 1
                kind = wrong.get(field)
                if kind is None:
                    f["same"] += 1
                    continue
                f["kinds"][KINDS[kind]] += 1
                if kind == "near":
                    f["near"] += 1
                else:
                    disagreements.append((row, field, KINDS[kind],
                                          [(a, mask(ta.get(field))), (b, mask(tb.get(field)))]))
    return {
        "n_answers": len(records),
        "graders": Counter(who for a in by_row.values() for who in a),
        "n_shared": len(shared),
        "fields": {k: v for k, v in fields.items() if v["pairs"]},
        "verdicts": verdicts,
        "disagreements": disagreements,
    }


def _pct(k, n) -> str:
    return f"{100 * k / n:5.1f}%" if n else "    –"


def report(out_dir, files=(), shapes=True) -> str:
    out = Path(out_dir)
    t = agreement(read_answers([out / "corrections.jsonl", *files]))
    lines = [f"Answers read: {t['n_answers']}, from "
             + ", ".join(f"{who or 'unknown'} ({n} documents)" for who, n in t["graders"].most_common())
             + ".",
             f"Documents answered by more than one grader: {t['n_shared']}."]
    if not t["n_shared"]:
        lines.append("Nothing to compare yet. Graders need the same shared set "
                     "(review --graders --overlap N) and their files listed here.")
        return "\n".join(lines)
    lines += ["", "share of grader pairs giving the same answer, then the same or "
                  "differing in formatting only"]
    for field, f in t["fields"].items():
        kinds = ", ".join(f"{n} {k}" for k, n in f["kinds"].most_common() if k != "formatting only")
        lines.append(f"  {field:<17}{_pct(f['same'], f['pairs'])} "
                     f"{_pct(f['same'] + f['near'], f['pairs'])} of {f['pairs']:>4} pairs"
                     + (f"   differ: {kinds}" if kinds else ""))
    v = t["verdicts"]
    if v["pairs"]:
        lines.append(f"  {v['pairs']} pairs where someone pressed \"Can't tell from the page\"; "
                     f"both did on {v['both']}.")
    rows = sorted({row for row, *_ in t["disagreements"]})
    if not rows:
        lines += ["", "No disagreements beyond formatting."]
        return "\n".join(lines)
    if shapes:
        lines += ["", "disagreements to settle (letters A/a, digits 9)"]
        for row, field, kind, who_said in t["disagreements"]:
            lines.append(f"  #{row:<4} {field:<17}{kind}")
            for who, shape in who_said:
                if shape or field != "can't tell":
                    lines.append(f"        {who or 'unknown'}: {shape or '(empty)'}")
    lines += ["", f"{len(rows)} documents to settle. Open them, read the page, and save "
                  "the right answer; it becomes the answer that counts:",
              f"  extract-text review --out {out_dir} --rows {','.join(map(str, rows))} --serve"]
    return "\n".join(lines)


def merge(out_dir, files) -> int:
    """Append every answer in `files` that is not already in
    DIR/corrections.jsonl, and rewrite corrections.csv. Returns how many
    were added. Running it twice adds nothing the second time."""
    out = Path(out_dir)
    have = {_key(c) for c in read_answers([out / "corrections.jsonl"])}
    added = 0
    with open(out / "corrections.jsonl", "a") as f:
        for c in read_answers(files):
            if _key(c) not in have:
                f.write(json.dumps(c) + "\n")
                have.add(_key(c))
                added += 1
    write_corrections_csv(out)
    return added
