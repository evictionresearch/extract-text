# Changing the rules on your own computer

The deterministic engine reads documents with written rules, which are Python code inside the package. Grading never changes them. A person does, and this guide shows how to do that on your own copy of the package, in nine steps: get the code, run the engine from it, find what to fix, find the rule, change it, measure the change against your graded documents, use it, keep it through package updates, and share it if you want to.

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

Suppose the defendant names on your documents end in "UNKNOWN OCCUPANTS", and the engine keeps that as if it were a person. Open `parties.py`, find `_GROUP_TERM_RE`, and add one line after the "all occupants" line:

```
      | all\s+(?:other\s+)?occupants?          # "all occupants"
      | unknown\s+occupants?                   # "unknown occupants"
```

`\s+` means one or more spaces, and `s?` an optional "s", so the line catches "UNKNOWN OCCUPANT" and "Unknown Occupants" alike (the list ignores capital letters). Reinstall (step 2), restart R, and try it on a made-up name:

```r
p <- reticulate::import("extract_text.parties")
reticulate::py_get_attr(p, "_strip_group_terms")("JANE Q. TENANT and UNKNOWN OCCUPANTS")
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

Re-scan the same documents into the same folder (getting-started step 11). Your graded answers are kept, `score_documents()` shows the new accuracy, and `case_table()` builds the table from the new readings.

## 8. Keep your changes through package updates

With git, save your change on a branch of its own, from inside the `extract-text` folder:

```bash
git checkout -b local-rules
git commit -am "Drop 'unknown occupants' from defendant names"
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

## Running the package's own tests (optional)

The package's tests check that existing behavior still holds after a change. They use only made-up documents:

```r
reticulate::py_install("pytest", envname = "r-extracttext", pip = TRUE)
system2(py, c("-m", "pytest", "-q", path.expand("~/extract-text/python/tests")))
```

Some tests are skipped when poppler or tesseract is missing. A failing test after your change means the change altered something the package relies on; read the test's name and message before going on.
