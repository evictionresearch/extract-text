"""Extraction through a locally hosted model.

The reason this exists: court records name people and give their addresses, and
a good deal of the work that most needs this tooling cannot send that text to a
third party. A local model is weaker than a frontier model at this task. It is
also the only AI option available when the data cannot leave the machine, and a
weaker extraction you are permitted to run beats a better one you are not.

Talks to Ollama's `/api/chat`, which accepts a JSON Schema in `format` and
constrains decoding to it. Any server exposing that shape works; point
`OLLAMA_HOST` at it.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..schema import AIExtraction, Extraction
from .base import SYSTEM_PROMPT, ground

DEFAULT_HOST = "http://localhost:11434"

# Same default as the vision lane: one model serves both, so a local setup
# only ever needs one pull. See ai/vision.py for why this model.
DEFAULT_MODEL = "qwen3.5:9b"


class LocalBackend:
    """Structured extraction from a model running on your own hardware."""

    name = "local"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.timeout = timeout

    def extract(self, text: str) -> Extraction:
        from .vision import resolve_model

        model = resolve_model(self.model, self.host)
        payload = {
            "model": model,
            "stream": False,
            "think": False,
            "format": AIExtraction.model_json_schema(),
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Extract the court record from the document below.\n\n"
                        f"<document>\n{text}\n</document>"
                    ),
                },
            ],
        }

        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"No local model server at {self.host}. Start one, or set "
                "OLLAMA_HOST."
            ) from exc

        content = body.get("message", {}).get("content", "")

        # Constrained decoding makes schema-valid output very likely but not
        # guaranteed, and small models sometimes stop mid-object. Surface that
        # as a clear failure rather than a half-filled record.
        try:
            parsed = AIExtraction.model_validate_json(content)
        except Exception as exc:
            raise RuntimeError(
                f"Local model returned output that did not match the schema: {exc}"
            ) from exc

        return ground(parsed, text, backend=f"{self.name}:{model}")


def available(host: str | None = None) -> bool:
    """True when a local model server answers."""
    base = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False
