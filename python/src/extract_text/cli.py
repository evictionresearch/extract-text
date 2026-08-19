"""The `extract-text` command.

Four subcommands cover the whole workflow:

    extract-text doctor                     check the setup, get install hints
    extract-text extract FILE               one document, JSON to the screen
    extract-text scan DIR --out RESULTS     a folder of documents to a table
    extract-text review --out RESULTS       build the human review page

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
        page = write_review(args.out, n=args.review_n)
        print(f"Review page: {page}", file=sys.stderr)
    else:
        print("Build the review page with: extract-text review --out "
              + str(args.out), file=sys.stderr)
    return 0


def cmd_review(args):
    from .pipeline import write_review

    page = write_review(args.out, n=args.n, seed=args.seed)
    print(f"Review page: {page}", file=sys.stderr)
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
    a.set_defaults(fn=cmd_review)

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
