"""The package has no cloud backend.

Its fixed rule is that everything runs on the user's own computer. A backend
for a cloud API shipped through 0.4.2 and was removed (MAINTENANCE.md,
"Pinned things, and why"). These tests keep it out.
"""

import re
from pathlib import Path

import pytest

import extract_text
from extract_text import ai

# SDKs whose only job is to send text or images to a hosted model
CLOUD_SDK_RE = re.compile(
    r"^\s*(?:import|from)\s+(anthropic|openai|boto3|cohere|mistralai|google\.generativeai)\b",
    re.MULTILINE,
)


def test_extract_ai_takes_the_local_backend_only():
    with pytest.raises(ValueError, match="no cloud backend"):
        extract_text.extract_ai("Case No. 25-2-00001-0", backend="anthropic")


def test_no_cloud_backend_is_exported():
    assert "AnthropicBackend" not in ai.__all__
    assert not hasattr(ai, "AnthropicBackend")


def test_no_module_imports_a_cloud_sdk():
    src = Path(extract_text.__file__).parent
    hits = sorted(p.relative_to(src).as_posix() for p in src.rglob("*.py")
                  if CLOUD_SDK_RE.search(p.read_text()))
    assert hits == []
