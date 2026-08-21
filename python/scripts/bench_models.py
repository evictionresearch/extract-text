#!/usr/bin/env python3
"""Compare local vision models on the extract-text task: fields and clock.

This is step 2 of MAINTENANCE.md's model review procedure, made repeatable.
It runs each candidate against one or more synthetic summons pages whose every
value is invented and known, scores the six fields the AI lane asks for, and
times the runs.

    # one page, with timing repeats
    python3 python/scripts/bench_models.py --repeat 3 qwen3.5:9b glm-ocr

    # the full degradation matrix (build it first with make_degraded_fixtures.py)
    python3 python/scripts/bench_models.py --degraded qwen3.5:9b glm-ocr gemma4:12b

    # arbitrary pages
    python3 python/scripts/bench_models.py --image a.png --image b.png MODEL ...

Use `--repeat 1` (the default) for matrix runs; the call count is
models x images x repeat and grows fast. Raise `--repeat` only when timing
precision on a single page is the point.

What this measures, precisely, so the number is not read as more than it is:

- **Field similarity.** Each returned field against the fixture's known value,
  using `extract_text.similarity.ratio`, the same function the validation work
  uses. Reported per page and averaged across pages.
- **Exact hits.** How many of the six normalize to the truth string exactly.
  A blunter measure than similarity and harder to flatter.
- **Seconds per page.** Cold is the first call after `ollama stop`, so it
  includes loading weights from disk and is sensitive to page cache; treat it
  as soft. Warm is the median of everything after, and is the number that
  survives repetition. A batch run pays warm, not cold.
- **Resident GB and placement.** What `ollama ps` reports the model occupying
  and whether it placed on GPU. A model that spills to CPU shows a warm time
  far out of line with its size, and this is where you see why.
- **Parse rung.** Whether the model returned clean JSON or had to be rescued
  by the regex fallback. A model that cannot hold the output contract is a
  maintenance problem regardless of how well it reads the page.

What this does NOT measure: accuracy in any sense that could support a switch.
These are synthetic pages. They tell you a model can do the task shape, roughly
what it costs, and how it degrades. Step 3 of the procedure, a few hundred real
documents on governed storage scored against the labeled truth sets, is the
only thing that can displace the pin, and that data never comes near a
machine's general-purpose tooling.

A model must already be pulled. This script never downloads anything.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_PYTHON = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_PYTHON / "src"))

from extract_text.ai.vision import (  # noqa: E402
    VISION_FIELDS,
    LocalVisionBackend,
    pulled_models,
)
from extract_text.similarity import norm, ratio  # noqa: E402

FIXTURES = REPO_PYTHON / "tests" / "fixtures"
DEFAULT_IMAGE = FIXTURES / "synthetic_summons_page1.png"
DEGRADED_DIR = FIXTURES / "degraded"

# Hardest last, so a run that is cut short still covers the easy cases.
DEGRADED_ORDER = (
    "clean.png",
    "lowdpi.png",
    "skewed.png",
    "photocopy.png",
    "noisy.png",
    "handwritten.png",
    "worst.png",
)

# The fixture's known values, transcribed from scripts/make_synthetic_fixtures.py.
# Every one is invented; see that file's docstring and the pii_sweep whitelist.
# Every degraded variant carries the same values, so one truth serves all pages.
TRUTH = {
    "plaintiff": "EXAMPLE PROPERTY LLC",
    "defendant": "JANE Q. TENANT and JON Q. TENANT",
    "address": "1234 EXAMPLE AVE S APT 5 SEATTLE, WA 98100",
    "law_firm": "EXAMPLE LAW GROUP PLLC",
    "law_firm_address": "100 MAIN ST STE 200 SEATTLE, WA 98101",
    "case_number": "25-2-00001-0",
}


def ollama_stop(model: str) -> None:
    """Evict the model so the next call pays a real cold load."""
    subprocess.run(
        ["ollama", "stop", model], capture_output=True, check=False, timeout=60
    )


def resident(model: str) -> tuple[str, str]:
    """What `ollama ps` says this model occupies, and where it placed."""
    try:
        out = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, check=False, timeout=30
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ("?", "?")
    family = model.split(":")[0]
    for line in out.splitlines()[1:]:
        if not line.startswith(family):
            continue
        parts = line.split()
        size = " ".join(parts[2:4]) if len(parts) > 3 else "?"
        where = next((p for p in parts if "GPU" in p or "CPU" in p), "?")
        return (size, where)
    return ("?", "?")


def score(fields: dict[str, str]) -> dict:
    """Per-field similarity against the fixture truth, plus two summaries."""
    per_field = {}
    exact = 0
    for key in VISION_FIELDS:
        got = fields.get(key) or ""
        want = TRUTH[key]
        per_field[key] = round(ratio(got, want), 3)
        if got and norm(got) == norm(want):
            exact += 1
    return {
        "per_field": per_field,
        "mean": round(statistics.mean(per_field.values()), 3),
        "exact": exact,
    }


def run_once(backend: LocalVisionBackend, image: Path) -> tuple[float, dict, list]:
    """One extraction. Returns seconds, the raw field values, and any flags."""
    start = time.perf_counter()
    result = backend.extract_image(image)
    elapsed = time.perf_counter() - start
    fields = {k: ev.quote for k, ev in result.evidence.items()}
    return elapsed, fields, list(result.flags)


def bench(model: str, images: list[Path], repeat: int) -> dict:
    """One model against every page. Cold load is paid once, at the start."""
    backend = LocalVisionBackend(model=model)
    row: dict = {"model": model, "pages": {}}

    ollama_stop(model)
    cold: float | None = None
    warm: list[float] = []
    flags: set[str] = set()

    for index, image in enumerate(images):
        try:
            for attempt in range(repeat):
                seconds, fields, page_flags = run_once(backend, image)
                if index == 0 and attempt == 0:
                    cold = seconds
                else:
                    warm.append(seconds)
                if attempt == 0:
                    row["pages"][image.name] = {**score(fields), "fields": fields}
                flags.update(page_flags)
        except (RuntimeError, OSError) as exc:
            row.setdefault("errors", {})[image.name] = str(exc)[:160]

    if not row["pages"]:
        return {"model": model, "error": row.get("errors", {}) or "no pages scored"}

    means = [p["mean"] for p in row["pages"].values()]
    row["cold_s"] = round(cold, 1) if cold is not None else None
    row["warm_s"] = round(statistics.median(warm), 1) if warm else None
    row["avg_mean"] = round(statistics.mean(means), 3)
    row["total_exact"] = sum(p["exact"] for p in row["pages"].values())
    row["max_exact"] = 6 * len(row["pages"])
    row["flags"] = sorted(flags)
    row["resident"], row["placement"] = resident(model)
    return row


def short(name: str) -> str:
    return name.removesuffix(".png")[:9]


def print_matrix(rows: list[dict], images: list[Path]) -> None:
    print("\nMean field similarity by page (1.000 = all six fields exact)\n")
    header = f"{'model':<20}" + "".join(f"{short(i.name):>11}" for i in images)
    header += f"{'AVG':>9}{'exact':>9}"
    print(header)
    print("-" * len(header))
    for row in rows:
        if "error" in row:
            print(f"{row['model']:<20} ERROR {row['error']}")
            continue
        line = f"{row['model']:<20}"
        for image in images:
            page = row["pages"].get(image.name)
            line += f"{page['mean']:>11.3f}" if page else f"{'-':>11}"
        line += f"{row['avg_mean']:>9.3f}"
        line += f"{row['total_exact']:>5}/{row['max_exact']:<3}"
        print(line)


def print_timing(rows: list[dict]) -> None:
    header = (
        f"\n{'model':<20} {'cold s':>7} {'warm s':>7} {'resident':>9} "
        f"{'placed':>9}  flags"
    )
    print(header)
    print("-" * (len(header) - 1))
    for row in rows:
        if "error" in row:
            continue
        cold = f"{row['cold_s']:.1f}" if row["cold_s"] is not None else "-"
        warm = f"{row['warm_s']:.1f}" if row["warm_s"] is not None else "-"
        print(
            f"{row['model']:<20} {cold:>7} {warm:>7} {row['resident']:>9} "
            f"{row['placement']:>9}  {','.join(row['flags']) or '-'}"
        )


def print_fields(rows: list[dict], image_name: str) -> None:
    scored = [r for r in rows if "error" not in r and image_name in r["pages"]]
    if not scored:
        return
    print(f"\nPer-field similarity on {image_name}\n")
    header = f"{'field':<18}" + "".join(f"{r['model'][:13]:>15}" for r in scored)
    print(header)
    print("-" * len(header))
    for key in VISION_FIELDS:
        line = f"{key:<18}"
        for row in scored:
            line += f"{row['pages'][image_name]['per_field'][key]:>15.3f}"
        print(line)


def resolve_images(args) -> list[Path]:
    if args.degraded:
        if not DEGRADED_DIR.is_dir():
            raise SystemExit(
                f"No degraded fixtures at {DEGRADED_DIR}. Build them with:\n"
                "  python3 python/scripts/make_degraded_fixtures.py"
            )
        found = [DEGRADED_DIR / n for n in DEGRADED_ORDER if (DEGRADED_DIR / n).exists()]
        extra = sorted(
            p for p in DEGRADED_DIR.glob("*.png") if p.name not in DEGRADED_ORDER
        )
        return found + extra
    if args.image:
        return list(args.image)
    return [DEFAULT_IMAGE]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("models", nargs="+", help="Ollama tags, already pulled")
    parser.add_argument(
        "--image", type=Path, action="append", help="page to score; repeatable"
    )
    parser.add_argument(
        "--degraded", action="store_true", help="score the whole degraded set"
    )
    parser.add_argument(
        "--repeat", type=int, default=1, help="runs per page; raise only for timing"
    )
    parser.add_argument("--json", type=Path, help="also write the full rows here")
    args = parser.parse_args(argv)

    images = resolve_images(args)
    missing_images = [i for i in images if not i.exists()]
    if missing_images:
        print(f"No such image: {missing_images[0]}", file=sys.stderr)
        return 2

    available = set(pulled_models())
    missing = [m for m in args.models if m not in available]
    if missing:
        print("Not pulled, so not benched: " + ", ".join(missing), file=sys.stderr)
        print("Pull them first; this script never downloads.", file=sys.stderr)
        args.models = [m for m in args.models if m in available]
        if not args.models:
            return 2

    calls = len(args.models) * len(images) * args.repeat
    print(f"Pages:  {len(images)} ({', '.join(i.name for i in images)})")
    print(f"Models: {len(args.models)}   Repeat: {args.repeat}   Calls: {calls}\n")

    rows = []
    for model in args.models:
        print(f"  running {model} ...", file=sys.stderr, flush=True)
        rows.append(bench(model, images, args.repeat))

    print_matrix(rows, images)
    print_timing(rows)
    if len(images) == 1:
        print_fields(rows, images[0].name)

    print(
        "\nSynthetic pages. This is a smoke test of task shape, cost, and how a\n"
        "model degrades. It is not evidence for a switch; MAINTENANCE.md step 3\n"
        "on governed data is the real bar."
    )

    if args.json:
        args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nRows written to {args.json}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
