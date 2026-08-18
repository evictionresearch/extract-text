# extract_text (Python)

The extraction engine. Full project documentation, including the ethics and data
use policies that govern real records, is in the repository root README.

```bash
pip install -e ".[dev]"
pytest
```

```python
from extract_text import extract_deterministic, extract_ai, compare

rules = extract_deterministic(text)          # rules only, no network
model = extract_ai(text, backend="local")    # or backend="anthropic"

report = compare(rules, model)
report.agreement_rate
report.needs_review
```

Regenerate the shared JSON Schema after changing `extract_text/schema.py`:

```bash
python scripts/build_schema.py
```

Licensed AGPL-3.0-or-later. Court records contain personally identifying
information; read `../DATA-USE.md` and `../ETHICS.md` before running this
against real filings.
