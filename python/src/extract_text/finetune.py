"""Training examples for fine-tuning the AI engine on the graders' labels.

`export_training_set(scan_dir, out_dir)` turns the corrections saved beside
a scan into the chat-format rows `mlx_vlm.train` reads: the page-1 image the
engine itself would see, the graders'-format prompt, and the label as the
JSON answer. The model learns whatever the labels show, so each label is
first cleaned with the package's own name rules, and the counts of what the
cleaning changed are returned for the run record.

Documents drawn at random are the test set and never become training rows:
they are what before-and-after scores are read on. Everything written holds
names and addresses, and so does a model trained on it, so `out_dir` must be
governed storage; only the counts this module returns may leave it.
"""

from __future__ import annotations

import json
import random
import shutil
from collections import Counter
from pathlib import Path

from .ai.vision import lists_prompt
from .corrections import _bare, _sha256, load_corrections
from .parties import _ENTITY_CLAUSE_RE, _strip_group_terms, is_placeholder

VALID_SHARE = 0.1
SPLIT_SEED = 20261020


def _defendants(names, changes: Counter) -> list[str]:
    out = []
    for name in names or []:
        if is_placeholder(name):
            # a placeholder ("JOHN DOE", or "JANE DOE" with a surname);
            # stripping keeps the original when nothing would be left, so
            # it is dropped here
            changes["defendant_placeholder_dropped"] += 1
            continue
        kept, found = _strip_group_terms(name)
        if found:
            changes["defendant_group_term_stripped"] += 1
        kept = _bare(kept)
        if kept:
            out.append(kept)
    return out


def _plaintiffs(joined: str, changes: Counter) -> list[str]:
    out = []
    for name in (joined or "").split(";"):
        name = name.strip()
        if not name:
            continue
        short = _ENTITY_CLAUSE_RE.sub("", name)
        if short != name:
            changes["plaintiff_description_dropped"] += 1
        bare = _bare(short)
        if bare != short:
            changes["plaintiff_trailing_punctuation_dropped"] += 1
        if bare:
            out.append(bare)
    return out


def clean_target(truth: dict, changes: Counter | None = None) -> dict:
    """A grader's answer as the answer the model is trained to give.

    The attorney block is in the target only when the answer has one: an
    answer saved without the attorney box says nothing about it, and
    training "no attorney" there would teach a falsehood."""
    changes = changes if changes is not None else Counter()
    target = {
        "plaintiffs": _plaintiffs(truth.get("plaintiff", ""), changes),
        "defendants": _defendants(truth.get("defendants"), changes),
        "defendant_address": {k: truth.get(k, "") or ""
                              for k in ("street", "unit", "city", "state", "zip")},
    }
    if "attorneys" in truth:
        lines = [_bare(n) for n in truth.get("attorneys") or [] if _bare(n)]
        firm = _bare(truth.get("attorney_firm", "") or "")
        if firm and firm.casefold() not in {n.casefold() for n in lines}:
            # round 1 kept the firm in its own box; round 2 has one box
            lines.append(firm)
            changes["attorney_firm_joined"] += 1
        target["attorneys"] = lines
        target["attorney_address"] = truth.get("attorney_address", "") or ""
    return target


def training_row(image: str, target: dict) -> dict:
    """One chat-format row: the prompt the engine runs with (without the
    attorney items when the target has no attorney block) and the answer."""
    prompt = lists_prompt(attorneys="attorneys" in target)
    return {
        "images": [image],
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)},
        ],
    }


def split_rows(latest: dict, valid_share=VALID_SHARE, seed=SPLIT_SEED):
    """Row numbers for training, validation, and test. Test is the random
    draw; training and validation share the flagged documents, never one
    whose document (by sha256) is also in the test set."""
    readable = {r: c for r, c in latest.items() if c["verdict"] != "unreadable"}
    test = sorted(r for r, c in readable.items() if c["sampled_as"] == "random")
    held = {readable[r].get("sha256") for r in test} - {"", None}
    pool = sorted(r for r, c in readable.items()
                  if c["sampled_as"] != "random" and c.get("sha256") not in held)
    rng = random.Random(seed)
    valid = sorted(rng.sample(pool, max(1, round(len(pool) * valid_share)))) if pool else []
    train = [r for r in pool if r not in set(valid)]
    return train, valid, test


def export_training_set(scan_dir, out_dir, dpi=150) -> dict:
    """Write `train.jsonl`, `valid.jsonl`, the page images, and `split.json`
    (row numbers only) into `out_dir`. Returns counts, never values."""
    from .documents import render_page

    scan, out = Path(scan_dir), Path(out_dir)
    images = out / "images"
    images.mkdir(parents=True, exist_ok=True)
    latest = load_corrections(scan)
    train, valid, test = split_rows(latest)
    changes: Counter = Counter()
    report = {"labeled": len(latest),
              "unreadable": sum(c["verdict"] == "unreadable" for c in latest.values()),
              "test_rows": len(test), "skipped": Counter()}
    for split, rows in (("train", train), ("valid", valid)):
        written = with_attorneys = 0
        with open(out / f"{split}.jsonl", "w") as f:
            for r in rows:
                c = latest[r]
                src = Path(c.get("file", ""))
                if not src.is_file():
                    report["skipped"]["document missing"] += 1
                    continue
                if c.get("sha256") and _sha256(src) != c["sha256"]:
                    report["skipped"]["document changed"] += 1
                    continue
                png = images / f"row_{r:04d}.png"
                if not png.exists():
                    page = render_page(src, page=1, dpi=dpi, out_path=png)
                    if page is None:
                        report["skipped"]["page did not render"] += 1
                        continue
                    if Path(page) != png:  # an image file is used as it is
                        shutil.copyfile(page, png)
                target = clean_target(c["truth"], changes)
                with_attorneys += "attorneys" in target
                f.write(json.dumps(training_row(str(png), target), ensure_ascii=False) + "\n")
                written += 1
        report[f"{split}_rows"] = written
        report[f"{split}_with_attorneys"] = with_attorneys
    (out / "split.json").write_text(json.dumps(
        {"train": train, "valid": valid, "test": test, "seed": SPLIT_SEED}, indent=1))
    report["changes"] = dict(changes)
    report["skipped"] = dict(report["skipped"])
    return report


# ---------------------------------------------------------------------------
# Paired comparison of saved readings, and how far machine agreement can be
# trusted as a label.

PAIR_KINDS = ("both right", "first only", "second only", "both wrong")


def _agree(a: dict, b: dict, field: str) -> bool:
    """Two readings give the same content for a field, formatting aside."""
    from .score import compare

    return compare({field: a.get(field)}, {field: b.get(field)}).get(field) in (None, "near")


def compare_runs(scan_dir, run_dir, labels, rows=None) -> dict:
    """Score two or more saved reading sets document by document against the
    latest corrections, so a change shows as the documents it flipped and
    not only as a total.

    `labels` name files RUN_DIR/eval/LABEL.jsonl (one `{"row", "reading"}`
    line per document, as finetune_eval.py writes them). `rows` limits the
    comparison to those row numbers; by default every row all the labels
    read. For each field and each pair of labels the result holds the four
    paired counts (`PAIR_KINDS`), the rows that flipped either way, and the
    agreement figures: how many documents the pair agreed on and how many of
    those the first was right on. Nothing in the result is a record value.
    """
    from .corrections import load_corrections
    from .score import FIELDS, compare

    scan, run = Path(scan_dir), Path(run_dir)
    latest = load_corrections(scan)
    readings = {}
    for label in labels:
        with open(run / "eval" / f"{label}.jsonl") as fh:
            readings[label] = {int(json.loads(line)["row"]): json.loads(line)["reading"]
                               for line in fh if line.strip()}
    shared = set.intersection(*(set(r) for r in readings.values()))
    shared = {r for r in shared if r in latest and latest[r]["verdict"] != "unreadable"}
    if rows is not None:
        shared &= set(rows)
    wrong = {label: {r: compare(latest[r]["truth"], readings[label][r]) for r in shared}
             for label in labels}

    def scored(label, r, field):
        truth, reading = latest[r]["truth"], readings[label][r]
        if field.startswith("attorney") and "attorneys" not in truth:
            return None
        if field == "attorneys" and "attorneys" not in reading:
            return None
        return wrong[label][r].get(field) is None

    out = {"n": len(shared), "labels": list(labels), "pairs": {}}
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            per_field = {}
            for field in FIELDS:
                counts = Counter()
                flipped = {"first only": [], "second only": []}
                agreed = agreed_right = 0
                for r in sorted(shared):
                    ra, rb = scored(a, r, field), scored(b, r, field)
                    if ra is None or rb is None:
                        continue
                    kind = ("both right" if ra and rb else "first only" if ra
                            else "second only" if rb else "both wrong")
                    counts[kind] += 1
                    if kind in flipped:
                        flipped[kind].append(r)
                    if _agree(readings[a][r], readings[b][r], field):
                        agreed += 1
                        agreed_right += ra
                if sum(counts.values()):
                    per_field[field] = {"counts": counts, "flipped": flipped,
                                        "agreed": agreed, "agreed_right": agreed_right}
            out["pairs"][(a, b)] = per_field
    return out


def compare_report(result: dict) -> str:
    """The printed form of `compare_runs`: counts, row numbers, and nothing
    from a record."""
    lines = [f"{result['n']} documents read by every label: " + ", ".join(result["labels"])]
    for (a, b), per_field in result["pairs"].items():
        lines += ["", f"{a} (first) against {b} (second)",
                  "  field              both   first  second   both   agree  right when agreed",
                  "                    right    only    only  wrong"]
        for field, f in per_field.items():
            c = f["counts"]
            share = (f"{100 * f['agreed_right'] / f['agreed']:5.1f}%" if f["agreed"] else "    -")
            lines.append(f"  {field:<17}{c['both right']:>6}{c['first only']:>8}"
                         f"{c['second only']:>8}{c['both wrong']:>7}{f['agreed']:>8}  {share}")
        flips = [(field, kind, rows) for field, f in per_field.items()
                 for kind, rows in f["flipped"].items() if rows]
        if flips:
            lines.append("  rows that flipped (document numbers):")
            for field, kind, rows in flips:
                lines.append(f"    {field:<15}{kind:<12}" + ", ".join(f"#{r}" for r in rows))
    return "\n".join(lines)
