"""Field contract shared by every backend and by the R wrapper.

These models are the source of truth. `schema/court_record.schema.json` is
generated from them by `scripts/build_schema.py`; do not hand-edit that file.

The design separates three things that extraction pipelines usually mash
together:

  CourtRecord   what was found
  Evidence      the verbatim source text each field was read from
  Extraction    the two above, plus which backend produced them

Keeping evidence separate is what makes a language model's output auditable.
The model returns the quote it based each field on, and the backend then checks
that the quote actually occurs in the source document. A field whose evidence
cannot be located in the source is not trustworthy, whatever the model asserted.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

Method = Literal["deterministic", "ai"]


class Party(BaseModel):
    """A named party to the action."""

    name: str
    role: Literal["plaintiff", "defendant", "other"]
    is_business: Optional[bool] = Field(
        default=None,
        description=(
            "True when the party appears to be a company, LLC, trust, or other "
            "entity rather than a natural person."
        ),
    )
    attorney: Optional[str] = None
    address: Optional[str] = None


class Judgment(BaseModel):
    """The disposition of the case, where one is recorded."""

    type: Optional[
        Literal[
            "possession",
            "money",
            "possession_and_money",
            "default",
            "dismissal",
            "stipulation",
            "other",
        ]
    ] = None
    date: Optional[dt.date] = None
    amount: Optional[float] = Field(
        default=None, description="Money judgment in dollars, if any."
    )
    in_favor_of: Optional[Literal["plaintiff", "defendant"]] = None


class CourtRecord(BaseModel):
    """A single eviction or unlawful detainer case.

    Every field is optional. Court documents vary enormously by jurisdiction and
    a missing field is information, not an error. Distinguishing "the document
    does not say" from "the extractor failed to read it" is the job of the
    comparison report, not the schema.
    """

    case_number: Optional[str] = None
    court_name: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = Field(
        default=None,
        description=(
            "State as written on the document, which may be a full name or an "
            "abbreviation. Normalizing to USPS codes is a downstream concern."
        ),
    )
    case_type: Optional[str] = Field(
        default=None,
        description=(
            "Case type as written on the document, e.g. 'Unlawful Detainer', "
            "'Forcible Entry and Detainer', 'Eviction'. Do not normalize."
        ),
    )
    filing_date: Optional[dt.date] = None
    plaintiffs: list[Party] = Field(default_factory=list)
    defendants: list[Party] = Field(default_factory=list)
    amount_claimed: Optional[float] = Field(
        default=None, description="Amount sought by the plaintiff, in dollars."
    )
    judgment: Optional[Judgment] = None
    disposition: Optional[str] = None
    disposition_date: Optional[dt.date] = None


class Evidence(BaseModel):
    """Where in the source document a single field came from."""

    quote: str = Field(
        description="Verbatim span of source text supporting the field."
    )
    span: Optional[tuple[int, int]] = Field(
        default=None,
        description=(
            "Character offsets of the quote in the source text. Populated by "
            "the deterministic engine directly, and by the AI backends by "
            "locating the returned quote."
        ),
    )
    grounded: bool = Field(
        default=False,
        description=(
            "True when the quote was found verbatim in the source text. A "
            "false value on an AI extraction means the model produced a quote "
            "the document does not contain."
        ),
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
