# From a folder of court documents to a table

You bring a folder of court documents, as PDFs or TIFF images. You leave with a table that has one row per document: the case number, the plaintiff, the defendants, and the address where the defendants were served. You also leave knowing how often each of those columns is right on your documents, because you checked a sample by hand.

This page is the whole procedure in plain words. It uses the rules engine, which needs no AI and, once installed, no internet. Your documents never leave your computer. The local AI engine is experimental and is not used here.

## Three places, the same eight steps

- **The [Get started page](https://evictionresearch.net/extract-text/get-started.html)** has the R code for each step, to copy and run, and a one-minute video of grading.
- **[`getting_started_example_script.R`](../getting_started_example_script.R)** is the same code in one file, with more explanation. Open it in RStudio and run it a block at a time.
- **This page** says what each step does and why, and ends with the same steps as terminal commands.

Step 5 means the same thing in all three, and so do the files each step writes.

## What you need

- A Mac, Windows, or Linux computer that you are allowed to keep court records on.
- Your documents in one folder on that computer. Subfolders are fine. Step 4 says which documents to put there.
- An empty folder for the results. Everything written there holds names and addresses, so keep it where you keep the documents. Keep both folders out of Dropbox, iCloud Drive, OneDrive, and any Google Drive folder that syncs.
- To follow the R code, R and RStudio.

## The eight steps

| | Step | What you do |
|---|---|---|
| 1 | Install four free programs | poppler, tesseract, Python, and git, once per computer |
| 2 | Install extract-text | Install the package and run its checkup |
| 3 | Read one example | The engine reads a made-up summons, and you compare |
| 4 | Scan a random 50 | The engine reads a random 50 of your documents |
| 5 | Grade and score | You check those 50 against the page, fix what is wrong, and read the score |
| 6 | Teach your forms (optional) | The engine learns where your court's forms print each field |
| 7 | Scan the whole folder | The engine reads everything, and you grade and score a second 50 |
| 8 | Build the table | One row per document, your answers in place of the engine's wherever you gave one |

### 1. Install four free programs

extract-text needs four programs that neither R nor Python installs. poppler opens PDF files. tesseract reads scanned pages (OCR). Python 3.10 or newer runs the engine. git downloads the engine during the install. The Get started page and the top of the script give the install lines for Mac, Windows, and Linux. On a work computer, the installs may need your IT department.

### 2. Install extract-text

Install the package and run its checkup. The checkup ends with "Ready: the deterministic engine can run." Do not go on until it says so. The script says what to do when it does not. The checkup reports the AI program (Ollama) as missing, and that is fine.

### 3. Read one example

Read the made-up summons that comes with the package and compare the result with the address the script tells you to expect.

### 4. Scan a random 50

Start with a random 50 of your documents, not the whole folder. A scanned page takes about 5 seconds to read, so the sample takes a few minutes. The result is not ready to use. Nobody knows yet how often it is right on your documents.

**Practice first, on made-up documents.** Steps 4 to 8 run on the package's 15 made-up documents as well as on real ones, so you can learn the grading page before you open a court record. The script and the Get started page have the lines that fetch them. The documents are few and partly repeat one another, so the practice scores mean nothing.

**Which documents to put in the folder.** The engine reads one document at a time and writes one row for every file, whatever kind of document the file is. Its rules are built for the summons. If your folder holds whole case files (complaints, orders, returns of service), a case gets a row for each of them. When the file names say which documents are summonses, scan those alone. The script shows how.

**Documents from outside Washington.** The rules that read the city and the state expect "WA" or "Washington" after the city. On a made-up Oregon summons and a made-up Texas one, the engine read the street, the unit, and the ZIP, left the city and state blank, and raised no flag. Every document you grade carries your city and state in the final table, and the others carry the street and ZIP alone. ["Documents from another state"](changing_rules.md#documents-from-another-state) shows the four-line change that makes the engine read your state.

### 5. Grade and score

A page opens in your browser. It shows each document beside what the engine read. For each document:

1. Check each field against the page. Change what is wrong, and leave a field blank when the document does not have it.
2. Look at the colored boxes on the page image. Each box shows where the engine read one value. Drag a box that sits over the wrong place to the right one. Where a field has no box, press the field's button under the image and drag across the value.
3. Press Save, even when the engine got everything right.

Plan on about an hour for 50 documents. You can stop at any point and pick up where you left off. [`GRADING.md`](../GRADING.md) says what belongs in each field, and [`grading_with_boxes.md`](grading_with_boxes.md) covers the boxes.

Then read the score. It has one row per field: how many documents you checked, and how many the engine got right, nearly right, left blank, or got wrong. Say the street row shows 43 right of 50 checked. The engine read the street right on 86 percent of your sample, and because 50 is a small sample, the share for the whole folder is probably between about 76 and 96 percent.

No score is right for everyone. Ask what the table is for. A count of filings by ZIP code can live with a street that is wrong one time in seven, and a mailing to tenants cannot. Look only at the fields you will use, and grade those with care, because a field you leave as the engine filled it is counted as right.

When a field you need is weak, there are three things to do.

- **The engine looked in the wrong place.** Its box sat over the wrong part of the page, or the field had no box. Step 6 can fix that for your court's forms, with no code.
- **The box was in the right place and the value was still wrong.** A rule has to change. Check for a newer version of the package, tell the Eviction Research Network what goes wrong, or change the rule on your own copy. The [Improve it page](https://evictionresearch.net/extract-text/improve.html) covers all three. Never send a real document, name, address, or case number.
- **Grade more.** Whatever the score, every document you grade is right in the final table. For a small folder, grading all of it is a sound plan.

### 6. Teach the engine your forms (optional)

Courts print their own forms, and a form can put the tenant's address where the engine's rules do not look. The boxes you fixed and drew while grading show where your court's forms print each field. From them the package writes a template for each form that has at least five graded documents. A template holds the form's printed words and a region of the page for each field. It holds no names or addresses.

You look at each template drawn over one of its pages and approve the ones that are right. Nothing learned is used until you approve it.

A template has two limits. A random 50 rarely holds five documents of a rare form, so expect templates only for the forms your court uses most; a larger first sample covers more forms. And a template changes where the engine looks, not how it reads. When the engine looks in the right place and still reads a value wrong, a rule has to change, which step 5 covers.

### 7. Scan the whole folder

The engine reads the whole folder, using the templates you approved, and its rules alone on every other document. This needs no attention while it runs. At about 5 seconds a document, 4,000 documents take five or six hours.

Then grade 50 more documents, drawn at random from the full run, the same way as step 5, and score again. The first sample told you whether to run everything. This one measures the run that becomes your table, templates included. Report its share right with the table. Grade 100 or more before you publish counts or send anything to people.

### 8. Build the table

The package writes `case_table.csv` in your results folder, one row per document. Wherever you graded a document, in either sample, your answer replaces the engine's, and the `source` column says which each row carries. The table is the input to the next stage of work, cleaning the names and addresses.

## What grading does

Grading does three things. The score tells you which fields to trust. Your answers go into the final table. And your boxes can teach the engine your court's forms, once you approve the template.

Grading does not change the engine's rules. Run the engine again on the same documents and it gives the same answers. Its readings change only when you update the package, change a rule on your own copy ([`changing_rules.md`](changing_rules.md)), or approve a template. Scan again only then. A second scan into the same folder keeps your corrections.

## When something goes wrong

- Run the setup check again. It names what is missing and how to fix it.
- Section 18 of [the manual](manual.md#18-troubleshooting) lists common problems.
- Write to evictions@berkeley.edu or open an issue on GitHub. Describe the problem, or reproduce it with the made-up summons. Never paste a real document, name, address, or case number.

## The same steps at a terminal

Install the four programs of step 1 first. Then make a private Python environment for the engine and turn it on. Python from Homebrew on a Mac, and from Debian or Ubuntu, refuses a plain `pip install` outside one, with the message "externally-managed-environment".

```bash
# 2. Install extract-text (Mac and Linux)
python3 -m venv ~/extract-text-env
source ~/extract-text-env/bin/activate
pip install "extract-text @ git+https://github.com/evictionresearch/extract-text#subdirectory=python"
extract-text doctor
```

On Windows, skip the first two lines. The Python that step 1 installs accepts the `pip install` line as it is. On a Mac or Linux, run the `source` line again in every new terminal window, before any `extract-text` command.

`DOCS` is your documents folder and `RESULTS` your results folder. To practice on the made-up documents, run `git clone --depth 1 https://github.com/evictionresearch/extract-text` and use `extract-text/python/tests/fixtures` as `DOCS`, with `RESULTS` somewhere outside that folder.

```bash
# 3. Read one example (after the git clone line above)
extract-text extract extract-text/python/tests/fixtures/synthetic_summons_scanned.pdf

# 4. Scan a random 50
extract-text scan DOCS --engine deterministic --sample 50 --seed 1 --out RESULTS/sample

# 5. Grade the sample (Ctrl-C when done), then read the score
extract-text review --out RESULTS/sample --random 50 --serve
extract-text score --out RESULTS/sample

# 6. Teach the engine your forms (optional)
extract-text templates learn --out RESULTS/sample
extract-text templates review --templates RESULTS/sample/templates --out RESULTS/sample
extract-text templates approve form-1 --templates RESULTS/sample/templates

# 7. Scan the whole folder (leave off --templates if you approved none),
#    then grade a second 50 and score it
extract-text scan DOCS --engine deterministic --out RESULTS/all --templates RESULTS/sample/templates
extract-text review --out RESULTS/all --random 50 --serve
extract-text score --out RESULTS/all

# 8. Build the table
extract-text case-table --out RESULTS/all --graded RESULTS/sample --save RESULTS/case_table.csv
```
