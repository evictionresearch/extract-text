# Grading reports

One file per grading round, written by `extract-text score --out FOLDER
--shapes --save reports/YYYY-MM-DD_NAME.txt`, and, for a round with a shared
set, its agreement report from `extract-text agree --out FOLDER FILES
--save reports/YYYY-MM-DD_agreement.txt`. A report holds counts, rates,
flags, grader names, and masked shapes (letters as A, digits as 9). It never
holds a name from a record, an address, a case number, or a file name, which
is why it can live in the repository while the corrections themselves stay
in governed storage.
