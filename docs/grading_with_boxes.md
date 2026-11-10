# Grading with boxes

A short guide for graders who run `getting_started_example_script.R` themselves and grade on the review page it opens. It adds to `GRADING.md`, which says what goes in each field; this page is about the boxes on the page image and where your grades end up.

## Before you grade

Download the documents from the Google Drive folder Tim shares to your own computer (Drive gives a zip; unzip it), somewhere that does not sync or share, and point `docs_dir` in step 4 of the script at the unzipped folder. Then run the script a block at a time through step 6. Step 4 scans a random sample of the documents into the results folder you named in the script, and step 6 opens the review page with saving on:

```r
review_documents(res, correct = TRUE, n = n_sample, draw = "random")
```

R waits while you grade. Press Esc in RStudio (Ctrl-C at a terminal) when you stop. Nothing is lost by stopping; run the same line again and the page shows what you saved. Use the same browser each time; Safari, Chrome, and Brave all work.

## What the boxes are

Each document shows its first page on the left. Colored boxes on the image show where the engine read each value, one color per field; hover over a box and it names its field. The colored buttons under the image are the key. The form on the right starts with what the engine read.

The boxes matter because the engine learns from them. Where a box sits over the right place, the engine learns that this form prints that field there. Where it sits over the wrong place and you move it, the engine learns where to look instead. So a box is right or wrong on its own, apart from the words in the form.

## How to grade a document

1. Check each field in the form against the page and fix what is wrong, as `GRADING.md` describes.
2. Look at the boxes. If a box sits over the wrong place, drag it to the right place, or drag a corner to reshape it, or press its cross to delete it. If a field has no box and the value is on the page, press the field's button under the image and drag across the page where the value is printed. You can draw more than one box for a field.
3. Box the defendants everywhere the page names them: in the caption near the top, and again in the service block in the middle. Cover the whole caption cell, from under "vs." down to the "Defendant(s)" line, so the box fits a longer list than this document shows.
4. If the document has several pages, arrows under the image turn them. There is no need to turn every page. Look at a later page only when a value is wrong or missing on the first page and the form prints it there.
5. Press Save. The message under the buttons says it saved and which fields the engine got wrong.

Press "Can't tell from the page" when the page does not settle the answer, and use the Note box for anything unusual.

## Where your grades are

Every save goes at once to two files in the sample folder of your results folder (the `results` path you set in the script, then `sample`):

- `corrections.jsonl`, every save in order, with the boxes
- `corrections.csv`, the latest answer per document, for a spreadsheet

The scan itself is `extracted.csv` in the same folder. The review page is `review/index.html` beside it. Send back `corrections.jsonl` and `corrections.csv` when you finish, through the Drive folder Tim names, never by email or chat. These files hold tenants' names and addresses, so they stay in the same protected storage as the court documents until then.

## If something goes wrong

- The page opens but Save does nothing: the page was opened as a file. Close it and run the `review_documents` line again, which serves it.
- The boxes do not move: the page was built by an older version. Run `review_documents(res, correct = TRUE, rebuild = TRUE)`.
- A yellow notice at the top says earlier answers belong to documents no longer at the same rows: the results folder was scanned again with a different draw. Tell Tim before grading further.
