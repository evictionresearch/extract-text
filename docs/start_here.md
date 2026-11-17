# From a folder of court documents to a table

You bring a folder of court documents, as PDFs or TIFF images. You leave with a table that has one row per document: the case number, the plaintiff, the defendants, and the address where the defendants were served. You also leave knowing how often each of those columns is right on your documents, because you checked a sample by hand.

This page is the whole procedure in plain words. It uses the rules engine, which needs no AI and, once installed, no internet. Your documents never leave your computer.

## Two ways to follow it

- **In R.** Open [`getting_started_example_script.R`](../getting_started_example_script.R) in RStudio and run it a block at a time. Each stage below names its step in the script, and the script explains each line.
- **At a terminal.** The command for each stage is at the end of this page.

The stages are the same either way, and so are the files they write.

## What you need

- A Mac, Windows, or Linux computer that you are allowed to keep court records on.
- Four free programs, installed once: poppler, tesseract, Python 3.10 or newer, and git. The top of the script and the [README](../README.md#install) give the install lines for each system. To follow the script you also need R and RStudio.
- Your documents in one folder on that computer. Subfolders are fine.
- An empty folder for the results. Everything written there holds names and addresses, so keep it where you keep the documents. Keep both folders out of Dropbox, iCloud Drive, OneDrive, and any Google Drive folder that syncs.

## The eight stages

| | Stage | What you do | Script steps |
|---|---|---|---|
| 1 | Set up | Install the package and read one made-up summons | 1 to 3 |
| 2 | Scan a sample | The engine reads a random 50 of your documents | 4 and 5 |
| 3 | Grade the sample | You check those 50 against the page and fix what is wrong | 6 |
| 4 | Read the score | You see how often each field was right, and decide whether to go on | 7 |
| 5 | Teach your forms (optional) | The engine learns where your court's forms print each field | 8 |
| 6 | Scan everything | The engine reads the whole folder | 9 |
| 7 | Grade a second sample | You check 50 more, from the full run, and score again | 10 and 11 |
| 8 | Build the table | One row per document, your answers in place of the engine's wherever you gave one | 13 |

### 1. Set up

Install the package and run its check. The check ends with "Ready: the deterministic engine can run." Do not go on until it says so; the script says what to do when it does not. Then read the made-up summons that comes with the package and compare the result with the address the script tells you to expect.

### 2. Scan a sample

Start with a random 50 of your documents, not the whole folder. A scanned page takes about 5 seconds to read, so the sample takes a few minutes. The result is not ready to use. Nobody knows yet how often it is right on your documents.

### 3. Grade the sample

A page opens in your browser. It shows each document beside what the engine read. For each document:

1. Check each field against the page. Change what is wrong, and leave a field blank when the document does not have it.
2. Look at the colored boxes on the page image. Each box shows where the engine read one value. Drag a box that sits over the wrong place to the right one. Where a field has no box, press the field's button under the image and drag across the value.
3. Press Save, even when the engine got everything right.

Plan on about an hour for 50 documents. You can stop at any point and pick up where you left off. [`GRADING.md`](../GRADING.md) says what belongs in each field, and [`grading_with_boxes.md`](grading_with_boxes.md) covers the boxes.

### 4. Read the score

The score has one row per field: how many documents you checked, and how many the engine got right, nearly right, left blank, or got wrong. Fifty random documents put the share right within about 10 points.

Decide here whether the fields you need are accurate enough to scan everything. If a field is weak, stage 5 may fix it. If it is still weak after that, check for a newer version of the package, or write to the Eviction Research Network at evictions@berkeley.edu. Never send a real document, name, address, or case number.

### 5. Teach the engine your forms (optional)

Courts print their own forms, and a form can put the tenant's address where the engine's rules do not look. The boxes you fixed and drew while grading show where your court's forms print each field. From them the package writes a template for each form that has at least five graded documents. A template holds the form's printed words and a region of the page for each field. It holds no names or addresses.

You look at each template drawn over one of its pages and approve the ones that are right. Nothing learned is used until you approve it.

A template has two limits. A random 50 rarely holds five documents of a rare form, so expect templates only for the forms your court uses most; a larger first sample covers more forms. And a template changes where the engine looks, not how it reads. When the engine looks in the right place and still reads a value wrong, a rule has to change, which stage 4 covers.

### 6. Scan everything

The engine reads the whole folder, using the templates you approved, and its rules alone on every other document. This needs no attention while it runs. At about 5 seconds a document, 4,000 documents take five or six hours.

### 7. Grade a second sample

Grade 50 more documents, drawn at random from the full run, the same way as stage 3, and score again. The first sample told you whether to run everything. This one measures the run that becomes your table, templates included. Report its share right with the table. Grade 100 or more before you publish counts or send anything to people.

### 8. Build the table

The package writes `case_table.csv` in your results folder, one row per document. Wherever you graded a document, in either sample, your answer replaces the engine's, and the `source` column says which each row carries. The table is the input to the next stage of work, cleaning the names and addresses.

## What grading does

Grading does three things. The score tells you which fields to trust. Your answers go into the final table. And your boxes can teach the engine your court's forms, once you approve the template.

Grading does not change the engine's rules. Run the engine again on the same documents and it gives the same answers. Its readings change only when you update the package, change a rule on your own copy ([`changing_rules.md`](changing_rules.md)), or approve a template. Scan again only then. A second scan into the same folder keeps your corrections.

## When something goes wrong

- Run the setup check again. It names what is missing and how to fix it.
- Section 18 of [the manual](manual.md#18-troubleshooting) lists common problems.
- Write to evictions@berkeley.edu or open an issue on GitHub. Describe the problem, or reproduce it with the made-up summons. Never paste a real document, name, address, or case number.

## The same stages at a terminal

Install the four programs first, then the engine. `DOCS` is your documents folder and `RESULTS` your results folder.

```bash
# 1. Set up
pip install "extract-text @ git+https://github.com/evictionresearch/extract-text#subdirectory=python"
extract-text doctor

# 2. Scan a sample
extract-text scan DOCS --engine deterministic --sample 50 --seed 1 --out RESULTS/sample

# 3. Grade the sample (Ctrl-C when done)
extract-text review --out RESULTS/sample --random 50 --serve

# 4. Read the score
extract-text score --out RESULTS/sample

# 5. Teach the engine your forms (optional)
extract-text templates learn --out RESULTS/sample
extract-text templates review --templates RESULTS/sample/templates --out RESULTS/sample
extract-text templates approve form-1 --templates RESULTS/sample/templates

# 6. Scan everything (leave off --templates if you approved none)
extract-text scan DOCS --engine deterministic --out RESULTS/all --templates RESULTS/sample/templates

# 7. Grade a second sample, and score it
extract-text review --out RESULTS/all --random 50 --serve
extract-text score --out RESULTS/all

# 8. Build the table
extract-text case-table --out RESULTS/all --graded RESULTS/sample --save RESULTS/case_table.csv
```
