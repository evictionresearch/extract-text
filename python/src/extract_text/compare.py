"""Compare two extractions of the same document.

This is the point of the package. Neither method is trustworthy alone: rules
miss what they were not written for, and a model can produce a fluent record
the document does not support. Run both and the disagreements tell you which
records a human should look at, which is a far smaller set than "all of them".

Agreement is evidence, not proof. Two methods can be wrong the same way,
especially when the document itself is wrong.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .schema import Extraction

Status = Literal["agree", "disagree", "only_a", "only_b", "both_missing"]


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten a nested model dump into dotted field paths."""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            out.update(flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            out.update(flatten(value, f"{prefix}.{index}"))
    else:
        out[prefix] = obj
    return out


def _comparable(value: Any) -> Any:
    """Normalize a value so cosmetic differences do not read as disagreement."""
    if value is None:
        return None
    if isinstance(value, str):
        collapsed = re.sub(r"\s+", " ", value).strip().casefold()
        return collapsed or None
    if isinstance(value, float):
        return round(value, 2)
    return value


@dataclass
class FieldComparison:
    path: str
    a: Any
    b: Any
    status: Status


@dataclass
class ComparisonReport:
    a: Extraction
    b: Extraction
    fields: list[FieldComparison] = field(default_factory=list)

    @property
    def disagreements(self) -> list[FieldComparison]:
        """Fields where both methods answered and the answers differ."""
        return [f for f in self.fields if f.status == "disagree"]

    @property
    def only_one_found(self) -> list[FieldComparison]:
        """Fields exactly one method populated.

        Usually a coverage gap in the rules rather than an error, and the main
        source of new patterns worth writing.
        """
        return [f for f in self.fields if f.status in ("only_a", "only_b")]

    @property
    def agreement_rate(self) -> float | None:
        """Share of contested fields where the two methods matched.

        Fields neither method populated are excluded; counting them would let a
        mostly empty document report near-perfect agreement.
        """
        contested = [f for f in self.fields if f.status != "both_missing"]
        if not contested:
            return None
        agreed = sum(1 for f in contested if f.status == "agree")
        return agreed / len(contested)

    def to_dict(self) -> dict[str, Any]:
        """Plain-data form, for JSON export and for the R wrapper.

        Keeps the bridge to other languages on one documented surface rather
        than having callers reach into dataclass internals.
        """
        return {
            "agreement_rate": self.agreement_rate,
            "needs_review": self.needs_review,
            "fields": [
                {"path": f.path, "a": f.a, "b": f.b, "status": f.status}
                for f in self.fields
            ],
            "a": {"method": self.a.method, "backend": self.a.backend},
            "b": {"method": self.b.method, "backend": self.b.backend},
        }

    @property
    def needs_review(self) -> list[str]:
        """Field paths a human should check, most serious first.

        An ungrounded AI field ranks above a plain disagreement: it means the
        model quoted text the document does not contain, which is a reason to
        distrust the whole record rather than just that field.
        """
        ungrounded = self.a.ungrounded_fields() + self.b.ungrounded_fields()
        disagreed = [f.path for f in self.disagreements]
        seen: dict[str, None] = {}
        for path in ungrounded + disagreed:
            seen.setdefault(path, None)
        return list(seen)


def compare(a: Extraction, b: Extraction) -> ComparisonReport:
    """Compare two extractions field by field."""
    flat_a = flatten(a.record.model_dump())
    flat_b = flatten(b.record.model_dump())

    report = ComparisonReport(a=a, b=b)
    for path in sorted(set(flat_a) | set(flat_b)):
        va, vb = flat_a.get(path), flat_b.get(path)
        ca, cb = _comparable(va), _comparable(vb)

        if ca is None and cb is None:
            status: Status = "both_missing"
        elif cb is None:
            status = "only_a"
        elif ca is None:
            status = "only_b"
        elif ca == cb:
            status = "agree"
        else:
            status = "disagree"

        report.fields.append(FieldComparison(path=path, a=va, b=vb, status=status))

    return report
