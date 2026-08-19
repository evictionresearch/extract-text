"""Court record text extraction, deterministic and AI side by side.

The one-line version:

    from extract_text import extract

    result = extract("summons.pdf")                  # rules only, no AI
    result.record.defendant_address
    result.flags

Both engines, compared:

    both = extract("summons.pdf", engine="both")
    both.record.defendant_address                    # the deterministic answer
    both.comparison.needs_review                     # what a person should check

A whole folder:

    from extract_text import scan

    rows = scan("documents/", engine="deterministic", out_dir="results/")

Everything runs on this machine. The deterministic engine is rules and
geometry; the AI engine is a local model served by Ollama. The one backend
that sends text elsewhere (`backend="anthropic"`) exists for cleared corpora
only, is never a default, and says so loudly in its own documentation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .compare import ComparisonReport, FieldComparison, compare, flatten
from .deterministic import extract as _extract_deterministic
from .schema import (
    Address,
    AIExtraction,
    Attorney,
    CourtRecord,
    DocumentInfo,
    Evidence,
    Extraction,
    Judgment,
    Party,
)

__version__ = "0.2.0"

__all__ = [
    "AIExtraction",
    "Address",
    "Attorney",
    "ComparisonReport",
    "CourtRecord",
    "DocumentInfo",
    "DualResult",
    "Evidence",
    "Extraction",
    "FieldComparison",
    "Judgment",
    "Party",
    "__version__",
    "compare",
    "extract",
    "extract_ai",
    "extract_deterministic",
    "flatten",
    "scan",
]


def _is_path(source) -> bool:
    if not isinstance(source, str):
        return True  # Path-like
    return "\n" not in source and len(source) < 4096 and os.path.exists(source)


def extract_deterministic(source, expected_case_number=None) -> Extraction:
    """Extract a court record using rules alone. No network, no model.

    `source` is document text or a path to a PDF, TIFF, PNG, or JPEG. The
    original file is always the better input: page positions switch on the
    address and attorney geometry and the OCR-quality flags.
    """
    return _extract_deterministic(source, expected_case_number)


def extract_ai(source, backend: str = "local", **kwargs) -> Extraction:
    """Extract a court record using a language model.

    `backend` is 'local' for a model on your own machine through Ollama (the
    default, because court records carry personally identifying information
    and the safe default keeps the text here), or 'anthropic' for the cloud
    API, which sends the text off this machine and needs a key.

    With the local backend, a file path goes to the vision model (it reads
    the page image, which is what handles handwriting), and plain text goes
    to the text model. Keyword arguments reach the backend constructor, e.g.
    `model="qwen3.5:9b"`, `host=`, `temperature=`.
    """
    if backend == "local":
        if _is_path(source):
            from .ai.vision import LocalVisionBackend

            source_text = kwargs.pop("source_text", None)
            return LocalVisionBackend(**kwargs).extract_file(source, source_text=source_text)
        from .ai.local_backend import LocalBackend

        return LocalBackend(**kwargs).extract(source)
    if backend == "anthropic":
        from .ai.anthropic_backend import AnthropicBackend

        if _is_path(source):
            raise ValueError(
                "The anthropic backend takes document text, not a file path. "
                "Extract the text first, and read DATA-USE.md before sending "
                "real records to any cloud API."
            )
        return AnthropicBackend(**kwargs).extract(source)
    raise ValueError(f"Unknown backend {backend!r}. Use 'local' or 'anthropic'.")


@dataclass
class DualResult:
    """Both engines' answers for one document, plus their comparison.

    `record` is the deterministic record: in a dual run the rules are the
    primary answer and the model is the cross-check, never the other way
    around unless you choose engine='ai'.
    """

    deterministic: Extraction
    ai: Extraction
    comparison: ComparisonReport

    @property
    def record(self) -> CourtRecord:
        return self.deterministic.record

    @property
    def flags(self) -> list[str]:
        return self.deterministic.flags + self.ai.flags

    @property
    def needs_review(self) -> list[str]:
        return self.comparison.needs_review


def extract(source, engine: str = "deterministic", model: str | None = None, **kwargs):
    """Extract one document. The simplest entry point.

    engine='deterministic' (default) returns an `Extraction` from rules
    alone. engine='ai' returns an `Extraction` from the local model.
    engine='both' runs the two and returns a `DualResult` whose
    `.comparison` says where they disagree.
    """
    if engine == "deterministic":
        return extract_deterministic(source, **kwargs)
    if engine == "ai":
        ai_kwargs = dict(kwargs)
        if model:
            ai_kwargs["model"] = model
        return extract_ai(source, backend="local", **ai_kwargs)
    if engine == "both":
        det = extract_deterministic(source, **kwargs)
        ai_kwargs = {"model": model} if model else {}
        if _is_path(source):
            # ground the model's quotes against the text the rules assembled
            from .documents import load_document

            try:
                source_text = load_document(source).text
            except Exception:
                source_text = None
            ai = extract_ai(source, backend="local", source_text=source_text, **ai_kwargs)
        else:
            ai = extract_ai(source, backend="local", **ai_kwargs)
        return DualResult(deterministic=det, ai=ai, comparison=compare(det, ai))
    raise ValueError("engine must be 'deterministic', 'ai', or 'both'")


def scan(inputs, engine: str = "deterministic", out_dir=None, **kwargs):
    """Batch extraction over files and folders. See `extract_text.pipeline`."""
    from .pipeline import scan as _scan

    return _scan(inputs, engine=engine, out_dir=out_dir, **kwargs)
