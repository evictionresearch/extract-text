"""Rule-based extraction.

Fast, free, reproducible, and auditable: every field it returns carries the
exact character span it was read from, so a reviewer can check the answer
against the source without rerunning anything. The tradeoff is coverage. Rules
read the documents they were written for and miss the rest, which is precisely
what the comparison against an AI backend is meant to surface.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from ..schema import CourtRecord, Evidence, Extraction, Judgment, Party
from .patterns import BUSINESS_MARKERS, CAPTIONS, PARTY_SPLIT, PATTERNS

_DATE_FORMATS = (
    "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y",
    "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
)


def parse_date(raw: str) -> date | None:
    """Parse the date shapes court documents actually use.

    Returns None rather than raising: an unparseable date is a data problem to
    report, not a reason to abandon the rest of the record.
    """
    cleaned = raw.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_money(raw: str) -> float | None:
    digits = re.sub(r"[^\d.]", "", raw)
    try:
        return float(digits)
    except ValueError:
        return None


def _first_match(text: str, field: str) -> re.Match[str] | None:
    for pattern in PATTERNS.get(field, []):
        match = pattern.search(text)
        if match:
            return match
    return None


def _parties(text: str) -> tuple[list[Party], list[Party], dict[str, Evidence]]:
    """Read the caption into plaintiff and defendant lists."""
    evidence: dict[str, Evidence] = {}
    caption = next(
        (m for m in (pattern.search(text) for pattern in CAPTIONS) if m), None
    )
    if not caption:
        return [], [], evidence

    sides = (("plaintiffs", "plaintiff"), ("defendants", "defendant"))
    out: dict[str, list[Party]] = {"plaintiffs": [], "defendants": []}

    for group, role in sides:
        block = caption.group(group)
        start = caption.start(group)
        for name in PARTY_SPLIT.split(block):
            # Strip whitespace and commas only. A trailing period is part of
            # "INC." and dropping it would be normalization.
            name = name.strip(" ,\t\n")
            if len(name) < 2:
                continue
            out[group].append(
                Party(
                    name=name,
                    role=role,  # type: ignore[arg-type]
                    is_business=bool(BUSINESS_MARKERS.search(name)),
                )
            )
            offset = block.find(name)
            path = f"{group}.{len(out[group]) - 1}.name"
            evidence[path] = Evidence(
                quote=name,
                span=(start + offset, start + offset + len(name)),
                grounded=True,
            )

    return out["plaintiffs"], out["defendants"], evidence


def extract(text: str) -> Extraction:
    """Extract a court record from `text` using rules alone."""
    values: dict[str, Any] = {}
    evidence: dict[str, Evidence] = {}

    coercions = {
        "filing_date": parse_date,
        "disposition_date": parse_date,
        "judgment.date": parse_date,
        "amount_claimed": parse_money,
        "judgment.amount": parse_money,
    }

    for field in PATTERNS:
        match = _first_match(text, field)
        if not match:
            continue
        raw = match.group("value").strip()
        coerced = coercions.get(field, str)(raw)
        if coerced is None:
            # Pattern matched but the value would not parse. Record the
            # evidence anyway so the failure is visible in review rather than
            # silently indistinguishable from an absent field.
            evidence[field] = Evidence(
                quote=raw, span=match.span("value"), grounded=True
            )
            continue
        values[field] = coerced
        evidence[field] = Evidence(
            quote=raw, span=match.span("value"), grounded=True
        )

    plaintiffs, defendants, party_evidence = _parties(text)
    evidence.update(party_evidence)

    judgment_fields = {
        key.split(".", 1)[1]: value
        for key, value in values.items()
        if key.startswith("judgment.")
    }

    record = CourtRecord(
        case_number=values.get("case_number"),
        court_name=values.get("court_name"),
        county=values.get("county"),
        state=values.get("state"),
        case_type=values.get("case_type"),
        filing_date=values.get("filing_date"),
        plaintiffs=plaintiffs,
        defendants=defendants,
        amount_claimed=values.get("amount_claimed"),
        judgment=Judgment(**judgment_fields) if judgment_fields else None,
        disposition=values.get("disposition"),
        disposition_date=values.get("disposition_date"),
    )

    return Extraction(
        record=record, method="deterministic", backend="rules", evidence=evidence
    )
