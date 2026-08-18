"""Extraction through the Anthropic API.

Text sent here leaves the machine. Court records contain party names and
addresses, so read DATA-USE.md before pointing this at real filings, and use
the local backend for anything that must not leave your infrastructure.
"""

from __future__ import annotations

import os

import anthropic

from ..schema import AIExtraction, Extraction
from .base import SYSTEM_PROMPT, ground

DEFAULT_MODEL = "claude-opus-5"

# Thinking is on by default on Opus 5 and counts against max_tokens, so this
# needs headroom well above the size of the record itself.
DEFAULT_MAX_TOKENS = 16_000


class AnthropicBackend:
    """Structured extraction via the Messages API.

    Uses structured outputs rather than prompting for JSON, so the response is
    schema-valid by construction and there is no parse-and-retry loop.
    """

    name = "anthropic"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        effort: str = "medium",
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        # A bare client resolves ANTHROPIC_API_KEY, then ANTHROPIC_AUTH_TOKEN,
        # then an `ant auth login` profile. Never pass a literal key.
        self.client = client or anthropic.Anthropic()

    def extract(self, text: str) -> Extraction:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            output_format=AIExtraction,
            output_config={"effort": self.effort},
            # The system prompt is identical across every document in a corpus,
            # so cache it. Opus 5 caches prefixes of 512 tokens and up; below
            # that the marker is a no-op rather than an error.
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract the court record from the document below.\n\n"
                        f"<document>\n{text}\n</document>"
                    ),
                }
            ],
        )

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise RuntimeError(
                f"Anthropic declined this document (category: {category}). "
                "Use the local backend for this record."
            )

        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                "Response hit max_tokens before completing. Raise max_tokens, "
                "lower effort, or split the document."
            )

        if response.parsed_output is None:
            raise RuntimeError("Model returned no parseable output.")

        return ground(response.parsed_output, text, backend=self.name)


def available() -> bool:
    """True when a credential is resolvable without prompting."""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    )
