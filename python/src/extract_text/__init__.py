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
geometry; the AI engine is a local model served by Ollama. No backend sends
a document, its text, or a reading anywhere else.
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

__version__ = "0.4.2"

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


def extract_deterministic(source, expected_case_number=None, templates=None) -> Extraction:
    """Extract a court record using rules alone. No network, no model.

    `source` is document text or a path to a PDF, TIFF, PNG, or JPEG. The
    original file is always the better input: page positions switch on the
    address and attorney geometry and the OCR-quality flags. `templates` is
    a folder of approved form templates (see `extract_text.templates`),
    read first on pages that match one.
    """
    return _extract_deterministic(source, expected_case_number, templates)


def extract_ai(source, backend: str = "local", **kwargs) -> Extraction:
    """Extract a court record using a language model.

    The model runs on your own machine through Ollama, and nothing is sent
    anywhere else. `backend` takes 'local' only. It is kept so earlier calls
    still run; the cloud backend this package once carried was removed,
    because court records carry personally identifying information and the
    package's rule is that they stay on the computer that holds them.

    A file path goes to the vision model (it reads the page image, which is
    what handles handwriting), and plain text goes to the text model.
    Keyword arguments reach the backend constructor, e.g.
    `model="qwen3.5:9b"`, `host=`, `temperature=`.
    """
    if backend == "local":
        if _is_path(source):
            from .ai.vision import LocalVisionBackend

            source_text = kwargs.pop("source_text", None)
            return LocalVisionBackend(**kwargs).extract_file(source, source_text=source_text)
        kwargs.pop("prompt_format", None)  # a vision prompt; the text model has its own
        from .ai.local_backend import LocalBackend

        return LocalBackend(**kwargs).extract(source)
    raise ValueError(
        f"Unknown backend {backend!r}. The only backend is 'local': this package "
        "runs models on your own computer and has no cloud backend."
    )


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


def extract(source, engine: str = "deterministic", model: str | None = None,
            prompt_format: str = "lists", **kwargs):
    """Extract one document. The simplest entry point.

    engine='deterministic' (default) returns an `Extraction` from rules
    alone. engine='ai' returns an `Extraction` from the local model.
    engine='both' runs the two and returns a `DualResult` whose
    `.comparison` says where they disagree. `prompt_format` picks the AI
    engine's prompt, 'lists' (the default) or 'v1', the original.
    """
    if engine == "deterministic":
        return extract_deterministic(source, **kwargs)
    if engine == "ai":
        ai_kwargs = {**kwargs, "prompt_format": prompt_format}
        if model:
            ai_kwargs["model"] = model
        return extract_ai(source, backend="local", **ai_kwargs)
    if engine == "both":
        det = extract_deterministic(source, **kwargs)
        ai_kwargs = {"prompt_format": prompt_format, **({"model": model} if model else {})}
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
