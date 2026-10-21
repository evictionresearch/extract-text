# Maintenance

This package is meant to improve on a schedule, not by accident. This file
is the schedule, the procedures behind it, and the running log of model
decisions. If you maintain a fork, adopt the same cadence.

## The cadence

| When | What | How it happens |
|---|---|---|
| Every push and pull request | Full test suite, Python and R | GitHub Actions (`tests.yml`) |
| Monthly, 1st of the month | A "model and dependency review" issue opens automatically with the checklist below | GitHub Actions (`model-watch.yml`) |
| Quarterly, or when a notable local model releases | Full model review (procedure below), decision logged here | Maintainer, prompted by the monthly issue |
| Before any release or external share | PII sweep over tree and history, full checks, version bump in all four places | Maintainer, checklist below |
| Open validation milestones | AI-lane head-to-head against the labeled Washington sets (deterministic re-score: **done 2026-08-20**, see below) | Maintainer, tracked in issues |

## Monthly review checklist

The automated issue carries this list. Close it with notes, even when the
answer is "no change."

1. Is Ollama's model library showing a newer vision-capable model in the
   7 to 14 billion parameter class with an open license? Candidates must run
   on a 16 GB machine.
2. Has the pinned default (`qwen3.5:9b`) received an update tag worth
   re-benchmarking?
3. Do poppler, tesseract, or ollama have releases that change behavior we
   pin (OCR engine, TSV output, API shape)?
4. `pip list --outdated` inside the dev environment: anything security
   relevant in pydantic or Pillow?
5. Are any flags firing at unusual rates in recent runs you know about?
   Rising `no_defendant_address` on a corpus that used to extract cleanly
   usually means a court changed its form layout; that is a new anchor
   waiting to be written.

## Model review procedure

The default local model is a pinned, documented choice, not a moving target.
To evaluate a candidate:

1. **Eligibility.** Vision capable, open weights, license an agency can
   accept (Apache 2.0 or similarly permissive), runs in 16 GB of memory
   through Ollama.
2. **Smoke.** `extract-text extract python/tests/fixtures/synthetic_summons_page1.png
   --engine ai --model CANDIDATE`. It must return the synthetic fields
   correctly and quickly.
3. **Bench.** Run the AI lane over a few hundred documents of real corpus
   you are authorized to hold, on governed storage, with
   `extract-text scan ... --engine both --model CANDIDATE`. Compare
   `address_similarity` distributions and `only_ai_found_address` rates
   against the current default on the same documents.
4. **Score against truth** where labeled data exists, using
   `extract_text.similarity` exactly as the validation work does.
5. **Decide and record.** A switch requires the candidate to beat the
   incumbent on truth-set similarity or coverage without losing speed
   beyond reason. Change `DEFAULT_VISION_MODEL` in
   `python/src/extract_text/ai/vision.py`, update the manual (sections 6
   and 15) and the README, add a row to the decision log below, and bump
   the minor version.

## Model decision log

| Date | Default | Decision and evidence |
|---|---|---|
| 2026-08-18 | `qwen3.5:9b` | Initial pin. Vision-capable, 9.7B parameters, Apache 2.0, runs in 16 GB through Ollama. Benchmarked by Cheng Ren on 300 Pierce County summons page-1 images: structured fields for all 300 in 1:22:40 (about 17 s/page); recovered a handwritten service address OCR could not read. Tag verified against ollama.com/library/qwen3.5/tags on 2026-08-18: `9b` exists at 6.6 GB, and `latest` currently points at the same model (digest `6488c96fa5fa`), so a machine holding either tag is running identical weights. Formal head-to-head against the labeled truth sets is an open milestone. |

## Port fidelity, measured on real documents (2026-08-18)

The deterministic engine is a port of a scanner validated in July 2026 against
5,100+ hand-labeled addresses. The question for this package is therefore not
"is it accurate" but "does it reproduce the tool that was already shown to be
accurate." That was measured by running both engines over the same real
Washington filings and comparing field by field.

**Setup.** 400 documents, sampled with a fixed seed across 15 county-years
(Pierce 2004 to 2017, King 2013, Whatcom), 366 requiring OCR and 34 with a
text layer. Record-level output stayed in the governed data tree; only
aggregates left it.

**Result.** Neither engine raised an error on any of the 400. These fields
were byte-identical across all 400 documents:

- `defendant_address_raw` (mean similarity 1.0000, 100% identical)
- `defendant_zip`, `defendant_anchor`
- `attorney_firm`, `attorney_zip`, `attorney_phone`, `attorney_names`
- `flags`, including the counts of all seven flag types that fired

Address yield was identical at 268/400 (67.0%), and 235/400 (58.8%) came
through with no flag at all. Yield splits 85.3% on text-layer PDFs against
65.3% on OCR, which is the expected penalty for scanned pages.

**Where they differ, and which is right.** Differences concentrate in the
component fields that the deliberate `STREET_RE` deviation touches. A blind
adjudication was run: page images were read independently and the true value
recorded before any engine output was inspected.

- `defendant_street`, 85 differences. Every one traced to direction handling.
  In the 3 that fell in the blind sample, the port was correct and the
  original wrong all 3 times, truncating `SE` to `S` and `SOUTH #208` to `S`.
  This matters more than it looks: 39th Ave S and 39th Ave SE are different
  streets, so the original was not merely incomplete, it was pointing at the
  wrong place.
- `attorney_street` (84) and `attorney_city` (50) move together. 35 cases show
  the original absorbing the first letter of the city into a phantom trailing
  direction, which is what produces a city of "Eattle". The port declines the
  match and recovers the correct city.
- `defendant_names` (36) and `doc_case_number` (3) are pure gains where the
  original returned nothing.

**Regression watch.** Across all fields the port lost 13 values and gained 36.
Every loss sits on a document already carrying a flag (`no_defendant_address`,
`defendant_equals_attorney`, or `case_number_mismatch`), so the port returns
blank exactly where the record was already headed for review. Under
flagged-never-guessed, a blank there is the better answer.

Of the 5 documents where the port produced a *shorter* street than the
original, reading the pages settled it as 2 wins for the port (the original
supplied a wrong direction), 2 wins for the original (it recovered a direction
from the "SO." abbreviation), and 1 tie where OCR interleaved a party name
into the address line and both engines failed.

## Known gaps in the address vocabulary

Found by the run above. These affect **both** engines, so they are inherited
limitations rather than port regressions, and they are the highest-value
improvements available. Measured against the 268 extracted defendant
addresses in that sample:

| Form | Share | Status |
|---|---|---|
| `NE` `NW` `SE` `SW` | 19.4% | handled (this is what the port fixed) |
| `NORTH` `SOUTH` `EAST` `WEST` | 28.4% | handled |
| `N.E.` `S.W.` with periods | 6.0% | **fixed 2026-08-19** |
| `SO.` / `NO.` abbreviation | 3.7% | **fixed 2026-08-19** |
| `SOUTHWEST` `SOUTHEAST` and kin | 0.7% | **fixed 2026-08-19** |

Cause: `DIRECTION` listed single letters before pairs, so `N` won before `NE`
was tried. The `(?!\w)` guard rescued the bare two-letter forms by forcing
backtracking, but a period satisfies the guard, and the spelled-out compounds
and `SO.` were absent from the vocabulary entirely.

**Applied 2026-08-19** (issue #2), together with two unit fixes the first
human rating round showed to matter more: `UNIT` now tolerates a `#` between
the keyword and the identifier ("Apt. # 201"), and `STREET_RE` accepts a
comma before the unit ("Commercial St., Suite 460"), which the old
whitespace-only separator could never reach.

How the decision was made, since the change touches a validated engine and
the truth-set re-score (issue #1) is still blocked:

1. 18 constructed cases, every historical regression guard included: 18 pass.
2. Re-extracted 250 real cards and classified every diff: 50 changed, of
   which 46 gained a unit, 3 were the already-shipped rail fix, 1 gained a
   direction. Zero addresses lost, zero house numbers changed.
3. Scored old vs new against the 24 human-typed corrections from the first
   rating round: **13 better (11 now exact), 10 unchanged, 1 nominally worse**
   — and that one is a wrong-block failure (the "Swanson Pllc" phantom city)
   where old and new are the same wrong address; only its length changed.

Human confirmation of the changed cards is queued for rating round 2. The
next release carrying this change should bump the minor version.

### The line-number rail, measured and partly fixed

An earlier note here called this low priority, on the grounds that a stray
rail digit leaves "a stray token inside an otherwise correct address". **That
was wrong.** Human rating of real output found the rail digit taking the place
of the house number: `13 39 EXAMPLE VALLEY DRIVE` for a house at 39, and
`18 1234 SAMPLE AVE SW` for one at 1234. A wrong house number is a wrong
address, and a plausible one, so a geocoder will place it without complaint.
Two of 24 corrections in the first rating round were this.

Measured on the offending pages, the rails sat at x1 = 0.149 and 0.156, past
the 0.145 band, missing the cutoff by as little as 0.004. They are unmistakable
as columns: on one page fifteen rail digits shared x1 between 0.155 and 0.156.

**What was tried and reverted.** Detecting the column per page and dropping
every member at the word level. It found the rails correctly and produced
cleaner clustered lines, but on 1 filing in 250 it changed which block the
extractor chose, turning a correct defendant address into the plaintiff
attorney's address. The rail digits were evidently propping up a block
boundary the extractor relies on. `layout.rail_columns` keeps the detector,
unused, because it is a sound measurement and may become safe if the block
extractor changes.

**What shipped.** `summons._skip_rail_house_number` rejects a house number in
rail range (1 to 28) when another number follows it that starts a perfectly
good address of its own. It cannot move a block boundary because it runs after
block selection. Over 250 real cards it changed 3 addresses, all correctly,
and lost none. A genuine low house number is safe: "13 39th EXAMPLE AVE S" stays at
13, because "39th" has no space after its digits and cannot begin a match.

## First human-rated results (2026-08-18, one rater, n=71)

A single rater worked through 79 cards of the Washington deck. Small, and one
person, so treat it as a direction finder rather than a rate. It is still the
first time this engine's output has been judged by a human against the page.

**Extraction was judged correct on 66.2% of 71 settled cards.** Well below the
July 2026 similarity scores, which is expected: this test asks whether the
whole address is right, including unit and direction, where the Levenshtein
metric gives credit for being close.

What the 24 typed corrections changed:

| Correction | Count |
|---|---|
| Added a unit or apartment the engine dropped | 11 |
| Fixed a wrong or missing direction | 6 |
| Removed junk the engine added | 3 |
| Other | 3 |
| Added other dropped words | 1 |

**Dropped units are the largest single failure, ahead of directions.** That
reorders the priority in the vocabulary fix: the `UNIT` pattern deserves at
least as much attention as `DIRECTION`. Several corrections show units the
engine never had a chance at, such as a suite following a comma
("Commercial St., Suite 460"), which `(\s+UNIT)?` cannot reach because it
requires whitespace directly after the street.

The round also exposed a parse bug: "and all others residing at" was read as a
party plus a city, producing `1800 OTHERS TEXAS ST, Residing, WA`. "Residing"
is not a city and should never appear in that field.

Two process lessons, both fixed:

- **Probes were monotonous.** All eight the rater saw altered the house number,
  because `corrupt()` tried that first and only fell back to ZIP. A rater
  learns to check the leading digits and the probe stops measuring general
  attention. It now picks at random among house number, ZIP and unit.
- **The guideline was ambiguous on abbreviations.** A card was marked wrong for
  showing `WA` where the page read `WASHINGTON`. The instructions now say
  abbreviations count as matching.

The probes did work as intended otherwise. Both misses took 8 and 9 seconds
against 13 to 31 seconds for every correct answer, so they caught genuine
lapses in attention rather than being unfair.

**Accuracy is not one number.** The same round, broken down:

| Slice | n | Correct |
|---|---|---|
| Whatcom | 44 | 72.7% |
| Pierce | 26 | 53.8% |
| tiff_ocr | 44 | 72.7% |
| pdf_ocr | 20 | 55.0% |
| `to_block` anchor | 58 | 70.7% |

A 19-point gap between two counties in the same state, on one rater's cards.
Small enough to be noise and large enough to check, which is why
`score_ratings.py` now reports accuracy by state, county, year, anchor and
text source as a matter of course. Counties use different forms, vendors and
scanners, so a rule that holds in one can fail in the next, and a single
headline number hides exactly the pattern worth acting on. Older Pierce years
looked worst of all (2005: 25% on 8 cards), which fits: those are the
typewriter-era and fill-in-form filings.

## Handwritten filings: how many there are, and why they are hard to use

Swept 5,817 Washington documents (Pierce, Whatcom, King) on 2026-08-18 looking
for filings whose service address was written by hand. Two things came out of
it, one about the corpus and one about the method.

**Confidence cannot find handwriting.** Tesseract does not return
low-confidence words for pen, it returns nothing at all, so a page with a
wholly handwritten address block still reports about 93 mean confidence from
its printed template. On a hand-labeled example the handwritten page was
indistinguishable from printed ones on every confidence statistic tried,
including confidence measured inside the service block.

What does work is comparing ink against OCR coverage: dark pixels inside the
service band that no word box accounts for. Measured only in the text column,
since pleading rules and the line-number rail otherwise put unexplained ink on
every page. Validated against images, a genuinely handwritten form scored
0.837 and 0.505 where ordinary printed filings scored 0.001 to 0.12.

**They are rare.** Of 4,819 measurable scans:

| Unexplained ink | Documents | Share |
|---|---|---|
| >= 0.25 | 98 | 2.0% |
| >= 0.35 | 51 | 1.1% |
| >= 0.45 | 12 | 0.25% |
| >= 0.55 | 6 | 0.12% |

Precision in the top band is roughly half. Spot-checking found true
handwriting at 0.837 and 0.505, but a printed form using dot leaders
(`.....Candice Vaughn`) scored 0.646 and a printed address inside a ruled box
scored 0.43, both false positives. **The honest rate is about 0.1% to 0.3%**,
so an archive of roughly 52,000 documents holds on the order of 50 to 150
handwritten filings, not thousands. Candidates at or above 0.35 are listed in
the sweep output for review.

**They cannot yet enter a rated deck safely.** A handwritten filing yields no
extracted address, so it cannot be a match/no-match card; it has to be a
transcription card that asks a person to type what they see. But the crop for
one is cut from a printed "TO:" label with no OCR output beneath it, so
word-box redaction has nothing to act on and the defendant's name sits in the
picture. Blanking the first row of ink works on printed-but-unparseable
filings and fails on handwriting, where descenders and the form's ruled lines
join the rows into one band that spans the whole crop. `render_card` refuses
rather than emitting a black rectangle, which means the genuinely handwritten
cards are dropped by the safety guard.

So handwriting needs either per-card human review before use, or a real
handwriting recogniser. It is the clearest case for the AI lane: Cheng Ren's
qwen benchmark recovered a handwritten service address that OCR could not
read, and this sweep is the measurement of how much of the corpus that
capability would unlock.

## The 2026-08-20 improvement pass

Every fix below traces to a failure class found by measurement (the 400-doc
A/B, the human rating round, or reading failed pages). Applied together and
measured together.

1. **No-suffix streets** ("1949 S. Sprague"-shaped), the largest cause of
   `no_defendant_address`. New `parse_address_nosuffix`: one backtracking
   pattern for house + optional direction + at most two name tokens +
   optional unit + a confirming city line. Every use flagged
   `street_no_suffix`. Converted 21 of 159 former failures (13%).
2. **Phantom cities.** "Residing" and firm names before "WA" are vetoed
   (`CITY_VETO`); the city search continues past a vetoed match instead of
   stopping, recovering the real city later in the block.
3. **Dot leaders** collapse to spaces before parsing; **superscript
   ordinals** ("150ᵀᴴ" arriving as "150™") join the street token class;
   **compound suffixes** ("115th St Ct SW", "88th Street Court SW") get an
   optional second type word; **quoted unit identifiers** ('unit "O"') parse.

Two selection rules had to come with it, both learned the hard way:

- **Strict beats no-suffix across the whole ladder.** Anchor priority alone
  let a no-suffix reading of an OCR-scrambled "TO:" block preempt the clean
  strict address a lower anchor had found on the same page. The candidate
  list now sorts strict-first, stable within each class.
- **An attorney collision demotes the winner.** When the chosen street equals
  the attorney's, the first non-colliding candidate on the audit trail takes
  over. On two rated cards this recovered the true defendant address
  ("Bakerview", "Broadway" — both suffix-less, both previously replaced by
  the attorney's office) from filings where the failure had been invisible.

**Measurement.** 85 tests pass, including 10 new. Across 250 real cards:
zero addresses lost, zero house numbers changed. Against the 24 human
corrections: 15 better, 5 same, 4 nominally worse — and every "worse" was
adjudicated on the page image: two are wins (the attorney-collision cards,
where the human had corrected a crop of the attorney block), one is a phantom
city honestly emptied, one is the same wrong block both ways.

**A lesson for the game.** A typed correction validates the region the crop
shows, not the document. Two round-1 corrections faithfully transcribed the
attorney's address because that is what the card showed. Treat corrections on
cards whose extraction later changes blocks as stale, and re-rate them.

## The formal re-score: this engine vs the July truth sets (2026-08-20)

The ground-truth file (`nlp1_paper_data.csv`, 5,171 labeled rows) and the
July validation kit were located on the external archive volume and copied
into the governed data tree, unblocking the milestone. The packaged engine —
port plus every deviation shipped since (direction/unit vocabulary, rail
guard, no-suffix parser, city veto, attorney demotion) — was run over the
**exact documents** the July validation used (the kit's manifests pin them),
and scored with the kit's own `validate.py`, so the metric is byte-for-byte
the paper's.

| Set | n | Yield | Mean ratio | >=0.7 (extr.) | >=0.7 (all) | ZIP agree |
|---|---|---|---|---|---|---|
| King HJP, July | 100 | 90.0% | 0.886 | 90.0% | 81.0% | 94.3% |
| King HJP, **now** | 100 | **92.0%** | **0.888** | **90.2%** | **83.0%** | **94.4%** |
| King thesis, July | 200 | 83.5% | 0.867 | 94.0% | 78.5% | 90.7% |
| King thesis, **now** | 200 | **84.0%** | **0.869** | 94.0% | **79.0%** | **92.1%** |
| King manual / Pierce | 27 | — | — | — | — | unchanged |

**Equal or better on every column of every set; no regression anywhere.**
The July numbers may now be claimed by this engine, not merely inherited
from the ported original.

Why these gains look small next to the strict-metric jump (66% → est. 80-85%
whole-address-correct): this scorer is the paper's forgiving Levenshtein
ratio, where a dropped unit costs a few characters. The improvement pass
mostly fixed exactly the things this metric barely sees. Both numbers are
true; they answer different questions.

## Failure mining at full scale (2026-08-20)

With the archive volume mounted, the validation stopped being a sample: all
5,168 labeled truth cases (of 5,171) have documents on the volume, and the
engine now runs and scores against every one of them in ~36 minutes. That
changed how improvement works. Instead of reading a handful of failures, the
engine's misses were classified programmatically against ground truth, the
dominant classes were read as page images, and each mechanism was fixed and
re-measured on the full set.

**What the mining found.** 903 failures; 683 were "no yield on an OCR'd
PDF" — and 90% of those had readable text and a findable attorney block.
Not scan quality: rules gaps. The mechanisms, each traced on a real page:

- a page-tall OCR smear of the pleading rule seeding a runaway line cluster
  that swallowed the whole service block (fixed structurally in
  `cluster_lines`: junk may join a line, only text-sized words define its
  band);
- superscript ordinals arriving as quote characters ('100" Avenue');
- the "TO THE DEFENDANT(S):" label missing from the anchor vocabulary, and
  junk leads one character wider than its tolerance ("19||");
- hyphenated house-ordinals ("229-17TH STREET"), trailing-period house
  numbers ("2360. NE Park Drive"), "CRT" and OCR's "PI" for "Pl.",
  standalone pipe tokens from split ordinals;
- names glued into `address_raw` when the label line carries both (the
  street match now marks the name/address boundary);
- an incomplete page-1 fragment ending the page scan and shadowing the
  complete service block on page 3 (complete-beats-incomplete, across the
  whole ladder);
- process-server declarations and "must be delivered to:" counsel blocks
  read as defendant stacks (vetoed — and the veto itself was measured,
  found over-broad, and narrowed: its first form cost 34 correct answers
  to prose false-fires).

**Results on the full truth set** (paper metric, kit scorer):

| King thesis, n=4,254 | Yield | Mean ratio | >=0.7 (extr.) | >=0.7 (all) | ZIP |
|---|---|---|---|---|---|
| July 2026 original (200-sample) | 83.5% | 0.867 | 94.0% | 78.5% | 90.7% |
| This engine, before mining | 85.2% | 0.875 | 95.6% | 81.5% | 93.4% |
| This engine, after mining | **92.4%** | **0.907** | **98.3%** | **90.8%** | **96.3%** |

HJP (King 2017, n=877): yield 90.0 -> **95.6%**, mean 0.886 -> **0.926**,
>=0.7-on-extracted 90.0 -> **99.5%**, >=0.7-on-all 81.0 -> **95.1%**.
Per-case scores live in `extract_text_training/_rescore_2026-08-20/full/` on
governed storage.

**The two small sets on the full run, including the one regression.** The
mining pass was scored at three points (`val_scores_before_fixes.csv`,
`val_scores_mid.csv`, `val_scores.csv` in the same directory), which makes
the precision trade legible. The final refuse-rather-than-emit round moved
the four groups as follows, mid to final:

| Group | n | Yield | Mean ratio | >=0.7 (all) |
|---|---|---|---|---|
| King thesis | 4,254 | 94.0 -> 92.4% | 0.873 -> **0.907** | 89.1 -> **90.8%** |
| King HJP | 877 | 96.6 -> 95.6% | 0.892 -> **0.926** | 90.4 -> **95.1%** |
| swipes (Pierce 11, Snohomish 8, King 7, Whatcom 1) | 27 | 100 -> **88.9%** | 0.884 -> 0.913 | 92.6 -> **81.5%** |
| manual (Pierce 6, King 3, Whatcom 1) | 10 | 70.0% flat | 0.941 -> 0.967 | 70.0% flat |

Mean ratio rose on all four, so the surviving answers are better. The
swipes set is the one place the trade did not pay: three correct
extractions became `no_defendant_address` refusals and a fourth fell 0.90
to 0.57 with `defendant_address_incomplete`, against one newly correct.
All four carry flags, so nothing went silently wrong, but a four-document
swing on 27 cases is worth re-checking on the next full run before
treating it as noise. Note this is the full-run swipes group of 27 across
four counties, not the 27 in the manifest re-run table above, which is
King manual 10 plus Pierce 17.

**Round 3 of the game** was rebuilt from this run by `build_truth_round.py`:
356 cards — the 317 remaining engine-vs-truth disagreements (median ratio
0.89: mostly unit/direction shading, no wholesale errors left in the deck),
plus 19 truth-exact cards shown unaltered as yes-probes and 20 one-digit
corruptions as no-probes. Rater time now goes only where the engine and a
hand label disagree, and the swipe adjudicates which one is right.

**The precision trade, made explicitly.** The counsel-block vetoes refuse 87
answers the previous pass emitted: 53 were wrong (attorney offices standing
in for defendants — the classic failure, silent until now), 34 were right.
Refusals are flagged and reviewable; silent wrong addresses are not. Two
documents remain honest losses where the only address on the page sits in
the bottom-right mailing-certificate corner that deliberately belongs to
counsel rules.

## Vision readings as game cards (2026-08-20)

36 documents the improved engine still fails on were read from page images by
a vision model (Claude, in-session). The readings did NOT enter any truth set.
Each became a game card (`V####`, `source=claude-vision`) built by
`build_vision_cards.py`: the reading is the typed guess, the reader's own
name extraction feeds the redaction, and the standard withhold rule applies.
People confirm or reject them by swiping, and `score_ratings.py` reports
accuracy per reader (rules vs claude-vision), so the two are judged on the
same footing.

Of the 36: **28 yielded readings** (21 built into cards; 7 had no locatable
crop anchor and are held for the transcription flow) and **8 were skips** —
and the skips are the finding. Four pro se fill-in forms carried the
**plaintiff's own address or the courthouse's address in the TO field**; a
reader that transcribes the TO block without checking whose name heads it
proposes the wrong household with full confidence. Any AI-lane prompt should
carry this check, and three of the four were handwritten, exactly the
documents the AI lane exists for.

The vision set also included readable handwriting (three filings), compound
suffixes, superscript ordinals, and a "1415 & 1417" dual house number —
coverage the deterministic engine cannot reach today.

**Round 2 deck** (`round2/serve`): 180 cards = 129 whose extraction changed
under the improvement pass + 21 conversions + 21 vision cards + 9 probes.
Round 1 stays frozen for raters mid-deck; the corrections lesson (a
correction validates the shown crop, not the document) applies when
comparing rounds.

## Two prompt-level defects, found and fixed on the corpus (2026-08-22)

The 24-document corpus (`scripts/make_corpus.py`, 4 layouts x 7 image
treatments, gitignored and regenerated on demand) was built because the
degradation set had a ceiling: four of five models scored a flat 1.000 on it,
so it could not rank anything. The corpus does discriminate, and the first two
things it found were both defects in how the task was specified rather than in
how well models read.

**1. The defendant group term became a phantom party.** Every defendant miss
for four of six models was one clause, the caption's trailing "and ALL OTHER
OCCUPANTS": 24 of 24 for glm-ocr, 16 of 16 for minicpm, 12 of 12 for
qwen3.5:9b, 2 of 2 for qwen3.8:27b-mlx. The prompt already lists that term and
asks for it to be dropped. Worse than the score, `_NAME_SPLIT_RE` splits on
"and", so the clause became a second defendant party literally named ALL OTHER
OCCUPANTS, on 12 of 24 pages with the pinned model. Fixed deterministically in
`strip_group_terms()` rather than by asking the model again. Re-benched: all
six models reproduced the predicted scores exactly, no non-defendant field
moved, and defendant similarity reached 1.000 for five of six.

**2. `law_firm` never said whether it wanted the firm or the person.** With the
defendant noise gone, law_firm was the leading defect, and 23 of its 28 misses
across six models were the signing attorney and bar number returned in place of
the firm entity ("Alex B. Counsel, WSBA #99999" for "SAMPLE & SPECIMEN
ATTORNEYS AT LAW"). No post-filter can fix that, since a firm name cannot be
derived from a person's name, so item 4 of the prompt now says to return the
firm itself and names the two things in the same signature block that are not
the firm. This is a deliberate deviation from Cheng Ren's benchmarked prompt,
the second after the appended case_number field.

Measured on the corpus, exact fields out of 144, before and after the prompt
change:

| model | before | after | law_firm misses |
|---|---|---|---|
| qwen3.5:9b (the pin) | 136 | **144** | 5 to 0 |
| minicpm-v4.5:8b | 139 | 141 | 3 to 1 |
| qwen3.8:27b-mlx | 138 | 140 | 1 to 0 |
| gemma4:26b | 132 | 138 | 10 to 4 |
| glm-ocr:latest | 130 | 132 | 2 to 4 |
| gemma4:12b | 104 | 106 | 7 to 5 |

Every model improved on total exact fields and five of six improved on
law_firm.

**The caveat, which is not small.** `glm-ocr` (0.9B) is the exception. Its
law_firm misses went up, its mean fell from 0.980 to 0.960, and its worst page
fell from 0.887 to 0.520. On that page, a noisy layout-3 render, every field
shifted by one and `law_firm` came back as "XYZ Attorney at Law", which is the
example string from the prompt itself. A model small enough to regurgitate the
prompt's examples is a model that a longer field description can destabilise.
Its apparent gains elsewhere are also not what they look like: the prompt
change stopped it tripping `vision_json_fallback`, so its address fields
stopped arriving with escaped newlines. Its before and after are therefore not
a clean law_firm comparison.

**What this does and does not license.** These are synthetic, machine-rendered
pages with a closed vocabulary. A perfect 144/144 for the pinned model means
the task specification is no longer the bottleneck on pages like these. It is
not evidence about real scans, real handwriting, or real firm names, and it
does not move `DEFAULT_VISION_MODEL`. Step 3 of the model review procedure, on
governed storage, remains the only thing that can.

## The 2026-09-30 improvement pass: the first new-user test

Tim ran the package as a new user on 30 real King County summonses in two
layouts (the pre-printed 2000s form and the e-filed 2010s form), corrected
every document on the review page, and sent back the scorer's report
(counts and masked shapes only; see docs/manual.md section 11). Scored
against the engine as it was that morning, the deterministic engine had
the plaintiff right on 0 of 30, the defendants on 5 of 30, the street on 16
of 30, and the unit on 14 of 30; city, state, and ZIP were 87 to 100
percent. Every one of these numbers is on a flagged-first review set, so
they describe the hard cases, not a corpus rate.

Reading the shapes rather than the counts, most of that was a few defects.

- **A comma in the unit.** The street pattern's unit group carries its
  separator, so a comma-led unit (", #12") reached the unit column comma and
  all, and the same comma sat inside the street. Eight of fourteen street
  errors and eight of sixteen unit errors were this one character.
- **Building lines as defendants.** The e-filed form prints the complex's
  name between the tenant and the street in the service block; the block
  reader took any digit-free line before the address as a party. Nine
  documents gained a phantom defendant this way. A line after the first
  name line that carries a building word (APARTMENTS, MANOR, VILLAGE, and
  kin, but not COURT, PLACE, PARK, or HOUSE, which are surnames) is now
  kept out of the parties.
- **The plaintiff reader.** Three separate faults. The flat-text caption
  pattern was allowed to override the positional reader, and on a scanned
  two-column caption it returns whatever sits before "v.", which was rail
  debris ("1]") or the defendant's name with OCR noise in front. The
  positional reader did not recognise the pre-printed form's
  "Plaintiff(s)," label. And a tall case-number stamp beside the caption
  made line clustering glue the plaintiff's two rows into one interleaved
  string. The reader now rebuilds the caption's left cell from its own
  words, cuts each row at the column divider (the first wide gap) instead
  of a fixed x, drops stamp-sized words, recognises the parenthesised
  label, joins a DBA line to the name above it, and falls back to the
  notice sentence ("...started against you ... by X, Plaintiff"). The
  positional result now wins the merge.
- **The case number.** King County stamps the courthouse code onto the
  check digit ("-3SEA"), and the pattern ended in a word boundary that
  cannot fall there. The positional pattern then found nothing, and the
  generic "Case No." pattern fell through to the notice sentence "if no
  case number has been assigned", returning a word fragment. 25 of the 26
  flagged documents were flagged for this. The check digit is now followed
  by a not-a-digit lookahead, and the generic pattern requires a digit.
- **Group terms and debris in names.** The deterministic engine kept
  "et al." (the AI engine already stripped it), and names carried a trailing
  "&", a leading rail fragment, or a parenthetical role. Cleaning now lives
  in `parties.py` and runs for both engines. Names listed with commas
  ("A B, C D, and E F") split when every piece has two or more words.
- **Superscript ordinals.** OCR reads 150TH as 150" or 150°; the pattern
  already accepted those characters, and the street column now says 150TH.
- **Building-plus-apartment units** ("BLDG C Apt # 5") and APARTMENT as a
  unit word were missing from the unit vocabulary.

Two synthetic fixtures now reproduce the two King County layouts
(`synthetic_kc_efiled.pdf`, `synthetic_kc_printed.pdf`, each also as an
image-only PDF for the OCR path), with the stamp, the rail rule, the
"Plaintiff(s)," label, the DBA line, the OCR debris, the building line, and
the notice sentence in them. Every change above has a test on those
fixtures or on invented strings.

What this pass did not touch, because the shapes did not settle it: a
trailing direction dropped from two streets, a city reading with a leading
extra word on a no-suffix street, and the attorney firm on the pre-printed
form (which is a lone attorney, not a firm). The scorer now prints the
masked address block beside each address error, so the next round of
corrections will show what those blocks held.

The measured effect on the 30 documents is in the project's issue tracker
(#17) once Tim re-scans and re-scores; nothing here was verified on real
records inside a session, by design.

## Case files: the first slice of case context (2026-10-02)

The package read the summons and nothing after it. Cheng Ren's 2024
dissertation (https://escholarship.org/uc/item/7f36p8n6) read the whole
Pierce County case file, 56,070 cases from 772,629 PDFs: the summons, the
judgment summary on the motion for default (principal, attorney fee, filing
fee, total), and the sheriff's return on the writ, with the case outcome
taken from which documents were on file (pp. 31 to 36). That work ran on
Microsoft Azure Document Intelligence, a cloud service, with models trained
on about 10 to 20 labeled pages per form.

`extract_text/casefile.py` and `extract-text cases` are the local,
rules-only start on the same ground: document type from the file name, the
case rolled up to answered, default, dismissed, judgment, and sheriff's
return, and the return's outcome read into the dissertation's five
categories. The manual's section 9 has the columns and the rules, including
the two choices that are this package's own.

What is not measured. Every test is synthetic. The file-name rules were
written from the dissertation's description of Pierce County's names and
have not been run on a real folder; the five return wordings are the ones the
dissertation quotes (pp. 35 to 36), and other counties and years may word
them differently. The first run is Tim's, `--names-only` first, and what
comes back into a session is the printed report. The dissertation's stage
counts (Figure 9, p. 46) are the benchmark for Pierce County.

Still to build, tracked in the goal issue: the judgment summary amounts,
filing and return dates, a title reader for collections whose files are not
named for their documents, the AI engine's reading of the same documents,
hand labels for outcomes, and R parity.

## Grading tools and the first graded report (2026-10-07)

Tim graded on the graders' page before the first round with student
graders, and the round's tools changed in response. The organizer's guide
is the manual's "Running a grading round" (section 11).

- **The batch did not hold.** Choosing 10 showed every document, because
  the card style (`display:flex`) overrode the `hidden` attribute the batch
  logic set. Hidden cards now have their own rule.
- **The plaintiff's attorney** (names, firm, address on one line) is on the
  form, the corrections record, and the scorer, but only on documents drawn
  by `review --attorneys N`, since a few dozen answers measure it and asking
  on every document slows grading. Older answers have no attorney block and
  are not scored on it. The AI engine is not scored on attorney names: its
  prompt asks for the firm and not the person who signed. No rescan was
  needed, because scans already carry the attorney columns.
- **`--order random`** serves the graders' documents in random order, so a
  partly graded folder still gives a fair accuracy estimate; worst first
  remains the default for finding failures.
- **Blind double grading.** `--overlap N` puts one randomly drawn shared set
  first for every grader. `extract-text agree` reports field-level agreement
  on it and lists disagreements masked, `--merge` keeps every grader's
  answer (the earlier advice to concatenate files kept only the last one per
  document), and `review --rows` opens the disagreements for settling with
  all answers shown.
- **`review --graders --rows N,N,...`** (added 2026-10-09) is a graders'
  page of just those documents: it records each grader's name and, unlike
  the settling page, shows no other answer. It lets graders re-grade a set
  one person already graded, blind, without that person's answers in the
  shared folder.

**What the first report measured.** 19 documents, all from the top of the
worst-first order (each with a scan flag or an engine disagreement), graded
by one person, 16 of them started
from the AI engine's reading (which flatters that engine). These are the
hardest cases in a 300-document King County sample, not a corpus rate. The
deterministic engine had plaintiff right on 1 of 19, defendants 0, street 1,
unit 10, city 2, state 5, ZIP 5. The AI engine had plaintiff right or nearly
on 19, defendants and street 13 each, unit and city 16 each, state and ZIP
17 each. On the 10 documents with an attorney answer, the deterministic
engine had the names on 5, the firm right or nearly on 5, and the address
on 1; the AI engine had the firm on 7 and the address right or nearly on
10. The page's ordering put every one of these failures in front of a
person first, though the report cannot say whether each carried a scan
flag rather than only an engine disagreement.

Eight of the 19 had no defendant address at all, which empties every
address field at once and accounts for most of the blanks; the scan's
shapes cannot show why, so the next tool is one that says whether the
address is in the document's text at all. Four mechanisms behind the other
failures were confirmed on invented strings: the label filter keeps
"Plaintiff" followed by fill-in underscores as a name; a standalone "ET al"
line is kept as a defendant; an address line led by rail debris passes as a
person's name; and an OCR "$" for "S" inside a name is not repaired. The
deterministic attorney firm takes the role line ("Attorneys for Plaintiff")
or the phone line, which is #25 measured for the first time. Rule fixes are
on hold by Tim's decision of 2026-10-07.

One scorer limitation is known and open: the deterministic engine's
attorney address is compared as its raw block, which can include the firm's
name, so it can count as different from a correct typed address. Comparing
the engine's parsed address parts would remove that.

## History rewritten before publication (2026-10-20)

A pre-publication audit found five example values in the rule file's
comments and docstrings, and in the tests and documentation that quote
them, that the PII sweep never triaged because it skips the rule files by
design. Tim judged them to be real: a case number, a house number and
street from a rating card, and three addresses used to document the
premises anchor and the OCR repair. All were replaced with the synthetic
values on the sweep's whitelist, and because they dated from the first
commits, the replacement was made across the whole history with
`git filter-repo` in a fresh clone, which also left behind the orphaned
commits from the 2026-10-01 force-push. The rewritten history was pushed
to a new repository under the same name; the old one was renamed
`extract-text-vintage` and kept private. Checks on the result: a
history-wide search for every replaced token finds nothing, the fixture
binaries are byte-identical, the sweep is clean, and the 170 tests pass.

Two lessons for the sweep. First, the rule-file skip is a blind spot:
anything quoted in a comment there must be invented, and a reviewer
should read those comments on every release. Second, the whitelist's
own comments must say where a value came from; "from the docs" was not
an answer.

The issues moved to the new repository the same evening and were
renumbered, because the old tracker had three pull requests (#7, #13,
#15) in its sequence and the new one starts clean: old #1 to #6 kept
their numbers, old #8 to #12 became #7 to #11, old #14 became #12, and
old #16 to #36 became #13 to #33 (subtract three). Issue numbers in this
file and in the hq notes dated before 2026-10-20 are the old ones unless
marked.

## The first round settled, and the form for round 2 (2026-10-20)

Two graders returned 300 answers (213 documents, 87 of them graded twice,
including a random 30 held out as the test set). They gave the same
defendants on 70% of the 135 shared pairs, about the AI engine's own
defendants score, so the 49 documents they disagreed on were settled
before any engine work, on the settling page (`review --rows`).

- **The settling page** shows the graders' answers side by side, one row
  per field, with the rows where they differ highlighted and a tally across
  the page. The form starts empty; **Keep this one** fills it from one
  answer, to save as is or edit. A saved settlement is marked `settled`,
  `agree` leaves it out of the graders' figures and stops listing the
  document, and the page shows the attorney box only where a grader
  answered it. It had asked on every card, and 23 settlements saved that
  unread box empty, which reads as "no attorney"; they were repaired by
  appending a copy without the attorney fields (marked `repaired`).
- **Answers were cut at 300 characters**, which shortened one long list of
  plaintiffs. The plaintiff now keeps 3000.
- **Labeling rules** learned while settling are in `GRADING.md`: no Doe
  placeholders, no surname the page does not show, an alias on its
  person's line as "a/k/a", the plaintiff's name without the description
  after it, nothing looked up off the page, the first address when it is
  unclear which is the defendant's. The scorer now also treats "its
  successors and/or assigns" as a description.
- **The form for round 2.** Plaintiffs, like defendants, go one per line;
  the box grows to fit and the answer is saved as one `; `-separated list.
  The attorneys and the firm share one box, one per line, because graders
  could not always tell a lawyer from the firm. Such answers have no
  `attorney_firm`; an engine's names and firm together are scored against
  the lines (`attorneys`), and its firm alone is right when it is one of
  them (`attorney_firm`), which keeps the AI engine, reading only the firm,
  comparable.

On the settled labels the AI engine has defendants right on 20 of the
random 30 (66.7%, against 50.0% on the unsettled labels), so part of its
apparent weakness was disagreement in the labels.

## Fine-tuning the AI engine on the graders' labels (2026-10-20)

The model learns the shape of what it is trained on, and the original
prompt asked for a shape the graders do not record (at most two defendants
on one line, the address as one string). So the fine-tune starts with a
second prompt in the graders' format, and the original stays the default.

- **The graders'-format prompt** (`ai/vision.py`, `lists_prompt`,
  `prompt_format="lists"`) asks for plaintiffs and defendants as lists, the
  defendant's address in parts, and the attorney box as lines plus an
  address, each with the `GRADING.md` rule. The prompt has no case number,
  because no label has one and the model would learn to leave it out. A
  training example whose label never answered the attorney box gets the
  prompt without the attorney items, so it never teaches "no attorney".
- **A Doe entry with a surname** ("JANE DOE" and the tenant's surname,
  "JOHN DOE II") is a placeholder too (`parties.is_placeholder`). The
  group-term rule strips trailing terms only, so ten such entries were
  still in the training labels.
- **The exporter** (`finetune.py`) cleans each label with the package's
  rules and returns counts of what changed: 22 placeholders dropped, 11
  plaintiff descriptions and 49 trailing commas off, 66 round-1 firms
  joined into the attorney lines. The random 30 are the test set and are
  never exported; the flagged 183 split 165 to training and 18 to
  validation (seed in `split.json`).
- **Toolchain**, verified 2026-10-20: `mlx-vlm` 0.7.9 in its own
  environment (it also needs `torch` and `torchvision`, for the Qwen3.5
  processor), base weights `mlx-community/Qwen3.5-9B-bf16`, LoRA rank 16,
  completion-only loss (`--train-on-completions`), `--max-seq-length 4096`
  (a page is about 2,100 image tokens; the default of 2048 would cut the
  answer off). The chat template renders the training prefix and the
  inference prompt identically, thinking off.
- **Scoring** (`scripts/finetune_eval.py`) runs on the held-out 30 with the
  scorer's own `compare`, in this process through mlx-vlm, so a trained
  adapter is scored without any server. Reproduced the settled baseline
  first: the original engine has defendants right on 20 of 30.
- **Serving** is through an OpenAI-style local server (`OpenAIVisionBackend`,
  LM Studio or `mlx_vlm.server`), since Ollama does not load LoRA adapters;
  the backend refuses any host but this machine. Trained weights are
  identifiable derived data and stay in the governed tree.

## Other reasons extraction fails

Reading the failures rather than counting them changed what looks worth
fixing. In a hand-inspected sample of documents where no address was found,
handwriting was one case in eight. The rest were printed and readable:

- **Streets with no type word.** "5037 So. Orchard", "1419-A South
  Ainsworth", "112 West Meeker". `STREET_RE` requires a suffix, and Tacoma
  in particular names many streets without one. This looks like the single
  largest cause.
- **Dot leaders.** `.....Candice Vaughn`, `....4815 115th St Ct SW....`
  Filler dots run into the tokens and defeat the pattern.
- **Superscript ordinals.** "150<sup>TH</sup> ST. SW" survives OCR as
  something the number pattern does not match.
- **Genuinely absent.** Some summonses simply do not print the defendant's
  address on page one, and returning nothing is correct.

## Observed engine differences

Notes for whoever runs the AI-lane head-to-head. These are observations from
spot runs, not measured rates; quantifying them is part of that milestone.

- **The AI lane's `law_firm` field absorbs neighbouring signature-block
  lines.** On the synthetic fixture it returned the attorney name, bar
  number, and "Attorneys for Plaintiff" role line along with the firm name,
  where the deterministic engine returned the firm name alone. The value is
  grounded (that text is on the page), so the check that catches invented
  answers does not catch an over-broad one. Expect the firm field to need
  either a tighter prompt or downstream trimming before it is analysis-ready.
- **Address fields agree closely.** Same fixture, similarity 0.818 raw
  against the deterministic answer, comfortably over the same-street
  threshold; the difference is trimming, not content.

## Release checklist

1. `pytest` green in `python/` (including the live model test on a machine
   that has Ollama).
2. `R CMD check` clean in `r/`, and `roxygen2::roxygenise("r")` run if any
   R documentation changed.
3. `python3 python/scripts/pii_sweep.py` reports clean. This sweeps the
   worktree, untracked files, and every blob in git history for
   case-number and address shapes; only the documented synthetic values
   may appear.
4. Schema regenerated if models changed:
   `python python/scripts/build_schema.py`.
5. Version bumped in **four** places, kept identical:
   `python/pyproject.toml`, `python/src/extract_text/__init__.py`
   (`__version__`), `r/DESCRIPTION`, `CITATION.cff`.
6. Fixtures regenerated only if their script changed
   (`python3 python/scripts/make_synthetic_fixtures.py`), and the manual's
   example outputs re-checked against them.
7. Tag, and note user-facing changes in the GitHub release.

## Regenerating things

| Artifact | Command |
|---|---|
| `schema/court_record.schema.json` | `python python/scripts/build_schema.py` |
| Synthetic fixtures | `python3 python/scripts/make_synthetic_fixtures.py` |
| R `NAMESPACE` and `man/` | `Rscript -e 'roxygen2::roxygenise("r")'` |

## Pinned things, and why

- **OCR settings** (tesseract LSTM engine, 300 dpi, TSV) are pinned in
  `documents.py` because they are part of what was validated.
- **AI decoding settings** (temperature 0, seed 42, thinking off) are
  pinned defaults in `vision.py` for reproducibility bookkeeping.
- **The vision prompt** deviates from Cheng Ren's benchmarked original in
  two documented ways: the appended `case_number` field, and the `law_firm`
  item saying it wants the firm and not the signing attorney (2026-08-22,
  measured above). Trailing defendant group terms are stripped in code
  rather than asked for, for the same reason.
- **The port note**: `STREET_RE` in `summons.py` deviates from the validated
  Washington scanner in four documented ways: the `(?!\w)` guard on the
  trailing direction (fixes "ST STE 200" and "AVE SEATTLE" misreads), the
  longest-first direction vocabulary with dotted pairs and `SO.`, the unit
  pattern tolerating `#` and a comma separator (all three above, applied
  2026-08-19), and `_skip_rail_house_number` rejecting a pleading line number
  glued to the house number. Each was measured on real documents before
  shipping; the evidence is in this file. The formal re-score landed
  2026-08-20 (sections above), so the full-truth-set numbers are this
  engine's own rather than the ported original's. On the pinned July
  documents it was equal or better on every column of every set; on the
  full sets the later mining pass improved every column of both large King
  sets and regressed the 27-case hand-swiped set, which is recorded with
  the rest of the full-set numbers above.
