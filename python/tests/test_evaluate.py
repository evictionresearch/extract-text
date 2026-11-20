"""The head-to-head measures, and the script that runs them, on made-up
documents. Every address and case number here is synthetic."""

import csv
import importlib.util
import shutil
from pathlib import Path

import pytest

from extract_text import evaluate as ev
from extract_text.documents import have

FIXTURES = Path(__file__).parent / "fixtures"
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

needs_system_tools = pytest.mark.skipif(
    not (have("pdftotext") and have("pdfinfo") and have("pdftoppm") and have("tesseract")),
    reason="poppler/tesseract not installed",
)


def _script():
    spec = importlib.util.spec_from_file_location("head_to_head", SCRIPTS / "head_to_head.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# the measures


def test_wilson_interval_is_wide_on_a_small_sample():
    lo, hi = ev.wilson(51, 65)
    assert 0.66 < lo < 0.68 and 0.86 < hi < 0.88
    assert ev.wilson(0, 0) == (0.0, 0.0)
    lo, hi = ev.wilson(10, 10)  # ten of ten is not proof of always
    assert 0.70 < lo < 0.75 and hi > 0.999


def test_exact_paired_test_reads_only_the_documents_that_separate_two_engines():
    assert round(ev.mcnemar_exact(2, 12), 4) == 0.0129
    assert ev.mcnemar_exact(5, 5) == 1.0
    assert ev.mcnemar_exact(0, 0) == 1.0
    assert ev.mcnemar_exact(0, 6) == ev.mcnemar_exact(6, 0)


def test_split_and_draw_are_fixed_by_the_seed():
    cases = [f"25-2-{i:05d}-0" for i in range(40)]
    a = ev.seeded_split(cases, 10, seed=7)
    assert a == ev.seeded_split(list(reversed(cases)), 10, seed=7)
    assert sum(part == "test" for part in a.values()) == 10
    assert a != ev.seeded_split(cases, 10, seed=8)
    assert ev.seeded_draw(cases, 5, seed=7) == ev.seeded_draw(cases, 20, seed=7)[:5]
    assert len(ev.seeded_draw(cases, 0, seed=7)) == 40


def test_a_typed_line_becomes_house_number_street_unit_and_zip():
    key = ev.truth_key("1234 Example Avenue South, Apt 5, Seattle, WA 98100")
    assert key["how"] == "pattern"
    assert (key["house"], key["street"], key["unit"], key["zip"]) == ("1234", "1234 EXAMPLE AVE S", "APT 5", "98100")
    # a street with no type word, read by the stricter pattern
    assert ev.truth_key("5037 So. Sample, Sampleton, WA 98100")["how"] == "no_suffix"
    # a line the patterns cannot read is cut at its first comma
    odd = ev.truth_key("Space 12 Example Mobile Park, Sampleton")
    assert odd["how"] == "comma" and odd["zip"] == ""
    assert ev.truth_key("")["how"] == "blank"


def test_strict_measure_catches_what_the_papers_measure_forgives():
    truth = ev.truth_key("1234 Example Avenue South, Apt 5, Seattle, WA 98100")
    right = {"street": "1234 EXAMPLE AVE S APT 5", "unit": "APT 5", "zip": "98100",
             "raw": "1234 EXAMPLE AVE S APT 5 SEATTLE, WA 98100"}
    got = ev.compare_address(truth, right)
    assert got["street"] and got["unit"] and got["zip"] and got["paper"]
    # the direction dropped: another street, and the paper's measure passes it
    no_direction = {**right, "street": "1234 EXAMPLE AVE APT 5", "raw": "1234 EXAMPLE AVE APT 5 SEATTLE, WA 98100"}
    got = ev.compare_address(truth, no_direction)
    assert got["paper"] and got["house"] and not got["street"]
    # the unit dropped: the street is right, the unit is not
    no_unit = {"street": "1234 EXAMPLE AVE S", "unit": "", "zip": "98100", "raw": "1234 EXAMPLE AVE S SEATTLE, WA 98100"}
    got = ev.compare_address(truth, no_unit)
    assert got["street"] and not got["unit"]
    # nothing returned
    got = ev.compare_address(truth, {"street": "", "raw": ""})
    assert not got["extracted"] and not got["street"] and got["zip"] is None


def test_a_street_split_off_into_the_unit_is_judged_on_the_whole_line():
    truth = ev.truth_key("1234 Example Ave NE Bldg 9 Apt 102, Sampleton, WA 98100")
    # the AI engine's split: the direction landed in the unit
    model = {"street": "1234 EXAMPLE AVE.", "unit": "NE BLDG 9 Apt # 102", "zip": "98100", "raw": ""}
    rules = {"street": "1234 EXAMPLE AVE. NE BLDG 9 Apt # 102", "unit": "BLDG 9 Apt # 102", "zip": "98100"}
    assert ev.compare_address(truth, model)["street"] and ev.compare_address(truth, rules)["street"]
    assert ev.reading_key(model)["unit"] == ev.reading_key(rules)["unit"]
    # a typed "#5" and a printed "APT 5" are the same unit
    assert ev.compare_address(ev.truth_key("1234 Example Ave S #5"),
                              {"street": "1234 EXAMPLE AVE S APT 5", "unit": "APT 5"})["unit"]
    # a unit the typist left off is counted, not scored wrong
    truths = {"a": ev.truth_key("1234 Example Ave S, Seattle, WA 98100")}
    s = ev.score_lane(truths, {"a": {"street": "1234 EXAMPLE AVE S APT 5", "unit": "APT 5"}}, ["a"])
    assert (s["street"], s.get("street_and_unit", 0), s["unit_added"], s["no_truth_unit"]) == (1, 0, 1, 1)
    # a unit with no unit word keeps the engine's own split
    assert ev.reading_key({"street": "1234 EXAMPLE ST", "unit": "B"})["street"] == "1234 EXAMPLE ST"


def test_accept_signals_count_coverage_and_how_often_the_street_is_right():
    truths = {c: ev.truth_key(a) for c, a in {
        "a": "1234 Example Ave S, Seattle, WA 98100", "b": "9876 Sample Ave, Seattle, WA 98100",
        "c": "100 Sample Street, Seattle, WA 98100"}.items()}
    rules = {"a": {"street": "1234 EXAMPLE AVE S"}, "b": {"street": "9999 EXAMPLE AVE"}, "c": {"street": ""}}
    model = {"a": {"street": "1234 Example Avenue South"}, "b": {"street": "9999 Example Ave"},
             "c": {"street": "100 Sample Street"}}
    listed = {"rules": {"a": "match", "b": "no_match", "c": ""}}
    rows = {r["signal"]: r for r in ev.tiers(truths, {"rules": rules, "ai": model}, ["a", "b", "c"], listed)}
    assert (rows["rules and the address list"]["covered"], rows["rules and the address list"]["right"]) == (1, 1)
    # the two lanes agree on a and on b, and b is wrong both ways: agreement is not proof
    assert (rows["rules = ai"]["covered"], rows["rules = ai"]["right"]) == (2, 1)
    assert (rows["rules = ai and the address list"]["covered"], rows["rules = ai and the address list"]["right"]) == (1, 1)
    p = ev.paired(truths, rules, model, ["a", "b", "c"])
    assert (p["both"], p["first_only"], p["second_only"], p["neither"]) == (1, 0, 1, 1)


def test_a_lost_street_is_sorted_by_the_stage_that_lost_it():
    truth = ev.truth_key("1234 Example Avenue South, Apt 5, Seattle, WA 98100")
    assert ev.loss_category(truth, "absent", [], "") == "not in the text"
    assert ev.loss_category(truth, "exact", [], "") == "in the text, no candidate"
    chosen_other = [("100 MAIN ST STE 200", "STE 200"), ("1234 EXAMPLE AVE S APT 5", "APT 5")]
    assert ev.loss_category(truth, "exact", chosen_other, "100 MAIN ST STE 200 SEATTLE, WA 98101") \
        == "a candidate, not chosen"
    # passed over first because the engine took it for the attorney's address
    assert ev.loss_category(truth, "exact", list(reversed(chosen_other)), "100 MAIN ST STE 200 SEATTLE, WA 98101") \
        == "a candidate, not chosen"
    split_wrong = [("1234 EXAMPLE AVE", "")]
    assert ev.loss_category(truth, "exact", split_wrong, "1234 Example Avenue South Apt 5 Seattle WA") \
        == "chosen block, parsed wrong"


# ---------------------------------------------------------------------------
# the script, end to end on three made-up documents


TYPED = {
    "25-2-00001-0": ("synthetic_summons_efiled.pdf", "1234 Example Avenue South, Apt 5, Seattle, WA 98100"),
    "25-2-00007-1": ("synthetic_kc_efiled.pdf", "5678 Sample Ave, Seattle, WA 98100"),
    # typed wrongly on purpose, so one street counts as lost
    "25-2-00008-3": ("synthetic_kc_printed.pdf", "99999 Nowhere Pkwy, Sampleton, WA 98100"),
}
PRIVATE = ("EXAMPLE", "Example", "SAMPLE", "Sample", "Nowhere", "NOWHERE", "25-2-0000", "98100", ".pdf", "images/")


@pytest.fixture
def setup(tmp_path):
    archive, truth = tmp_path / "images", tmp_path / "truth.csv"
    with open(truth, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case", "plainAddress", "extractStatus", "county"])
        for case, (fixture, typed) in TYPED.items():
            folder = archive / "King" / "2025" / case
            folder.mkdir(parents=True)
            shutil.copyfile(FIXTURES / fixture, folder / "summons.pdf")
            w.writerow([case, typed, "thesis", "King"])
        w.writerow(["26-2-01234-1", "1234 Example Avenue, Sampleton, WA 98100", "thesis", "King"])  # no folder
        w.writerow(["25-2-00001-0", "1234 Example Avenue, Sampleton, WA 98100", "HJP", "King"])  # other provenance
    listed = tmp_path / "addresses.csv"
    listed.write_text("address,zip\n1234 Example Ave S,98100\n5678 Sample Ave,98100\n")
    return archive, truth, listed, tmp_path / "out"


@needs_system_tools
def test_head_to_head_runs_end_to_end_and_prints_no_value(setup, capsys, monkeypatch):
    archive, truth, listed, out = setup
    h2h = _script()

    assert h2h.main(["describe", "--truth", str(truth)]) == 0
    described = capsys.readouterr().out
    assert "4 'thesis' rows" in described and "pattern 4" in described

    assert h2h.main(["split", "--truth", str(truth), "--archive", str(archive), "--out", str(out),
                     "--test", "3"]) == 0
    said = capsys.readouterr().out
    assert "3 have a summons on disk" in said and "3 test, 0 dev" in said
    with pytest.raises(SystemExit):  # the split is made once
        h2h.main(["split", "--truth", str(truth), "--archive", str(archive), "--out", str(out)])

    # a stand-in for the model: right where the rules are right, and it
    # drops a direction on one document
    real_lane = h2h.make_lane

    def lane(name, model, cache):
        if name == "rules":
            return real_lane(name, model, cache)
        rules = real_lane("rules", model, cache)

        def read(path):
            r = rules(path)
            r["street"] = r["street"].replace(" AVE S", " AVE")
            r["raw"] = r["raw"].replace(" AVE S", " AVE")
            return r
        return read

    monkeypatch.setattr(h2h, "make_lane", lane)
    assert h2h.main(["run", "--out", str(out), "--lanes", "rules,ai", "--n", "0"]) == 0
    first = capsys.readouterr().out
    assert "3 read now" in first
    assert h2h.main(["run", "--out", str(out), "--lanes", "rules,ai", "--n", "0"]) == 0
    assert "3 already read, 0 read now" in capsys.readouterr().out  # a second run reads nothing again

    assert h2h.main(["score", "--truth", str(truth), "--out", str(out), "--n", "0",
                     "--addresses", str(listed), "--zip-column", "zip"]) == 0
    report = capsys.readouterr().out
    assert "3 of 3 drawn cases read by every lane (rules, ai)" in report
    assert "rules / ai" in report and "The rule is not met" in report
    assert "rules and the address list" in report and "2 listed addresses" in report

    assert h2h.main(["loss", "--truth", str(truth), "--out", str(out), "--n", "0"]) == 0
    lost = capsys.readouterr().out
    assert "2 right, 1 lost" in lost and "not in the text" in lost

    for text in (described, said, first, report, lost):
        for word in PRIVATE:
            assert word not in text, f"{word!r} was printed"


@needs_system_tools
def test_scores_on_the_made_up_documents(setup):
    archive, truth, listed, out = setup
    h2h = _script()
    h2h.main(["split", "--truth", str(truth), "--archive", str(archive), "--out", str(out), "--test", "3"])
    h2h.main(["run", "--out", str(out), "--lanes", "rules", "--n", "0"])
    rows = h2h.load_truth(truth, "thesis")
    readings = h2h.load_readings(out, "rules")
    cases = sorted(readings)
    truths = {c: ev.truth_key(rows[c]["plainAddress"]) for c in cases}
    s = ev.score_lane(truths, readings, cases)
    assert (s["n"], s["extracted"], s["street"]) == (3, 3, 2)
    assert s["unit_kept"] == 1 and s["truth_units"] == 1
