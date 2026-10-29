"""Field contract shared by every backend and by the R wrapper.

These models are the source of truth. `schema/court_record.schema.json` is
generated from them by `scripts/build_schema.py`; do not hand-edit that file.

The design separates three things that extraction pipelines usually mash
together:

  CourtRecord   what was found
  Evidence      where each field came from (verbatim text, or a page anchor)
  Extraction    the two above, plus which backend produced them

Keeping evidence separate is what makes a language model's output auditable.
The model returns the quote it based each field on, and the backend then checks
that the quote actually occurs in the source document. A field whose evidence
cannot be located in the source is not trustworthy, whatever the model asserted.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Method = Literal["deterministic", "ai"]


class Address(BaseModel):
    """A postal address, kept both as printed and split into parts.

    `raw` is always populated when an address was found at all. The parts are
    filled when the parser could separate them; a missing part means the
    document did not print it or the parser could not isolate it, and the raw
    string is the fallback for review.
    """

    raw: str = Field(description="The address as printed, joined onto one line.")
    street: str | None = Field(
        default=None, description="House number and street, e.g. '1234 Example Ave S'."
    )
    unit: str | None = Field(
        default=None, description="Apartment, unit, suite, or space, as printed."
    )
    city: str | None = None
    state: str | None = None
    zip: str | None = Field(
        default=None, description="5-digit ZIP, or ZIP+4 when the document prints one."
    )


class Party(BaseModel):
    """A named party to the action."""

    name: str
    role: Literal["plaintiff", "defendant", "other"]
    is_business: bool | None = Field(
        default=None,
        description=(
            "True when the party appears to be a company, LLC, trust, or other "
            "entity rather than a natural person."
        ),
    )
    attorney: str | None = None
    address: Address | None = None


class Attorney(BaseModel):
    """Counsel of record, usually the plaintiff's attorney on a summons.

    On Washington summonses this is the block in the bottom-right corner of
    the page. It matters for two reasons: it identifies who is filing, and it
    is the classic wrong-answer trap, because a naive extractor returns the
    attorney's address as the tenant's.
    """

    names: str | None = Field(
        default=None, description="Attorney name(s) as printed, '; ' separated."
    )
    firm: str | None = None
    address: Address | None = None
    phone: str | None = None
    bar_numbers: str | None = Field(
        default=None,
        description="State bar numbers as printed (WSBA numbers in Washington), ';' separated.",
    )


class Judgment(BaseModel):
    """The disposition of the case, where one is recorded."""

    type: Literal["possession", "money", "possession_and_money", "default", "dismissal", "stipulation", "other"] | None = None
    date: dt.date | None = None
    amount: float | None = Field(
        default=None, description="Money judgment in dollars, if any."
    )
    in_favor_of: Literal["plaintiff", "defendant"] | None = None


class CourtRecord(BaseModel):
    """A single eviction or unlawful detainer case.

    Every field is optional. Court documents vary enormously by jurisdiction and
    a missing field is information, not an error. Distinguishing "the document
    does not say" from "the extractor failed to read it" is the job of the
    comparison report and the flags, not the schema.
    """

    case_number: str | None = None
    court_name: str | None = None
    county: str | None = None
    state: str | None = Field(
        default=None,
        description=(
            "State as written on the document, which may be a full name or an "
            "abbreviation. Normalizing to USPS codes is a downstream concern."
        ),
    )
    case_type: str | None = Field(
        default=None,
        description=(
            "Case type as written on the document, e.g. 'Unlawful Detainer', "
            "'Forcible Entry and Detainer', 'Eviction'. Do not normalize."
        ),
    )
    filing_date: dt.date | None = None
    plaintiffs: list[Party] = Field(default_factory=list)
    defendants: list[Party] = Field(default_factory=list)
    defendant_address: Address | None = Field(
        default=None,
        description=(
            "The defendant household's service address from the summons: the "
            "single most important field for eviction research, because it is "
            "what geocoding and neighborhood analysis are built on."
        ),
    )
    attorney: Attorney | None = Field(
        default=None, description="Plaintiff-side counsel of record, as printed."
    )
    amount_claimed: float | None = Field(
        default=None, description="Amount sought by the plaintiff, in dollars."
    )
    judgment: Judgment | None = None
    disposition: str | None = None
    disposition_date: dt.date | None = None


class Evidence(BaseModel):
    """Where in the source document a single field came from."""

    quote: str = Field(
        description="Verbatim span of source text supporting the field."
    )
    span: tuple[int, int] | None = Field(
        default=None,
        description=(
            "Character offsets of the quote in the source text. Populated by "
            "the deterministic engine when it read flat text, and by the AI "
            "backends by locating the returned quote."
        ),
    )
    grounded: bool = Field(
        default=False,
        description=(
            "True when the quote was verified against the source: found "
            "verbatim in the text, or produced directly by a positional rule "
            "reading the page. A false value on an AI extraction means the "
            "quote could not be verified against the document."
        ),
    )
    anchor: str | None = Field(
        default=None,
        description=(
            "For positional extraction, the named rule that produced the "
            "value, e.g. 'to_block', 'premises_prose', 'attorney_block'. "
            "This is the audit trail: every value records the rule that "
            "found it."
        ),
    )
    page: int | None = Field(
        default=None, description="1-based page the value was read from, if known."
    )
    box: tuple[float, float, float, float] | None = Field(
        default=None,
        description=(
            "Where on that page the value was read, as (x0, y0, x1, y1) "
            "fractions of the page width and height from the top left. Set by "
            "the deterministic engine when it read a file; the review page "
            "draws it over the page image."
        ),
    )


class DocumentInfo(BaseModel):
    """How the text was obtained from the file, for provenance."""

    file: str | None = Field(default=None, description="File name, not the full path.")
    n_pages: int | None = None
    text_source: Literal["plain_text", "pdf_text_layer", "pdf_ocr", "tiff_ocr", "image_ocr"] | None = Field(
        default=None,
        description=(
            "'pdf_text_layer' means the PDF carried digital text and OCR was "
            "never run; the *_ocr values mean the page images were read by "
            "OCR at 300 dpi."
        ),
    )
    ocr_mean_conf: float | None = Field(
        default=None,
        description="Mean OCR word confidence 0-100, when OCR ran. Low values mean poor scans.",
    )


class Extraction(BaseModel):
    """A record, its evidence, and the provenance of both."""

    record: CourtRecord
    method: Method
    backend: str = Field(
        description="Backend identifier, e.g. 'rules', 'anthropic', 'local'."
    )
    evidence: dict[str, Evidence] = Field(
        default_factory=dict,
        description=(
            "Keyed by dotted field path, e.g. 'case_number', "
            "'judgment.amount', 'defendants.0.name'."
        ),
    )
    flags: list[str] = Field(
        default_factory=list,
        description=(
            "Named review flags, e.g. 'no_defendant_address', 'low_ocr_conf', "
            "'defendant_equals_attorney'. An empty list means every check "
            "passed. A flagged document belongs in the review queue; it is "
            "never silently guessed at."
        ),
    )
    document: DocumentInfo | None = None

    def ungrounded_fields(self) -> list[str]:
        """Field paths whose evidence was not found in the source text."""
        return [path for path, ev in self.evidence.items() if not ev.grounded]


class AIExtraction(BaseModel):
    """What a language model is asked to return.

    Deliberately flatter than `Extraction`. The model fills the record and a
    flat quote map; the backend does the grounding check and assembles the
    `Extraction`. Asking the model to also report offsets or confidence would
    invite it to invent both.
    """

    record: CourtRecord
    evidence: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "For each field you populated, the verbatim text from the document "
            "that supports it. Key by dotted field path. Quote exactly, "
            "including punctuation and capitalization. Do not paraphrase."
        ),
    )
