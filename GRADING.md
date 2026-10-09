# Grading extractions

You have been asked to check what the software read off eviction summonses
and to type the right answer where it is wrong. Your answers become the
test set that the deterministic engine is fixed against, so a careful ten
is worth more than a hurried hundred.

## What you need

1. This repository, cloned, and Python 3.10 or newer. Then, in a terminal:

       cd extract-text/python
       python3 -m venv .venv && source .venv/bin/activate
       pip install -e .
       extract-text --version

   A version number means it is installed. Grading needs nothing else: no
   AI model and no scanning tools, because the readings and the page images
   are already in the folder you receive.

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

Write the address as printed: street without the unit, unit on its own
(`Apt 5`, `BLDG C Apt 5`, `#12`), city, state, ZIP. Defendants go one per
line, named people only; leave out "all other occupants", "John Doe", and
"et al". The plaintiff is the landlord or company at the top of the page.

Some documents also have a **Plaintiff's attorney** box (`--attorneys 100`
puts it on 100 documents drawn at random, the same ones for every grader;
leave the option off and no document has it). It is the signature block, usually at the
bottom right of the page. Attorneys go one per line, each name as printed,
without "Attorney for Plaintiff" or the bar number. Firm is the firm or
office name, left empty if the block has none. Address goes on one line,
as printed (street, suite, city, state, ZIP). If the plaintiff has no
attorney (signed by the landlord itself), clear all three.

After a batch, press **Grade another batch** or close the tab. Everything
saved stays saved; reopening the page shows your work. Press Ctrl-C in the
terminal when you are done.

## Sending it back

    extract-text score --out /path/to/the/folder --shapes --save reports/$(date +%F)_YOURNAME.txt

Commit that report file to this repository, or email it to Tim; it holds no
record values. Then copy `corrections.jsonl` from the scan folder, rename it
with your name (`corrections_YOURNAME.jsonl`), and upload it to the same
restricted Drive folder the zip came from. That file holds names and
addresses: never commit it, email it, or put it anywhere else.
