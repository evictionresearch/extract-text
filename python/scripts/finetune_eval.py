"""Score an AI engine on the held-out random draw of a grading round.

    python finetune_eval.py --scan ROUND_DIR --run RUN_DIR --engine scan
    python finetune_eval.py --scan ROUND_DIR --run RUN_DIR --engine ollama --model qwen3.5:9b
    python finetune_eval.py --scan ROUND_DIR --run RUN_DIR --engine mlx \
        --model BASE_WEIGHTS [--adapter ADAPTER_DIR] --label tuned

`scan` scores the AI engine's reading saved in the round's scan (the
original prompt), `rules` the deterministic engine's columns from the same
scan, `ollama` runs the engine's default prompt (the graders' format, with the
case number) through Ollama, and `mlx` runs the prompt the fine-tune was
trained with in this process through mlx-vlm, with or without a LoRA adapter,
so a fine-tuned model is scored without any server. The rows are
the `test` list in RUN_DIR/data/split.json, which the exporter wrote and
training never saw.

Each engine's readings are saved to RUN_DIR/eval/LABEL.jsonl, in governed
storage, since they hold names and addresses. What is printed is the
share of fields right, the way `extract-text score` counts it, how each
firm miss happened, how often the case number matches the rules engine's
in the scan, and nothing from a record.

    python finetune_eval.py --scan ROUND_DIR --run RUN_DIR --compare LABEL_A LABEL_B

compares saved readings document by document: both right, one right, both
wrong, the rows that flipped, and how often the two agreed and were right
when they agreed. `--rows all` scores every graded row instead of the
held-out draw, for that agreement check only; readings made that way must
never feed training.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

from extract_text.ai.vision import LISTS_PROMPT, LocalVisionBackend
from extract_text.corrections import _sha256, load_corrections
from extract_text.documents import render_page
from extract_text.finetune import clean_target
from extract_text.parties import _party_key
from extract_text.pipeline import ai_reading, case_key, machine_reading, read_scan
from extract_text.score import FIELDS, _names_wrong, _squash, compare


def reading_of(x) -> dict:
    """An extraction in the shape a correction takes, attorneys and firm
    apart as round 1 recorded them, and every attorney line together."""
    r = x.record
    a = r.defendant_address
    att = r.attorney
    people = [n for n in (att.names or "").split("; ") if n] if att else []
    firm = (att.firm or "") if att else ""
    return {
        "plaintiff": "; ".join(p.name for p in r.plaintiffs),
        "defendants": [p.name for p in r.defendants],
        "street": (a.street or "") if a else "", "unit": (a.unit or "") if a else "",
        "city": (a.city or "") if a else "", "state": (a.state or "") if a else "",
        "zip": (a.zip or "") if a else "",
        "attorneys": people, "attorney_firm": firm,
        "attorney_address": (att.address.raw if att and att.address else "") or "",
        "attorney_lines": [*people, *([firm] if firm else [])],
        "case_number": r.case_number or "",
    }


def firm_miss(truth: dict, reading: dict) -> str:
    """How a round-1 firm miss happened, in words that carry no value."""
    want, got = truth.get("attorney_firm", ""), reading.get("attorney_firm", "")
    people = reading.get("attorneys") or []
    if _squash(want) and any(_party_key(want) == _party_key(n) for n in people):
        return "firm read as a person"
    if _squash(got) and any(_party_key(got) == _party_key(n) for n in truth.get("attorneys") or []):
        return "a person read as the firm"
    if not _squash(got):
        return "no firm line" if people else "no attorney block"
    return "another firm line"


class MLXBackend(LocalVisionBackend):
    """The graders'-format prompt through mlx-vlm in this process."""

    name = "mlx-vision"

    def __init__(self, model_path: str, adapter: str | None, label: str):
        super().__init__(model=label, prompt_format="lists", prompt=LISTS_PROMPT)
        from mlx_vlm import load

        self._resolved = label
        self.mlx_model, self.processor = load(model_path, adapter_path=adapter)
        self.config = self.mlx_model.config
        self._image = None

    def _chat(self, b64_image: str) -> str:
        from mlx_vlm import generate
        from mlx_vlm.prompt_utils import apply_chat_template

        prompt = apply_chat_template(self.processor, self.config, self.prompt,
                                     num_images=1, enable_thinking=False)
        out = generate(self.mlx_model, self.processor, prompt, image=[str(self._image)],
                       max_tokens=1024, temperature=0.0, verbose=False)
        return getattr(out, "text", out)

    def extract_image(self, image_path, source_text=None):
        self._image = image_path
        return super().extract_image(image_path, source_text)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--scan", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--engine", choices=("scan", "rules", "ollama", "mlx"), default=None,
                   help="scan: the AI reading saved in the round; rules: the deterministic "
                        "engine's columns; ollama or mlx: run the graders'-format prompt")
    p.add_argument("--model", default="qwen3.5:9b")
    p.add_argument("--adapter", default=None)
    p.add_argument("--label", default=None)
    p.add_argument("--rows", choices=("test", "all"), default="test",
                   help="test: the held-out random draw (default); all: every graded row, "
                        "for an agreement check that must never feed training")
    p.add_argument("--limit", type=int, default=None, help="first N rows only (a check)")
    p.add_argument("--compare", nargs="+", metavar="LABEL", default=None,
                   help="instead of scoring, compare saved readings document by document: "
                        "two or more labels from RUN_DIR/eval")
    a = p.parse_args(argv)

    scan, run = Path(a.scan), Path(a.run)
    if a.compare:
        from extract_text.finetune import compare_report, compare_runs

        text = compare_report(compare_runs(scan, run, a.compare))
        (run / "eval" / ("compare_" + "_vs_".join(a.compare) + ".txt")).write_text(text + "\n")
        print(text)
        return
    if not a.engine:
        p.error("--engine is required unless --compare is given")
    label = a.label or a.engine
    latest = load_corrections(scan)
    if a.rows == "all":
        test = sorted(r for r, c in latest.items() if c["verdict"] != "unreadable")[:a.limit]
    else:
        test = json.loads((run / "data" / "split.json").read_text())["test"][:a.limit]
    images = run / "test_images"
    images.mkdir(exist_ok=True)
    (run / "eval").mkdir(exist_ok=True)

    backend = None
    if a.engine == "ollama":
        backend = LocalVisionBackend(model=a.model, prompt_format="lists")
    elif a.engine == "mlx":
        backend = MLXBackend(a.model, a.adapter, label)
    rows, details = read_scan(scan)

    tallies = {f: Counter() for f in (*FIELDS, "attorney_lines")}
    flags = Counter()
    firm_misses = Counter()
    case = Counter()
    started = time.time()
    with open(run / "eval" / f"{label}.jsonl", "w") as saved:
        for i, r in enumerate(test, 1):
            c = latest[r]
            truth = c["truth"]
            if a.engine in ("scan", "rules"):
                if c.get("sha256") and _sha256(Path(details[r - 1].get("file", ""))) != c["sha256"]:
                    flags["skipped: document changed"] += 1
                    continue
                if a.engine == "rules":
                    reading = machine_reading(rows[r - 1])
                else:
                    reading = ai_reading(details[r - 1]) or c.get("ai") or {}
            else:
                png = images / f"row_{r:04d}.png"
                if not png.exists():
                    page = render_page(c["file"], page=1, dpi=150, out_path=png)
                    if page is not None and Path(page) != png:
                        png.write_bytes(Path(page).read_bytes())
                try:
                    x = backend.extract_image(png)
                except Exception as exc:  # one bad page must not sink the run
                    flags[f"error: {type(exc).__name__}"] += 1
                    continue
                flags.update(x.flags)
                reading = reading_of(x)
            saved.write(json.dumps({"row": r, "reading": reading}, ensure_ascii=False) + "\n")
            wrong = compare(truth, reading)
            if "attorneys" in truth and "attorney_firm" in truth and wrong.get("attorney_firm"):
                firm_misses[firm_miss(truth, reading)] += 1
            rules_case = case_key(rows[r - 1].get("case_number"))
            if rules_case and "case_number" in reading:
                case["n"] += 1
                case["agree"] += case_key(reading["case_number"]) == rules_case
            for field in FIELDS:
                if field.startswith("attorney") and "attorneys" not in truth:
                    continue
                if field == "attorneys" and "attorneys" not in reading:
                    continue
                tallies[field]["n"] += 1
                kind = wrong.get(field)
                tallies[field]["right" if kind is None else kind] += 1
            if "attorneys" in truth and "attorney_lines" in reading:
                # every line of the box, attorneys and firm together, against
                # the cleaned label, which is how round 2 records it
                want = clean_target(truth)["attorneys"]
                kind = _names_wrong(want, reading["attorney_lines"])
                tallies["attorney_lines"]["n"] += 1
                tallies["attorney_lines"]["right" if kind is None else kind] += 1
            if i % 5 == 0:
                print(f"  {label}: {i} of {len(test)} documents, "
                      f"{time.time() - started:.0f} s", file=sys.stderr, flush=True)

    lines = [f"{label}: {len(test)} {'graded documents' if a.rows == 'all' else 'random documents held out'}, "
             f"{time.time() - started:.0f} s",
             "  field             right  right or near"]
    for field, t in tallies.items():
        if t["n"]:
            kinds = ", ".join(f"{n} {k}" for k, n in t.most_common()
                              if k not in ("n", "right"))
            lines.append(f"  {field:<17}{t['right']:>3} of {t['n']:<3}"
                         f"{100 * t['right'] / t['n']:5.1f}%  "
                         f"{100 * (t['right'] + t['near']) / t['n']:5.1f}%"
                         + (f"   wrong: {kinds}" if kinds else ""))
    if case["n"]:
        lines.append(f"  case_number      {case['agree']:>3} of {case['n']:<3}"
                     f"{100 * case['agree'] / case['n']:5.1f}%  agree with the rules engine")
    if firm_misses:
        lines.append("  attorney_firm misses: "
                     + ", ".join(f"{n} {k}" for k, n in firm_misses.most_common()))
    if flags:
        lines.append("  flags: " + ", ".join(f"{n} {k}" for k, n in flags.most_common()))
    text = "\n".join(lines)
    (run / "eval" / f"{label}_score.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
