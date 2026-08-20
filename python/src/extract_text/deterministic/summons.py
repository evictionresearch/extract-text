"""Positional extraction for eviction summons pages.

This is the validated core of the deterministic engine, ported from the
Eviction Research Network's Washington scanner (`wa_doc_scan.py`; method
lineage Thomas, Ramiller, Ren & Toomet 2024, *Cityscape* 26(1):241-259, and
scored against 5,100+ hand-labeled addresses in July 2026). It reads two
things off a summons that matter most and are easiest to get wrong:

- the **defendant service address**, the mid-page block where the tenant is
  named and served, found by an anchor ladder (first hit wins):
  `to_block` → `premises_prose` → `address_stack` → `caption_cell`
- the **plaintiff attorney block**, bottom-right, found geometrically and
  scored on firm keyword, street, city, and phone

Keeping the two separate is the whole game: the classic failure of flat-text
extraction is returning the attorney's address as the tenant's. Every rule
here exists to prevent that, and the residual case is flagged
(`defendant_equals_attorney`) rather than passed through silently.

Documents that fail a check are flagged, never guessed. The review queue and
the optional AI lane exist for those.

The geometry is tuned on Washington unlawful detainer documents from four
counties in three formats. Most anchors are plain American-court conventions
(service blocks, bottom-right signature blocks) and travel reasonably well,
but treat results in a new jurisdiction as unvalidated until you have scored
them against hand-labeled truth. See docs/manual.md, "Using this outside
Washington".
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..layout import cluster_lines
from ..schema import Address, Attorney, Evidence, Party

# ---------------------------------------------------------------------------
# constants and patterns (ported verbatim from wa_doc_scan.py)
# ---------------------------------------------------------------------------

# WA superior court case number, e.g. 25-2-00001-0 (the "2" = civil)
WA_CASE_NO_RE = re.compile(r"\b(\d{2})[- ]?2[- ]?(\d{5})[- ]?(\d)\b")

# CRT is a court abbreviation King County forms actually print ("80TH CRT
# NE"); PI is OCR's l->I misread of "Pl." — both found by truth-set mining,
# where each cost the whole address.
STREET_SUFFIX = (
    r"(?:AVE(?:NUE)?|ST(?:REET)?|STR|RD|ROAD|DR(?:IVE)?|LN|LANE|BLVD|BOULEVARD|"
    r"WAY|CT|CRT|COURT|CIR(?:CLE)?|PL(?:ACE)?|PI|PKWY|PARKWAY|HWY|HIGHWAY|"
    r"TER(?:RACE)?|LOOP|TRL|TRAIL|XING|CROSSING)"
)
# Longest alternatives first: the regex engine takes the first branch that
# matches, so with N before NE the direction "NE" ends at "N" and the stray
# "E" corrupts whatever follows. Measured on 268 real extracted addresses,
# the forms the shorter vocabulary lost: dotted pairs "N.E."/"S.W." (6.0%),
# the "SO." abbreviation (3.7%), spelled compounds "SOUTHWEST" (0.7%) — about
# one address in ten carrying a truncated or dropped direction. "SO" is
# accepted only with its period, so the word "SO" in prose stays untouched.
DIRECTION = (
    r"(?:NORTHEAST|NORTHWEST|SOUTHEAST|SOUTHWEST|NORTH|SOUTH|EAST|WEST"
    r"|[NS]\.?[EW]|SO\.|[NSEW])"
)
# Unit keywords tolerate an optional "#" before the identifier: forms print
# "Apt. # 201" as readily as "Apt. 201", and the first human rating round
# found dropped units to be the single largest correction category (11 of 24).
# The identifier may be quoted — fill-in forms print 'unit "O"'.
_UNIT_ID = r"[\"']?[\w-]+[\"']?"
UNIT = (
    rf"(?:#\s?{_UNIT_ID}|APT\.?\s?#?\s?{_UNIT_ID}|UNIT\s?#?\s?{_UNIT_ID}|"
    rf"STE\.?\s?#?\s?{_UNIT_ID}|SUITE\s?#?\s?{_UNIT_ID}|SPACE\s?#?\s?{_UNIT_ID}|"
    rf"TRLR\s?#?\s?{_UNIT_ID}|LOT\s?#?\s?{_UNIT_ID})"
)

# street line: house number + words + suffix, optionally followed by direction/unit
# street-name tokens allow %/°/™ and straight/curly quotes — all OCR misreads
# of superscript ordinals: "150ᵀᴴ ST" arrives as "150™ ST", and "100ᵗʰ Avenue"
# as '100" Avenue' (found by mining the truth set; that one character cost the
# whole address).
# Port note: the trailing direction carries a (?!\w) guard the original
# wa_doc_scan pattern lacked, so "ST STE 200" no longer loses its unit to a
# phantom direction "S" and "AVE SEATTLE" no longer becomes "AVE S" + city
# "Eattle". Strictly narrower; behavior is otherwise identical to the
# validated original.
# The unit group accepts a comma separator ("Commercial St., Suite 460") —
# found by human rating, where a comma-led suite was unreachable because the
# group required whitespace immediately after the street.
# Compound suffixes: Pierce County names streets "115th St Ct SW" and
# "88th Street Court SW" — a second type word directly after the first. The
# lazy name expansion stops at the first suffix, so without the optional
# compound tail the street truncates at "St" and the court and direction are
# lost. The compound list is tight (court/place/circle) because the common
# suffixes would eat the following city ("TERRACE SPRINGFIELD").
STREET_RE = re.compile(
    rf"\b(\d{{1,6}})\.?[\s-]+((?:{DIRECTION}\.?\s+)?[\w'\"’”.\-%°™]+(?:\s+[\w'\"’”.\-%°™]+){{0,4}}?"
    rf"\s+{STREET_SUFFIX}\.?(?:\s+(?:CT|COURT|PL|PLACE|CIR|CIRCLE)\.?)?"
    rf"(?:\s+{DIRECTION}\.?(?!\w))?)((?:\s+|\s*,\s*){UNIT})?",
    re.IGNORECASE,
)
# city, state zip — the state token is configurable per jurisdiction; the
# Washington forms ship as the default the engine was validated on
CITY_WA_RE = re.compile(
    r"\b([A-Za-z][A-Za-z .'-]{2,30}?)[,.]?\s+(?:WA|WASH\.?|WASHINGTON)\b[,.]?\s*(\d{5}(?:-\d{4})?)?",
    re.IGNORECASE,
)
ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
PHONE_RE = re.compile(r"\(?\b(\d{3})\)?[\s.\-/]?(\d{3})[\s.\-]?(\d{4})\b")
WSBA_RE = re.compile(r"WSBA\s*#?\s*(\d{3,6})", re.IGNORECASE)

FIRM_KEYWORDS = re.compile(
    r"\b(LAW|LEGAL|PLLC|P\.?\s?L\.?\s?L\.?\s?C|P\.?\s?S\.?|L\.?\s?L\.?\s?P|INC|"
    r"ATTORNEY|ATTORNEYS|ASSOCIATES|LAW\s+OFFICES?|FIRM|GROUP)\b",
    re.IGNORECASE,
)
GENERIC_ROLE_RE = re.compile(r"^\s*Attorneys?\s+for\s+", re.IGNORECASE)
PROSE_WORDS_RE = re.compile(
    r"\b(landlord|notice|deadline|respond|lawsuit|tenancy|belongings|sheriff)\b",
    re.IGNORECASE,
)
ATTY_NAME_RE = re.compile(
    r"([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){1,3})\s*[,/]?\s*WSBA", re.IGNORECASE
)
# blank-form publisher footers that must not be mistaken for a law firm
FORM_PUBLISHER_RE = re.compile(
    r"LEGAL\s+BLANK|REPRODUCED|MATERIAL\s+©?\s*\d{4}|©", re.IGNORECASE
)

# anchors for the defendant service block. Up to two short junk tokens may
# precede "TO:" — OCR sometimes reads the rail digits as letters ("nN No TO:").
# The junk-lead tolerance is {1,4} because OCR renders a rail digit plus the
# pleading rule as tokens like "19||" (four characters); "TO THE DEFENDANT(S):"
# is a common King County label the original vocabulary lacked — mining the
# truth set found whole documents failing on that one missing word.
#: process-server declaration labels; an address on such a line is the
#: server's, found grabbed by the stack anchor on a real page-3 declaration
SERVER_DECL_RE = re.compile(
    r"\(\s*(?:printed\s+name|address|signature|date)\s*\)", re.IGNORECASE)

#: the "deliver your notice of appearance or answer to:" instruction — the
#: address under it is plaintiff counsel's, printed as a freestanding stack
#: that the stack anchor otherwise reads as the defendant's. Found on two
#: truth-set filings where it displaced the true service block.
# Deliberately narrow: "notice of appearance" and "answer must" also occur in
# ordinary body paragraphs, and matching them vetoed true service stacks that
# happened to sit below such prose (87 documents lost yield before this was
# tightened). Only the instruction's own tail phrase is safe.
DELIVER_TO_RE = re.compile(
    r"(must\s+be\s+delivered\s+to|delivered?\s+to\s*:\s*$)", re.IGNORECASE)

TO_ANCHOR_RE = re.compile(
    r"^\s*(?:\S{1,4}\s+){0,2}TO\s*:\s*(DEFENDANT\S*\s*:?)?"
    r"|^\s*(?:\S{1,4}\s+){0,2}TO\s+(?:THE\s+)?DEFENDANT\S*\s*:?",
    re.IGNORECASE,
)
ADDRESS_LABEL_RE = re.compile(r"^\s*ADDRESS\s*:", re.IGNORECASE)
PREMISES_RE = re.compile(
    r"PREMISES\s+(?:LOCATED|SITUATED)\s+AT\s+(.{8,140}?)(?:[.;]\s|\n|$)",
    re.IGNORECASE | re.DOTALL,
)
# prose that ends the TO: block
PROSE_STOP_RE = re.compile(
    r"(this is (a )?notice|a lawsuit has been started|your landlord is asking|"
    r"if you want to defend|the deadline for)",
    re.IGNORECASE,
)
# a block labeled/attributed to the plaintiff's side is not the defendant's.
# "landlord" is deliberately absent — it saturates the notice prose and
# over-triggers; role labels say "Plaintiff" / "attorney for".
PLAINTIFF_SIDE_RE = re.compile(r"\b(plaintiff|attorney)\b", re.IGNORECASE)
# boilerplate co-defendant phrasing that is not part of the mailing address
OCCUPANT_NOISE_RE = re.compile(
    r"(and\s+)?all\s+other\s+occupants.*|(and\s+)?all\s+occupants.*|"
    r"(and\s+)?any\s+other\s+occupants.*|does\s+1.*|john\s+doe.*|jane\s+doe.*",
    re.IGNORECASE,
)

SUMMONS_NAME_RE = re.compile(r"summons", re.IGNORECASE)

STREET_STOPWORDS = {
    "the", "a", "an", "of", "on", "in", "to", "and", "or", "for", "this",
    "at", "is", "be", "you", "your", "if", "no", "any", "with", "by",
}

# OCR digit-confusion repair for house numbers. Some scanned-then-e-filed
# summonses carry their own (bad) OCR in the text layer — "L234 EXAMPLE ST"
# for 1234 — and the digit-led street pattern then drops the whole address.
# A token repairs only when it is mostly digits already and becomes all
# digits under the classic confusions; "123B"-style true alphanumeric house
# numbers are left alone. Applied only after the strict pass found nothing,
# and surfaced as a house_number_repaired flag for audit.
OCR_DIGIT_MAP = str.maketrans("OoIiLl|SsZzBG", "0011111552286")


def repair_house_numbers(t):
    """Return (repaired_text, n_repaired)."""
    out, n = [], 0
    for tok in t.split(" "):
        if 2 <= len(tok) <= 6 and not tok.isdigit() \
                and not re.fullmatch(r"\d+[A-Za-z]", tok):
            fixed = tok.translate(OCR_DIGIT_MAP)
            if fixed.isdigit() and sum(c.isdigit() for c in tok) * 2 >= len(tok):
                out.append(fixed)
                n += 1
                continue
        out.append(tok)
    return " ".join(out), n


def _first_street_match(t):
    """First STREET_RE hit whose street name doesn't lead with a stopword
    (stopword-led matches are OCR scrambles, e.g. "98387 the enter court")."""
    for m in STREET_RE.finditer(t):
        if m.group(2).split()[0].rstrip(".").lower() in STREET_STOPWORDS:
            continue
        return m
    return None


def _skip_rail_house_number(t, sm):
    """Reject a house number that is really a pleading line number.

    When the line-number rail drifts out of the margin band, OCR reads its
    digit as the first word of the address line and the street pattern takes it
    as the house number: "13 39 Sudden Valley Drive" for a house at 39, and
    "18 1234 Example Ave S" for one at 1234. Both were found by a human rating
    real extractions, and both are silently wrong rather than obviously broken,
    which is the dangerous kind: a geocoder will happily place number 13.

    The tell is a short integer in rail range sitting immediately before
    another number that starts a perfectly good address of its own. A genuine
    "13 39th Ave" is safe, because "39th Ave" has no whitespace after its
    digits and so cannot start a match.

    The correction is made here rather than by dropping the rail word earlier.
    Removing those words at the word level was tried: it detected the rails
    correctly, but changed which block the extractor selected on one filing in
    250, once swapping a correct defendant address for the plaintiff
    attorney's. Fixing it at parse time cannot move a block boundary.
    """
    if sm is None:
        return sm
    house = sm.group(1)
    if not (len(house) <= 2 and 1 <= int(house) <= 28):
        return sm
    after = sm.start(1) + len(house)
    if not re.match(r"\s+\d{1,6}\s", t[after:]):
        return sm
    alt = _first_street_match(t[after:])
    if alt is None or alt.start() > 2:
        return sm
    shifted = STREET_RE.search(t, after)
    return shifted if shifted is not None else sm


# Words that end up in front of "WA"/"Washington" without being a city.
# "and all others residing at ... Washington" makes a city of "Residing";
# a signature block makes one of "Swanson Pllc". No Washington place name
# contains any of these, so one of them anywhere in the captured city means
# the capture is prose or a firm name, and an empty city (with the ZIP kept)
# is the honest answer. Found by human rating of real extractions.
CITY_VETO = {
    "residing", "resident", "residents", "occupant", "occupants", "others",
    "pllc", "llc", "llp", "inc", "ps", "esq", "wsba", "attorney", "attorneys",
    "law", "office", "offices", "firm", "associates", "plaintiff", "plaintiffs",
    "defendant", "defendants", "county", "superior", "court",
    # courtroom vocabulary that reaches the no-suffix street parser, where a
    # case-caption fragment ("9 EVICTIONS SUMMONS Residential") would
    # otherwise read as house + street + city
    "summons", "eviction", "evictions", "residential", "notice", "lawsuit",
    "deadline", "response", "washington", "judge", "clerk", "cause",
}


def _clean_city(raw_city):
    """The city as CITY_WA_RE captured it, cleaned of OCR junk and prose.

    Margin/OCR junk glues onto the city's head ("Ny Oo Seattle", "W Federal
    Way" from an absorbed direction letter, "C Bellingham" from a "#C" that
    lost its #) — lead tokens without a true vowel are not city names (y alone
    doesn't clear "Yn"), and neither are 1-2 letter fragments ("Oo", "Ob")
    except the genuine "La" of La Center / La Conner."""
    toks = raw_city.strip(" ,.").title().split()
    while toks and (
            not re.search(r"[aeiou]", toks[0], re.IGNORECASE)
            or (len(toks[0]) <= 2 and toks[0].lower() != "la")):
        toks.pop(0)
    if any(tk.rstrip(".,").lower() in CITY_VETO for tk in toks):
        return ""
    return " ".join(toks)


def parse_address(text):
    """Split a joined address string into components; returns None if no
    street pattern is present. Keeps the raw string alongside components."""
    # Dot leaders first: fill-in forms print ".....4815 115th St....." and the
    # runs of dots glue onto the tokens. Two or more dots never occur inside a
    # legitimate address, so they collapse to a space; single periods (St.,
    # N.E., et. al.) are untouched.
    t = re.sub(r"\s+", " ", re.sub(r"\.{2,}", " ", text)).strip(" ,.;")
    repaired = False
    sm = _skip_rail_house_number(t, _first_street_match(t))
    t2, n_fix = repair_house_numbers(t)
    if n_fix:
        # the repaired text competes by POSITION: the true address sits at the
        # head of the block, so a repaired match there must win over a strict
        # match that only exists because scrambled prose later in the block
        # happens to look digit-led ("47 zv ... ST"). Strictly earlier only:
        # an equal-start match means the house number was already clean, and
        # adopting the rewrite would corrupt genuine letter-led unit
        # designators downstream ("# L205" is building L, not 1205)
        sm2 = _first_street_match(t2)
        if sm2 and (sm is None or sm2.start() < sm.start()):
            t, sm, repaired = t2, sm2, True
    if not sm:
        return None
    street = re.sub(r"\s+", " ", sm.group(0)).strip(" ,.")
    unit = re.sub(r"\s+", " ", sm.group(3)).strip() if sm.group(3) else ""
    rest = t[sm.end():]
    city = state = zipc = ""
    end = min(len(t), sm.end() + 45)  # raw trim point when no city/zip found
    # First city match whose capture survives cleaning. Stopping at the first
    # match regardless loses real cities: in "...all others residing at ...
    # BELLINGHAM, WA" the first thing before a state token is the prose word
    # "residing", and the genuine city sits one match further on.
    cm = None
    for c in CITY_WA_RE.finditer(rest):
        cm = cm or c                        # fallback: first match's zip/trim
        if _clean_city(c.group(1)):
            cm = c
            break
    if cm:
        city = _clean_city(cm.group(1))
        state = "WA"
        zipc = cm.group(2) or ""
        end = sm.end() + cm.end()
    else:
        zm = ZIP_RE.search(rest)
        if zm:
            zipc = zm.group(1)
            end = sm.end() + zm.end()
    # trim trailing prose the block over-collected; keep any leading context
    return {
        "address_raw": t[:end].strip(" ,.;"),
        "street": street,
        "unit": unit,
        "city": city,
        "state": state,
        "zip": zipc,
        "house_repaired": repaired,
    }


# Streets with no type word at all: "5037 So. Orchard", "1949 S. Sprague",
# "112 West Meeker", "1419-A South Ainsworth". Tacoma in particular names many
# streets this way, and STREET_RE requires a suffix, so these were the single
# largest cause of no_defendant_address in a hand-inspected failure sample.
# The pattern is deliberately tight: house number (optionally "-A"), an
# optional direction, then at most TWO name tokens, then an optional unit —
# and it is only consulted where a city/state line confirms the reading.
NOSUFFIX_LINE_RE = re.compile(
    rf"^\s*\d{{1,6}}(?:-[A-Za-z])?\s+(?:{DIRECTION}\.?\s+)?[A-Za-z][\w'.\-]*"
    rf"(?:\s+[A-Za-z][\w'.\-]*)?(?:(?:\s+|\s*,\s*){UNIT})?\s*$",
    re.IGNORECASE,
)


# The whole no-suffix address as ONE pattern, so the regex engine's
# backtracking settles the street/city split. Matching street and city
# separately fails on exactly the hard inputs: the lazy city capture in
# "112 West Meeker Puyallup, WA" starts at "West" and eats the street, and in
# "...Orchard, #C University Place, WA" it starts at the unit's letter. With
# a single pattern the engine tries allocations until street, optional unit,
# and city are all satisfied at once.
# The separator before the city is MANDATORY ([\s,.;]+, not *): with an
# optional separator the engine, having failed to place a city before "WA",
# will shrink the last street token mid-word and split "Puyallup" into street
# "Puyal" + city "lup". A required separator makes a mid-word split
# unsatisfiable, so backtracking drops the whole optional token instead.
NOSUFFIX_ADDR_RE = re.compile(
    rf"\b(\d{{1,6}})(-[A-Za-z])?\s+((?:{DIRECTION}\.?\s+)?[A-Za-z][\w'.\-]*"
    rf"(?:\s+[A-Za-z][\w'.\-]*)?)((?:\s+|\s*,\s*){UNIT})?[\s,.;]+"
    rf"([A-Za-z][A-Za-z .'-]{{2,30}}?)[,.]?\s+(?:WA|WASH\.?|WASHINGTON)\b[,.]?"
    rf"\s*(\d{{5}}(?:-\d{{4}})?)?",
    re.IGNORECASE,
)


def parse_address_nosuffix(text):
    """Parse an address whose street has no type word, on stricter terms.

    Runs only after the strict pass found nothing, and only accepts a street
    that sits immediately before a city/state line — the city is the
    confirmation that replaces the missing suffix. Every use is surfaced as a
    street_no_suffix flag, because this rule is newer than the validated
    original and its output should be reviewable as a class.
    """
    t = re.sub(r"\s+", " ", re.sub(r"\.{2,}", " ", text)).strip(" ,.;")
    if _first_street_match(t):
        return None                          # the strict pass owns this text
    dir_only = re.compile(rf"^{DIRECTION}\.?$", re.IGNORECASE)
    for m in NOSUFFIX_ADDR_RE.finditer(t):
        name_toks = m.group(3).split()
        if name_toks[0].rstrip(".,").lower() in STREET_STOPWORDS:
            continue
        if any(tok.rstrip(".,").lower() in CITY_VETO for tok in name_toks):
            continue                         # caption fragment, not a street
        # a name that is nothing but suffix words is a form that dropped the
        # actual street name ("3116 Street #11" printed by the clerk) —
        # rejecting it lets the anchor ladder fall through to the caption,
        # which usually carries the full address
        suffix_only = re.compile(rf"^{STREET_SUFFIX}\.?$", re.IGNORECASE)
        if all(suffix_only.match(tok) or dir_only.match(tok) for tok in name_toks):
            continue
        if all(dir_only.match(tok) for tok in name_toks):
            continue                         # "1502 SOUTH" alone is not a street
        city = _clean_city(m.group(5))
        if not city:
            continue                         # confirmation gone, reading unsafe
        street = re.sub(r"\s+", " ", m.group(1) + (m.group(2) or "") + " "
                        + m.group(3) + (m.group(4) or "")).strip(" ,.")
        unit = re.sub(r"\s+", " ", m.group(4)).strip(" ,") if m.group(4) else ""
        return {
            "address_raw": t[m.start():m.end()].strip(" ,.;"),
            "street": street,
            "unit": unit,
            "city": city,
            "state": "WA",
            "zip": m.group(6) or "",
            "house_repaired": False,
            "street_no_suffix": True,
        }
    return None


def looks_like_name_line(text):
    t = text.strip()
    if not t or STREET_RE.search(t) or CITY_WA_RE.search(t):
        return False
    return bool(re.search(r"[A-Za-z]{2}", t)) and not re.search(r"\d{3}", t)


# ---------------------------------------------------------------------------
# the defendant anchor ladder
# ---------------------------------------------------------------------------


def extract_defendant_block(lines, pg=1):
    """Anchor A: the mid-page service block ('TO:' / 'TO DEFENDANT(S):',
    the labeled 'ADDRESS:' variant). Returns (result, anchor_tag)."""
    p1 = [l for l in lines if l.page == pg]
    deferred = None
    for i, ln in enumerate(p1):
        t = ln.text.strip()
        is_to = bool(TO_ANCHOR_RE.match(t)) and len(t) < 90 and 0.15 < ln.y0 < 0.85
        is_addr_label = bool(ADDRESS_LABEL_RE.match(t)) and 0.15 < ln.y0 < 0.90
        if not (is_to or is_addr_label):
            continue
        # collect the anchored block: this line's remainder + following lines
        block, names = [], []
        first = TO_ANCHOR_RE.sub("", t) if is_to else ADDRESS_LABEL_RE.sub("", t)
        if first.strip():
            block.append(first.strip())
        j = i + 1
        last_y = ln.y1
        while j < len(p1):
            nxt = p1[j]
            if nxt.y0 - last_y > 0.055 or PROSE_STOP_RE.search(nxt.text):
                break
            if ADDRESS_LABEL_RE.match(nxt.text):
                block.append(ADDRESS_LABEL_RE.sub("", nxt.text).strip())
            else:
                block.append(nxt.text.strip())
            last_y = nxt.y1
            j += 1
            if len(block) > 8:
                break
        # split names from address inside the block. Before the address has
        # begun, any line WITHOUT a digit is a name or building line: the
        # address's first line always carries the house number, and the old
        # looks-like-a-name test wrongly started the address at "STEVE E.
        # WASHINGTON" because the surname tripped the city/state pattern,
        # gluing the parties into the address itself.
        addr_started = False
        addr_parts = []
        for part in block:
            clean = OCCUPANT_NOISE_RE.sub("", part).strip(" ,;")
            if not addr_started and clean and (
                    looks_like_name_line(clean)
                    or not any(ch.isdigit() for ch in clean)):
                names.append(clean)
                continue
            if part.strip():
                addr_started = True
                addr_parts.append(part.strip())
        # an "ADDRESS:"/"TO:" label inside an attorney signature block is the
        # firm's address (Suite + TELEPHONE NO. + WSBA) — not the defendant's
        block_text = " ".join(block)
        if re.search(r"TELEPHONE\s+NO|WSBA|ATTORNEYS?\s+(AT\s+LAW|FOR)|LAW\s+OFFICE",
                     block_text, re.IGNORECASE):
            continue
        # When the label's own line carries names AND the address ("TO THE
        # DEFENDANT(S): JOHN DOE; All Occupants ... 6200 EXAMPLE AVE S ..."),
        # the digit test starts the address at that line and the party names
        # ride along into address_raw. The street match marks the boundary:
        # everything before it is attribution and belongs in names.
        joined = " ".join(addr_parts)
        sm0 = _first_street_match(joined)
        if sm0 and sm0.start() > 0:
            head = OCCUPANT_NOISE_RE.sub("", joined[:sm0.start()]).strip(" ,;:")
            if re.search(r"[A-Za-z]{2}", head) and not ADDRESS_LABEL_RE.match(head):
                names.append(head)
            joined = joined[sm0.start():]
        parsed = parse_address(joined) if addr_parts else None
        nosuffix = None
        if not parsed and addr_parts:
            # the confirmed-by-city fallback for streets with no type word
            nosuffix = parse_address_nosuffix(joined)
        for cand in (parsed, nosuffix):
            if cand:
                cand["defendant_names"] = "; ".join(n for n in names if n)[:200]
                used = p1[i:j]
                cand["block_conf"] = round(sum(l.conf for l in used) / len(used), 1)
                tag = "to_block" if is_to else "address_label"
                if cand is parsed:
                    return cand, tag
                # A no-suffix reading never outranks a strict one anywhere in
                # this anchor: it is remembered and only returned if the whole
                # scan finds no strict block. Letting it win immediately was
                # measured to change block selection — a scrambled caption
                # fragment preempted the true service block lower on the page.
                if deferred is None:
                    deferred = (cand, tag)
    return deferred if deferred else (None, None)


def extract_defendant_premises(lines, pg=1):
    """Anchor B: prose '...PREMISES LOCATED AT 1234 Example Avenue South,
    Seattle, WA 98100.' anywhere on the page."""
    p1_text = "\n".join(l.text for l in lines if l.page == pg)
    m = PREMISES_RE.search(p1_text)
    if not m:
        return None, None
    parsed = parse_address(m.group(1))
    # a line wrap inside the sentence truncates the lazy capture before the
    # city/zip ("1234 115th St Ct E" / newline / "Puyallup, WA 98374").
    # Retry on a wider flattened window; accept the wider parse only when it
    # anchors on the SAME street and genuinely completes the address (a zip,
    # or a city found within a line's reach) — otherwise distant prose like
    # "…Pierce County, Washington" would masquerade as the city.
    wide = re.sub(r"\s+", " ", p1_text[m.start(1): m.start(1) + 200])
    if not parsed:
        parsed = parse_address(wide)
    elif not parsed["city"] and not parsed["zip"]:
        p2 = parse_address(wide)
        if p2 and p2["street"] == parsed["street"] and (
                p2["zip"] or
                (p2["city"] and len(p2["address_raw"]) <= len(parsed["address_raw"]) + 45)):
            parsed = p2
    return (parsed, "premises_prose") if parsed else (None, None)


def extract_defendant_stack(lines, pg=1):
    """Anchor D: a freestanding street-line + city/state-line stack in the
    body band (some older summonses print the service block with no 'TO:'
    label). Left-of-center, above the attorney zone; topmost stack wins."""
    p1 = [l for l in lines if l.page == pg and 0.22 < l.y0 < 0.72 and l.x0 < 0.60]
    deferred = None
    for i, ln in enumerate(p1):
        t = ln.text.strip()
        streetish = STREET_RE.search(t) or NOSUFFIX_LINE_RE.match(t)
        if len(t) > 70 or not streetish or PROSE_STOP_RE.search(t):
            continue
        # a return-of-service declaration prints the SERVER's address next to
        # "(Printed Name)"/"(Address)" labels — never the defendant's
        if SERVER_DECL_RE.search(t):
            continue
        # a signature/service block attributed to the plaintiff's side is
        # the landlord's return address, not the defendant's — skip it.
        # Attribution lines sit ABOVE the address ("Plaintiff, or Attorney
        # for Plaintiff"); lines below are notice prose, don't test them.
        context = p1[max(0, i - 3): i + 1]
        if any(PLAINTIFF_SIDE_RE.search(c.text) or DELIVER_TO_RE.search(c.text)
               for c in context):
            continue
        # a city/state line must follow within ~2 line heights
        for nxt in p1[i + 1: i + 3]:
            if nxt.y0 - ln.y1 > 0.05:
                break
            if CITY_WA_RE.search(nxt.text) and len(nxt.text.strip()) < 50:
                joined = f"{t} {nxt.text.strip()}"
                parsed = parse_address(joined)
                nosuffix = None if parsed else parse_address_nosuffix(joined)
                cand = parsed or nosuffix
                if not cand:
                    continue
                # names: up to two immediately preceding short name-ish lines
                names = []
                for prev in reversed(p1[max(0, i - 2): i]):
                    if ln.y0 - prev.y1 > 0.05 or not looks_like_name_line(prev.text):
                        break
                    names.insert(0, OCCUPANT_NOISE_RE.sub("", prev.text).strip(" ,;"))
                cand["defendant_names"] = "; ".join(n for n in names if n)[:200]
                cand["block_conf"] = round((ln.conf + nxt.conf) / 2, 1)
                if parsed:
                    return cand, "address_stack"
                # a no-suffix stack never preempts a strict stack further down
                # the page; it is only returned when the whole scan finds none
                if deferred is None:
                    deferred = (cand, "address_stack")
    return deferred if deferred else (None, None)


def extract_defendant_caption(lines, pg=1):
    """Anchor C: address inside the caption's defendant cell (between the
    'vs.' line and the 'Defendant(s).' label, left half of the page)."""
    p1 = [l for l in lines if l.page == pg and l.x0 < 0.60]
    vs_y = def_y = None
    for ln in p1:
        t = ln.text.strip().rstrip(".,")
        if vs_y is None and re.fullmatch(r"vs?\.?", t, re.IGNORECASE):
            vs_y = ln.y0
        if vs_y is not None and re.search(r"\bDEFENDANTS?\b", t, re.IGNORECASE) and len(t) < 30:
            def_y = ln.y0
            break
    if vs_y is None:
        return None, None
    hi = def_y if def_y is not None else vs_y + 0.25
    cell = " ".join(l.text for l in p1 if vs_y < l.y0 < hi)
    parsed = parse_address(cell)
    return (parsed, "caption_cell") if parsed else (None, None)


DEFENDANT_ANCHORS = (extract_defendant_block, extract_defendant_premises,
                     extract_defendant_stack, extract_defendant_caption)


# lines that belong to the court header, never to a party name
_HEADER_NOISE_RE = re.compile(
    r"\b(COURT|COUNTY|STATE\s+OF|WASHINGTON|SUPERIOR|DISTRICT|JUSTICE|IN\s+THE)\b",
    re.IGNORECASE,
)
_PLAINTIFF_LABEL_RE = re.compile(r"^Plaintiffs?[,.]?$", re.IGNORECASE)
_VS_LINE_RE = re.compile(r"^vs?\.?,?$", re.IGNORECASE)


def _left_cell_text(line, cutoff=0.55):
    """A caption is two columns; the case number lives in the right one.
    Rebuild the line from words left of the divider so 'EXAMPLE LLC,' and
    'Case No. 25-2-00001-0' stop being one string."""
    return " ".join(w.text for w in line.words if w.x0 < cutoff).strip()


def extract_plaintiff_caption(lines, pg=1):
    """Plaintiff name(s) from the caption's upper-left cell.

    Newer than the address anchors and not part of the July 2026 address
    validation; treat output as a convenience to be reviewed, not a
    validated field. Looks for the 'Plaintiff,' designator line (or the
    'vs.' line) and takes the name lines directly above it.
    """
    p1 = [l for l in lines if l.page == pg and l.y0 < 0.55 and l.x0 < 0.60]
    label_idx = None
    for i, ln in enumerate(p1):
        cell = _left_cell_text(ln)
        if _PLAINTIFF_LABEL_RE.match(cell) or _VS_LINE_RE.match(cell):
            label_idx = i
            break
    if label_idx is None:
        return []
    names = []
    for prev in reversed(p1[max(0, label_idx - 3): label_idx]):
        cell = _left_cell_text(prev)
        if not cell or _HEADER_NOISE_RE.search(cell) or not looks_like_name_line(cell):
            break
        for name in re.split(r"\s+(?:and|&)\s+", cell.strip(" ,;"), flags=re.IGNORECASE):
            name = name.strip(" ,;")
            if len(name) >= 2:
                names.insert(0, name)
    return names


def try_defendant(lines, pages):
    """Run the anchor ladder over the given pages; first hit wins but all
    candidates are kept for the audit trail.

    The page scan stops early only once a COMPLETE candidate (city or ZIP
    present) exists. An incomplete page-1 fragment used to end the scan and
    shadow a complete service block on a later page — measured on a real
    filing where a garbled caption cell (no city, no ZIP) beat the true
    premises paragraph on page 3. Incomplete candidates are still returned,
    and still win when nothing complete ever appears."""
    candidates = []
    for pg in pages:
        for fn in DEFENDANT_ANCHORS:
            parsed, anchor = fn(lines, pg)
            if parsed:
                candidates.append((f"{anchor}@p{pg}" if pg != 1 else anchor, parsed, pg))
        if any(p.get("city") or p.get("zip") for _, p, _ in candidates):
            break
    return candidates


# ---------------------------------------------------------------------------
# the attorney block
# ---------------------------------------------------------------------------


def extract_attorney(lines, words):
    """Bottom-right block scoring across the pages read. The per-page footer
    (firm + address + phone) and the last-page signature block both land
    here; the highest-scoring cluster wins. The zone is built from WORDS
    (spatial filter first, then cluster) so a left page-footer at the same
    height cannot merge with the attorney block and widen it past the
    filters; centered body prose is excluded by the x0 threshold."""
    zone_words = [w for w in words if w.y0 > 0.68 and w.x0 > 0.40]
    zones = defaultdict(list)
    for ln in cluster_lines(zone_words):
        if (ln.x1 - ln.x0) < 0.55 and not PROSE_WORDS_RE.search(ln.text) \
                and not FORM_PUBLISHER_RE.search(ln.text):
            zones[ln.page].append(ln)
    # split each page's zone into contiguous vertical runs — the attorney
    # block is a tight stack; stray right-half fragments of body lines are
    # isolated and score low on their own
    best, best_score = None, 0
    for page, zlines in sorted(zones.items()):
        zlines = sorted(zlines, key=lambda l: l.y0)
        runs, cur = [], []
        for l in zlines:
            if cur and l.y0 - cur[-1].y1 > 0.035:
                runs.append(cur)
                cur = []
            cur.append(l)
        if cur:
            runs.append(cur)
        for run in runs:
            joined = " ".join(l.text for l in run)
            score = 0
            if FIRM_KEYWORDS.search(joined):
                score += 2
            if STREET_RE.search(joined):
                score += 2
            if CITY_WA_RE.search(joined):
                score += 1
            if PHONE_RE.search(joined):
                score += 1
            if score > best_score:
                best, best_score = (page, run, joined), score
    if not best or best_score < 3:
        return None
    page, zlines, joined = best
    text = " | ".join(l.text for l in zlines)
    # firm line: shortest keyword line that isn't a street/phone/role line
    firm, fallback = "", ""
    for l in sorted(zlines, key=lambda l: len(l.text)):
        lt = re.sub(r"\s+", " ", l.text.strip(" |"))
        if not FIRM_KEYWORDS.search(lt) or STREET_RE.search(lt) or PHONE_RE.search(lt):
            continue
        if GENERIC_ROLE_RE.match(lt):
            fallback = fallback or lt
            continue
        firm = lt
        break
    firm = firm or fallback
    parsed = parse_address(joined) or {}
    phone = PHONE_RE.search(joined)
    # names + bar numbers often sit outside the footer (signature block)
    wsba, atty_names = [], []
    for ln in lines:
        for m in WSBA_RE.finditer(ln.text):
            wsba.append(m.group(1))
        nm = ATTY_NAME_RE.search(ln.text)
        if nm:
            atty_names.append(re.sub(r"\s+", " ", nm.group(1)))
    return {
        "attorney_names": "; ".join(dict.fromkeys(atty_names))[:150],
        "attorney_firm": firm[:120],
        "attorney_address_raw": parsed.get("address_raw", ""),
        "attorney_street": parsed.get("street", ""),
        "attorney_unit": parsed.get("unit", ""),
        "attorney_city": parsed.get("city", ""),
        "attorney_state": parsed.get("state", ""),
        "attorney_zip": parsed.get("zip", ""),
        "attorney_phone": "-".join(phone.groups()) if phone else "",
        "attorney_wsba": ";".join(dict.fromkeys(wsba))[:60],
        "attorney_page": page,
        "attorney_zone_text": text[:400],
    }


def extract_case_number(lines, expected=None):
    """WA-format case number from page 1; `expected` (e.g. from a folder or
    docket list) enables the mismatch check without ever overriding what the
    document itself says."""
    p1_text = " ".join(l.text for l in lines if l.page == 1)
    m = WA_CASE_NO_RE.search(p1_text)
    doc_case = f"{m.group(1)}-2-{m.group(2)}-{m.group(3)}" if m else ""
    match = (doc_case == expected) if (doc_case and expected) else None
    return doc_case, match


# ---------------------------------------------------------------------------
# assembly into the shared schema
# ---------------------------------------------------------------------------


def _to_address(parsed) -> Address:
    return Address(
        raw=parsed.get("address_raw") or parsed.get("attorney_address_raw") or "",
        street=parsed.get("street") or None,
        unit=parsed.get("unit") or None,
        city=parsed.get("city") or None,
        state=parsed.get("state") or None,
        zip=parsed.get("zip") or None,
    )


def _split_defendant_names(joined: str) -> list[str]:
    """The service block joins names with '; ' per line; a single line can
    still hold 'A and B'. Split conservatively and keep names as printed."""
    names = []
    for part in joined.split(";"):
        part = part.strip(" ,;")
        if not part:
            continue
        for name in re.split(r"\s+(?:and|&)\s+", part, flags=re.IGNORECASE):
            name = name.strip(" ,;")
            if len(name) >= 2:
                names.append(name)
    return names


def extract_summons_fields(doc, expected_case_number=None):
    """Run the full positional pass over a loaded Document.

    Returns (fields, evidence, flags) where `fields` is a dict holding
    `case_number`, `defendants` (list[Party]), `defendant_address`
    (Address or None), `attorney` (Attorney or None), plus the raw
    candidate list for the audit trail.
    """
    from .patterns import BUSINESS_MARKERS  # shared with the text rules

    lines, words = doc.lines, doc.words
    evidence: dict[str, Evidence] = {}
    flags: list[str] = []

    candidates = try_defendant(lines, doc.pages_read)
    # belt-and-suspenders: a "defendant" whose name line LEADS with a
    # plaintiff-side role label is the wrong-address failure — reject rather
    # than emit. Only the head of the names field is tested; role words deep
    # in an OCR-scrambled prose ramble are not attribution.
    candidates = [
        (a, p, pg) for a, p, pg in candidates
        if not PLAINTIFF_SIDE_RE.search(p.get("defendant_names", "")[:60])
    ]
    # A strict-pattern candidate outranks a no-suffix one from ANY anchor,
    # not just its own: ladder position alone let a no-suffix reading of an
    # OCR-scrambled "TO:" block preempt the clean strict address a lower
    # anchor had found on the same page. Likewise a candidate WITH a city or
    # ZIP outranks one with neither — a garbled page-1 caption fragment
    # otherwise shadows the complete service block on page 3. Stable sort
    # keeps ladder order within each class.
    candidates.sort(key=lambda c: (bool(c[1].get("street_no_suffix")),
                                   not (c[1].get("city") or c[1].get("zip"))))
    defendant = dict(candidates[0][1]) if candidates else {}
    def_anchor = candidates[0][0] if candidates else ""
    def_page = candidates[0][2] if candidates else None

    attorney_raw = extract_attorney(lines, words) or {}

    # The classic wrong-address failure is the chosen "defendant" address
    # being the plaintiff attorney's. When that collision fires and another
    # candidate on the audit trail does NOT collide, the non-colliding one is
    # the better answer even if it came from the weaker (no-suffix) pattern:
    # a service block reading "201 Broadway" beats a strict match on the
    # attorney's office tower. The flag still fires when no alternative
    # exists, so nothing is ever silently guessed.
    def _street_norm(s):
        return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()

    def _collides(street, att):
        # literal equality missed '22525 SE 64" Place Ste.278' against the
        # firm's '22525 SE 64" Place' — same office, one suite tail. Prefix
        # match after normalization catches the suite/unit variants.
        a, b = _street_norm(street), _street_norm(att)
        return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))

    att_street = attorney_raw.get("attorney_street") or ""
    if defendant and att_street and _collides(defendant.get("street", ""), att_street):
        for a, p, pg in candidates[1:]:
            if not _collides(p.get("street", ""), att_street):
                defendant, def_anchor, def_page = dict(p), a, pg
                break
    doc_case, case_match = extract_case_number(lines, expected_case_number)

    # ---- flags, ported logic ----
    if not words:
        flags.append("no_text")
    if doc.source != "pdf_text_layer" and words and doc.ocr_mean_conf < 60:
        flags.append("low_ocr_conf")
    if not defendant:
        flags.append("no_defendant_address")
    elif not defendant.get("zip") and not defendant.get("city"):
        flags.append("defendant_address_incomplete")
    if defendant.get("house_repaired"):
        flags.append("house_number_repaired")  # informational: audit trail
    if defendant.get("street_no_suffix"):
        # informational: the street carried no type word and was accepted on
        # the strength of the city line. Newer rule than the validated
        # original, so its output stays reviewable as a class.
        flags.append("street_no_suffix")
    if defendant.get("block_conf") is not None and defendant.get("block_conf", 100) < 70 \
            and doc.source != "pdf_text_layer":
        flags.append("defendant_block_low_conf")  # handwriting / poor scan
    pro_se = any(re.search(r"\bPRO\s+SE\b", l.text, re.IGNORECASE) for l in lines)
    if pro_se:
        flags.append("pro_se_plaintiff")  # self-represented; no firm expected
    if not attorney_raw and not pro_se:
        flags.append("no_attorney_block")
    if defendant and attorney_raw and defendant.get("street") \
            and defendant["street"].lower() == attorney_raw.get("attorney_street", "").lower():
        flags.append("defendant_equals_attorney")  # the classic wrong-address failure
    if case_match is False:
        flags.append("case_number_mismatch")

    # ---- assemble schema objects + evidence ----
    defendant_address = None
    defendants: list[Party] = []
    if defendant:
        defendant_address = _to_address(defendant)
        evidence["defendant_address"] = Evidence(
            quote=defendant.get("address_raw", ""), grounded=True,
            anchor=def_anchor, page=def_page,
        )
        for k, name in enumerate(_split_defendant_names(defendant.get("defendant_names", ""))):
            defendants.append(Party(
                name=name, role="defendant",
                is_business=bool(BUSINESS_MARKERS.search(name)),
                address=defendant_address,
            ))
            evidence[f"defendants.{k}.name"] = Evidence(
                quote=name, grounded=True, anchor=def_anchor, page=def_page,
            )

    attorney = None
    if attorney_raw:
        attorney_address = None
        if attorney_raw.get("attorney_address_raw"):
            attorney_address = Address(
                raw=attorney_raw["attorney_address_raw"],
                street=attorney_raw.get("attorney_street") or None,
                unit=attorney_raw.get("attorney_unit") or None,
                city=attorney_raw.get("attorney_city") or None,
                state=attorney_raw.get("attorney_state") or None,
                zip=attorney_raw.get("attorney_zip") or None,
            )
        attorney = Attorney(
            names=attorney_raw.get("attorney_names") or None,
            firm=attorney_raw.get("attorney_firm") or None,
            address=attorney_address,
            phone=attorney_raw.get("attorney_phone") or None,
            bar_numbers=attorney_raw.get("attorney_wsba") or None,
        )
        evidence["attorney"] = Evidence(
            quote=attorney_raw.get("attorney_zone_text", ""), grounded=True,
            anchor="attorney_block", page=attorney_raw.get("attorney_page"),
        )

    if doc_case:
        evidence["case_number"] = Evidence(
            quote=doc_case, grounded=True, anchor="wa_case_number", page=1,
        )

    plaintiffs: list[Party] = []
    for k, name in enumerate(extract_plaintiff_caption(lines)):
        plaintiffs.append(Party(
            name=name, role="plaintiff",
            is_business=bool(BUSINESS_MARKERS.search(name)),
        ))
        evidence[f"plaintiffs.{k}.name"] = Evidence(
            quote=name, grounded=True, anchor="caption_plaintiff", page=1,
        )

    fields = {
        "case_number": doc_case or None,
        "plaintiffs": plaintiffs,
        "defendants": defendants,
        "defendant_address": defendant_address,
        "attorney": attorney,
        "candidates": [
            {"anchor": a, **{k: v for k, v in p.items()}} for a, p, _ in candidates
        ],
        "pro_se": pro_se,
    }
    return fields, evidence, flags
