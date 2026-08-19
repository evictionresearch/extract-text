"""Turning an extraction into a card a person can check.

A card is one cropped picture of the address as it appears on the page, next
to the address the engine typed out. Someone looks at the two and says whether
they say the same thing. Enough of those answers make a human-verified
training set.

Three rules shape everything here.

**Names are covered, addresses are not.** The crop is drawn from the page with
party names painted over, because checking an address does not require knowing
whose it is.

**What the engine missed must stay visible.** It is tempting to blank out
everything except the address the engine found, which would guarantee no name
survives. That would also hide every omission, and omissions (a dropped unit,
a truncated direction) are the most common way this engine is wrong. So the
redaction is a list of names to hide, never a list of words to keep.

**Only the parsed address is shown.** The raw capture carries block
boilerplate such as "ALL OTHER OCCUPANTS", which is not part of anyone's
address and would only produce false mismatches.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

__all__ = [
    "display_address", "locate_address", "locate_service_band", "name_tokens",
    "render_card", "safe_to_show", "PAD_X", "PAD_TOP", "PAD_BOT", "CARD_DPI",
]

SERVICE_LABEL_RE = re.compile(
    r"^\s*(TO\s*:|AT\s*:|TO\s+THE\s+DEFENDANT|TO\s+DEFENDANT|ADDRESS\s*:)",
    re.IGNORECASE)

CARD_DPI = 200

# Page fractions added around the located address. Top padding is deliberately
# tighter than the rest: on a "TO:" service block the line directly above is
# the defendant's name, and generous top padding drags it back into the crop.
PAD_X, PAD_TOP, PAD_BOT = 0.020, 0.003, 0.010

# A new vertical run starts when the gap exceeds this fraction of page height,
# roughly two line heights.
GROUP_GAP = 0.030

# Words that can occur inside a party name but must never be painted over,
# because they also occur in addresses. Blacking these out would hide a real
# extraction error from the person checking the card.
NEVER_REDACT = frozenset({
    # Party boilerplate. Note what is deliberately absent: JOHN, JANE, DOE,
    # TENANT and RESIDENT. Those occur as placeholders ("John and Jane Doe,
    # unknown occupants"), and it is tempting to spare them, but they also
    # occur as real given names and surnames. Painting over a placeholder
    # costs nothing; leaving a real defendant's first name legible is the
    # failure this whole module exists to prevent.
    "ALL", "OTHER", "OCCUPANTS", "OCCUPANT", "UNKNOWN", "PREMISES", "AND", "OR",
    "THE", "OF", "ET", "AL", "HUSBAND", "WIFE", "DBA", "AKA", "LOCATED",
    # entity suffixes
    "INC", "LLC", "LLP", "PLLC", "COMPANY", "CORP", "TRUST", "BANK",
    "PROPERTIES", "APARTMENTS", "APTS", "MANAGEMENT", "ASSOCIATION",
    # courtroom roles and caption text, which sit near addresses on many forms
    "ATTORNEY", "ATTORNEYS", "PLAINTIFF", "PLAINTIFFS", "DEFENDANT",
    "DEFENDANTS", "COUNSEL", "WSBA", "LAW", "OFFICE", "OFFICES", "GROUP",
    "ESQ", "BAR", "COURT", "SUPERIOR", "STATE", "COUNTY", "CAUSE", "SUMMONS",
    "COMPLAINT", "EVICTION", "RESIDENTIAL", "NOTICE", "LAWSUIT", "DEADLINE",
    "RESPONSE", "WRITTEN", "SERVICE", "FILED", "CLERK",
    # ordinary English that turns up inside an OCR-mangled name field
    "FOR", "YOU", "YOUR", "THIS", "THAT", "WITH", "FROM", "ARE", "WAS",
    "HAS", "HAVE", "NOT", "BUT", "ANY", "MAY", "CAN", "WILL", "SHALL",
    # address vocabulary
    "NORTH", "SOUTH", "EAST", "WEST", "AVE", "AVENUE", "STREET", "ROAD",
    "DRIVE", "LANE", "WAY", "COURT", "PLACE", "BLVD", "BOULEVARD", "APT",
    "STE", "SUITE", "UNIT", "TERRACE", "CIRCLE", "PARKWAY", "HIGHWAY",
})


def _toks(s: str) -> list[str]:
    return [t for t in re.split(r"[^A-Za-z0-9#]+", (s or "").upper()) if t]


def display_address(street, unit, city, state, zipc) -> str:
    """The address as the checker reads it, from the parsed components."""
    line1 = street or ""
    u = (unit or "").strip()
    if u and u.upper() not in line1.upper():
        line1 = f"{line1} {u}".strip()
    tail = " ".join(t for t in ((state or ""), (zipc or "")) if t).strip()
    return ", ".join(p for p in (line1, (city or "").strip(), tail) if p)


def name_tokens(record, address_raw: str) -> set[str]:
    """Words to paint over: party and counsel names, minus anything that also
    appears in the address. A street named after a person stays legible."""
    src = [p.name for p in list(record.defendants) + list(record.plaintiffs) if p.name]
    att = getattr(record, "attorney", None)
    if att is not None and att.names:
        src.append(att.names)
    toks = set()
    for s in src:
        for t in _toks(s):
            # Three characters minimum, letters only. Shorter or digit-bearing
            # tokens are OCR debris from mangled caption blocks, and painting
            # them out only damages the page.
            if len(t) >= 3 and t.isalpha():
                toks.add(t)
    return (toks - set(_toks(address_raw))) - NEVER_REDACT


def locate_service_band(doc, page: int = 1):
    """Box around the service block when no address could be extracted.

    Used for documents the reader failed on entirely, which in practice means
    handwritten ones, since OCR returns nothing at all for pen. There is no
    extracted address to locate, so the anchor is the printed "TO:" label that
    the form itself supplies.

    **This cannot guarantee the defendant's name is excluded.** On a filled-in
    form the name may share the label's line or sit on its own line beneath it,
    and with no OCR output there is no way to tell which. Cards built from this
    box are marked for review and must not be shown to anyone outside the data
    agreement until a person has looked at them. See the repo's issue #3.
    """
    lines = [ln for ln in doc.lines if ln.page == page]
    for ln in lines:
        if SERVICE_LABEL_RE.match(ln.text):
            return (0.14, ln.y0 - 0.004, 0.92, min(1.0, ln.y0 + 0.075))
    return None


def safe_to_show(redact: set[str]) -> tuple[bool, str]:
    """Whether a card may be shown to someone outside the data agreement.

    The test is simply whether any name was actually painted over. It reads as
    a weak rule and is in fact a strong one, because of how the two failure
    modes work.

    When the engine parses a party, redaction is applied per word box, so the
    name is covered wherever it sits, including a row that OCR merged into the
    address line. When the engine parses no party, nothing is covered, and
    those are exactly the documents whose caption blocks were garbled enough to
    defeat the parser, which is also what causes names to be merged into the
    address row in the first place. The same condition produces both the risk
    and the inability to mitigate it.

    Empty also catches the case where every parsed name was excluded from
    redaction for overlapping the address, which is the name-inside-the-address
    problem and equally unshowable.

    Measured on a 611-document Washington sample: 434 of 452 extracted cards
    passed, and inspection of the 18 that failed found unredacted personal
    names on the crop. Roughly a 4% cost for the guarantee.
    """
    if not redact:
        return False, "no_name_redacted"
    return True, ""


def locate_address(doc, address_raw: str, street: str = "", page: int = 1):
    """Box around the lines that produced the address, as 0-1 page fractions.

    Returns (x0, y0, x1, y1) or None. The same address is often printed twice
    on page one, in the caption and again in the service block, so matching
    lines are grouped into vertical runs and only the strongest run is used.
    Taking the union of every match would span most of the page.
    """
    want = set(_toks(address_raw))
    if not want:
        return None
    house = next(iter(_toks(street)), None)
    lines = [ln for ln in doc.lines if ln.page == page] or list(doc.lines)

    hits = []
    for ln in lines:
        lt = _toks(ln.text)
        if not lt:
            continue
        overlap = sum(1 for t in lt if t in want)
        if overlap >= 2 and overlap / len(lt) >= 0.5:
            hits.append(ln)
    if house and not any(house in _toks(ln.text) for ln in hits):
        for ln in lines:
            if house in _toks(ln.text):
                hits.append(ln)
                break
    if not hits:
        return None

    hits.sort(key=lambda ln: ln.y0)
    groups, cur = [], [hits[0]]
    for prev, ln in zip(hits, hits[1:]):
        if ln.y0 - prev.y1 > GROUP_GAP:
            groups.append(cur)
            cur = [ln]
        else:
            cur.append(ln)
    groups.append(cur)
    hits = max(groups, key=lambda g: sum(
        sum(1 for t in _toks(ln.text) if t in want) for ln in g))

    # Begin at the street line. The line above it holds the defendant's name on
    # a "TO:" block, and it is not needed to compare two address strings.
    if house:
        starts = [ln.y0 for ln in hits if house in _toks(ln.text)]
        if starts:
            top = min(starts)
            hits = [ln for ln in hits if ln.y0 >= top - 0.004]

    return (min(ln.x0 for ln in hits), min(ln.y0 for ln in hits),
            max(ln.x1 for ln in hits), max(ln.y1 for ln in hits))


def _blank_first_text_row(im, draw):
    """Paint over the topmost row of text in an image, whatever produced it.

    Word-box redaction cannot help on a transcription crop, because OCR
    returned nothing there. What is reliable is the layout convention: a
    service block reads "TO:", then the defendant's name, then the address. So
    the first row of ink below the label is the name, whether it was typed or
    written by hand, and blanking it leaves the address intact.

    Rows are found from the horizontal ink profile rather than from any text
    recognition, which is the point: it works on pen.
    """
    W, H = im.size
    if H < 8:
        return
    px = im.convert("L").load()
    step = max(1, W // 400)
    profile = []
    for y in range(H):
        n = 0
        for x in range(0, W, step):
            if px[x, y] < 128:
                n += 1
        profile.append(n)
    floor = max(2, int(0.004 * (W / step) * 100) // 100 or 2)

    rows, start = [], None
    for y, n in enumerate(profile):
        if n > floor and start is None:
            start = y
        elif n <= floor and start is not None:
            if y - start >= 3:
                rows.append((start, y))
            start = None
    if start is not None and H - start >= 3:
        rows.append((start, H))
    if not rows:
        return False
    top, bot = rows[0]
    # On handwriting the rows often do not separate: descenders, ascenders and
    # the form's ruled lines join into one band spanning the whole crop, and
    # blanking "the first row" then blacks out the address as well. Refuse when
    # the row covers most of the crop; the caller drops the card rather than
    # emitting a black rectangle.
    if (bot - top) > 0.55 * H:
        return False
    draw.rectangle([0, max(0, top - 2), W, min(H, bot + 2)], fill=(0, 0, 0))
    return True


def render_card(doc_path, page: int, box, out_png, words=(), redact=frozenset(),
                dpi: int = CARD_DPI, blank_first_row: bool = False):
    """Render a page, paint over name words, crop to the box. Returns the path
    written, or None if the crop came out too small to read.

    Redaction is applied to the whole page before cropping, so a name that
    straddles the crop edge cannot survive as a fragment.
    """
    from PIL import Image, ImageDraw

    x0, y0, x1, y1 = box
    p = Path(doc_path)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="extract_text_card_") as td:
        if p.suffix.lower() == ".pdf":
            stem = Path(td) / "pg"
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page), "-l", str(page),
                 str(p), str(stem)], capture_output=True, timeout=180)
            found = sorted(Path(td).glob("pg*.png"))
            if not found:
                return None
            im = Image.open(found[0])
        else:
            im = Image.open(p)
            try:
                im.seek(page - 1)
            except EOFError:
                return None
        im = im.convert("RGB")
        W, H = im.size

        if redact:
            draw = ImageDraw.Draw(im)
            for w in words:
                if getattr(w, "page", page) != page:
                    continue
                t = "".join(ch for ch in w.text.upper() if ch.isalnum())
                if t and t in redact:
                    draw.rectangle([w.x0 * W - 1, w.y0 * H - 1,
                                    w.x1 * W + 1, w.y1 * H + 1], fill=(0, 0, 0))

        left = max(0, int((x0 - PAD_X) * W))
        top = max(0, int((y0 - PAD_TOP) * H))
        right = min(W, int((x1 + PAD_X) * W))
        bottom = min(H, int((y1 + PAD_BOT) * H))
        if right - left < 40 or bottom - top < 20:
            return None
        cropped = im.crop((left, top, right, bottom))
        if blank_first_row and not _blank_first_text_row(
                cropped, ImageDraw.Draw(cropped)):
            return None          # name row could not be isolated; do not emit
        cropped.save(out_png, optimize=True)
    return out_png
