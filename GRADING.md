# Grading extractions

You have been asked to check what the software read off eviction summonses
and to type the right answer where it is wrong. Your answers become the
test set the engines are measured against and the examples the AI engine
learns from, so a careful ten is worth more than a hurried hundred.

## What you need

1. This repository, cloned, and Python 3.10 or newer. Then, in a terminal:

       cd extract-text/python
       python3 -m venv .venv && source .venv/bin/activate
       pip install -e .
       extract-text --version

   A version number means it is installed. Grading needs nothing else: no
   AI model and no scanning tools, because the readings and the page images
   are already in the folder you receive. If you already have the
   repository from an earlier round, update it with
   `git fetch origin && git reset --hard origin/main` from its folder; a
   plain `git pull` refuses, because the history was rewritten before the
   repository went public on 2026-10-20.

2. A scan folder from Tim, as a zip in a restricted Google Drive folder
   shared with you by name (never by email, never by a public link). It
   holds `extracted.csv`, `extracted.jsonl`, and a `review` folder of page
   images. It is real court records. Download the zip, unzip it on your own
   computer, and work from that copy. Keep it out of this repository and out
   of any other shared or synced folder, and delete it when the round is
   over.

## Grading

    extract-text review --out /path/to/the/folder --graders --attorneys 100 --serve

Your browser opens the page from a server on your own computer; nothing
leaves it. At the top, type your name (required) and email, and choose how
many documents to grade. Ten is a good first batch. The page shows you the
documents most in need of a person first and hides the rest. If Tim asks for
`--order random` in the command, it serves them in random order instead;
grade them the same way. If Tim gives you a list of document numbers to
grade first, add `--rows` and the list (for example `--rows 3,8,21`) to the
same command; the page then holds just those documents, and once they are
done you run the command again without `--rows`.

For each document, compare the page image (click it to enlarge; the form
stays beside it) with the form below the two engines' readings. Fix what is
wrong, clear what the page does not show, and press **Save**. If the form
is already right, press **Save** anyway; that records that the software was
right. If you cannot tell from the page, press **Can't tell from the page**.
The **Use AI engine's reading** button fills the form from the AI's answer
when that is closer; check it against the page before saving.
The "Open the full document" link does not work on your copy, since the
original files are not in the folder; the page image is what you grade from.

Type only what the page shows, as printed. Do not add anything the page
leaves out, such as a ZIP code it does not print: the answers teach
software to read the page, and it cannot look things up. When something
printed is hard to read (a digit that could be a 5 or a 6), you may check
an outside source to choose between the readings the page allows; say so
in the note. Only the first page is shown; if names or the address run
onto the next page, grade what this page shows and say so in the note.

Leave off a comma or semicolon at the end of a name; it only separates the
name from what follows on the page. A period that ends an abbreviation
("Inc.", "Jr.") stays. Save drops a trailing comma for you.

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
- A business the defendant does business as ("d/b/a") goes on a line of
  its own, so businesses can be counted.
- If the page spells a name two ways, type the likelier spelling and say
  so in the note.

**Plaintiff.** The landlord or company at the top of the page, the name
only: leave out the description after it ("a Washington limited liability
company", "a public body corporate and politic", "its successors and/or
assigns") and any trailing comma. Several plaintiffs go one per line; the
box grows to fit.

Some documents also have a **Plaintiff's attorney** box (`--attorneys 100`
puts it on 100 documents drawn at random, the same ones for every grader;
leave the option off and no document has it). It is the signature block,
usually at the bottom right of the page. Attorneys and the firm go in one
box, one per line, each as printed and in any order: every attorney's name
and the firm or office name, without "Attorney for Plaintiff" or the bar
number. Address goes on one line, as printed (street, suite, city, state,
ZIP). If the plaintiff has no attorney (signed by the landlord itself),
clear both boxes.

The **Note** box is for anything unusual: a name spelled two ways, a
second address, an address on the next page, a block you are unsure of.
Notes are read, and they shape the rules for the next round.

After a batch, press **Grade another batch** or close the tab. Everything
saved stays saved; reopening the page shows your work. Press Ctrl-C in the
terminal when you are done.

## Sending it back

Copy `corrections.jsonl` from the scan folder, rename it with your name
(`corrections_YOURNAME.jsonl`; with two folders in a round, add the folder's
name too), and upload it to the same restricted Drive folder the zip came
from. That is the only file Tim needs; he makes the
reports from it. It holds names and addresses: never commit it, email it,
or put it anywhere else.
