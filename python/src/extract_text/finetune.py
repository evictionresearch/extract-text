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
