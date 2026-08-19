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
