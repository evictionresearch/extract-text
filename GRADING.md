# Grading: what belongs in each field

Guide version: 0.9. Every saved answer records this version, so a later
change to these rules can tell which answers followed which. A ruling
raises it, together with `GRADING_VERSION` in
`python/src/extract_text/pipeline.py`, and applies from the next round,
never inside one. Version 1.0 is the guide frozen for the gold set, with
the trade-name rule.

You are checking what the software read off an eviction summons and typing
the right answer where it is wrong. Your answers are what the engine is
scored against, and they go into the final table in place of the engine's,
so a careful ten is worth more than a hurried hundred.

This page is for anyone grading on the review page: a person following the
[Get started](https://evictionresearch.net/extract-text/get-started.html)
steps on their own documents (step 5), and a grader in one of the Eviction
Research Network's rounds. It says what belongs in each field. Two other
pages go with it.

- [`docs/grading_with_boxes.md`](docs/grading_with_boxes.md) covers the
  colored boxes on the page image and where your answers are saved.
- [`docs/grading_round.md`](docs/grading_round.md) is for graders in a
  Network round: the zip, opening the page, and sending answers back.

## For each document

Compare the page image (click it to enlarge; the form stays beside it) with
the form below the engine's reading. Fix what is wrong, clear what the page
does not show, and press **Save**. If the form is already right, press
**Save** anyway; that records that the software was right. If you cannot
tell from the page, press **Can't tell from the page**.

Type only what the page shows, as printed. Do not add anything the page
leaves out, such as a ZIP code it does not print: the answers measure how
well software reads the page, and it cannot look things up. When something
printed is hard to read (a digit that could be a 5 or a 6), you may check
an outside source to choose between the readings the page allows; say so
in the note.

Grade from the first page. If names or the address run onto another page,
turn to it with the arrows under the image. If the page has no arrows,
grade what the first page shows and say so in the note.

Leave off a comma or semicolon at the end of a name; it only separates the
name from what follows on the page. A period that ends an abbreviation
("Inc.", "Jr.") stays. Save drops a trailing comma for you.

## The fields

**Address.** Street without the unit, unit on its own (`Apt 5`,
`BLDG C Apt 5`, `#12`), city, state, ZIP. It is the defendant's address,
in the caption or after "TO:", never the attorney's address in the bottom
right. If the page gives the defendant two addresses, use the address of
the property the eviction is about and mention the other in the note. If
it's unclear which address is correct, use the first one and make a note
about the decision.

**Defendants.** One per line, named people as printed.

- Leave out placeholders and group words: "all other occupants", "John
  Doe", "Jane Doe", "et al".
- Do not add a surname the page does not show. A defendant listed by first
  name only is typed by first name only.
- An alias stays on its person's line, written with "a/k/a" whatever the
  page's wording ("also known as", "who also appears of record as"), for
  example `PAT EXAMPLE a/k/a PATRICIA EXAMPLE`.
- A business the defendant does business as ("d/b/a", "DBA", "doing
  business as") goes on a line of its own, so businesses can be counted.
  Type the business name alone and leave out the letters "d/b/a". A page
  that prints `PAT EXAMPLE d/b/a EXAMPLE CAFE` is typed as two lines,
  `PAT EXAMPLE` and `EXAMPLE CAFE`.
- If the page spells a name two ways, type the likelier spelling and say
  so in the note.

**Plaintiff.** The landlord or company at the top of the page, the name
only: leave out the description after it ("a Washington limited liability
company", "a public body corporate and politic", "its successors and/or
assigns") and any trailing comma. Leave out a trade name too: when the
page prints `EXAMPLE HOLDINGS LLC d/b/a EXAMPLE PARK APARTMENTS`, the
plaintiff is `EXAMPLE HOLDINGS LLC`, and neither "d/b/a" nor the name after
it is typed. Several plaintiffs go one per line; the box grows to fit, and
the page starts it that way when the engine read more than one.

**Plaintiff's attorney.** Some pages ask for it on some documents. It is
the signature block, usually at the bottom right of the page. Attorneys and
the firm go in one box, one per line, each as printed and in any order:
every attorney's name and the firm or office name, without "Attorney for
Plaintiff" or the bar number. Address goes on one line, as printed (street,
suite, city, state, ZIP). If the plaintiff has no attorney (signed by the
landlord itself), clear both boxes.

**Note.** For anything unusual: a name spelled two ways, a second address,
an address on the next page, a block you are unsure of.

## The boxes

Colored boxes on the page image show where the engine read each value.
When one is in the wrong place, fix it: drag the box to move it, drag a
corner to reshape it, or press its cross to delete it. When one is missing,
draw it. Pick the field under the image (Plaintiff, Defendants, Address,
Attorney, Case number) and drag across the page where the value is
printed. A box you draw is added to the ones already there, the engine's
included, so nothing has to be drawn twice. Box every place a
field is printed: the defendants in the caption and again in the service
block, the attorney block on every page it repeats. A box can go on any
page. You do not need to turn every page: grade from the first, and look
further only for a value that is wrong or missing there. The engine learns
a form's layout from these boxes, so draw one whenever the engine looked in
the wrong place. A wrong value in the right place needs no box.
[`docs/grading_with_boxes.md`](docs/grading_with_boxes.md) has more.

## When you are done

On your own documents (step 5 of Get started), close the tab, stop the page
(Esc in RStudio, Ctrl-C at a terminal), and score the engine against your
answers with `score_documents(res)`. Your answers are in
`corrections.jsonl` and `corrections.csv` in the scan folder. They hold
names and addresses, so they stay on your computer, with the court
documents.

Your answers can also help improve the engine for everyone, but they do not
go to the Eviction Research Network by email, chat, or GitHub. What you can
send at any time is a description, in your own words, of what the engine
got wrong, with no name, address, or case number, to evictions@berkeley.edu.
Your answers, and any file made from your records, need a data agreement
between your organization and UC Berkeley first. The
[Improve it](https://evictionresearch.net/extract-text/improve.html) page
has the steps.

In a Network grading round, send your answers back as
[`docs/grading_round.md`](docs/grading_round.md) says.
