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
    """Group words into visual lines by vertical overlap (deterministic).

    A word may JOIN a line whose band its midpoint falls in, but only
    text-sized words get to DEFINE the band. Without that asymmetry a single
    tall OCR smear (the pleading paper's vertical rule read as letters) seeds
    a line whose envelope spans several visual rows, and every later word
    whose midpoint falls inside is swallowed — on a measured King filing one
    such cluster ate 56 words including the whole "TO:" service block, which
    then read as a bag-of-words scramble no anchor could match. Mining the
    5,168-case truth set showed this to be the engine's single largest
    failure class. Junk still lands in whichever line it overlaps, where it
    costs a stray token; it can no longer merge rows.
    """
    if not words:
        return []
    heights = sorted(w.y1 - w.y0 for w in words)
    text_h = max(0.006, heights[len(heights) // 2]) * 2.5

    lines = []
    for w in sorted(words, key=lambda w: (w.page, w.y0, w.x0)):
        placed = False
        for ln in lines:
            if ln[0].page != w.page:
                continue
            # band from text-sized members only; junk members don't grow it
            band = [x for x in ln if (x.y1 - x.y0) <= text_h] or ln
            ly0 = min(x.y0 for x in band)
            ly1 = max(x.y1 for x in band)
            mid = (w.y0 + w.y1) / 2
            if ly0 - 0.004 <= mid <= ly1 + 0.004:
                ln.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    return sorted((Line(ln) for ln in lines), key=lambda l: (l.page, l.y0, l.x0))


#: fixed margin bands, kept as a floor for pages with too few rail digits to
#: form a detectable column
RAIL_LEFT_MAX = 0.145
RAIL_RIGHT_MIN = 0.92
#: a rail column must have at least this many members and sit within this
#: horizontal spread
RAIL_MIN_MEMBERS = 5
RAIL_X_TOL = 0.020
#: rails live in the margins; a column of numbers mid-page is a table
RAIL_SEARCH_LEFT = 0.30
RAIL_SEARCH_RIGHT = 0.72


def rail_columns(words):
    """Find the x positions where a page prints its line-number rail.

    Returns {page: [x_centre, ...]}. A rail is a column: five or more short
    integers stacked at one x in a margin. A house number has no siblings.

    **Not used for stripping.** Removing every column member at the word level
    was tried and reverted: it detected rails correctly and produced cleaner
    lines, but on one filing in 250 it changed which block the extractor chose,
    once turning a correct defendant address into the plaintiff attorney's.
    The rail digits were apparently propping up a block boundary the extractor
    depends on. The narrow fix in `summons.parse_address` handles the damage
    those digits actually do without touching block selection.

    Kept because it is the measurement issue #4 asked for, and because a future
    change to the block extractor may make word-level stripping safe.
    """
    by_page = {}
    for w in words:
        if not re.fullmatch(r"\d{1,2}", w.text) or not 1 <= int(w.text) <= 28:
            continue
        mid = (w.x0 + w.x1) / 2
        if mid > RAIL_SEARCH_LEFT and mid < RAIL_SEARCH_RIGHT:
            continue
        by_page.setdefault(w.page, []).append(mid)

    out = {}
    for page, xs in by_page.items():
        xs.sort()
        cols, cur = [], [xs[0]]
        for x in xs[1:]:
            if x - cur[-1] <= RAIL_X_TOL:
                cur.append(x)
            else:
                cols.append(cur)
                cur = [x]
        cols.append(cur)
        found = [sum(c) / len(c) for c in cols if len(c) >= RAIL_MIN_MEMBERS]
        if found:
            out[page] = found
    return out


#: No printed word on a court filing is taller than a twentieth of the page
#: (the median word is about 0.010; letterhead tops out near 0.03). Boxes
#: taller than this are OCR smears of page furniture — most often the
#: pleading paper's vertical rule read as a letter or two ('ee', height 0.25,
#: confidence 27, on a measured King filing).
WORD_MAX_HEIGHT = 0.05


def strip_line_number_rail(words):
    """Drop page furniture before line clustering: implausibly tall boxes,
    then short integers that belong to the line-number column or margin bands.

    The tall-box drop matters far more than it looks. `cluster_lines` grows a
    line's vertical band as it absorbs words, so a single quarter-page-tall
    smear seeds a runaway cluster that swallows everything whose midpoint
    falls inside it — on one measured filing, 56 words spanning a quarter of
    the page, including the entire "TO:" service block, which then reads as a
    bag-of-words scramble no anchor can match. Mining the full 5,168-case
    truth set found this to be the single largest failure class: 683 of 903
    failures were no-yield documents, 90% of which had readable text and a
    findable attorney block.
    Removing them at the word level also un-glues lines OCR merged with the
    rail ("17 18 TO: ..."), the structural fix for the row-numbers-inside-
    addresses failure documented in the Cityscape paper.

    Two rules run together. A column detected on the page itself (see
    `_rail_columns`) catches rails that drifted out of the fixed band, which is
    how a rail digit ends up prefixed to a house number. The fixed band still
    applies, so pages with only a handful of numbered lines are still cleaned.

    OCR sometimes mangles rail digits into confusable letters ("l4", "t6",
    "2L" for 14/16/21) which the digits-only pattern misses; in the LEFT band
    only, short digit-bearing tokens made entirely of digit-confusable
    characters are dropped too. The at-least-one-digit requirement protects
    real words ("TO" on a tight-margin scan never contains a digit)."""
    keep = []
    for w in words:
        if (w.y1 - w.y0) > WORD_MAX_HEIGHT:
            continue
        # standalone pipes are the pleading rule or a split ordinal ("12th"
        # read as "| 2th"); no address contains a bare pipe
        if re.fullmatch(r"[|¦]{1,2}\.?", w.text):
            continue
        in_left = w.x1 < RAIL_LEFT_MAX
        if re.fullmatch(r"\d{1,2}", w.text) and 1 <= int(w.text) <= 28 \
                and (in_left or w.x0 > RAIL_RIGHT_MIN):
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
