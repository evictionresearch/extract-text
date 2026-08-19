"""Address similarity, the metric the validation work is scored on.

Ported from the ERN validation harness (`validate.py`), which follows the
2024 Cityscape paper: a normalized Levenshtein ratio between two address
strings, with 0.7 or above counted as a same-street match. Edit distance
counts how many single-character changes turn one string into the other; the
ratio scales that by the combined length, so 1.0 means identical and 0.0
means nothing in common.

Used two ways: to score extractions against hand-labeled truth, and in batch
runs to compare the deterministic and AI answers for the same document so
disagreements can be flagged for review.
"""

from __future__ import annotations

import re


def norm(s: str) -> str:
    """Comparison normal form: lowercase alphanumerics, single spaces,
    common suffix abbreviations expanded so 'Pl'/'Place' agree."""
    s = s.lower()
    s = re.sub(r"[^a-z0-9#]+", " ", s)
    expansions = {
        "ave": "avenue", "av": "avenue", "st": "street", "rd": "road",
        "dr": "drive", "ln": "lane", "blvd": "boulevard", "pl": "place",
        "ct": "court", "cir": "circle", "hwy": "highway", "pkwy": "parkway",
        "ter": "terrace", "sq": "square", "apt": "#", "unit": "#", "ste": "#",
        "n": "north", "s": "south", "e": "east", "w": "west",
        "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
        "wa": "washington", "wash": "washington",
    }
    toks = [expansions.get(t, t) for t in s.split()]
    return " ".join(toks)


def lev(a: str, b: str) -> int:
    """Plain dynamic-programming Levenshtein distance."""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ratio(a: str, b: str) -> float:
    """Levenshtein ratio as in the paper: (lensum - dist) / lensum."""
    if not a and not b:
        return 1.0
    d = lev(a, b)
    return (len(a) + len(b) - d) / (len(a) + len(b))


def address_similarity(a: str | None, b: str | None) -> float | None:
    """Ratio between two addresses in comparison normal form.

    None when either side is missing: absence is a coverage question, not a
    similarity of zero.
    """
    if not a or not b:
        return None
    return round(ratio(norm(a), norm(b)), 3)


SAME_STREET_THRESHOLD = 0.7
