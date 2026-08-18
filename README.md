# extract-text

Court record text extraction, showing deterministic and AI methods side by side on the same document.

Court records are the raw material of eviction research, and they arrive as scanned PDFs, WebForms tables, and clerk exports with no consistent structure. This package extracts structured fields from that text two ways, then reports where the two methods agree.

- **Deterministic** extraction uses regular expressions and layout rules. It is fast, free, fully auditable, and produces the same answer every time.
- **AI** extraction uses a language model, either through the Anthropic API or a locally hosted model. It handles the messy documents rules cannot, at the cost of reproducibility.

Neither is the right answer on its own. The point of the package is the comparison: run both, and treat disagreement as a signal about which records need review.

## Status

Early scaffold. The schema, the deterministic engine, and the backend interface are in place. Nothing here has been validated against a real court corpus yet.

## Layout

```
schema/          Shared field contract (JSON Schema), the source of truth for both languages
python/          The extraction engine
r/               A thin R wrapper over the Python engine via reticulate
docs/            Method notes
```

## Python

```bash
cd python
pip install -e ".[dev]"
```

```python
from extract_text import extract_deterministic, extract_ai, compare

text = open("case.txt").read()

rules = extract_deterministic(text)
model = extract_ai(text, backend="anthropic")

report = compare(rules, model)
report.disagreements    # fields where the two methods differ
report.agreement_rate   # share of populated fields that match
```

Every extracted field carries its own provenance: which method produced it, what confidence it claims, and the character span in the source text it came from. That is what makes the comparison meaningful rather than two opaque dictionaries.

### Backends

| Backend | Where the text goes | Use when |
|---|---|---|
| `anthropic` | Anthropic API | Development, and any corpus already cleared for third-party processing |
| `local` | A model on your own machine (Ollama) | Records containing party names, addresses, or anything else that must not leave the machine |

Court records contain personally identifying information. The `local` backend exists so that constraint does not force you to give up AI extraction entirely. Read `ETHICS.md` and `DATA-USE.md` before pointing this at real filings.

## R

The R package wraps the Python engine through reticulate so that the state pipelines can call it directly.

```r
# install.packages("remotes")
remotes::install_github("evictionresearch/extract-text", subdir = "r")

library(extracttext)
extracttext_install()   # one-time: creates the Python environment

rules <- extract_deterministic(txt)
model <- extract_ai(txt, backend = "local")
compare_extractions(rules, model)
```

Note on names. The repository is `extract-text`; the Python import package is `extract_text`; the R package is `extracttext`, because R package names cannot contain hyphens or underscores. If this is ever published to PyPI the distribution name will need to be more distinctive than `extract-text`, which is generic and probably taken.

## License

AGPL-3.0-or-later. See `LICENSE`.

Commercial use is permitted. Building a closed-source product or hosted service on this code is not: the AGPL requires that anyone who modifies it, including anyone who runs it as a network service, release their source under the same terms.

Separate terms govern the data. A software license reaches the software, not the records you extract with it, so the constraints that matter for court records live in `DATA-USE.md`. `ETHICS.md` states the uses this project will not support.

## Authors

Cheng Ren (University at Albany, SUNY), Tim Thomas (Eviction Research Network, UC
Berkeley), Aaron Culich (UC Berkeley).

Citation metadata is in `CITATION.cff`. Author order there reflects
contribution to the project and is separate from copyright ownership, which is
governed by the CLA in `CONTRIBUTING.md`.
