# Address Check

A card game for building a human-verified training set of address
extractions. Each card shows a cropped picture of an address as it appears on
a court filing, next to the address the extractor typed out. A person says
whether the two say the same thing, and can optionally type what the picture
actually says.

The design follows **braindr** (https://braindr.us) by Anisha Keshavan,
Jason D. Yeatman, and Ariel Rokem, described in *Combining Citizen Science and
Deep Learning to Amplify Expertise in Neuroimaging*, Frontiers in
Neuroinformatics 13:29 (2019), https://doi.org/10.3389/fninf.2019.00029.
Two ideas are borrowed directly. The first is reducing the judgement to one
tap on one image, which is what makes volume possible. The second matters
more: rating people against items whose answer is already known, and weighting
their votes by how well they do, rather than counting every vote equally.

## Try it without any real data

The repo contains no card images. This builds a small deck from the invented
documents in `python/tests/fixtures/`, using the same code path a real deck
uses:

```bash
python3 game/make_demo_deck.py
cd game/demo && python3 -m http.server 8000
# open http://localhost:8000/
```

Four cards, all synthetic. One is a correct reading; three are wrong in the
ways this extractor actually gets things wrong.

## Build a real deck

```bash
python3 python/scripts/build_card_deck.py \
    --archive ~/data/evictionresearch/washington \
    --out    ~/data/evictionresearch/washington/_training_2026-08-18 \
    --n 700
```

Then serve it:

```bash
cp game/index.html ~/data/evictionresearch/washington/_training_2026-08-18/
cd ~/data/evictionresearch/washington/_training_2026-08-18
python3 -m http.server 8000
```

`--out` must point outside the repo. A deck is real court records: roughly
18 KB per card image, so a 450-card deck is about 8 MB of filings. `.gitignore`
blocks `deck.json`, `cards.csv`, `gold.csv`, and crop folders, but the real
protection is putting them in governed storage to begin with.

The addresses come from the **deterministic engine**. No model is involved, so
the labels say where the rules are right and where they are wrong.

## Running a rating round

The path from swipes to a training set, in order.

**1. Build a deck and freeze it.** Everyone in a round rates the *same* deck in
the *same* order. That is deliberate. With a handful of raters, shuffling per
person spreads thin coverage across many cards and nothing reaches consensus,
whereas a shared order stacks two or three votes onto the same cards and
settles them. Do not rebuild the deck mid-round: card ids are positional, and
regenerating invalidates ratings already collected.

**2. Serve only what raters need.** Point the web server at a directory holding
`index.html`, `deck.json` and `crops/` and nothing else. The deck folder also
contains `gold.csv` (the probe answers) and `cards.csv` (case numbers, file
paths, full addresses); serving the parent directory publishes both.

```bash
mkdir -p DECK/serve
cp game/index.html DECK/deck.json DECK/serve/
ln -s ../crops DECK/serve/crops
cd DECK/serve && python3 -m http.server 8000 --bind 127.0.0.1
```

Confirm before inviting anyone: `curl -o /dev/null -w '%{http_code}\n'
http://127.0.0.1:8000/gold.csv` must print 404.

**3. Send the deck to other raters.** Bundle `index.html`, `deck.json` and
`crops/`, and nothing else. Include instructions for starting a local server;
most raters have never run one. The bundle is real court records, so it goes
through whatever channel the data agreement allows, not email.

**4. Collect exports.** Each rater types their name in the app and presses
*Export my ratings*, which saves `ratings-NAME.json`. Any number of cards
helps; nobody needs to finish the deck.

**5. Score.** See below. Two or more votes per card is the useful threshold;
below that the scorer marks a card `unsettled` rather than guessing.

**6. Act on it.** `labels.csv` gives per-card verdicts and confidence. Cards
labeled `incorrect` with a typed correction are the highest-value output: they
say what the right answer was, not merely that the engine was wrong.

## Collecting and scoring answers

Raters press **Export my ratings** and send back a small JSON file. Then:

```bash
python3 game/score_ratings.py \
    --deck-dir ~/data/evictionresearch/washington/_training_2026-08-18 \
    --ratings ratings/*.json \
    --out ~/data/evictionresearch/washington/_training_2026-08-18/labels.csv
```

This scores every rater against the probes, drops anyone at or below chance,
weights the rest by the square of their probe accuracy, and writes one row per
card with a label (`correct`, `incorrect`, `disputed`, `unsettled`), a
confidence, and the most common typed correction.

## How names are handled

Only addresses are shown. Names are painted over before the crop is taken, and
because redaction works on word boxes rather than lines it still covers a name
that OCR merged into the address row.

A card is only included if at least one name was actually covered. That reads
as a weak rule and is a strong one: when the engine parses a party, redaction
has a target and works; when it parses none, nothing is covered, and those are
exactly the garbled documents where names end up merged into the address line.
The same condition creates the risk and removes the ability to mitigate it, so
those cards are withheld and written to `quarantine/` for internal review
instead. On a 611-document Washington sample this withheld 18 of 452 cards,
about 4%. Inspecting them found unredacted personal names on the crop, so the
rule was doing real work.

Redaction never hides anything except names. It is tempting to blank
everything except the address the engine found, which would guarantee no name
survives, but it would also hide every omission, and omissions such as a
dropped unit or a truncated direction are the most common way this engine is
wrong. Those have to stay visible or the exercise is pointless.

**Before showing a deck to anyone outside the data agreement**, settle the
audience question. See issue #3.

## Truth rounds: spend raters only where labels disagree

When a hand-labeled truth set exists (`nlp1_paper_data.csv` for Washington),
most cards would waste rater time re-confirming what the labels already
settle. `python/scripts/build_truth_round.py` builds a round from a
truth-scored run instead:

- **Disagreement cards** — engine answer differs from the truth label. These
  are the only cards that need human eyes: the engine is wrong, or the
  years-old label is wrong, and the swipe adjudicates.
- **Real gold probes** — cards whose engine answer matches truth exactly are
  shown either unaltered (correct answer *yes*) or with one digit changed
  (correct answer *no*). Earlier rounds could only corrupt text to make
  no-probes; a truth set finally provides yes-probes, so a rater who rejects
  everything is caught as surely as one who accepts everything.
- Clear agreements never reach the deck; the label settles them.

## Vision cards: model readings enter the game, not the truth set

Some documents defeat the deterministic engine entirely: handwriting,
superscript ordinals, clerk-omitted street names. A vision model (Claude
reading page images, or the local qwen lane) can often still read them — but
a model's reading is a **proposal, not ground truth**, so it enters the game
as a card exactly like an engine extraction: a person swipes, and only
confirmed readings graduate to the training set.

`python/scripts/build_vision_cards.py` turns a readings CSV (address + party
names per document) into cards with ids `V####` and a `source` column, so
`score_ratings.py` reports accuracy per reader — rules vs claude-vision vs
qwen — on the same footing. The reader supplies the names it saw, which is
what makes redaction work on documents where the engine parsed no parties:
the same withhold-if-nothing-redacted rule applies.

Two lessons from the first vision round, worth keeping:

- On pro se fill-in forms the TO field frequently holds the **plaintiff's or
  even the courthouse's** address, not the defendant's. A reader that blindly
  transcribes the TO block will propose the wrong household with full
  confidence. Of 36 pages read, 4 were this trap; they were recorded as skips.
- Reading the *names* is what makes the cards safe to show, so a reader that
  only extracts addresses cannot feed the game.

## Attention probes

Roughly 8% of the deck is a copy of a real card whose typed address has had one
digit changed, so the correct answer is always "does not match". These measure
whether a rater is reading or swiping, and they are the basis of the weighting.
`gold.csv` holds the answers and is never served to the app.

Only digit changes are used. Flipping a direction or dropping a unit can
accidentally *correct* a guess that was already wrong, which would mark a probe
"no" when "yes" is the honest answer. Once a first round produces
confirmed-correct cards, richer probes can be built from those.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app. No frameworks, no network calls, no analytics. |
| `make_demo_deck.py` | Builds the synthetic demo deck. |
| `score_ratings.py` | Weights raters and writes the labeled training set. |
| `../python/scripts/build_card_deck.py` | Builds a real deck from an archive. |
| `../python/src/extract_text/cards.py` | Cropping, redaction, and the safety rule. |

## Notes on the app

Ratings are held in `localStorage` until exported, so a closed tab does not
lose a session. There is no server and nothing is transmitted; the export step
is deliberate and manual. It works on a phone (swipe) and on a desktop (arrow
keys), because most raters will use whichever is nearer.
