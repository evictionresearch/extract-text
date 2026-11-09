"""The `extract-text` command.

Five subcommands cover the whole workflow:

    extract-text doctor                     check the setup, get install hints
    extract-text extract FILE               one document, JSON to the screen
    extract-text scan DIR --out RESULTS     a folder of documents to a table
    extract-text review --out RESULTS       build the human review page
    extract-text review --out RESULTS --serve   review and save corrections
    extract-text score --out RESULTS        score the engines against the corrections
    extract-text agree --out RESULTS FILE   how often graders agree, and merging their answers
    extract-text import --out RESULTS FILE  answers downloaded from the graders' page, as corrections
    extract-text templates learn --out RESULTS   form templates from the graded documents' boxes
    extract-text templates review --templates DIR --out RESULTS   a page to check them on
    extract-text templates approve NAME --templates DIR           let the engine use one
    extract-text scan DIR --out RESULTS --templates DIR           read with the approved templates
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
from pathlib import Path


def cmd_doctor(args):
    from .doctor import run_doctor

    ready = run_doctor(model=args.model)
    return 0 if ready else 1


def cmd_extract(args):
    from . import extract

    kwargs = {"templates": args.templates} if args.templates else {}
    result = extract(args.file, engine=args.engine, model=args.model,
                     prompt_format=args.prompt, **kwargs)
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
        exclude=args.exclude,
        templates=args.templates,
    )
    flagged = sum(1 for r in rows if r.get("flags"))
    found = sum(1 for r in rows if r.get("defendant_street"))
    print(f"\n{len(rows)} documents scanned, {found} with a defendant street "
          f"address, {flagged} flagged for review.", file=sys.stderr)
    if args.templates:
        from collections import Counter

        by_form = Counter(r.get("template") or "(no template)" for r in rows)
        print("Form templates: " + ", ".join(f"{name} {n}" for name, n in by_form.most_common()),
              file=sys.stderr)
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

    pages = args.pages
    if args.rows and args.graders:
        page = write_review(args.out, seed=args.seed, graders=True, attorneys=args.attorneys,
                            order=args.order, overlap=args.overlap, rows=args.rows, pages=pages)
    elif args.rows:
        # the settling page adds the attorney box wherever a grader answered
        # it; asking on every card saved an unread box as "no attorney"
        page = write_review(args.out, seed=args.seed, attorneys=args.attorneys, rows=args.rows,
                            pages=pages)
    elif args.graders:
        page = write_review(args.out, seed=args.seed, graders=True, attorneys=args.attorneys,
                            order=args.order, overlap=args.overlap, pages=pages)
    elif args.random:
        page = write_review(args.out, n=args.random, seed=args.seed, flagged_first=False,
                            attorneys=args.attorneys, pages=pages)
    else:
        page = write_review(args.out, n=args.n, seed=args.seed, attorneys=args.attorneys, pages=pages)
    if args.serve:
        from .corrections import serve_review

        serve_review(args.out, port=args.port, open_browser=not args.no_open)
    else:
        print(f"Review page: {page}", file=sys.stderr)
    return 0


def cmd_score(args):
    if getattr(args, "where", False):
        from .score import where_report

        text = where_report(args.out)
        print(text)
        if getattr(args, "save", None):
            with open(args.save, "w") as f:
                f.write(text + "\n")
        return 0
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


def cmd_import(args):
    from pathlib import Path

    from .corrections import import_answers

    for path in args.files:
        dest, n = import_answers(args.out, path)
        print(f"{n} answers from {Path(path).name} written to {dest}", file=sys.stderr)
    return 0


def _presets():
    from .address_check import PRESETS

    return PRESETS


def cmd_check_addresses(args):
    from .address_check import AddressList, check_scan, evaluation, summary

    if args.preset:
        addresses = AddressList.from_preset(args.reference, args.preset)
    elif args.street:
        addresses = AddressList.from_csv(args.reference, street=args.street, zip=args.zip,
                                         city=args.city)
    else:
        print("give --preset, or --street (and --zip, --city) naming the list's columns",
              file=sys.stderr)
        return 2
    results = check_scan(args.out, addresses, min_similarity=args.min_similarity)
    # counts only; the suggestions themselves are in address_check.csv
    print(summary(results))
    report = evaluation(args.out, results)
    if report:
        print(report)
    print(f"Details: {Path(args.out) / 'address_check.csv'}", file=sys.stderr)
    return 0


def cmd_templates(args):
    from .templates import (
        DEFAULT_DIR,
        approve_template,
        learn_templates,
        load_templates,
        write_templates_review,
    )

    if args.what == "learn":
        written, text = learn_templates(args.out, args.templates, min_pages=args.min_pages,
                                        rows=args.rows, name=args.name)
        print(text)
        if written:
            tdir = args.templates or str(Path(args.out) / DEFAULT_DIR)
            page = write_templates_review(tdir, args.out)
            print(f"Review page: {page}", file=sys.stderr)
        return 0
    if args.what == "review":
        page = write_templates_review(args.templates, args.out)
        print(f"Review page: {page}", file=sys.stderr)
        return 0
    if args.what == "approve":
        path = approve_template(args.name, args.templates, approved=not args.withdraw)
        print(f"{'Withdrawn' if args.withdraw else 'Approved'}: {path}", file=sys.stderr)
        return 0
    if args.what == "list":
        found = load_templates(args.templates, approved_only=False)
        if not found:
            print(f"No templates in {args.templates}")
        for t in found:
            regions = ", ".join(k for k in t.regions)
            print(f"{t.name:<20}{'approved' if t.approved else 'not approved':<14}"
                  f"{t.pages:>3} pages  {len(t.fingerprint):>4} words  regions: {regions or 'none'}")
        return 0
    return 2


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
    a.add_argument("--templates", default=None, metavar="DIR",
                   help="a folder of approved form templates, read first on pages that match")
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
    a.add_argument("--exclude", action="append", default=None, metavar="DIR",
                   help="skip every document of that earlier scan, by path and by "
                        "content (repeatable), so a new round never repeats one")
    a.add_argument("--no-recursive", action="store_true",
                   help="do not descend into subdirectories")
    a.add_argument("--parquet", action="store_true",
                   help="require parquet output (needs pyarrow)")
    a.add_argument("--review", action="store_true",
                   help="also build the review page")
    a.add_argument("--review-n", type=int, default=30)
    a.add_argument("--templates", default=None, metavar="DIR",
                   help="a folder of approved form templates (extract-text templates), "
                        "read first on pages that match one")
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
    a.add_argument("--pages", type=int, default=1, metavar="N",
                   help="render the first N pages of each document when building the page "
                        "(default 1). Served, every other page is rendered when a reviewer "
                        "turns to it; opened as a file (the graders' page) only rendered "
                        "pages can be shown")
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
    a.add_argument("--where", action="store_true",
                   help="for each document whose street the deterministic engine got wrong, "
                        "say whether the graders' street is in the document's text at all "
                        "(a rule failure) or not (an OCR failure); reads every such document again")
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

    a = sub.add_parser("import", help="turn the answers a grader downloaded from the "
                                      "graders' page into a corrections file")
    a.add_argument("--out", required=True, help="the scan folder the page was built from")
    a.add_argument("files", nargs="+", metavar="FILE",
                   help="the graders' answers_NAME_FOLDER.jsonl files")
    a.set_defaults(fn=cmd_import)

    a = sub.add_parser("check-addresses",
                       help="check a scan's addresses against a list of real addresses")
    a.add_argument("--out", required=True, help="the scan's output directory")
    a.add_argument("--reference", required=True, metavar="CSV",
                   help="a CSV of the addresses that exist, e.g. a county's address points")
    a.add_argument("--preset", default=None,
                   help="column names of a known list: " + ", ".join(sorted(_presets())))
    a.add_argument("--street", default=None, help="column with house number and street")
    a.add_argument("--zip", default=None, help="column with the ZIP code")
    a.add_argument("--city", default=None, help="column with the city")
    a.add_argument("--min-similarity", type=float, default=0.8,
                   help="how alike a listed street must be to be suggested (0 to 1)")
    a.set_defaults(fn=cmd_check_addresses)

    a = sub.add_parser("templates", help="form templates: where a form prints each field, "
                                         "learned from graded documents' boxes, no code")
    what = a.add_subparsers(dest="what", required=True)
    b = what.add_parser("learn", help="learn templates from a scan's graded documents")
    b.add_argument("--out", required=True, help="the scan folder with corrections.jsonl")
    b.add_argument("--templates", default=None, metavar="DIR",
                   help="where to write them (default: templates/ inside the scan folder)")
    b.add_argument("--min-pages", type=int, default=5, metavar="N",
                   help="pages a form needs before a template is written (default 5)")
    b.add_argument("--rows", type=_row_list, default=None, metavar="N,N,...",
                   help="learn from these graded documents only")
    b.add_argument("--name", default=None,
                   help="with --rows: treat them as one form and give its template this name")
    b = what.add_parser("review", help="build the page that shows each template over a page")
    b.add_argument("--templates", required=True, metavar="DIR")
    b.add_argument("--out", default=None, help="the scan folder they were learned from, "
                                                "to show a learned page under the regions")
    b = what.add_parser("approve", help="let the engine use a template")
    b.add_argument("name", help="the template's name (its file name without .json)")
    b.add_argument("--templates", required=True, metavar="DIR")
    b.add_argument("--withdraw", action="store_true", help="take the approval back")
    b = what.add_parser("list", help="the templates in a folder and their status")
    b.add_argument("--templates", required=True, metavar="DIR")
    a.set_defaults(fn=cmd_templates)

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
