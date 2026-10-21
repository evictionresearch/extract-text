"""Party-name cleanup shared by both engines. All names invented."""

from __future__ import annotations

import json

from extract_text.ai.vision import LocalVisionBackend
from extract_text.deterministic.summons import _split_defendant_names
from extract_text.parties import drop_plaintiff_matches


def test_rules_names_drop_group_terms():
    assert _split_defendant_names("PAT EXAMPLE et al and EXAMPLE RIDGE APARTMENTS") == [
        "PAT EXAMPLE", "EXAMPLE RIDGE APARTMENTS"]
    assert _split_defendant_names("JO SAMPLE and any and all other residing") == ["JO SAMPLE"]
    assert _split_defendant_names("A ROE and B ROE, husband and wife; all other occupants") == [
        "A ROE", "B ROE"]
    assert _split_defendant_names("et al") == []


def test_defendant_that_is_the_plaintiff_is_dropped():
    kept, dropped = drop_plaintiff_matches(
        ["PAT EXAMPLE", "EXAMPLE RIDGE APARTMENTS"],
        ["Example Ridge Apartments, LLC, a Washington limited liability company"])
    assert kept == ["PAT EXAMPLE"]
    assert dropped == ["EXAMPLE RIDGE APARTMENTS"]


def test_plaintiff_key_drops_the_caption_description():
    from extract_text.parties import _party_key

    key = _party_key("EXAMPLE HOMES")
    assert _party_key("EXAMPLE HOMES, a public body corporate and politic,") == key
    assert _party_key("EXAMPLE HOMES, its successors and/or assigns,") == key
    assert _party_key("EXAMPLE HOMES, LLC") == key
    # an "its" that is part of the name stays
    assert _party_key("ITS EXAMPLE HOMES") != key


def test_shared_surname_is_not_a_match():
    kept, dropped = drop_plaintiff_matches(["PAT EXAMPLE"], ["LEE EXAMPLE"])
    assert kept == ["PAT EXAMPLE"] and dropped == []
    kept, dropped = drop_plaintiff_matches(["PAT EXAMPLE"], [])
    assert kept == ["PAT EXAMPLE"] and dropped == []


def test_ai_engine_drops_the_plaintiff_from_defendants(tmp_path):
    reply = json.dumps({
        "plaintiff": "EXAMPLE RIDGE APARTMENTS LLC",
        "defendant": "PAT EXAMPLE and EXAMPLE RIDGE APARTMENTS",
        "address": "1234 EXAMPLE AVE S APT 5, SEATTLE, WA 98100",
        "law_firm": "", "law_firm_address": "", "case_number": "25-2-00001-0",
    })
    backend = LocalVisionBackend()
    backend._resolved = "fake:1"
    backend._chat = lambda b64: reply
    page = tmp_path / "page.png"
    page.write_bytes(b"not really an image; the fake model never looks")
    x = backend.extract_image(page)
    assert [p.name for p in x.record.defendants] == ["PAT EXAMPLE"]
    assert "defendant_matches_plaintiff" in x.flags


def test_names_are_cleaned_and_listed_names_split():
    from extract_text.parties import (
        clean_party_name,
        finish_party_names,
        split_listed_names,
    )

    assert clean_party_name("=) ao PAT EXAMPLE") == "PAT EXAMPLE"
    assert clean_party_name("1] PAT EXAMPLE (TENANT) &") == "PAT EXAMPLE"
    assert clean_party_name("A. B. EXAMPLE") == "A. B. EXAMPLE"     # initials survive
    assert finish_party_names(["EXAMPLE GREENS LLC", "DBA EXAMPLE GREENS", "9]", "TO:",
                               "this is notice of a lawsuit to evict you"]) == [
        "EXAMPLE GREENS LLC DBA EXAMPLE GREENS"]
    assert split_listed_names("PAT EXAMPLE, LEE EXAMPLE, and JO EXAMPLE") == [
        "PAT EXAMPLE", "LEE EXAMPLE", "JO EXAMPLE"]
    assert split_listed_names("EXAMPLE, JOHN") == ["EXAMPLE, JOHN"]
    assert split_listed_names("EXAMPLE GREENS, LLC") == ["EXAMPLE GREENS, LLC"]
