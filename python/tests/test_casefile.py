"""Case-file tests: folders of documents in, case outcomes out. All synthetic."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest

from extract_text import casefile
from extract_text.casefile import (
    CaseSummary,
    document_type,
    report,
    scan_cases,
    sheriff_return_status,
)
from extract_text.cli import main
from extract_text.documents import have

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

needs_system_tools = pytest.mark.skipif(
    not (have("pdftotext") and have("pdfinfo") and have("pdftoppm") and have("tesseract")),
    reason="poppler/tesseract not installed",
)

OUSTED = ("On March 3, 2025, I ousted and ejected, with the aid of the County, "
          "the defendant from possession of the premises described in said Writ "
          "of Restitution, and placed the plaintiff in possession of the premises.")
PEACEFUL = ("On March 3, 2025, I placed the plaintiff in peaceful possession of "
            "the above described premises.")
PER_ATTORNEY = ("At the request of the attorney for the plaintiff, on March 3, "
                "2025, I am returning said Writ of Restitution. Per the attorney, "
                "the defendants have moved.")
PER_PLAINTIFF = ("At the request of the plaintiff, on March 3, 2025, I am "
                 "returning said Writ of Restitution. Per the plaintiff, the "
                 "defendant has moved.")
EXPIRED = ("On March 3, 2025, I am returning said Writ of Restitution "
           "unsatisfied. The Sheriff's Office has not been contacted to schedule "
           "an eviction, and as of March 2, 2025, the Writ of Restitution has "
           "expired.")


@pytest.mark.parametrize("name, expected", [
    ("Summons.pdf", "summons"),
    ("SUMMONS_AND_COMPLAINT.pdf", "summons"),
    ("Complaint for Unlawful Detainer.pdf", "complaint"),
    ("Answer to Complaint.pdf", "answer"),
    ("notice-of-appearance.tif", "answer"),
    ("Motion for Default Judgment.pdf", "default_motion"),
    ("Order of Default.pdf", "default_motion"),
    ("Order of Dismissal.pdf", "dismissal"),
    ("motion_to_dismiss.pdf", "dismissal"),
    ("Judgment Summary.pdf", "judgment"),
    ("Judgement.pdf", "judgment"),
    ("Writ of Restitution.pdf", "writ"),
    ("Order for Writ.pdf", "writ"),
    ("Sheriff's Return Writ 2.pdf", "sheriff_return"),
    ("SheriffsReturn.pdf", "sheriff_return"),
    ("Return on Writ of Restitution.pdf", "sheriff_return"),
    ("Return of Service.pdf", "other"),
    ("Declaration of Mailing.pdf", "other"),
])
def test_document_type_from_file_name(name, expected):
    assert document_type(name) == expected


@pytest.mark.parametrize("text, expected", [
    (OUSTED, "ousted_ejected"),
    (PEACEFUL, "peaceful_possession"),
    (PER_ATTORNEY, "return_per_attorney"),
    (PER_PLAINTIFF, "return_per_plaintiff"),
    (EXPIRED, "expired"),
    ("SHERIFF'S RETURN\n\nOn March 3, 2025, I ousted\nand   ejected the defendant",
     "ousted_ejected"),
    (OUSTED + " " + PEACEFUL, "ambiguous"),
    ("a page the rules cannot read", "unread"),
    ("", "unread"),
])
def test_sheriff_return_status(text, expected):
    assert sheriff_return_status(text) == expected


def _case(*names, returns=()):
    return CaseSummary("c", [(n, document_type(n)) for n in names], list(returns))


def test_dismissal_alone_is_dismissed():
    c = _case("Summons.pdf", "Order of Dismissal.pdf")
    assert c.outcome == "dismissed" and c.flags == []


def test_dismissal_and_judgment_is_judgment():
    c = _case("Summons.pdf", "Motion to Dismiss.pdf", "Judgment.pdf")
    assert c.outcome == "judgment"
    assert "dismissal_and_judgment" in c.flags
    assert "judgment_no_sheriff_return" in c.flags


def test_default_motion_or_writ_counts_as_judgment():
    assert _case("Summons.pdf", "Motion for Default Judgment.pdf").outcome == "judgment"
    assert _case("Summons.pdf", "Writ of Restitution.pdf").outcome == "judgment"


def test_summons_alone_has_no_outcome():
    c = _case("Summons.pdf", "Complaint.pdf")
    assert c.outcome == "none_recorded" and c.sheriff_evicted is None


def test_missing_summons_is_flagged():
    assert "no_summons" in _case("Complaint.pdf").flags


def test_an_eviction_on_any_return_decides_the_case():
    names = ("Summons.pdf", "Judgment.pdf", "Sheriffs Return Writ 1.pdf",
             "Sheriffs Return Writ 2.pdf")
    c = _case(*names, returns=("ousted_ejected", "expired"))
    assert c.sheriff_return_status == "ousted_ejected" and c.sheriff_evicted is True
    c = _case(*names, returns=("expired", "return_per_plaintiff"))
    assert c.sheriff_return_status == "return_per_plaintiff"
    assert c.sheriff_evicted is False


def test_unread_return_is_flagged_not_guessed():
    c = _case("Summons.pdf", "Judgment.pdf", "Sheriffs Return.pdf", returns=("unread",))
    assert c.sheriff_evicted is None and "sheriff_return_unread" in c.flags


def _touch_case(root, case, *names):
    d = root / case
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_bytes(b"%PDF-1.4")
    return d


def test_scan_cases_rolls_up_folders_and_writes_tables(tmp_path, monkeypatch):
    src = tmp_path / "court_images"
    _touch_case(src, "case_a", "Summons.pdf", "Motion for Default Judgment.pdf",
                "Judgment.pdf", "Writ of Restitution.pdf", "Sheriffs Return.pdf")
    _touch_case(src, "case_b", "Summons.pdf", "Answer.pdf", "Order of Dismissal.pdf",
                "Declaration of Mailing.pdf")
    _touch_case(src, "case_c", "Summons.pdf")

    class _Doc:
        text = PEACEFUL

    monkeypatch.setattr(casefile, "load_document", lambda path, pages=None: _Doc())
    out = tmp_path / "results"
    cases = scan_cases(src, out_dir=out, progress=False)
    assert [c.outcome for c in cases] == ["judgment", "dismissed", "none_recorded"]

    with open(out / "cases.csv", newline="") as f:
        rows = {r["case_dir"]: r for r in csv.DictReader(f)}
    assert rows["case_a"]["sheriff_return_status"] == "peaceful_possession"
    assert rows["case_a"]["sheriff_evicted"] == "True"
    assert rows["case_a"]["has_default_motion"] == "True"
    assert rows["case_b"]["has_answer"] == "True"
    assert rows["case_b"]["n_untyped"] == "1"
    assert rows["case_c"]["sheriff_evicted"] == ""

    with open(out / "case_documents.csv", newline="") as f:
        docs = list(csv.DictReader(f))
    assert len(docs) == 10
    assert {"case_dir": "case_b", "file": "Answer.pdf", "doc_type": "answer"} in docs


def test_names_only_never_opens_a_document(tmp_path, monkeypatch):
    src = tmp_path / "court_images"
    _touch_case(src, "case_a", "Summons.pdf", "Judgment.pdf", "Sheriffs Return.pdf")

    def _boom(path, pages=None):
        raise AssertionError("a document was opened")

    monkeypatch.setattr(casefile, "load_document", _boom)
    (case,) = scan_cases(src, read_returns=False, progress=False)
    assert case.outcome == "judgment" and case.sheriff_return_status == ""


def test_report_is_counts_only(tmp_path, monkeypatch, capsys):
    src = tmp_path / "court_images"
    _touch_case(src, "25-2-00001-0", "Summons.pdf", "Judgment.pdf",
                "Sheriffs Return.pdf", "TENANT Declaration of Mailing.pdf")
    _touch_case(src, "25-2-00002-0", "Summons.pdf", "Order of Dismissal.pdf")

    class _Doc:
        text = EXPIRED

    monkeypatch.setattr(casefile, "load_document", lambda path, pages=None: _Doc())
    assert main(["cases", str(src), "--out", str(tmp_path / "results"),
                 "--save", str(tmp_path / "reports" / "cases.txt")]) == 0
    printed = capsys.readouterr().out
    assert "Cases: 2" in printed
    assert "declaration" in printed and "mailing" in printed
    # neither a folder name nor a word from a file name that is not on the list
    assert "00001" not in printed and "tenant" not in printed.lower()
    assert (tmp_path / "reports" / "cases.txt").read_text().strip() == printed.strip()
    assert report([]) == "No cases."


@needs_system_tools
def test_a_sheriffs_return_is_read_from_the_file(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "make_synthetic_fixtures", SCRIPTS / "make_synthetic_fixtures.py")
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    items = [
        (150, 64, 12, "SUPERIOR COURT OF WASHINGTON"),
        (190, 82, 12, "COUNTY OF SAMPLE"),
        (90, 120, 10, "EXAMPLE PROPERTY LLC, Plaintiff,"),
        (350, 120, 10, "Case No. 25-2-00001-0"),
        (90, 140, 10, "v."),
        (350, 140, 10, "SHERIFF'S RETURN ON WRIT OF RESTITUTION"),
        (90, 160, 10, "JANE Q. TENANT, Defendant."),
        (90, 240, 10, "On March 3, 2025, I ousted and ejected, with the aid of the"),
        (90, 258, 10, "County, the defendant from possession of the premises described"),
        (90, 276, 10, "in said Writ of Restitution, and placed the plaintiff in"),
        (90, 294, 10, "possession of the premises."),
    ]
    case = tmp_path / "court_images" / "case_a"
    case.mkdir(parents=True)
    (case / "Summons.pdf").write_bytes(b"%PDF-1.4")
    (case / "Sheriffs Return.pdf").write_bytes(fixtures.build_text_pdf(items))
    (summary,) = scan_cases(tmp_path / "court_images", progress=False)
    assert summary.sheriff_return_status == "ousted_ejected"
    assert summary.sheriff_evicted is True
