# Grading extractions

You have been asked to check what the software read off eviction summonses
and to type the right answer where it is wrong. Your answers become the
test set the engines are measured against and the examples the AI engine
learns from, so a careful ten is worth more than a hurried hundred.

## What you need

Google Chrome and a zip from Tim in a restricted Google
Drive folder shared with you by name (never by email, never by a public
link). Nothing to install, and no terminal.

The zip holds a `review` folder: the grading page and the page images it
shows. It is real court records. Download the zip, unzip it on your own
computer, and work from that copy. Keep it out of any shared or synced
folder (not in Dropbox, iCloud Drive, OneDrive, or a Google Drive that
syncs), leave it where you unzipped it until the round is over, and delete
it then.

## Grading

Open the `review` folder and double-click `index.html`. If it opens in a
browser other than Chrome, open it from Chrome instead (File, Open
File). Do not use a private or incognito window: it
forgets your answers when it closes.

At the top, type your name (required) and email, and choose how many
documents to grade. Ten is a good first batch. The page decides the order
(Tim set it when he built the page) and shows one batch at a time.

For each document, compare the page image (click it to enlarge; the form
stays beside it) with the form below the two engines' readings. Fix what is
wrong, clear what the page does not show, and press **Save**. If the form
is already right, press **Save** anyway; that records that the software was
right. If you cannot tell from the page, press **Can't tell from the page**.
The **Use AI engine's reading** button fills the form from the AI's answer
when that is closer; check it against the page before saving.
Only the page image is in the folder; it is what you grade from.

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

Some documents also have a **Plaintiff's attorney** box (Tim chooses how
many when he builds the page; they are drawn at random, the same ones for
every grader). It is the signature block,
usually at the bottom right of the page. Attorneys and the firm go in one
box, one per line, each as printed and in any order: every attorney's name
and the firm or office name, without "Attorney for Plaintiff" or the bar
number. Address goes on one line, as printed (street, suite, city, state,
ZIP). If the plaintiff has no attorney (signed by the landlord itself),
clear both boxes.

The **Note** box is for anything unusual: a name spelled two ways, a
second address, an address on the next page, a block you are unsure of.
Notes are read, and they shape the rules for the next round.

After a batch, press **Grade another batch** or close the tab. Each Save
is kept in that browser on that computer, and reopening `index.html` there
shows your work. Use the same browser every time, and do not clear its
browsing data until the round is over.

## Sending it back

When you stop for the day, press **Download my answers** in the green box
at the top. The browser saves a file named
`answers_YOURNAME_FOLDER.jsonl` to your Downloads folder. Upload it to the
same restricted Drive folder the zip came from. Each download holds every
answer you have saved on that page so far, so the newest file is the only
one Tim needs; replace the older one in Drive. With two folders in a
round, each folder's page gives its own file.

The green box counts the answers not yet downloaded, and the browser asks
before you close the page while there are any. If your answers ever
disappear from the page (a cleared browser, a new computer), press
**Bring back answers from a downloaded file** and choose your newest
download.

The file holds names and addresses: Drive only. Never email it, commit
it, or put it anywhere else, and delete it from Downloads when Tim
confirms he has it.

## The terminal route

The page also runs from a server on your own computer, as in round 1:
clone this repository, install it (`cd extract-text/python && python3 -m
venv .venv && source .venv/bin/activate && pip install -e .`), and run

    extract-text review --out /path/to/the/folder --graders --attorneys 100 --serve

on a full scan folder. Saves then go to `corrections.jsonl` in that
folder; rename a copy `corrections_YOURNAME.jsonl` and upload it to Drive.
Press Ctrl-C in the terminal when you are done. If you have the
repository from an earlier round, update it with
`git fetch origin && git reset --hard origin/main` from its folder; a
plain `git pull` refuses, because the history was rewritten before the
repository went public on 2026-10-20.
