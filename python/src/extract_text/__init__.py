"""Court record text extraction, deterministic and AI side by side.

    from extract_text import extract_deterministic, extract_ai, compare

    rules = extract_deterministic(text)
    model = extract_ai(text, backend="local")
    report = compare(rules, model)
"""

from __future__ import annotations

from .compare import ComparisonReport, FieldComparison, compare, flatten
from .deterministic import extract as _extract_deterministic
from .schema import (
    AIExtraction,
    CourtRecord,
    Evidence,
    Extraction,
    Judgment,
    Party,
)

__version__ = "0.1.0"

__all__ = [
    "extract_deterministic",
    "extract_ai",
    "compare",
    "flatten",
    "ComparisonReport",
    "FieldComparison",
    "Extraction",
    "AIExtraction",
    "CourtRecord",
    "Party",
    "Judgment",
    "Evidence",
    "__version__",
]


def extract_deterministic(text: str) -> Extraction:
    """Extract a court record using rules alone. No network, no API key."""
    return _extract_deterministic(text)


def extract_ai(text: str, backend: str = "local", **kwargs) -> Extraction:
    """Extract a court record using a language model.

    `backend` is 'local' for a model on your own machine, or 'anthropic' for
    the API. The default is 'local' because court records carry personally
    identifying information and the safe default is the one that keeps the text
    on the machine. Remaining keyword arguments go to the backend constructor.
    """
    if backend == "local":
        from .ai.local_backend import LocalBackend

        return LocalBackend(**kwargs).extract(text)
    if backend == "anthropic":
        from .ai.anthropic_backend import AnthropicBackend

        return AnthropicBackend(**kwargs).extract(text)
    raise ValueError(f"Unknown backend {backend!r}. Use 'local' or 'anthropic'.")
