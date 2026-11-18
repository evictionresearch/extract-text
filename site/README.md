# The extract-text website

Five pages in the Eviction Research Network's 2026 design: the home page, Get started, How it works, Improve it, and About. The site is published at <https://evictionresearch.net/extract-text/> (since 2026-11-10).

## Edit a page

Each page is one `.qmd` file: `index.qmd`, `get-started.qmd`, `how-it-works.qmd`, `improve.qmd`, `about.qmd`. The text is plain markdown. The block between the `---` lines at the top holds the page title and the opening section (`hero`). Lines that start with `:::` open and close the boxes of the layout (a card, a row of cards, a notice); leave them in place and edit the text between them.

The header, the footer, and the fonts live in one file, `_extensions/ern/extract-text/template.html`, so a change there reaches all four pages.

## Rebuild after an edit

You need [Quarto](https://quarto.org). In a terminal:

```bash
cd site
quarto render
```

This rewrites the four `.html` files beside the `.qmd` files. Open `index.html` in a browser to look. The `.html` files are committed with their sources, as on the main ERN site.

## Files

```
index.qmd, get-started.qmd, how-it-works.qmd, improve.qmd, about.qmd   the pages
*.html                                                     the rendered pages
_extensions/ern/extract-text/template.html                 header, footer, page frame
assets/css/ern-2026.css          copy of the ERN design system (do not edit here)
assets/css/extract-text-2026.css what only this site needs
images/                          ERN logos, the Berkeley Sociology lockup, the
                                 illustration, and the three author portraits
media/                           the videos and their still images
```

`ern-2026.css`, the logos, the illustration, and the portraits are copies from the main site's repository (`evictionresearch.github.io`). Nothing keeps them in sync. When the main site's stylesheet changes, copy it here again.

## Keep in step with the package

- The example output blocks on `get-started.qmd` (the light boxes) were printed by the package on the made-up test documents. Print them again when the output changes shape.
- `get-started.qmd` shows each step three ways, in tabs: R, Terminal, and Python. The R tabs follow `getting_started_example_script.R`, and the Terminal and Python tabs follow the last two sections of `docs/start_here.md`. When either changes, change the page. A tab set is a `.tabs` box holding one `.tab` box for each of the three, marked `data-tab="r"`, `"terminal"`, or `"python"`; the script in `template.html` adds the buttons and keeps every set on the page on the same choice. A link can open the page on a tab (`get-started.html?tab=terminal`).
- The Terminal and Python example output on `get-started.qmd` was printed on the 15 tracked made-up documents in `python/tests/fixtures/` on 2026-11-18, six of them graded on the review page. The folder names are written as `DOCS` and `RESULTS`, and the grader's user name as `yourname`.
- `improve.qmd` follows `docs/changing_rules.md` in its second half, and its example report was printed by `extract-text score --shapes` on made-up documents. When the guide or the report changes, change the page.
- The version number appears in `index.qmd` (the badge), `how-it-works.qmd` (Status), and `about.qmd` (the citation). The release checklist in `MAINTENANCE.md` should include them.
- The accuracy numbers in `how-it-works.qmd` and `index.qmd` come from section 13 of `docs/manual.md`. Change them there first.
- The step numbers are shared. `get-started.qmd`, `getting_started_example_script.R`, and `docs/start_here.md` use the same eight steps, and other pages refer to them by number. Renumber all three together or not at all.
- The status of the two engines (the rules engine released, the local AI engine experimental) is stated on `index.qmd`, `how-it-works.qmd`, `get-started.qmd`, the README, and section 2 of the manual. Change them together when the AI engine's test is finished.

## The videos

The two on the site's pages run one minute, with text on screen and no sound. Each has a "Read what the video says" list under it on the page, which holds the same words for anyone who cannot watch it. When a video changes, change its list.

The grading video's list is a fuller script, and the page shows it one line at a time under the player as the video plays. Each line in `get-started.qmd` carries `data-start`, the second of the video it begins at. The times follow the holds in the recording script, so when the video is recorded again, set them again. The short script in `template.html` that does this works for any video whose list has `class="script"` and `data-start` on its lines.

- `media/overview.mp4` is on the home page. It says what the tool reads, shows the rules engine, the local AI engine, and the two together, then privacy, grading, other court documents, and what is planned.
- `media/grading.mp4` is on the Get started page (step 5). It shows one document being graded: a misread city fixed, a box drawn for the defendants and added to the engine's own, the cross that deletes a box, and Save. It was recorded again on 2026-11-17, when a drawn box stopped taking the place of the engine's. The picture zooms in on the part of the page in use, and the captions run across the top of the frame, clear of the player's controls. Every document in it is one of the made-up test pages in `python/tests/fixtures/corpus/`.
- `media/demo.mp4` and `media/demo.gif` are for the repository's README, not for a page of this site. They run 28 seconds, with no title card and no end card, because the README plays the `.gif` on its own in a loop; the logo stays in the caption bar throughout, and the first caption says the documents are made up. They show a scan of the 15 tracked made-up documents from the terminal, one document on the review page, and the table that comes out. The terminal lines and the table rows were read from that scan's own output, not typed in. The README shows the `.gif`, which plays where the README is read, and links it to the `.mp4` here. Record both again when the scan's printed lines or the review page change.

Two rules for any video made for this site. The Eviction Research Network logo appears in it, on the title and end cards and on screen throughout. And no video is ever made from real court documents. Record the grading video again when the review page changes, and the overview when what it says stops being true.

## Where the facts come from

Checked 2026-11-10.

- The *Cityscape* citation, authors, affiliations, and summary: the article's HUD USER page, <https://www.huduser.gov/portal/periodicals/cityscape/vol26num1/article12.html>.
- The dissertation's title, degree, year, and the counts of cases and files: its title page and abstract, <https://escholarship.org/uc/item/7f36p8n6>.
- Cheng Ren's title and the dissertation award: his University at Albany profile, <https://www.albany.edu/cihs/faculty/cheng-ren>, and the university's news item of January 2025, <https://www.albany.edu/news-center/news/2025-qa-cheng-ren-leveraging-ai-advance-housing-justice>.
- Tim Thomas's title and description: his UC Berkeley Sociology profile, <https://sociology.berkeley.edu/visiting-faculty/tim-thomas>.
- Aaron Culich's title: the main ERN site's About page.
- The braindr citation: <https://doi.org/10.3389/fninf.2019.00029>.
- The Eviction Research Network sentence on the About page and in the footer is the canonical wording from the ERN library's `ORG.md`. Do not paraphrase it.
- Everything about the package: `README.md`, `docs/manual.md`, `CHANGELOG.md`, `MAINTENANCE.md`, `ETHICS.md`, and `DATA-USE.md` in this repository.

## Publish

A push to `main` that changes anything in `site/` publishes the site. The workflow is `.github/workflows/pages.yml`. It publishes only the site's own files, never the whole repository:

```
index.html
get-started.html
how-it-works.html
about.html
assets/
images/
media/
```

To publish a new file or folder, add it to the list in the workflow's "Collect" step. Render before you push (`quarto render`), because the workflow publishes the `.html` files as committed and does not run Quarto.
