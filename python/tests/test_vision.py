"""Vision-lane tests.

The parsing ladder and the field mapping are tested without any model, so
they run everywhere. The one live test at the bottom talks to a local
Ollama server and skips unless the server is up and the model is pulled;
nothing in this suite ever calls a network beyond localhost.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from extract_text.ai.vision import (
    DEFAULT_VISION_MODEL,
    LocalVisionBackend,
    available,
    extract_fields_fallback,
    fields_to_record,
    parse_llm_json_best_effort,
    pulled_models,
    strip_group_terms,
)

FIXTURES = Path(__file__).parent / "fixtures"

GOOD = ('{"plaintiff": "EXAMPLE PROPERTY LLC", "defendant": "JANE Q. TENANT '
        'and JON Q. TENANT", "address": "1234 EXAMPLE AVE S APT 5, SEATTLE, '
        'WA 98100", "law_firm": "EXAMPLE LAW GROUP PLLC", "law_firm_address": '
        '"100 MAIN ST STE 200, SEATTLE, WA 98101", "case_number": "25-2-00001-0"}')


def test_strict_json_parses():
    assert parse_llm_json_best_effort(GOOD)["plaintiff"] == "EXAMPLE PROPERTY LLC"


def test_code_fenced_json_parses():
    fenced = f"```json\n{GOOD}\n```"
    assert parse_llm_json_best_effort(fenced)["case_number"] == "25-2-00001-0"


def test_json_with_prose_around_it_parses():
    noisy = f"Here is the extraction you asked for:\n{GOOD}\nLet me know!"
    assert parse_llm_json_best_effort(noisy)["law_firm"] == "EXAMPLE LAW GROUP PLLC"


def test_garbage_returns_none_then_regex_fallback_recovers_fields():
    near_json = ('{"plaintiff": "EXAMPLE PROPERTY LLC", "defendant": "JANE Q. '
                 'TENANT", "address": "1234 EXAMPLE AVE S, "SEATTLE" WA", '
                 '"law_firm": "X", "law_firm_address": "Y", "case_number": "Z"}')
    assert parse_llm_json_best_effort(near_json) is None  # broken quoting
    got = extract_fields_fallback(near_json)
    assert got["plaintiff"] == "EXAMPLE PROPERTY LLC"
    assert got["defendant"] == "JANE Q. TENANT"


def test_fields_map_into_the_shared_schema():
    record = fields_to_record({
        "plaintiff": "EXAMPLE PROPERTY LLC",
        "defendant": "JANE Q. TENANT and JON Q. TENANT",
        "address": "1234 EXAMPLE AVE S APT 5, SEATTLE, WA 98100",
        "law_firm": "EXAMPLE LAW GROUP PLLC",
        "law_firm_address": "100 MAIN ST STE 200, SEATTLE, WA 98101",
        "case_number": "25-2-00001-0",
    })
    assert record.case_number == "25-2-00001-0"
    assert [d.name for d in record.defendants] == ["JANE Q. TENANT", "JON Q. TENANT"]
    assert record.defendants[0].is_business is False
    assert record.plaintiffs[0].is_business is True
    assert record.defendant_address.street == "1234 EXAMPLE AVE S APT 5"
    assert record.defendant_address.zip == "98100"
    assert record.attorney.firm == "EXAMPLE LAW GROUP PLLC"
    assert record.attorney.address.zip == "98101"


@pytest.mark.parametrize("raw, want", [
    # The defect the 2026-08-20 corpus bench found: four of six models return
    # the caption's group term even though the prompt names it as excluded.
    ("ALEX P. OCCUPANT, and ALL OTHER OCCUPANTS", "ALEX P. OCCUPANT"),
    ("SMITH PROPERTIES LLC, et al.", "SMITH PROPERTIES LLC"),
    ("MARIA LOPEZ and all others", "MARIA LOPEZ"),
    ("MARIA LOPEZ, Does 1-10", "MARIA LOPEZ"),
    ("JOHN SMITH and JANE SMITH, husband and wife", "JOHN SMITH and JANE SMITH"),
    # Captions stack them, so one pass is not enough.
    ("JOHN SMITH and JANE SMITH, husband and wife, et al.", "JOHN SMITH and JANE SMITH"),
])
def test_trailing_group_terms_are_stripped(raw, want):
    assert strip_group_terms(raw) == want


@pytest.mark.parametrize("raw", [
    # Two named defendants joined by "and" is the shape the group terms
    # imitate, and it must survive untouched.
    "JANE Q. TENANT and JON Q. TENANT",
    "ALEX P. OCCUPANT",
    # A surname is not a group term even when it reads like one.
    "OCCUPANT PROPERTIES LLC",
    # A field that is nothing but a group term is wrong either way; keeping it
    # leaves the problem visible in the evidence instead of hiding it.
    "ALL OTHER OCCUPANTS",
])
def test_real_names_are_never_stripped(raw):
    assert strip_group_terms(raw) == raw


def test_group_term_does_not_become_a_second_defendant():
    """The reason this filter exists: the name split runs on "and"."""
    record = fields_to_record({
        "plaintiff": "EXAMPLE PROPERTY LLC",
        "defendant": "ALEX P. OCCUPANT, and ALL OTHER OCCUPANTS",
        "address": None, "law_firm": None,
        "law_firm_address": None, "case_number": "25-2-00001-0",
    })
    assert [d.name for d in record.defendants] == ["ALEX P. OCCUPANT"]


def test_na_and_blank_mean_missing_not_a_value():
    record = fields_to_record({
        "plaintiff": "NA", "defendant": "", "address": None,
        "law_firm": "NA", "law_firm_address": "NA", "case_number": "NA",
    })
    assert record.case_number is None
    assert record.plaintiffs == []
    assert record.defendants == []
    assert record.defendant_address is None
    assert record.attorney is None


def _model_ready() -> bool:
    if not available():
        return False
    models = pulled_models()
    return DEFAULT_VISION_MODEL in models or any(
        m.split(":")[0] == DEFAULT_VISION_MODEL.split(":")[0] for m in models
    )


@pytest.mark.skipif(not _model_ready(), reason="Ollama with a qwen3.5 model not available")
def test_live_local_model_reads_the_synthetic_page():
    """End to end on the synthetic page image. Slow (tens of seconds)."""
    models = pulled_models()
    model = (DEFAULT_VISION_MODEL if DEFAULT_VISION_MODEL in models
             else next(m for m in models
                       if m.split(":")[0] == DEFAULT_VISION_MODEL.split(":")[0]))
    backend = LocalVisionBackend(model=model)
    x = backend.extract_image(FIXTURES / "synthetic_summons_page1.png")
    assert x.method == "ai"
    assert x.backend.startswith("local-vision-lists:")
    # a competent vision model must at least return the defendant's street
    addr = x.record.defendant_address
    assert addr is not None and "EXAMPLE" in addr.raw.upper()
