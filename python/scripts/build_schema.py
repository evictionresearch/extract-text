#!/usr/bin/env python3
"""Regenerate schema/court_record.schema.json from the Pydantic models.

The models in extract_text/schema.py are the source of truth. This writes the
language-neutral copy that the R wrapper and any other consumer reads, so the
two cannot drift.

    python scripts/build_schema.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from extract_text.schema import Extraction  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "schema" / "court_record.schema.json"

schema = Extraction.model_json_schema()
schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
schema["$id"] = (
    "https://github.com/evictionresearch/extract-text/blob/main/"
    "schema/court_record.schema.json"
)
schema["description"] = (
    "Generated from extract_text.schema. Do not hand-edit; run "
    "python/scripts/build_schema.py instead."
)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")

# Path written, for the caller to confirm
OUT
