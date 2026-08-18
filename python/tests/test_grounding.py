"""The hallucination check.

`ground()` is what makes AI extraction auditable, so it is tested directly and
without a model. No network, no API key.
"""

from __future__ import annotations

from extract_text.ai import ground
from extract_text.schema import AIExtraction, CourtRecord

SOURCE = """\
Case No. CV-2024-0912
Filed on 07/08/2024 in the District Court of Marion County.
Judgment Amount: $3,200.00
"""


def _ai(record: CourtRecord, evidence: dict[str, str]) -> AIExtraction:
    return AIExtraction(record=record, evidence=evidence)


def test_verbatim_quote_is_grounded_with_an_exact_span():
    result = ground(
        _ai(CourtRecord(case_number="CV-2024-0912"), {"case_number": "CV-2024-0912"}),
        SOURCE,
        backend="test",
    )
    ev = result.evidence["case_number"]
    assert ev.grounded
    assert SOURCE[ev.span[0] : ev.span[1]] == "CV-2024-0912"
    assert result.ungrounded_fields() == []


def test_quote_the_document_does_not_contain_is_flagged():
    result = ground(
        _ai(CourtRecord(case_number="CV-2024-9999"), {"case_number": "CV-2024-9999"}),
        SOURCE,
        backend="test",
    )
    assert result.evidence["case_number"].grounded is False
    assert result.ungrounded_fields() == ["case_number"]


def test_line_wrapped_quote_still_grounds_but_without_a_span():
    """PDF extraction breaks lines mid-phrase; an honest quote survives that."""
    wrapped = "Filed on 07/08/2024 in the District\nCourt of Marion County."
    result = ground(
        _ai(CourtRecord(court_name="District Court"), {"court_name": wrapped}),
        SOURCE,
        backend="test",
    )
    ev = result.evidence["court_name"]
    assert ev.grounded
    assert ev.span is None


def test_method_and_backend_are_recorded():
    result = ground(_ai(CourtRecord(), {}), SOURCE, backend="local:llama3.2")
    assert result.method == "ai"
    assert result.backend == "local:llama3.2"
