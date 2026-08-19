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
| Open validation milestones | AI-lane head-to-head against the labeled Washington sets; deterministic re-score after the street-direction port fix | Maintainer, tracked in issues |

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
- **The port note**: `STREET_RE` in `summons.py` carries a word-boundary
  guard on the trailing street direction that the validated Washington
  scanner lacked. It strictly narrows matching (fixes "ST STE 200" and
  "AVE SEATTLE" misreads). Re-scoring the labeled sets with this port is an
  open milestone; until then, treat the July 2026 numbers as the ported
  original's and this engine's as expected-equal-or-better.
