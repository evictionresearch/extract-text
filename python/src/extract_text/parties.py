"""Party-name cleanup shared by both engines.

Plain text rules, no model: the deterministic engine uses these on the names
it reads from the service block, and the AI engine uses the same rules on the
names the model returns, so a name is cleaned the same way whichever engine
read it.
"""

from __future__ import annotations

import re

# Trailing group terms a caption adds after the named defendants. The vision
# prompt already lists these and asks the model to drop them; four of the six
# models benched on 2026-08-20 returned them anyway. Because names are split
# on "and", a clause left in place became a second, phantom defendant named
# "ALL OTHER OCCUPANTS". Stripping it in code is deterministic, so the output
# no longer depends on a model following an instruction. The service block
# read by the deterministic engine carries the same terms ("et al."), so it
# strips them too.
_GROUP_TERM_RE = re.compile(
    r"""
    [\s,;&]*                                  # separator before the clause
    (?:\band\b\s*)?                           # an optional joining "and"
    (?:
        any\s+and\s+all\s+other[\w\s]*        # "any and all other residing..."
      | all\s+(?:other\s+)?occupants?          # "all occupants"
      | all\s+others?                           # "all others"
      | husband\s+and\s+wife
      | (?:john|jane)\s*/\s*(?:john|jane)\s+does?   # "John/Jane Doe"
      | (?:john|jane)\s+does?                   # "Jane Doe"
      | does?\s*\d+\s*(?:-|through|to)\s*\d+     # "Does 1-10"
      | et\.?\s*al\.?
      | et\.?\s*ux\.?
    )
    \s*\.?\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _strip_group_terms(text: str) -> tuple[str, bool]:
    """The stripping itself, plus whether a group term was what came off.

    Trailing punctuation is trimmed on the same pass, and is far more common
    than a group term, so the two are reported separately. Only a real term
    should raise a flag that claims one was found.
    """
    current = text
    found = False
    while True:
        shorter = _GROUP_TERM_RE.sub("", current)
        if shorter != current:
            found = True
        shorter = shorter.strip(" ,;&")
        if shorter == current:
            break
        current = shorter
    return (current or text), found


# Words that name a business's legal form rather than the business, so
# "EXAMPLE RIDGE APARTMENTS, LLC" and "Example Ridge Apartments" compare equal.
_ENTITY_WORDS = {
    "the", "llc", "l", "c", "inc", "incorporated", "co", "corp", "corporation",
    "company", "lp", "llp", "ltd", "limited", "liability", "pllc", "a",
    "partnership", "dba",
}


# The descriptive clause a caption hangs on a business plaintiff: "EXAMPLE
# LLC, a Washington limited liability company".
_ENTITY_CLAUSE_RE = re.compile(r"(?:,\s*|\s+)an?\s+(?:[a-z]+\s+)?(?:limited|corporation|"
                               r"company|partnership|general|non-?profit|public|"
                               r"municipal|housing)\b.*$", re.IGNORECASE)


def _party_key(name: str) -> str:
    name = _ENTITY_CLAUSE_RE.sub("", name)
    words = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
    return " ".join(w for w in words if w not in _ENTITY_WORDS)


def drop_plaintiff_matches(defendants: list[str], plaintiffs: list[str]):
    """Remove any defendant name that is the plaintiff's name.

    In an unlawful detainer the landlord is never also a defendant, so a
    "defendant" matching the plaintiff is a misread: the reader took a line
    from the plaintiff's side of the page (a return address block, a "TO:"
    line that runs on into the landlord's name) as a party served. Matching is
    exact after dropping case, punctuation, and legal-form words, so two
    people who merely share a surname are never merged.

    Returns (kept, dropped)."""
    keys = {_party_key(p) for p in plaintiffs if _party_key(p)}
    kept, dropped = [], []
    for name in defendants:
        (dropped if _party_key(name) in keys else kept).append(name)
    return kept, dropped


# Labels and leftovers that are never a party: a bare "TO:", a role word, a
# line that is only punctuation
_LABEL_RE = re.compile(r"^(?:TO|DEFENDANTS?|PLAINTIFFS?|ALL|AND|OCCUPANTS?)\s*:?$", re.IGNORECASE)
# a leading run of OCR debris: rail digits and box borders read as short
# tokens ("1]", "=)", "ao", "ht") before the name proper. Initials and short
# capitalised particles ("A.", "MC") are kept.
_LEADING_JUNK_RE = re.compile(r"^(?:(?![A-Z]{1,2}\.?(?:\s|$))\S{1,2}\s+)+")
_DBA_RE = re.compile(r"^(?:d/?b/?a|a/?k/?a|f/?k/?a)\b", re.IGNORECASE)


def clean_party_name(name: str) -> str:
    """One party name as printed, without the debris a scan or a caption
    hangs on it: OCR junk before it, a trailing "and" or "&" that joined it
    to the next line, a parenthetical role ("(TENANT)"), and stray
    punctuation at either end."""
    name = _LEADING_JUNK_RE.sub("", (name or "").strip())
    name = re.sub(r"^TO\s*:\s*", "", name, flags=re.IGNORECASE)
    for _ in range(2):  # a role in parentheses can sit either side of the "&"
        name = re.sub(r"[\s,;]*(?:\band\b|&)\s*$", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\s*\([^)]*\)\s*$", "", name)
    return name.strip(" ,;:~*—–-")


def plausible_party_name(name: str) -> bool:
    """Whether a string can be a party at all. Letters must make up most of
    it (a rail fragment such as "1]" cannot), it must not be a label, and a
    run of lowercase words is prose from the notice, not a name."""
    if not name or _LABEL_RE.match(name):
        return False
    letters = sum(ch.isalpha() for ch in name)
    if letters < 3 or letters * 2 < len(name.replace(" ", "")):
        return False
    words = name.split()
    lower = sum(1 for w in words if w.islower())
    if len(words) >= 4 and lower * 10 >= len(words) * 6:
        return False
    return True


def finish_party_names(names: list[str]) -> list[str]:
    """Clean a list of names read from a caption or service block: debris
    off, implausible entries out, and a "DBA ..." line joined to the name
    before it, since it continues that party rather than naming another."""
    out: list[str] = []
    for raw in names:
        name = clean_party_name(raw)
        if not plausible_party_name(name):
            continue
        if _DBA_RE.match(name) and out:
            out[-1] = f"{out[-1]} {name}"
        else:
            out.append(name)
    return out


def split_listed_names(name: str) -> list[str]:
    """Split "A B, C D, and E F" into names. Only when every piece has two
    or more words, so "SMITH, JOHN" and "EXAMPLE, LLC" stay whole."""
    pieces = [p.strip(" ,;") for p in re.split(r",\s*(?:and\s+)?", name)]
    pieces = [p for p in pieces if p]
    if len(pieces) >= 2 and all(len(p.split()) >= 2 for p in pieces):
        return pieces
    return [name]
