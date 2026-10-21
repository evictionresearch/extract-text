"""Language-model extraction backends.

Backends load lazily. The Anthropic SDK is an optional dependency, so importing
this package must not require it: a local-only install has no reason to carry
an API client it will never call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import SYSTEM_PROMPT, ExtractionBackend, ground
from .local_backend import LocalBackend
from .vision import (
    DEFAULT_VISION_MODEL,
    LISTS_PROMPT,
    VISION_PROMPT,
    LocalVisionBackend,
    OpenAIVisionBackend,
    available,
    pulled_models,
)

if TYPE_CHECKING:  # pragma: no cover
    from .anthropic_backend import AnthropicBackend

__all__ = [
    "DEFAULT_VISION_MODEL",
    "LISTS_PROMPT",
    "SYSTEM_PROMPT",
    "VISION_PROMPT",
    "AnthropicBackend",
    "ExtractionBackend",
    "LocalBackend",
    "LocalVisionBackend",
    "OpenAIVisionBackend",
    "available",
    "ground",
    "pulled_models",
]


def __getattr__(name: str) -> Any:
    if name == "AnthropicBackend":
        try:
            from .anthropic_backend import AnthropicBackend
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The Anthropic backend needs the SDK: "
                "pip install 'extract-text[anthropic]'"
            ) from exc
        return AnthropicBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
