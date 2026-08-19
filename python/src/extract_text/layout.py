"""Words with page positions, and the geometry that makes rules work.

Ported from the Eviction Research Network's Washington scanner
(`wa_doc_scan.py`, validated against hand-labeled addresses July 2026). The
central idea is that every word carries its position on the page, normalized
to 0-1 in both axes, so extraction rules can reason about *where* text sits
rather than only what it says.

That is also what fixes the failure the 2024 Cityscape paper documented:
court pleading paper prints a rail of line numbers (1-26) down the left
margin, and flat OCR text interleaves those digits into whatever sits beside
them, so "123 4th Street S" becomes "123 4th Street S 17 18 Seattle". With
positions, the rail is identified by geometry and removed before any text is
assembled.
"""

from __future__ import annotations

import re


class Word:
    """One word on a page. Coordinates are normalized 0-1, origin top-left."""

    __slots__ = ("conf", "page", "text", "x0", "x1", "y0", "y1")

    def __init__(self, page, x0, y0, x1, y1, text, conf=100.0):
        self.page, self.x0, self.y0, self.x1, self.y1 = page, x0, y0, x1, y1
        self.text, self.conf = text, conf

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Word(p{self.page} {self.text!r} @{self.x0:.2f},{self.y0:.2f})"


class Line:
    """A y-clustered row of words on one page; coordinates normalized 0-1."""

    __slots__ = ("page", "words", "x0", "x1", "y0", "y1")

    def __init__(self, words):
        self.words = sorted(words, key=lambda w: w.x0)
        self.page = words[0].page
        self.x0 = min(w.x0 for w in words)
        self.y0 = min(w.y0 for w in words)
        self.x1 = max(w.x1 for w in words)
        self.y1 = max(w.y1 for w in words)

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    @property
    def conf(self):
        return sum(w.conf for w in self.words) / len(self.words)


def cluster_lines(words):
    """Group words into visual lines by vertical overlap (deterministic)."""
    lines = []
    for w in sorted(words, key=lambda w: (w.page, w.y0, w.x0)):
        placed = False
        for ln in lines:
            if ln[0].page != w.page:
                continue
            # overlap test against the running line's vertical band
            ly0 = min(x.y0 for x in ln)
            ly1 = max(x.y1 for x in ln)
            mid = (w.y0 + w.y1) / 2
            if ly0 - 0.004 <= mid <= ly1 + 0.004:
                ln.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    return sorted((Line(ln) for ln in lines), key=lambda l: (l.page, l.y0, l.x0))


def strip_line_number_rail(words):
    """Drop the pleading-paper rail before line clustering: 1-2 digit integers
    (1-28) whose entire box sits in the left (or right) margin band. Removing
    them at the word level also un-glues lines OCR merged with the rail
    ("17 18 TO: ...") — the structural fix for the row-numbers-inside-
    addresses failure documented in the Cityscape paper.

    OCR sometimes mangles rail digits into confusable letters ("l4", "t6",
    "2L" for 14/16/21) which the digits-only pattern misses; in the LEFT band
    only, short digit-bearing tokens made entirely of digit-confusable
    characters are dropped too. The at-least-one-digit requirement protects
    real words ("TO" on a tight-margin scan never contains a digit)."""
    keep = []
    for w in words:
        in_left = w.x1 < 0.145
        if re.fullmatch(r"\d{1,2}", w.text) and 1 <= int(w.text) <= 28 \
                and (in_left or w.x0 > 0.92):
            continue
        if in_left and re.fullmatch(r"[0-9OoIiLl|SsZzBGTtJj]{1,2}", w.text) \
                and any(c.isdigit() for c in w.text):
            continue
        keep.append(w)
    return keep


def page_text(lines, page=None):
    """Assembled text, one clustered line per row, optionally for one page."""
    if page is None:
        return "\n".join(l.text for l in lines)
    return "\n".join(l.text for l in lines if l.page == page)
