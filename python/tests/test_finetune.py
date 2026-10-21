"""Fine-tuning tests: the graders'-format prompt and parser, the OpenAI-style
backend, and the training-set exporter. Synthetic values only; no model and
no network beyond a server started here on 127.0.0.1."""

from __future__ import annotations

import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from extract_text.ai.vision import (
    LISTS_PROMPT,
    LocalVisionBackend,
    OpenAIVisionBackend,
    list_fields_to_record,
    lists_prompt,
)
from extract_text.corrections import _sha256
from extract_text.finetune import clean_target, export_training_set, split_rows

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "synthetic_summons_page1.png"

ANSWER = {
    "plaintiffs": ["EXAMPLE PROPERTY LLC"],
    "defendants": ["JANE Q. TENANT", "JON Q. TENANT a/k/a JON TENANT", "JOHN DOE"],
    "defendant_address": {"street": "1234 EXAMPLE AVE S", "unit": "Apt 5",
                          "city": "SEATTLE", "state": "WA", "zip": "98100"},
    "attorneys": ["SAM EXAMPLE", "EXAMPLE LAW GROUP PLLC"],
    "attorney_address": "100 MAIN ST STE 200, SEATTLE, WA 98101",
}


def test_lists_prompt_asks_for_the_attorney_block_only_when_told():
    assert '"attorneys"' in LISTS_PROMPT and "bar number" in LISTS_PROMPT
    without = lists_prompt(attorneys=False)
    assert '"attorneys"' not in without and "attorney_address" not in without
    assert '"defendant_address"' in without


def test_list_fields_map_into_the_shared_schema():
    record = list_fields_to_record(ANSWER)
    # the placeholder is dropped; the alias stays on its person's line
    assert [d.name for d in record.defendants] == [
        "JANE Q. TENANT", "JON Q. TENANT a/k/a JON TENANT"]
    assert record.defendant_address.street == "1234 EXAMPLE AVE S"
    assert record.defendant_address.unit == "Apt 5"
    assert record.defendant_address.raw == "1234 EXAMPLE AVE S Apt 5, SEATTLE, WA 98100"
    assert record.plaintiffs[0].is_business is True
    assert record.attorney.firm == "EXAMPLE LAW GROUP PLLC"
    assert record.attorney.names == "SAM EXAMPLE"
    assert record.attorney.address.raw.endswith("98101")


def test_list_fields_tolerate_strings_and_blanks():
    record = list_fields_to_record({
        "plaintiffs": "EXAMPLE PROPERTY LLC,", "defendants": "JANE Q. TENANT; JON Q. TENANT",
        "defendant_address": "1234 EXAMPLE AVE S APT 5, SEATTLE, WA 98100",
        "attorneys": [], "attorney_address": "",
    })
    assert [p.name for p in record.plaintiffs] == ["EXAMPLE PROPERTY LLC"]
    assert len(record.defendants) == 2
    assert record.defendant_address.zip == "98100"
    assert record.attorney is None
    empty = list_fields_to_record({"plaintiffs": [], "defendants": [],
                                   "defendant_address": {"street": ""}})
    assert empty.defendant_address is None and empty.plaintiffs == []


def test_lists_extraction_flags_an_unparsable_answer():
    class Broken(LocalVisionBackend):
        def _chat(self, b64):
            return "not json at all"
    x = Broken(model="m", prompt_format="lists")
    x._resolved = "m"
    out = x.extract_image(PAGE)
    assert "vision_json_unparsed" in out.flags and "vision_no_fields" in out.flags


def test_prompt_format_must_be_known():
    with pytest.raises(ValueError):
        LocalVisionBackend(prompt_format="v2")


def test_openai_backend_refuses_a_host_off_this_machine():
    with pytest.raises(ValueError):
        OpenAIVisionBackend(model="m", host="http://10.0.0.5:1234")
    with pytest.raises(ValueError):
        OpenAIVisionBackend(model="m", host="http://0.0.0.0:1234")


def test_openai_backend_reads_a_local_server():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.update(body)
            data = json.dumps({"choices": [{"message": {
                "content": "```json\n" + json.dumps(ANSWER) + "\n```"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        backend = OpenAIVisionBackend(
            model="tuned", host=f"http://127.0.0.1:{server.server_address[1]}",
            prompt_format="lists")
        out = backend.extract_image(PAGE)
    finally:
        server.shutdown()
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png")
    assert out.backend == "openai-vision-lists:tuned"
    assert out.record.attorney.firm == "EXAMPLE LAW GROUP PLLC"


def test_clean_target_applies_the_labeling_rules():
    changes = Counter()
    target = clean_target({
        "plaintiff": "EXAMPLE RIDGE LLC, a Washington limited liability company; "
                     "SAMPLE BANK, its successors and/or assigns,,",
        "defendants": ["JANE Q. TENANT, et al.", "ALL OTHER OCCUPANTS", "PAT EXAMPLE,",
                       "JANE DOE TENANT", "JOHN DOE II", "SAM DOERING"],
        "street": "1234 EXAMPLE AVE S", "unit": "Apt 5", "city": "SEATTLE",
        "state": "WA", "zip": "98100",
        "attorneys": ["SAM EXAMPLE"], "attorney_firm": "EXAMPLE LAW GROUP PLLC,",
        "attorney_address": "100 MAIN ST, SEATTLE, WA 98101",
    }, changes)
    assert target["plaintiffs"] == ["EXAMPLE RIDGE LLC", "SAMPLE BANK"]
    assert target["defendants"] == ["JANE Q. TENANT", "PAT EXAMPLE", "SAM DOERING"]
    assert target["attorneys"] == ["SAM EXAMPLE", "EXAMPLE LAW GROUP PLLC"]
    assert target["defendant_address"]["unit"] == "Apt 5"
    assert changes["plaintiff_description_dropped"] == 2
    assert changes["defendant_placeholder_dropped"] == 3
    assert changes["defendant_group_term_stripped"] == 1
    assert changes["attorney_firm_joined"] == 1


def test_clean_target_leaves_out_an_attorney_block_nobody_answered():
    target = clean_target({"plaintiff": "EXAMPLE LLC", "defendants": ["JANE Q. TENANT"],
                           "street": "", "unit": "", "city": "", "state": "", "zip": ""})
    assert "attorneys" not in target and "attorney_address" not in target


def test_round_two_box_is_not_joined_twice():
    target = clean_target({"plaintiff": "", "defendants": [], "attorneys": [
        "SAM EXAMPLE", "EXAMPLE LAW GROUP PLLC"], "attorney_address": ""})
    assert target["attorneys"] == ["SAM EXAMPLE", "EXAMPLE LAW GROUP PLLC"]


def _correction(row, sampled_as, sha, verdict="corrected", attorneys=True):
    truth = {"plaintiff": "EXAMPLE PROPERTY LLC", "defendants": ["JANE Q. TENANT"],
             "street": "1234 EXAMPLE AVE S", "unit": "", "city": "SEATTLE",
             "state": "WA", "zip": "98100"}
    if attorneys:
        truth.update(attorneys=["SAM EXAMPLE"], attorney_firm="EXAMPLE LAW GROUP PLLC",
                     attorney_address="100 MAIN ST, SEATTLE, WA 98101")
    return {"row": row, "file": str(PAGE), "sha256": sha, "sampled_as": sampled_as,
            "verdict": verdict, "truth": truth}


def test_split_keeps_the_random_draw_out_of_training():
    latest = {r: {"verdict": "corrected", "sampled_as": "flagged", "sha256": f"s{r}"}
              for r in range(1, 41)}
    for r in (3, 7, 9):
        latest[r]["sampled_as"] = "random"
    latest[12]["sha256"] = "s7"  # the same document drawn twice
    latest[20]["verdict"] = "unreadable"
    train, valid, test = split_rows(latest)
    assert test == [3, 7, 9]
    assert not set(train) & set(test) and not set(valid) & set(test)
    assert 12 not in train + valid and 20 not in train + valid
    assert not set(train) & set(valid)
    assert len(train) + len(valid) == 35


def test_export_writes_chat_rows_and_returns_only_counts(tmp_path):
    scan = tmp_path / "scan"
    scan.mkdir()
    sha = _sha256(PAGE)
    lines = [_correction(1, "flagged", sha), _correction(2, "flagged", sha, attorneys=False),
             _correction(3, "random", "other"), _correction(4, "flagged", "stale"),
             _correction(5, "flagged", sha, verdict="unreadable")]
    lines.append({**_correction(2, "flagged", sha, attorneys=False), "note": "later answer"})
    (scan / "corrections.jsonl").write_text("".join(json.dumps(c) + "\n" for c in lines))

    out = tmp_path / "set"
    report = export_training_set(scan, out)
    assert report["labeled"] == 5 and report["unreadable"] == 1 and report["test_rows"] == 1
    assert report["skipped"] == {"document changed": 1}
    rows = [json.loads(line) for name in ("train.jsonl", "valid.jsonl")
            for line in (out / name).read_text().splitlines()]
    assert len(rows) == report["train_rows"] + report["valid_rows"] == 2
    for row in rows:
        assert Path(row["images"][0]).is_file()
        target = json.loads(row["messages"][1]["content"])
        asks = '"attorneys"' in row["messages"][0]["content"]
        assert asks == ("attorneys" in target)
    assert json.loads((out / "split.json").read_text())["test"] == [3]
    # the report is counts only: no value from a label anywhere in it
    assert "EXAMPLE" not in json.dumps(report)


def test_the_engine_default_is_the_lists_prompt_with_the_case_number():
    from extract_text.ai.vision import LISTS_ENGINE_PROMPT, VISION_PROMPT

    assert LocalVisionBackend().prompt == LISTS_ENGINE_PROMPT
    assert LocalVisionBackend(prompt_format="v1").prompt == VISION_PROMPT
    assert '"case_number"' in LISTS_ENGINE_PROMPT
    # the prompt the fine-tune was trained with is unchanged, and a tuned
    # model served through the OpenAI-style lane is asked that one
    assert '"case_number"' not in LISTS_PROMPT
    assert LISTS_ENGINE_PROMPT.startswith(LISTS_PROMPT.split("\n\nRules:")[0])
    assert OpenAIVisionBackend(model="m").prompt == LISTS_PROMPT
    assert "\t4.\tcase_number" in lists_prompt(attorneys=False, case_number=True)
    record = list_fields_to_record({**ANSWER, "case_number": "25-2-00001-0"})
    assert record.case_number == "25-2-00001-0"
    assert list_fields_to_record(ANSWER).case_number is None


@pytest.mark.parametrize("state, code", [
    ("Washington", "WA"), ("WASHINGTON", "WA"), ("Wash.", "WA"), ("wa", "wa"),
    ("New York", "NY"), ("Oregon", "OR"), ("", None),
])
def test_a_written_out_state_becomes_its_postal_code(state, code):
    addr = {**ANSWER["defendant_address"], "state": state}
    record = list_fields_to_record({**ANSWER, "defendant_address": addr})
    assert record.defendant_address.state == code


def test_a_one_line_address_gets_the_postal_code_too():
    record = list_fields_to_record(
        {**ANSWER, "defendant_address": "1234 EXAMPLE AVE S, SEATTLE, Washington 98100"})
    assert record.defendant_address.state == "WA"


@pytest.mark.parametrize("lines, firm, people", [
    # an office line beats a solo attorney's "Attorney at Law"
    (["SAM EXAMPLE, Attorney at Law", "EXAMPLE LAW GROUP PLLC"],
     "EXAMPLE LAW GROUP PLLC", ["SAM EXAMPLE, Attorney at Law"]),
    # with no office line, the solo attorney's line is the firm
    (["SAM EXAMPLE, Attorney at Law"], "SAM EXAMPLE, Attorney at Law", []),
    # the role line and bar numbers are dropped, as GRADING.md asks
    (["SAM EXAMPLE, WSBA #12345", "Attorneys for Plaintiff", "EXAMPLE & SAMPLE, P.S."],
     "EXAMPLE & SAMPLE, P.S.", ["SAM EXAMPLE"]),
    (["SAM EXAMPLE, WSBA No. 12345, Attorney for Plaintiff, EXAMPLE LAW PLLC"],
     "SAM EXAMPLE, EXAMPLE LAW PLLC", []),
    # a second office-looking line stays with the people, never dropped
    (["EXAMPLE LAW PLLC", "SAMPLE LEGAL SERVICES", "SAM EXAMPLE"],
     "EXAMPLE LAW PLLC", ["SAMPLE LEGAL SERVICES", "SAM EXAMPLE"]),
    (["SAM EXAMPLE", "ROBIN SAMPLE"], None, ["SAM EXAMPLE", "ROBIN SAMPLE"]),
])
def test_the_firm_is_the_line_that_reads_most_as_an_office(lines, firm, people):
    att = list_fields_to_record({**ANSWER, "attorneys": lines}).attorney
    assert att.firm == firm
    assert (att.names or "").split("; ") == (people or [""])
