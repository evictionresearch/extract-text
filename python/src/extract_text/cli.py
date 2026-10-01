"""The `extract-text` command.

Five subcommands cover the whole workflow:

    extract-text doctor                     check the setup, get install hints
    extract-text extract FILE               one document, JSON to the screen
    extract-text scan DIR --out RESULTS     a folder of documents to a table
    extract-text review --out RESULTS       build the human review page
    extract-text review --out RESULTS --serve   review and save corrections
    extract-text score --out RESULTS        score the engines against the corrections

Run any of them with -h for the options. The library behind this is
importable from Python (`import extract_text`) and from R (the `extracttext`
package); the command exists so that none of that is required just to
process a folder.
"""

from __future__ import annotations

import argparse
import json
import sys


def cmd_doctor(args):
    from .doctor import run_doctor

    ready = run_doctor(model=args.model)
    return 0 if ready else 1


def cmd_extract(args):
    from . import extract

    result = extract(args.file, engine=args.engine, model=args.model)
    if args.engine == "both":
        payload = {
            "deterministic": result.deterministic.model_dump(mode="json"),
            "ai": result.ai.model_dump(mode="json"),
            "agreement_rate": result.comparison.agreement_rate,
            "needs_review": result.comparison.needs_review,
        }
    else:
        payload = result.model_dump(mode="json")
    json.dump(payload, sys.stdout, indent=2, default=str)
    print()
    return 0


def cmd_scan(args):
    from .pipeline import scan, write_review

    rows = scan(
        args.inputs,
        engine=args.engine,
        out_dir=args.out,
        model=args.model,
        limit=args.limit,
        sample=args.sample,
        seed=args.seed,
        recursive=not args.no_recursive,
        parquet=(True if args.parquet else None),
    )
    flagged = sum(1 for r in rows if r.get("flags"))
    found = sum(1 for r in rows if r.get("defendant_street"))
    print(f"\n{len(rows)} documents scanned, {found} with a defendant street "
          f"address, {flagged} flagged for review.", file=sys.stderr)
    print(f"Results in {args.out}/extracted.csv (and extracted.jsonl).",
          file=sys.stderr)
    if args.review:
        print("Building the review page...", file=sys.stderr)
        page = write_review(args.out, n=args.review_n)
        print(f"Review page: {page}", file=sys.stderr)
    else:
        print("Build the review page with: extract-text review --out "
              + str(args.out), file=sys.stderr)
    return 0


def cmd_review(args):
    from .pipeline import write_review

    if args.graders:
        page = write_review(args.out, seed=args.seed, graders=True)
    elif args.random:
        page = write_review(args.out, n=args.random, seed=args.seed, flagged_first=False)
    else:
        page = write_review(args.out, n=args.n, seed=args.seed)
    if args.serve:
        from .corrections import serve_review

        serve_review(args.out, port=args.port, open_browser=not args.no_open)
    else:
        print(f"Review page: {page}", file=sys.stderr)
    return 0


def cmd_score(args):
    from .score import report

    text = report(args.out, shapes=args.shapes)
    print(text)
    if args.save:
        from pathlib import Path

        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(text + "\n")
        print(f"Report saved to {args.save}", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="extract-text",
        description="Court record text extraction, deterministic and AI, local only.",
    )
    ap.add_argument("--version", action="store_true", help="print the version and exit")
    sub = ap.add_subparsers(dest="cmd")

    a = sub.add_parser("doctor", help="check the setup and say how to fix what is missing")
    a.add_argument("--model", default=None, help="AI model tag to check for")
    a.set_defaults(fn=cmd_doctor)

    a = sub.add_parser("extract", help="extract one document, JSON to stdout")
    a.add_argument("file")
    a.add_argument("--engine", choices=("deterministic", "ai", "both"),
                   default="deterministic")
    a.add_argument("--model", default=None, help="AI model tag (default qwen3.5:9b)")
    a.set_defaults(fn=cmd_extract)

    a = sub.add_parser("scan", help="extract a folder of documents into a table")
    a.add_argument("inputs", nargs="+", help="files and/or directories")
    a.add_argument("--out", required=True, help="output directory for results")
    a.add_argument("--engine", choices=("deterministic", "ai", "both"),
                   default="deterministic")
    a.add_argument("--model", default=None, help="AI model tag (default qwen3.5:9b)")
    a.add_argument("--limit", type=int, default=0, help="scan only the first N")
    a.add_argument("--sample", type=int, default=0, metavar="N",
                   help="scan N documents drawn at random from everything found")
    a.add_argument("--seed", type=int, default=42, help="seed for --sample")
    a.add_argument("--no-recursive", action="store_true",
                   help="do not descend into subdirectories")
    a.add_argument("--parquet", action="store_true",
                   help="require parquet output (needs pyarrow)")
    a.add_argument("--review", action="store_true",
                   help="also build the review page")
    a.add_argument("--review-n", type=int, default=30)
    a.set_defaults(fn=cmd_scan)

    a = sub.add_parser("review", help="build the human review page from a scan")
    a.add_argument("--out", required=True, help="the scan's output directory")
    a.add_argument("--n", type=int, default=30)
    a.add_argument("--seed", type=int, default=42)
    a.add_argument("--random", type=int, default=0, metavar="N",
                   help="show N documents drawn at random from the whole scan, "
                        "flagged or not, instead of flagged first")
    a.add_argument("--graders", action="store_true",
                   help="the graders' page: every document, worst first, name and "
                        "email recorded, each grader picks a batch size")
    a.add_argument("--serve", action="store_true",
                   help="open the page with correction saving on (this computer only)")
    a.add_argument("--port", type=int, default=8765)
    a.add_argument("--no-open", action="store_true",
                   help="with --serve, do not open a browser window")
    a.set_defaults(fn=cmd_review)

    a = sub.add_parser("score", help="score both engines against the saved corrections")
    a.add_argument("--out", required=True, help="the scan's output directory")
    a.add_argument("--shapes", action="store_true",
                   help="also print each wrong value in masked form")
    a.add_argument("--save", default=None, metavar="FILE",
                   help="also write the report to FILE (it holds no record values)")
    a.set_defaults(fn=cmd_score)

    args = ap.parse_args(argv)
    if args.version:
        from . import __version__

        print(__version__)
        return 0
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
