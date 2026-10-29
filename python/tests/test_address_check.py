"""The address check. The list and every address here are invented."""

from __future__ import annotations

import csv

from extract_text.address_check import AddressList, check_scan, summary


def _list(tmp_path):
    path = tmp_path / "points.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["FULL", "ZIP", "CITY"])
        w.writerow(["1234 EXAMPLE AVE S", "98100", "SAMPLETON"])
        w.writerow(["1234 SAMPLE AVE S", "98100", "SAMPLETON"])
        w.writerow(["5678 EXAMPLE WAY", "98101", "SAMPLETON"])
        w.writerow(["12345 SE 999TH PL", "98102", "OTHERTON"])
    return AddressList.from_csv(path, street="FULL", zip="ZIP", city="CITY")


def test_match_near_and_no_match(tmp_path):
    al = _list(tmp_path)
    assert al.n == 4
    # spelled out, standardized to the listed form
    got = al.check("1234 Example Avenue South", "Apt 5", "Sampleton", "WA", "98100")
    assert got["address_check"] == "match"
    # an OCR slip, at the same house number in the same ZIP code
    got = al.check("1234 EXAMPLF AVE S", "APT 5", "Sampleton", "WA", "98100")
    assert got["address_check"] == "near"
    assert got["address_suggested"] == "1234 EXAMPLE AVE S APT 5, SAMPLETON, WA 98100"
    # the right street under the wrong ZIP code: suggested with the listed one
    got = al.check("5678 EXAMPLE WAY", None, "Sampleton", "WA", "98100")
    assert got["address_check"] == "near" and got["address_suggested"].endswith("WA 98101")
    # a numbered street run into the house number
    assert al.check("12345-999TH PL SE", None, "Otherton", "WA", "98102")["address_check"] == "no_match"
    assert al.check("12345 SE 999TH PL", None, "Otherton", "WA", "98102")["address_check"] == "match"
    # nothing listed at that number
    assert al.check("9999 EXAMPLE AVE S", None, "Sampleton", "WA", "98100")["address_check"] == "no_match"
    # nothing to check
    assert al.check("", None, None, None, None)["address_check"] == ""


def test_a_tie_is_not_suggested(tmp_path):
    al = _list(tmp_path)
    # XAMPLE is one edit from both EXAMPLE and SAMPLE, so neither is offered
    got = al.check("1234 XAMPLE AVE S", None, "Sampleton", "WA", "98100")
    assert got["address_check"] == "no_match" and got["address_suggested"] == ""


def test_check_scan_writes_one_row_per_document_and_counts_only(tmp_path):
    al = _list(tmp_path)
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    rows = [{"file": "a.pdf", "defendant_street": "1234 EXAMPLE AVE S", "defendant_unit": "",
             "defendant_city": "SAMPLETON", "defendant_state": "WA", "defendant_zip": "98100"},
            {"file": "b.pdf", "defendant_street": "", "defendant_unit": "",
             "defendant_city": "", "defendant_state": "", "defendant_zip": ""}]
    with open(scan_dir / "extracted.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (scan_dir / "extracted.jsonl").write_text("{}\n{}\n")
    results = check_scan(scan_dir, al)
    assert [r["doc"] for r in results] == [1, 2]
    assert [r["address_check"] for r in results] == ["match", ""]
    assert (scan_dir / "address_check.csv").exists()
    text = summary(results)
    assert text == "Address check, 2 documents: 1 match, 1 not checked"
    assert "EXAMPLE" not in text


def test_evaluation_counts_against_corrections(tmp_path):
    import json

    from extract_text.address_check import evaluation

    al = _list(tmp_path)
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    rows = [  # read right; read with an OCR slip; read, but the document had none
        {"defendant_street": "1234 EXAMPLE AVE S", "defendant_unit": "", "defendant_city": "SAMPLETON",
         "defendant_state": "WA", "defendant_zip": "98100"},
        {"defendant_street": "1234 EXAMPLF AVE S", "defendant_unit": "", "defendant_city": "SAMPLETON",
         "defendant_state": "WA", "defendant_zip": "98100"},
        {"defendant_street": "5678 EXAMPLE WAY", "defendant_unit": "", "defendant_city": "SAMPLETON",
         "defendant_state": "WA", "defendant_zip": "98101"},
    ]
    with open(scan_dir / "extracted.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (scan_dir / "extracted.jsonl").write_text("{}\n{}\n{}\n")
    assert evaluation(scan_dir, check_scan(scan_dir, al, write=False)) is None

    truths = ["1234 Example Avenue South", "1234 EXAMPLE AVE S", ""]
    with open(scan_dir / "corrections.jsonl", "w") as f:
        for i, street in enumerate(truths, 1):
            f.write(json.dumps({"row": i, "verdict": "checked", "truth": {"street": street}}) + "\n")
    text = evaluation(scan_dir, check_scan(scan_dir, al, write=False))
    assert text.startswith("Against 3 corrected documents")
    match_line = next(line for line in text.splitlines() if line.strip().startswith("match"))
    near_line = next(line for line in text.splitlines() if line.strip().startswith("near"))
    assert match_line.split()[1:] == ["1", "0", "1"]   # right, wrong, no address
    assert near_line.split()[1:] == ["0", "1", "0"]
    assert "suggestion was the corrected street in 1 of 1" in text
    assert "EXAMPLE" not in text
