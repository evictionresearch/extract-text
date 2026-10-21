"""The `extract-text` command.

Five subcommands cover the whole workflow:

    extract-text doctor                     check the setup, get install hints
    extract-text extract FILE               one document, JSON to the screen
    extract-text scan DIR --out RESULTS     a folder of documents to a table
    extract-text review --out RESULTS       build the human review page
    extract-text review --out RESULTS --serve   review and save corrections
    extract-text score --out RESULTS        score the engines against the corrections
    extract-text agree --out RESULTS FILE   how often graders agree, and merging their answers
    extract-text cases DIR --out RESULTS    roll case folders up to their outcomes

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

    result = extract(args.file, engine=args.engine, model=args.model,
                     prompt_format=args.prompt)
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
        prompt_format=args.prompt,
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


def _count_or_all(value):
    if value == "all":
        return value
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("a number of documents, or 'all'")


def _row_list(value):
    try:
        return [int(v) for v in value.split(",") if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError("document numbers separated by commas, e.g. 12,57")


def cmd_review(args):
    from .pipeline import write_review

    if args.rows and args.graders:
        page = write_review(args.out, seed=args.seed, graders=True, attorneys=args.attorneys,
                            order=args.order, overlap=args.overlap, rows=args.rows)
    elif args.rows:
        # the settling page adds the attorney box wherever a grader answered
        # it; asking on every card saved an unread box as "no attorney"
        page = write_review(args.out, seed=args.seed, attorneys=args.attorneys, rows=args.rows)
    elif args.graders:
        page = write_review(args.out, seed=args.seed, graders=True, attorneys=args.attorneys,
                            order=args.order, overlap=args.overlap)
    elif args.random:
        page = write_review(args.out, n=args.random, seed=args.seed, flagged_first=False,
                            attorneys=args.attorneys)
    else:
        page = write_review(args.out, n=args.n, seed=args.seed, attorneys=args.attorneys)
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


def cmd_agree(args):
    from .agree import merge, report

    text = report(args.out, args.files)
    print(text)
    if args.save:
        from pathlib import Path

        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(text + "\n")
        print(f"Report saved to {args.save}", file=sys.stderr)
    if args.merge:
        added = merge(args.out, args.files)
        print(f"Merged {added} answers into {args.out}/corrections.jsonl "
              "(every grader's answer kept).", file=sys.stderr)
    return 0


def cmd_cases(args):
    from .casefile import report, scan_cases

    cases = scan_cases(args.inputs, out_dir=args.out,
                       read_returns=not args.names_only,
                       recursive=not args.no_recursive)
    text = report(cases)
    print(text)
    if args.save:
        from pathlib import Path

        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(text + "\n")
        print(f"Report saved to {args.save}", file=sys.stderr)
    print(f"Results in {args.out}/cases.csv (and case_documents.csv).",
          file=sys.stderr)
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
    a.add_argument("--prompt", choices=("lists", "v1"), default="lists",
                   help="AI engine prompt: lists (default) or v1, the original")
    a.set_defaults(fn=cmd_extract)

    a = sub.add_parser("scan", help="extract a folder of documents into a table")
    a.add_argument("inputs", nargs="+", help="files and/or directories")
    a.add_argument("--out", required=True, help="output directory for results")
    a.add_argument("--engine", choices=("deterministic", "ai", "both"),
                   default="deterministic")
    a.add_argument("--model", default=None, help="AI model tag (default qwen3.5:9b)")
    a.add_argument("--prompt", choices=("lists", "v1"), default="lists",
                   help="AI engine prompt: lists (default) or v1, the original")
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
    a.add_argument("--order", choices=("worst", "random"), default="worst",
                   help="with --graders: 'worst' shows the documents most in need of a "
                        "person first (finds failures); 'random' serves them in random "
                        "order, so what gets graded measures accuracy")
    a.add_argument("--overlap", type=int, default=0, metavar="N",
                   help="with --graders: put the same N documents, drawn at random, first "
                        "for every grader, so `extract-text agree` can compare their answers")
    a.add_argument("--rows", type=_row_list, default=None, metavar="N,N,...",
                   help="a page of just these document numbers, showing every grader's "
                        "answer, for settling disagreements; with --graders, a blind "
                        "graders' page of just these documents that records each name")
    a.add_argument("--attorneys", type=_count_or_all, default=0, metavar="N",
                   help="also ask for the plaintiff's attorney on N documents drawn at "
                        "random (the same documents for every grader of a folder), or 'all'")
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

    a = sub.add_parser("agree", help="how often graders agree on the documents they shared")
    a.add_argument("--out", required=True, help="the scan's output directory")
    a.add_argument("files", nargs="*", metavar="FILE",
                   help="graders' returned corrections_NAME.jsonl files")
    a.add_argument("--merge", action="store_true",
                   help="also add every grader's answers to the scan's corrections.jsonl")
    a.add_argument("--save", default=None, metavar="FILE",
                   help="also write the report to FILE (it holds no record values)")
    a.set_defaults(fn=cmd_agree)

    a = sub.add_parser("cases", help="roll case folders up to their outcomes")
    a.add_argument("inputs", nargs="+", help="directories of case folders")
    a.add_argument("--out", required=True, help="output directory for results")
    a.add_argument("--names-only", action="store_true",
                   help="type documents by file name and stop; do not open "
                        "the sheriff's returns")
    a.add_argument("--no-recursive", action="store_true",
                   help="do not descend into subdirectories")
    a.add_argument("--save", default=None, metavar="FILE",
                   help="also write the report to FILE (it holds counts only)")
    a.set_defaults(fn=cmd_cases)

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
