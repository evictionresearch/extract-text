"""Language-model extraction backends.

Every backend here runs a model on the user's own computer. None sends a
document, its text, or a reading to a cloud service.
"""

from __future__ import annotations

from .base import SYSTEM_PROMPT, ExtractionBackend, ground
from .local_backend import LocalBackend
from .vision import (
    DEFAULT_VISION_MODEL,
    LISTS_ENGINE_PROMPT,
    LISTS_PROMPT,
    VISION_PROMPT,
    LocalVisionBackend,
    OpenAIVisionBackend,
    available,
    pulled_models,
)

__all__ = [
    "DEFAULT_VISION_MODEL",
    "LISTS_ENGINE_PROMPT",
    "LISTS_PROMPT",
    "SYSTEM_PROMPT",
    "VISION_PROMPT",
    "ExtractionBackend",
    "LocalBackend",
    "LocalVisionBackend",
    "OpenAIVisionBackend",
    "available",
    "ground",
    "pulled_models",
]

