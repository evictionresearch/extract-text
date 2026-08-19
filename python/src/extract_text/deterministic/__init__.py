"""Rule-based extraction: regular expressions plus positional layout rules.

Two layers, merged by `extract()`:

- **Text rules** (`extract.py`, `patterns.py`): field patterns applied to
  flat text. Case number, court, county, dates, amounts, caption parties.
  These work on any text from any jurisdiction.
- **Positional rules** (`summons.py`): the anchor ladder and attorney-block
  geometry, which need word positions and therefore the original file.
  These produce the defendant service address and the attorney block, and
  they carry the validation work from the Washington corpus.

Given a file path, both layers run and merge. Given a plain string, the text
rules run, plus a conservative text-only service-block scan; the geometric
protections (and the attorney block, which depends on them) need positions,
so extracting from the original file is always better than from pasted text.
"""

from __future__ import annotations

import os
import re

from ..schema import CourtRecord, Evidence, Extraction, Party
from .extract import extract as extract_from_text
from .extract import parse_date, parse_money
from .patterns import BUSINESS_MARKERS, PATTERNS
from .summons import (
    OCCUPANT_NOISE_RE,
    PROSE_STOP_RE,
    TO_ANCHOR_RE,
    extract_summons_fields,
    looks_like_name_line,
    parse_address,
)

__all__ = [
    "PATTERNS",
    "extract",
    "extract_from_document",
    "extract_from_file",
    "extract_from_text",
    "parse_date",
    "parse_money",
]

_ATTORNEY_BLOCK_RE = re.compile(
    r"TELEPHONE\s+NO|WSBA|ATTORNEYS?\s+(AT\s+LAW|FOR)|LAW\s+OFFICE", re.IGNORECASE
)


def _text_service_block(text: str):
    """Text-only fallback for the 'TO:' service block.

    Plain text has no geometry, so this reuses the block-walking logic of the
    positional anchor on raw lines and applies the same attorney-marker
    veto. It is deliberately conservative; with no page coordinates there is
    no way to tell a bottom-right attorney block from body text except by its
    wording.
    """
    lines = text.splitlines()
    for i, raw in enumerate(lines):
        t = raw.strip()
        if not TO_ANCHOR_RE.match(t) or len(t) > 90:
            continue
        block = []
        first = TO_ANCHOR_RE.sub("", t).strip()
        if first:
            block.append(first)
        for nxt in lines[i + 1: i + 9]:
            if PROSE_STOP_RE.search(nxt) or not nxt.strip():
                break
            block.append(nxt.strip())
        if _ATTORNEY_BLOCK_RE.search(" ".join(block)):
            continue
        names, addr_parts, addr_started = [], [], False
        for part in block:
            clean = OCCUPANT_NOISE_RE.sub("", part).strip(" ,;")
            if not addr_started and clean and looks_like_name_line(clean):
                names.append(clean)
                continue
            if part.strip():
                addr_started = True
                addr_parts.append(part.strip())
        parsed = parse_address(" ".join(addr_parts)) if addr_parts else None
        if parsed:
            parsed["defendant_names"] = "; ".join(n for n in names if n)[:200]
            return parsed
    return None


def extract_from_document(doc, expected_case_number: str | None = None) -> Extraction:
    """Full deterministic extraction from an already loaded Document."""
    from .. import documents
    from ..schema import DocumentInfo

    fields, evidence, flags = extract_summons_fields(doc, expected_case_number)
    # fallback: combined summons+complaint bundles can bury the service
    # block or premises language on interior pages
    if not fields["defendant_address"] and doc.n_pages > 2:
        added = documents.load_fallback_pages(doc)
        if added:
            fields, evidence, flags = extract_summons_fields(doc, expected_case_number)

    base = extract_from_text(doc.text)
    record = _merge(base, fields)
    merged_evidence = {**base.evidence, **evidence}

    return Extraction(
        record=record,
        method="deterministic",
        backend="rules",
        evidence=merged_evidence,
        flags=flags,
        document=DocumentInfo(
            file=os.path.basename(str(doc.path)),
            n_pages=doc.n_pages,
            text_source=doc.source,  # type: ignore[arg-type]
            ocr_mean_conf=doc.ocr_mean_conf if doc.source != "pdf_text_layer" else None,
        ),
    )


def extract_from_file(path, expected_case_number: str | None = None) -> Extraction:
    """Full deterministic extraction from a PDF, TIFF, or image file."""
    from .. import documents

    doc = documents.load_document(path)
    return extract_from_document(doc, expected_case_number)


def _merge(base: Extraction, fields: dict) -> CourtRecord:
    """Overlay the positional results onto the text-rule record.

    Positional wins where both found something: it was read from a located
    page region, which is stronger provenance than a pattern match in flat
    text.
    """
    record = base.record.model_copy(deep=True)
    if fields["case_number"]:
        record.case_number = fields["case_number"]
    if fields.get("plaintiffs") and not record.plaintiffs:
        record.plaintiffs = fields["plaintiffs"]
    if fields["defendants"]:
        record.defendants = fields["defendants"]
    if fields["defendant_address"]:
        record.defendant_address = fields["defendant_address"]
    if fields["attorney"]:
        record.attorney = fields["attorney"]
        # attach counsel to the plaintiff parties: on a summons the block is
        # the plaintiff's counsel of record
        for p in record.plaintiffs:
            if p.attorney is None:
                p.attorney = fields["attorney"].names or fields["attorney"].firm
    return record


def extract(source: str | os.PathLike, expected_case_number: str | None = None) -> Extraction:
    """Extract a court record using rules alone. No network, no model.

    `source` is either document text (a string containing newlines or that
    does not name an existing file) or a path to a PDF, TIFF, PNG, or JPEG.
    Working from the file is always better: page positions enable the
    address and attorney rules and the OCR-quality flags.
    """
    if not isinstance(source, str) or (
        "\n" not in source and len(source) < 4096 and os.path.exists(source)
    ):
        return extract_from_file(source, expected_case_number)

    base = extract_from_text(source)
    parsed = _text_service_block(source)
    if parsed:
        from .summons import _split_defendant_names, _to_address

        record = base.record
        record.defendant_address = _to_address(parsed)
        base.evidence["defendant_address"] = Evidence(
            quote=parsed.get("address_raw", ""), grounded=True, anchor="to_block_text"
        )
        if not record.defendants:
            for k, name in enumerate(_split_defendant_names(parsed.get("defendant_names", ""))):
                record.defendants.append(Party(
                    name=name, role="defendant",
                    is_business=bool(BUSINESS_MARKERS.search(name)),
                    address=record.defendant_address,
                ))
                base.evidence[f"defendants.{k}.name"] = Evidence(
                    quote=name, grounded=True, anchor="to_block_text"
                )
    return base
