"""Regular expressions for reading fields off a court document.

Patterns are grouped by field and tried in order, so put the most specific
first. Each pattern must define exactly one capturing group named `value`; the
engine uses that group's span to record where the value came from.

Jurisdictions differ enough that a single pattern set will not hold everywhere.
The intended path is a base set here plus per-state overrides registered through
`PATTERNS` copies, following the same copy-adapt approach the state pipelines
use rather than one shared engine that silently changes behavior under a state.
"""

from __future__ import annotations

import re

Pattern = re.Pattern[str]


def _c(pattern: str) -> Pattern:
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


# Common date shapes seen on filings and dockets. Kept as a fragment so field
# patterns can embed it without repeating themselves.
_DATE = (
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2})"
)

_MONEY = r"\$\s?[\d,]+(?:\.\d{2})?"


PATTERNS: dict[str, list[Pattern]] = {
    "case_number": [
        # a case number always carries a digit; without that requirement the
        # notice sentence "if no case number has been assigned" yielded a
        # word fragment as the number (2026-09-30 new-user test)
        _c(r"\bCase\s*(?:No\.?|Number|#)\s*[:\-]?\s*(?P<value>(?=[A-Z0-9\-/]*\d)[A-Z0-9][A-Z0-9\-/]{3,24})"),
        _c(r"\bDocket\s*(?:No\.?|Number|#)\s*[:\-]?\s*(?P<value>(?=[A-Z0-9\-/]*\d)[A-Z0-9][A-Z0-9\-/]{3,24})"),
    ],
    "court_name": [
        _c(r"^\s*(?P<value>(?:IN THE )?[A-Z][A-Za-z .']+ COURT(?: OF [A-Z][A-Za-z .']+)?)\s*$"),
    ],
    "county": [
        _c(r"\bCOUNTY\s+OF\s+(?P<value>[A-Z][A-Za-z .'\-]+)"),
        _c(r"\b(?P<value>[A-Z][A-Za-z .'\-]+)\s+COUNTY\b"),
    ],
    "state": [
        _c(r"\bSTATE\s+OF\s+(?P<value>[A-Z][A-Za-z ]+)"),
    ],
    "case_type": [
        _c(r"(?P<value>Unlawful\s+Detainer|Forcible\s+Entry\s+and\s+Detainer|Forcible\s+Detainer|Eviction|Summary\s+Ejectment|Landlord[/\s-]+Tenant)"),
    ],
    "filing_date": [
        _c(rf"\bFil(?:ed|ing)\s*(?:on|Date)?\s*[:\-]?\s*(?P<value>{_DATE})"),
        _c(rf"\bDate\s+Filed\s*[:\-]?\s*(?P<value>{_DATE})"),
    ],
    "amount_claimed": [
        _c(rf"\b(?:Amount\s+(?:Claimed|Demanded|in\s+Controversy)|Total\s+Due|Past\s+Due\s+Rent)\s*[:\-]?\s*(?P<value>{_MONEY})"),
    ],
    "judgment.date": [
        _c(rf"\bJudgment\s+(?:Entered|Date)\s*[:\-]?\s*(?P<value>{_DATE})"),
    ],
    "judgment.amount": [
        _c(rf"\bJudgment\s+(?:Amount|for)\s*[:\-]?\s*(?P<value>{_MONEY})"),
    ],
    "disposition": [
        _c(r"\bDisposition\s*[:\-]?\s*(?P<value>[A-Za-z][A-Za-z ,'\-]{2,60})"),
    ],
    "disposition_date": [
        _c(rf"\bDisposition\s+Date\s*[:\-]?\s*(?P<value>{_DATE})"),
    ],
}


# Party blocks are read separately. Captions come in two shapes, and the
# labeled one must be tried first: its designator lines sit between the names
# and the versus token, so the inline pattern would otherwise capture the word
# "Plaintiffs" as a party name.
#
#   labeled                          inline
#   ACME HOLDINGS LLC,               Acme Holdings LLC v. Jordan Rivera
#                     Plaintiffs,
#   v.
#   JORDAN RIVERA,
#                     Defendants.
#
# Known limitation: each side must fit on one line. Captions that wrap a long
# list of names across lines will capture only the last line.
CAPTIONS: list[Pattern] = [
    _c(
        r"(?P<plaintiffs>[^\n]{2,300}?),?[ \t]*\n\s*Plaintiff(?:s|\(s\))?[,.]?[ \t]*\n\s*"
        r"(?:-?v\.?|vs\.?|versus)-?[ \t]*\n?\s*"
        r"(?P<defendants>[^\n]{2,300}?),?[ \t]*\n\s*Defendant(?:s|\(s\))?[,.]"
    ),
    _c(
        r"^(?P<plaintiffs>[^\n]{2,200}?)[ \t]*,?[ \t]+(?:v\.?|vs\.?|versus)[ \t]+"
        r"(?P<defendants>[^\n]{2,200}?)[ \t]*$"
    ),
]

# Split a side into individual names. Periods are deliberately not treated as
# separators or stripped, so "RIVERSIDE PROPERTIES INC." keeps its suffix.
PARTY_SPLIT = re.compile(r"\s*(?:,|\band\b|&)\s*", re.IGNORECASE)

# Suffixes that mark a party as an entity rather than a natural person.
BUSINESS_MARKERS = _c(
    r"\b(?:LLC|L\.L\.C\.|Inc\.?|Incorporated|Corp\.?|Corporation|Company|Co\.|"
    r"L\.?P\.?|LLP|Trust|Properties|Partners|Associates|Management|Holdings|"
    r"Apartments|Realty|Group)\b"
)
