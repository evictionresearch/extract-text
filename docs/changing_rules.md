# Changing the rules on your own computer

The deterministic engine reads documents with written rules, which are Python code inside the package. Grading never changes them. A person does, and this guide shows how to do that on your own copy of the package, in nine steps: get the code, run the engine from it, find what to fix, find the rule, change it, measure the change against your graded documents, use it, keep it through package updates, and share it if you want to.

A form template, learned from the boxes drawn while grading, improves the engine's reading of your own documents with no code at all. The last chapter, "Teaching the engine a form, without code", covers it. Try that first when the engine misses the same field on documents that share a printed form. A template changes where the engine looks, not how it reads. The rules in this guide still do the reading inside each box. When the rules themselves need to change, work with the Eviction Research Network (section 9) or follow the steps below on your own copy.

Most fixes are a line or two in a regular expression (a text pattern). You need to be comfortable reading and editing short patterns; no other Python is needed for most changes. The commands below are R, from the same session you use for the getting-started script.

## Before you start

You need a scan with graded documents, from steps 4 to 7 of `getting_started_example_script.R`, because every change is measured against them. Two graded sets are better than one: develop a change on the first sample and test it on the second (step 9's sample from the full run). A change shaped on the documents it is measured on always looks better than it is.

## 1. Get your own copy of the code

Copy the code with [git](https://git-scm.com/downloads), in Terminal on a Mac or PowerShell on Windows:

```bash
git clone https://github.com/evictionresearch/extract-text.git
```

This makes a folder called `extract-text` in the current directory. Without git, use the green Code button on GitHub, then Download ZIP, and unzip it; git is better, because it lets you take later updates without losing your changes (step 8).

Keep this folder apart from the folders that hold court documents, and never copy court documents or results into it.

## 2. Run the engine from your copy

```r
extracttext_install(source = "~/extract-text/python")   # the folder from step 1
```

Then restart R. From now on the engine runs from your copy. After every edit, run that line again and restart R; it takes about 20 seconds.

Do not run `extracttext_install()` without `source`, or step 1 of the getting-started script, while you work this way: both install the package from GitHub and replace your rules with the published ones.

## 3. Find what to fix

Start from the score of your graded documents:

```r
score_documents(res, save = "score_report.txt")
```

The saved report lists, field by field, how many documents the engine got right, nearly right, left blank, or got wrong, and shows each wrong value in masked form (letters become A or a, digits 9), so you can see the shape of a failure without the name or address. On your own computer you can also compare the engine's reading with your answer directly: `corrections.jsonl` in the scan folder holds both for every graded document, and `case_table()` beside `res` shows your answers next to the engine's readings, row for row.

Two columns of the scan tell you which rule was involved. `defendant_anchor` names the rule that found the defendants' address (see step 4), and `flags` lists the checks a document failed. For a single document, `extract_deterministic(f)$evidence` shows the rule and the place on the page for every value.

Look for a failure that repeats. One odd document is not worth a rule; five with the same shape are.

## 4. Find the rule

Every path below is inside the folder from step 1.

- **`python/src/extract_text/parties.py`**: cleanup of party names, shared by both engines. Near the top, `_GROUP_TERM_RE` is the list of phrases dropped from the end of the defendants' names ("et al.", "all other occupants", "John Doe").
- **`python/src/extract_text/deterministic/summons.py`**: the core of the engine, in four parts, each under a heading comment. "Constants and patterns" holds the case-number format, street types, unit words, the city, state, and ZIP pattern, and the repairs for common OCR misreadings. "The defendant anchor ladder" holds the four ways the address is found, tried in order until one works: `to_block` (the TO: service block), `premises_prose` ("premises located at"), `address_stack` (a street line over a city line), and `caption_cell` (the case caption); the plaintiff reader follows it. "The attorney block" finds the plaintiff's attorney at the bottom right. "Assembly" puts the fields together.
- **`python/src/extract_text/deterministic/patterns.py`**: general patterns for other fields (court name, county, filing date, amounts, disposition).
- **`python/src/extract_text/standardize.py`**: the USPS forms used in the `_std` address columns.

Three rules are specific to Washington and marked where they are defined: the state name in the city, state, and ZIP pattern, the superior court case-number format, and the bar-number label (manual section 16).

Most rules carry a comment saying why they exist, and many say what they must not catch. Read it before changing the rule.

## 5. Change the rule, with a worked example

Suppose the defendant names on your documents end in "OCCUPANTS OF THE PREMISES", and the engine keeps that as if it were a person. Open `parties.py`, find `_GROUP_TERM_RE`, and add one line after the "unknown occupants" line:

```
      | unknown\s+occupants?                   # "unknown occupants" (2026-11-09)
      | occupants\s+of\s+the\s+premises        # "occupants of the premises"
```

`\s+` means one or more spaces, so the line catches the phrase however the spaces fall, and the list ignores capital letters, so "Occupants of the Premises" is caught too. Reinstall (step 2), restart R, and try it on a made-up name:

```r
p <- reticulate::import("extract_text.parties")
reticulate::py_get_attr(p, "_strip_group_terms")("JANE Q. TENANT and OCCUPANTS OF THE PREMISES")
```

The first value returned should be `JANE Q. TENANT`.

Change one thing at a time, so a measurement can be traced to it. Put a comment above the change saying what it fixes, with a made-up example, never a real name, address, or case number. And keep patterns narrow: a pattern that catches more than you meant breaks documents that were right.

## 6. Measure the change

`rules_eval.py`, in your copy, reads every graded document again with your rules and counts, field by field, what the change fixed and what it broke:

```r
py <- reticulate::virtualenv_python("r-extracttext")
eval_script <- path.expand("~/extract-text/python/scripts/rules_eval.py")

# the first sample, where you developed the change
system2(py, c("-I", eval_script, "--out", sample_dir))
```

Each field gets a line: how many graded documents, how many the engine had right before (as saved in the scan), how many it has right now, and how many were fixed and broken. Add `"--shapes"` to see each wrong value in masked form. The page text is kept in `_rules_eval_cache` inside the scan folder, so a second run takes seconds.

Then test on documents the change was not shaped on, the second sample:

```r
system2(py, c("-I", eval_script, "--out", all_dir))
```

Keep a change that fixes documents there and breaks none. A change that breaks anything needs a second look before you use it.

## 7. Use it

Re-scan the same documents into the same folder (getting-started step 12). Your graded answers are kept, `score_documents()` shows the new accuracy, and `case_table()` builds the table from the new readings.

## 8. Keep your changes through package updates

With git, save your change on a branch of its own, from inside the `extract-text` folder:

```bash
git checkout -b local-rules
git commit -am "Drop 'occupants of the premises' from defendant names"
```

When the Eviction Research Network publishes an update, bring it into your copy and reinstall (step 2):

```bash
git fetch origin
git merge origin/main
```

Where the update changed the same lines you did, git stops and asks you to choose; otherwise the two sets of changes combine. Measure again (step 6) after every update.

## 9. Share a change back, if you want to

A fix that would help others is welcome as a pull request on GitHub; `CONTRIBUTING.md` covers how. Its one rule without exceptions applies: every example and test uses made-up values.

Do not attach documents, extracted values, corrections, or score reports from your records to an issue or pull request, even masked ones, because GitHub is public. If you want the Eviction Research Network to look at results from your records, ask first: that needs a data agreement between your organization and UC Berkeley before anything is sent.

## Teaching the engine a form, without code

The rules above are general: they look for a "TO:" label, a street line over a city line, an attorney block at the bottom right. A court's own form can defeat them, printing the tenant's address under a label the rules do not know, in a column where they do not look, or on a page they do not read. A form template fixes that for one form at a time, with no code: it records where that form prints each field, and the engine looks there first on every document it recognizes as that form.

A template tells the engine where to look. The rules still do the reading inside each box. They split the names from the street, find the city and ZIP, and drop the words a form prints around them. So a template fixes the engine looking in the wrong place, which is most of what goes wrong on an unfamiliar form. It does not fix a rule that misreads what it finds, such as a street type it does not know or a unit written a new way, and it does not fix a scan OCR got wrong. For those the rules need to change, in one of two ways. Work with the Eviction Research Network, which measures and publishes rule changes for every user; section 9 says how to ask, and that nothing from your records is sent. Or change the rules on your own copy by the steps above.

A template is learned from grading. On the review page, every value the engine read has a box on the page image. Where a box is wrong, and the page can save (served with `correct = TRUE`, or the graders' page), move it, reshape it at its corners, or delete it, the engine's own box included. Where one is missing, pick the field under the page and drag across the image where the value really is, on whichever page it is printed. The boxes are saved with your answer. A box can be joined by another for the same field. Box every place the form prints a field: the defendants in the caption and again in the service block, the attorney block in the footer of every page, an address on page 3 of a bundle. The engine reads every region and lists a defendant named twice once. Where you left a field as the engine read it, the engine's own box counts as confirmed by you. Both kinds of box teach the template.

### What a template is

One readable JSON file per form, in a `templates` folder beside the scan (or a folder you name), with two parts:

- a **fingerprint**: the words the form itself prints, with their positions on the page. A word qualifies when it is on nearly every graded page of the form at the same place. Names, addresses, and case numbers differ from page to page, so they never qualify, and anything inside a field's region is left out as well. A new page is recognized when enough of these words are found where they belong, allowing for the shift a scanner adds to a whole page.
- **regions** per field (plaintiff, defendants, address, attorney, case number), each on a page: the union of the boxes for that field on that page across the graded documents, as fractions of the page width and height from the top left, so scan resolution does not matter, with the count of boxes it came from. A field can have a region on more than one page (the attorney block on pages 1 and 2; an address on page 3), and the engine reads those pages for a matching document even when its ordinary pass would skip them. A box far from the others is left out as a slip of the mouse, and the file says so.

The file holds those words and coordinates and the row numbers it was learned from. It holds no value from any document, which is what lets a county share a template back to the Eviction Research Network. Look at the file before sharing it all the same, and ask first, as section 9 says.

### Learn, look, approve, use

In R, from the scan you graded (here `res_all`, the full run):

```r
learn_templates(res_all)
```

This reads every graded document that has a box again (the text is cached beside the scan), groups the documents by the printed form of their first page, and writes one template per form that has at least five graded documents, as `form-1.json`, `form-2.json`, and so on in `results/all/templates/`. The report says how many graded documents had a labeled position, how they grouped, and for each region how many drawn and confirmed boxes it came from. A form on fewer than five documents is named in the report and gets no template. Grade more of its documents, or lower `min_pages` if you accept a thinner template. Ten to twenty per form is the figure from the method this follows, Cheng Ren's dissertation, where a layout model is trained per form. The review page says when a template has fewer than ten.

```r
review_templates(res_all)
```

This opens a page showing each template's regions drawn over the pages of one document it was learned from, with the printed words that identify the form as small dots. Check two things: that each region sits over the part of the form where that field is printed, and that no dot sits on a name or an address. The page renders a document's pages, so its folder stays with the scan.

```r
approve_template("form-1", res_all)
```

Nothing learned is used until a person approves it. Approval writes your login name and the date into the file, and `approve_template("form-1", res_all, approved = FALSE)` takes it back. Then re-scan with the folder:

```r
res_all <- scan_documents(docs_dir, out_dir = all_dir,
                          templates = file.path(all_dir, "templates"))
table(res_all$template)
score_documents(res_all)
```

The `template` column names the form each document matched (blank for none), and `defendant_anchor` reads `template:form-1` wherever the address came from the template's region (`template:form-1@p3` when the region is on page 3). On a document that matches, each field is read from its regions first, in page order. A region that is empty on that document, or holds nothing that parses as that field, leaves the field to the ordinary rules, so a template can only add readings, never remove the rules' own. A document that matches no template is read exactly as before. A folder with no approved template is an error rather than a silent no-op, so a run that used none is never mistaken for one that did.

### Measuring what a template did

`rules_eval.py` (step 6) takes `--templates`:

```r
system2(py, c("-I", eval_script, "--out", all_dir, "--templates", file.path(all_dir, "templates")))
```

The report counts, field by field, what the templates fixed and broke against your graded answers, and how many documents matched each template. The same rule as for a rule change applies: measure on documents the template was not learned from (the second graded sample, or `--rows` for the rows you held out), and keep a template that fixes documents there and breaks none.

### When it does not help

- **The form is not recognized.** `table(res_all$template)` shows few or no matches for a form you know is common. Scans of the same form from different years or firms can shift or re-set the printed text. Grade and box more documents of it and learn again, or lower `match_threshold` in the file, the share of fingerprint words a page must show, 0.6 by default, a little at a time, measuring each change.
- **A region is too narrow.** A region is the union of the boxes it was learned from, so a value longer than any of them, a fourth defendant where every graded document had two, can fall outside it. Grade and box a document that has the longer value, and learn again.
- **The value is on a page nobody boxed.** The engine reads the pages that have regions. If the address of some documents sits on page 3 and no graded document was boxed there, turn to page 3 on the review page, draw the box, and learn again. The template then carries a page-3 region beside the page-1 one.
- **The right place is read wrong.** The region is where the value is, but the reading is still wrong or blank. A rule, not a position, is the problem. Say so to the Eviction Research Network with the masked shapes from `score_documents(res, save = ...)`, or change the rule on your own copy (steps 1 to 8).
- **Two forms were grouped as one, or one as two.** The grouping uses the words two pages share at the same positions. `learn_templates(res_all, rows = c(...), name = "county-summons-2017")` learns one template from exactly the documents you name.
- **The same words fall in a region on every document**, as on a form that prints a fixed line inside the address block. They are left out of the fingerprint by design, since the region is where values live, and the rules that parse the region ignore printed labels at its head.

### Where templates live

Templates live in the user's results folder, never in a code repository. A template holds no personal values, but the `review` folder beside it holds page images, which do. The deterministic engine stays deterministic with templates. The same document with the same templates always gives the same answer, and no model is involved.

## Running the package's own tests (optional)

The package's tests check that existing behavior still holds after a change. They use only made-up documents:

```r
reticulate::py_install("pytest", envname = "r-extracttext", pip = TRUE)
system2(py, c("-m", "pytest", "-q", path.expand("~/extract-text/python/tests")))
```

Some tests are skipped when poppler or tesseract is missing. A failing test after your change means the change altered something the package relies on; read the test's name and message before going on.
