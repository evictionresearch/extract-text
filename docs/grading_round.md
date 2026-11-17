# Grading in a Network round

This page is for graders in one of the Eviction Research Network's grading
rounds, where several people grade the same set of documents from a zip.
If you are following the Get started steps on your own documents, you do
not need it: your review page is served from your own computer and saves
as you go.

[`GRADING.md`](../GRADING.md) says what belongs in each field. Read it
first. Your answers become the test set the engines are measured against
and the examples the AI engine learns from, so a careful ten is worth more
than a hurried hundred.

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

Grade each document as [`GRADING.md`](../GRADING.md) describes. Three
things differ on a round's page.

- The form sits below the two engines' readings. The **Use AI engine's
  reading** button fills the form from the AI's answer when that is
  closer; check it against the page before saving.
- Only the page images are in the folder; they are what you grade from. If
  names or the address run onto a page the folder does not show, grade
  what is shown and say so in the note.
- Some documents also have a **Plaintiff's attorney** box (Tim chooses how
  many when he builds the page; they are drawn at random, the same ones for
  every grader).

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
