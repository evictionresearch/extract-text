# extract_text (Python)

The extraction engine and the `extract-text` command. Full documentation,
including the manual, the ethics and data-use policies, and the maintenance
schedule, lives at the repository root.

```bash
pip install -e ".[dev]"
pytest                       # live-model test skips itself without Ollama
ruff check src tests scripts
```

```python
from extract_text import extract, extract_deterministic, extract_ai, compare, scan

x = extract("summons.pdf")                        # deterministic, no network
both = extract("summons.pdf", engine="both")      # rules + local AI, compared
rows = scan("folder/", engine="deterministic", out_dir="results/")
```

Command line equivalents:

```bash
extract-text doctor
extract-text extract summons.pdf --engine both
extract-text scan folder/ --out results/ --review
```

Maintenance scripts:

```bash
python scripts/build_schema.py            # regenerate schema/court_record.schema.json
python scripts/make_synthetic_fixtures.py # regenerate the synthetic test documents
python scripts/pii_sweep.py               # sweep tree + git history for record shapes
```

Licensed AGPL-3.0-or-later. Court records contain personally identifying
information; read `../DATA-USE.md` and `../ETHICS.md` before running this
against real filings, and never commit real records or their outputs here.
