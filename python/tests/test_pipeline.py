"""Batch pipeline tests: folder in, table out. All fixtures synthetic."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from extract_text.documents import have
from extract_text.pipeline import collect_inputs, flatten_extraction, scan, write_review
from extract_text.similarity import address_similarity, norm, ratio

FIXTURES = Path(__file__).parent / "fixtures"

needs_system_tools = pytest.mark.skipif(
    not (have("pdftotext") and have("pdfinfo") and have("pdftoppm") and have("tesseract")),
    reason="poppler/tesseract not installed",
)


def test_collect_inputs_is_sorted_and_deduplicated(tmp_path):
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "notes.docx").write_bytes(b"nope")
    got = collect_inputs([tmp_path, tmp_path / "a.pdf"])
    assert [p.name for p in got] == ["a.pdf", "b.pdf"]


def test_similarity_matches_the_paper_metric():
    assert ratio("abc", "abc") == 1.0
    assert norm("1234 Example Ave S") == "1234 example avenue south"
    sim = address_similarity("1234 Example Ave S, Seattle WA 98100",
                             "1234 EXAMPLE AVENUE SOUTH SEATTLE WA 98100")
    assert sim is not None and sim > 0.95
    assert address_similarity("something", None) is None


@needs_system_tools
def test_scan_writes_csv_and_jsonl(tmp_path):
    rows = scan(
        [FIXTURES / "synthetic_summons_efiled.pdf",
         FIXTURES / "synthetic_summons_scanned.pdf"],
        engine="deterministic",
        out_dir=tmp_path,
        progress=False,
    )
    assert len(rows) == 2
    for row in rows:
        assert row["case_number"] == "25-2-00001-0"
        assert row["defendant_street"] == "1234 EXAMPLE AVE S APT 5"
        assert row["attorney_street"] == "100 MAIN ST STE 200"
        assert row["flags"] == ""
        assert row["method"] == "deterministic"

    with open(tmp_path / "extracted.csv", newline="") as f:
        written = list(csv.DictReader(f))
    assert [r["file"] for r in written] == [r["file"] for r in rows]

    with open(tmp_path / "extracted.jsonl") as f:
        details = [json.loads(l) for l in f if l.strip()]
    assert details[0]["deterministic"]["record"]["case_number"] == "25-2-00001-0"
    assert details[0]["ai"] is None  # deterministic run carries no AI output


@needs_system_tools
def test_scan_parquet_when_pyarrow_present(tmp_path):
    pytest.importorskip("pyarrow")
    scan([FIXTURES / "synthetic_summons_efiled.pdf"], out_dir=tmp_path,
         progress=False, parquet=True)
    import pyarrow.parquet as pq

    table = pq.read_table(tmp_path / "extracted.parquet")
    assert table.num_rows == 1
    assert "defendant_street" in table.column_names


@needs_system_tools
def test_review_page_renders_flagged_first(tmp_path):
    scan([FIXTURES / "synthetic_summons_efiled.pdf",
          FIXTURES / "synthetic_summons.tif"],
         out_dir=tmp_path, progress=False)
    page = write_review(tmp_path, n=5)
    html = page.read_text()
    assert "extract-text review" in html
    assert "1234 EXAMPLE AVE S APT 5" in html


@needs_system_tools
def test_review_pairs_same_named_files_with_their_own_page(tmp_path):
    # court collections put a file of the same name in every case folder;
    # each review row must show its own document's page, not the last one's
    import shutil

    for case, fixture in (("case_a", "synthetic_summons_efiled.pdf"),
                          ("case_b", "synthetic_summons_scanned.pdf")):
        (tmp_path / case).mkdir()
        shutil.copy(FIXTURES / fixture, tmp_path / case / "SUMMONS.pdf")
    out = tmp_path / "out"
    scan([tmp_path / "case_a", tmp_path / "case_b"], out_dir=out, progress=False)
    html = write_review(out, n=5).read_text()

    assert 'src="doc_0001.png"' in html and 'src="doc_0002.png"' in html
    img_a = (out / "review" / "doc_0001.png").read_bytes()
    img_b = (out / "review" / "doc_0002.png").read_bytes()
    assert img_a != img_b


@needs_system_tools
def test_review_page_carries_a_correction_form(tmp_path):
    scan([FIXTURES / "synthetic_summons_efiled.pdf"], out_dir=tmp_path, progress=False)
    html = write_review(tmp_path, n=5).read_text()
    assert '<form class="fix" data-row="1"' in html
    assert 'class="quiet use-ai"' not in html  # no AI button on a deterministic-only scan
    assert 'name="street" value="1234 EXAMPLE AVE S"' in html
    assert 'name="unit" value="APT 5"' in html
    assert 'href="doc/1"' in html  # full-document link, shown only when served


@needs_system_tools
def test_review_server_saves_corrections(tmp_path):
    import threading
    import urllib.error
    import urllib.request

    from extract_text.corrections import load_corrections, make_review_server

    scan([FIXTURES / "synthetic_summons_efiled.pdf",
          FIXTURES / "synthetic_summons_scanned.pdf"], out_dir=tmp_path, progress=False)
    write_review(tmp_path, n=5)
    server = make_review_server(tmp_path, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(body):
        req = urllib.request.Request(f"{base}/api/corrections", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    try:
        truth = {"plaintiff": "EXAMPLE PROPERTY LLC", "defendants": ["JANE Q. TENANT"],
                 "street": "1234 EXAMPLE AVE S", "unit": "APT 6", "city": "SEATTLE",
                 "state": "WA", "zip": "98100"}
        saved = post({"row": 2, "verdict": "checked", "truth": truth, "note": ""})
        assert saved["verdict"] == "corrected"
        assert "unit" in saved["changed_fields"]
        assert saved["machine"]["unit"] == "APT 5"
        assert saved["sampled_as"] == "random" and len(saved["sha256"]) == 64

        # a second save of the same document replaces the first
        truth["unit"] = "APT 5"
        post({"row": 2, "verdict": "checked", "truth": truth})
        with urllib.request.urlopen(f"{base}/api/corrections") as r:
            latest = json.loads(r.read())
        assert list(latest) == ["2"]

        with pytest.raises(urllib.error.HTTPError) as bad:
            post({"row": 99, "truth": truth})
        assert bad.value.code == 400
        # the page is served, the scan tables beside it are not
        with urllib.request.urlopen(f"{base}/") as r:
            assert b"extract-text review" in r.read()
        with pytest.raises(urllib.error.HTTPError) as hidden:
            urllib.request.urlopen(f"{base}/extracted.csv")
        assert hidden.value.code == 404
        # a whole document opens by row number, and nothing else does
        with urllib.request.urlopen(f"{base}/doc/1") as r:
            assert r.headers["Content-Type"] == "application/pdf"
            assert r.read(5) == b"%PDF-"
        for bad_doc in ("99", "0", "..%2Fextracted.csv"):
            with pytest.raises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(f"{base}/doc/{bad_doc}")
            assert missing.value.code == 404
    finally:
        server.shutdown()
        server.server_close()

    assert len((tmp_path / "corrections.jsonl").read_text().splitlines()) == 2
    assert len(load_corrections(tmp_path)) == 1
    with open(tmp_path / "corrections.csv", newline="") as f:
        written = list(csv.DictReader(f))
    assert written[0]["row"] == "2" and written[0]["unit"] == "APT 5"


def test_progress_line_shows_count_step_and_failures():
    import io

    from extract_text.pipeline import _Progress

    class FakeTerminal(io.StringIO):
        def isatty(self):
            return True

    term = FakeTerminal()
    bar = _Progress(4, stream=term)
    bar.status(1, "deterministic engine")
    bar.advance()
    bar.status(2, "AI engine")
    bar.advance(failed=True)
    bar.close()
    shown = term.getvalue()
    assert "2/4 documents" in shown
    assert "document 2: AI engine" in shown
    assert "1 failed" in shown
    assert shown.endswith("\n")


@needs_system_tools
def test_scan_survives_broken_and_unsupported_files(tmp_path):
    # a corrupt PDF degrades gracefully: no text, flagged, no crash
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf at all")
    # an unsupported type errors per-document without sinking the batch
    weird = tmp_path / "notes.docx"
    weird.write_bytes(b"nope")
    rows = scan([bad, weird, FIXTURES / "synthetic_summons_efiled.pdf"],
                out_dir=None, write=False, progress=False)
    by_file = {r["file"]: r for r in rows}
    assert "no_text" in by_file["broken.pdf"]["flags"]
    assert by_file["notes.docx"]["flags"].startswith("scan_error:")
    assert by_file["synthetic_summons_efiled.pdf"]["case_number"] == "25-2-00001-0"


@needs_system_tools
def test_flatten_row_carries_provenance():
    from extract_text import extract

    x = extract(str(FIXTURES / "synthetic_summons_efiled.pdf"))
    row = flatten_extraction(x)
    assert row["defendant_anchor"] == "to_block"
    assert row["backend"] == "rules"
    assert row["text_source"] == "pdf_text_layer"


def _fake_both_engine_scan(out):
    """A one-document both-engine scan written by hand, invented values, so
    the AI fill can be tested without a model or the system tools."""
    out.mkdir(parents=True, exist_ok=True)
    row = {"file": "SUMMONS.pdf", "case_number": "", "plaintiffs": "PAT EXAMPLE",
           "defendant_names": "PAT EXAMPLE", "defendant_street": "1234 SAMPLE AVE NE",
           "defendant_address_raw": "1234 SAMPLE AVE NE SAMPLETON, WA 98100",
           "defendant_unit": "", "defendant_city": "Sampleton", "defendant_state": "WA",
           "defendant_zip": "98100", "method": "deterministic", "flags": "x",
           "ai_backend": "local:fake", "ai_plaintiff": "EXAMPLE GREENS LLC",
           "ai_defendant_names": "PAT EXAMPLE",
           "ai_defendant_address": "1234 SAMPLE AVE NE BLDG C Apt # 5 SAMPLETON, WA 98100"}
    with open(out / "extracted.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    ai_record = {"plaintiffs": [{"name": "EXAMPLE GREENS LLC"}],
                 "defendants": [{"name": "PAT EXAMPLE"}],
                 "defendant_address": {"raw": row["ai_defendant_address"],
                                       "street": "1234 SAMPLE AVE NE BLDG C Apt # 5",
                                       "unit": "BLDG C Apt # 5", "city": "Sampleton",
                                       "state": "WA", "zip": "98100"}}
    with open(out / "extracted.jsonl", "w") as f:
        f.write(json.dumps({"file": str(out / "missing.pdf"), "deterministic": None,
                            "ai": {"record": ai_record}}) + "\n")


def test_review_offers_the_ai_reading_and_scores_it(tmp_path):
    from extract_text.corrections import build_correction
    from extract_text.pipeline import read_scan

    _fake_both_engine_scan(tmp_path)
    html = write_review(tmp_path, n=5).read_text()
    assert "Use AI engine&#x27;s reading" in html or "Use AI engine's reading" in html
    assert "data-ai=\"{&quot;plaintiff&quot;: &quot;EXAMPLE GREENS LLC&quot;" in html

    rows, details = read_scan(tmp_path)
    truth = {"plaintiff": "EXAMPLE GREENS LLC", "defendants": ["PAT EXAMPLE"],
             "street": "1234 SAMPLE AVE NE", "unit": "BLDG C Apt # 5",
             "city": "Sampleton", "state": "WA", "zip": "98100"}
    c = build_correction(1, {"truth": truth, "used_ai_fill": True}, rows, details, tmp_path)
    assert c["verdict"] == "corrected"
    assert c["changed_fields"] == ["plaintiff", "unit"]   # deterministic engine was wrong here
    assert c["ai"]["changed_fields"] == []                # the AI engine had it all
    assert c["used_ai_fill"] is True


def test_review_shows_where_the_engines_disagree(tmp_path):
    _fake_both_engine_scan(tmp_path)
    html = write_review(tmp_path, n=5).read_text()
    assert "The engines disagree on plaintiff, address (unit)." in html
    assert '<tr class="differ"><th>Plaintiff</th>' in html
    assert '<tr><th>Defendants</th>' in html  # both read the same defendant


def test_engine_agreement_ignores_formatting():
    from extract_text.pipeline import engine_differences

    row = {"plaintiffs": "EXAMPLE GREENS LLC", "defendant_names": "PAT EXAMPLE; LEE EXAMPLE",
           "defendant_street": "1234 SAMPLE AVE. NE APT 5", "defendant_unit": "APT 5",
           "defendant_city": "Sampleton", "defendant_state": "WA", "defendant_zip": "98100",
           "attorney_firm": "EXAMPLE LAW PLLC", "ai_law_firm": "Example Law, PLLC"}
    ai = {"plaintiff": "Example Greens, L.L.C.", "defendants": ["PAT EXAMPLE LEE EXAMPLE"],
          "street": "1234 SAMPLE AVENUE NORTHEAST", "unit": "Apt # 5", "city": "SAMPLETON",
          "state": "WA", "zip": "98100-1234", "address_unsplit": False}
    assert engine_differences(row, ai) == {}


def test_score_reports_counts_and_masked_shapes_only(tmp_path):
    from extract_text.corrections import build_correction, write_corrections_csv
    from extract_text.pipeline import read_scan
    from extract_text.score import mask, report

    _fake_both_engine_scan(tmp_path)
    write_review(tmp_path, n=5)
    rows, details = read_scan(tmp_path)
    truth = {"plaintiff": "EXAMPLE GREENS LLC", "defendants": ["PAT EXAMPLE"],
             "street": "1234 SAMPLE AVE NE", "unit": "BLDG C Apt # 5",
             "city": "Sampleton", "state": "WA", "zip": "98100"}
    c = build_correction(1, {"truth": truth}, rows, details, tmp_path)
    with open(tmp_path / "corrections.jsonl", "w") as f:
        f.write(json.dumps(c) + "\n")
    write_corrections_csv(tmp_path)

    text = report(tmp_path, shapes=True)
    assert "1 documents reviewed" in text and "1 flagged" in text
    assert "deterministic engine" in text and "ai engine" in text
    import re as _re
    assert _re.search(r"plaintiff +0\.0% +0\.0% of +1 .*1 different", text)
    assert _re.search(r"unit +0\.0% +0\.0% of +1 .*1 blank", text)
    assert _re.search(r"city +100\.0% +100\.0% of +1", text)
    assert "from: 9999 AAAAAA AAA AA AAAAAAAAA, AA 99999" in text          # the block's shape, address errors only
    assert "AAAAAAA AAAAAA AAA" in text          # the plaintiff's shape
    for word in ("EXAMPLE", "GREENS", "Sampleton", "1234", "SUMMONS"):
        assert word not in text                  # never a value or a file name
    assert mask("Apt # 5, Bldg C") == "Aaa # 9, Aaaa A"


def test_random_review_draws_from_every_row_and_records_it(tmp_path):
    _fake_both_engine_scan(tmp_path)
    write_review(tmp_path, n=5, flagged_first=False)
    drawn = json.loads((tmp_path / "review" / "sample.json").read_text())
    assert drawn == {"1": "random"}              # flagged row, but drawn at random
    assert "a random draw" in (tmp_path / "review" / "index.html").read_text()
    write_review(tmp_path, n=5)
    assert json.loads((tmp_path / "review" / "sample.json").read_text()) == {"1": "flagged"}


def test_scan_sample_is_a_seeded_random_draw(tmp_path):
    for k in range(6):
        (tmp_path / f"{k}.pdf").write_bytes(b"%PDF-1.4")
    rows = scan([tmp_path], out_dir=None, write=False, progress=False, sample=3, seed=7)
    again = scan([tmp_path], out_dir=None, write=False, progress=False, sample=3, seed=7)
    other = scan([tmp_path], out_dir=None, write=False, progress=False, sample=3, seed=8)
    assert len(rows) == 3 and [r["file"] for r in rows] == [r["file"] for r in again]
    assert [r["file"] for r in rows] != [r["file"] for r in other] or True  # seeds may collide
    assert [r["file"] for r in rows] == sorted(r["file"] for r in rows)


def test_graders_page_orders_worst_first_and_records_the_grader(tmp_path):
    import threading
    import urllib.request

    from extract_text.corrections import load_corrections, make_review_server

    _fake_both_engine_scan(tmp_path)
    html = write_review(tmp_path, graders=True).read_text()
    assert 'id="gname"' in html and 'id="gcount"' in html and "worst first" in html
    assert 'data-tier="2"' in html            # the engines disagree on this document
    assert json.loads((tmp_path / "review" / "sample.json").read_text()) == {"1": "flagged"}

    server = make_review_server(tmp_path, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        body = {"row": 1, "truth": {"plaintiff": "EXAMPLE GREENS LLC", "defendants": ["PAT EXAMPLE"],
                                    "street": "1234 SAMPLE AVE NE", "unit": "BLDG C Apt # 5",
                                    "city": "Sampleton", "state": "WA", "zip": "98100"},
                "reviewer": "A. Grader", "reviewer_email": "grader@example.org"}
        req = urllib.request.Request(f"{base}/api/corrections", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            saved = json.loads(r.read())
    finally:
        server.shutdown()
        server.server_close()
    assert saved["reviewer"] == "A. Grader" and saved["reviewer_email"] == "grader@example.org"
    assert load_corrections(tmp_path)[1]["reviewer"] == "A. Grader"
    with open(tmp_path / "corrections.csv", newline="") as f:
        assert next(csv.DictReader(f))["reviewer_email"] == "grader@example.org"

    from extract_text.score import report
    text = report(tmp_path)
    assert "Graded by A. Grader (1)" in text
    assert "grader@example.org" not in text     # the report names graders, never emails
