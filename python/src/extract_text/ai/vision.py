"""Vision extraction: a local model reads the page image directly.

This is the lane for documents OCR cannot read, handwriting above all. The
model sees the rendered page, not extracted text, so nothing depends on
character recognition working first.

The approach, prompt design, and benchmark are Cheng Ren's
(`infor_extr_qwen.ipynb`): one structured prompt per summons page-1 image to
a locally hosted qwen3.5 9B vision model through Ollama, five fields back as
JSON, with a strict-then-best-effort parser and a regex fallback for
near-JSON output. Bench run summer 2026: 300 Pierce County summons page-1
images in 1:22:40 (about 17 seconds a page), a structured defendant field
returned for all 300. A case-number field is added here beyond the
benchmarked five, so batch runs can cross-check the document against the
docket.

Everything happens on this machine. The image goes to the Ollama server on
localhost, which is a program running on your own computer, not a cloud
service. No account, no key, no per-page cost.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ..schema import (
    Address,
    Attorney,
    CourtRecord,
    DocumentInfo,
    Evidence,
    Extraction,
    Party,
)

DEFAULT_HOST = "http://localhost:11434"

# The model this package is validated against. 9 billion parameters, vision
# capable, Apache 2.0 licensed, runs on a 16 GB machine. Pull it once with:
#   ollama pull qwen3.5:9b
# MAINTENANCE.md carries the schedule for revisiting this choice as better
# local models appear.
DEFAULT_VISION_MODEL = "qwen3.5:9b"

VISION_FIELDS = ("plaintiff", "defendant", "address", "law_firm",
                 "law_firm_address", "case_number")

# Cheng Ren's prompt, as benchmarked, with the case_number field appended and
# one clarification to the law_firm item. On the 2026-08-21 corpus bench, 23 of
# the 28 law_firm misses across six models were the signing attorney and bar
# number returned in place of the firm entity; the item never said which one it
# wanted. Recorded as a deliberate deviation in MAINTENANCE.md.
VISION_PROMPT = """\
You are a researcher extracting structured information from court summons documents related to housing cases.

Your task is to read the provided document image and extract the following information:
	1.	Plaintiff — Usually listed at around 20% position of the document with keyword plaintiff around. Plaintiff could be a company or an individual. Usually, plaintiff's information is before the defendant's information.
	2.	Defendant — Usually listed at around 30% position of the document. Extract only the complete defendant name line and return up to the first two explicitly named defendants exactly as written, including both names when joined by "and" or "&", but excluding any trailing generic/group terms (e.g., "et al.", "all occupants", "husband and wife", "John/Jane Doe", "ALL OTHER OCCUPANTS", "all others", "and any and all other residing..."); do not truncate after the first name. Defendant could be a company or an individual.
	3.	Tenant full address — Usually appears in the middle section of the document, which usually ending with zipcode. Sometimes, it also has county name in the address.
	4.	Law firm representing the plaintiff — Typically appears near the bottom right of the document (e.g., "XYZ Attorney at Law," "Law Offices of ...", "INVESTMENT GROUP"). If there is Attorney at Law after the name, including Attorney at Law as well. Return the firm itself, not the individual attorney who signed for it: the same signature block usually carries a person's name with a bar number (e.g., "WSBA #12345") and a role line such as "Attorneys for Plaintiff", and neither of those is the firm name.
	5.	Address of the law firm representing the plaintiff — Usually the last full address appearing in the document. (Be cautious, the phone number is located near this text that I don't need.)
	6.	Case number — Usually printed in or near the caption, in the upper portion of the document, labeled "Case No." or similar.

Rules:
	•	Extract only information explicitly stated in the text.
	•	Do not infer or guess missing information.
	•	If any field is missing or unclear, return "NA".
	•	Return only the requested fields.
	•	Output must be valid JSON with no additional text.

Output format:

{
  "plaintiff": "",
  "defendant": "",
  "address": "",
  "law_firm": "",
  "law_firm_address": "",
  "case_number": ""
}
"""


def parse_llm_json_best_effort(content):
    """Return dict if we can parse JSON, else None. (Cheng Ren's ladder.)"""
    if content is None:
        return None

    s = content.strip()

    # 1) strict
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 2) strip code fences
    s2 = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        return json.loads(s2)
    except json.JSONDecodeError:
        pass

    # 3) extract first {...}
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return None


def extract_fields_fallback(raw: str) -> dict:
    """Field-by-field regex recovery for near-JSON output. (Cheng Ren's.)"""
    fields = list(VISION_FIELDS)
    result = {}
    for i, field in enumerate(fields):
        next_field = fields[i + 1] if i + 1 < len(fields) else None
        if next_field:
            pattern = rf'"{field}"\s*:\s*"?(.*?)"?\s*,\s*"{next_field}"'
        else:
            pattern = rf'"{field}"\s*:\s*"?(.*?)"?\s*}}'
        match = re.search(pattern, raw, re.DOTALL)
        result[field] = match.group(1).strip().strip('"') if match else None
    return result


def _clean(value) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    if not v or v.upper() == "NA":
        return None
    return v


_NAME_SPLIT_RE = re.compile(r"\s+(?:and|&)\s+", re.IGNORECASE)

# Trailing group terms a caption adds after the named defendants. The vision
# prompt already lists these and asks the model to drop them; four of the six
# models benched on 2026-08-20 returned them anyway. Because _NAME_SPLIT_RE
# splits on "and", a clause left in place became a second, phantom defendant
# named "ALL OTHER OCCUPANTS". Stripping it here is deterministic, so the
# output no longer depends on a model following an instruction.
_GROUP_TERM_RE = re.compile(
    r"""
    [\s,;&]*                                  # separator before the clause
    (?:\band\b\s*)?                           # an optional joining "and"
    (?:
        any\s+and\s+all\s+other[\w\s]*        # "any and all other residing..."
      | all\s+(?:other\s+)?occupants?          # "all occupants"
      | all\s+others?                           # "all others"
      | husband\s+and\s+wife
      | (?:john|jane)\s*/\s*(?:john|jane)\s+does?   # "John/Jane Doe"
      | (?:john|jane)\s+does?                   # "Jane Doe"
      | does?\s*\d+\s*(?:-|through|to)\s*\d+     # "Does 1-10"
      | et\.?\s*al\.?
      | et\.?\s*ux\.?
    )
    \s*\.?\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_group_terms(value) -> str | None:
    """Drop trailing generic party terms from a defendant line.

    Only trailing terms go, and only ones the prompt already names, so a real
    surname is never at risk. Repeats until stable because captions stack them
    ("JOHN SMITH and JANE SMITH, husband and wife, et al."). If stripping would
    empty the field the original is kept instead: a value that is entirely a
    group term is wrong either way, and discarding it would hide that from
    the evidence record rather than surface it.
    """
    cleaned = _clean(value)
    if cleaned is None:
        return None
    return _strip_group_terms(cleaned)[0]


def _strip_group_terms(text: str) -> tuple[str, bool]:
    """The stripping itself, plus whether a group term was what came off.

    Trailing punctuation is trimmed on the same pass, and is far more common
    than a group term, so the two are reported separately. Only a real term
    should raise a flag that claims one was found.
    """
    current = text
    found = False
    while True:
        shorter = _GROUP_TERM_RE.sub("", current)
        if shorter != current:
            found = True
        shorter = shorter.strip(" ,;&")
        if shorter == current:
            break
        current = shorter
    return (current or text), found


def fields_to_record(fields: dict) -> CourtRecord:
    """Map the flat vision fields into the shared schema."""
    from ..deterministic.patterns import BUSINESS_MARKERS
    from ..deterministic.summons import parse_address

    def to_address(value):
        if value is None:
            return None
        parsed = parse_address(value)
        if parsed:
            return Address(
                raw=value,
                street=parsed["street"] or None,
                unit=parsed["unit"] or None,
                city=parsed["city"] or None,
                state=parsed["state"] or None,
                zip=parsed["zip"] or None,
            )
        return Address(raw=value)

    plaintiff = _clean(fields.get("plaintiff"))
    defendant = strip_group_terms(fields.get("defendant"))
    address = _clean(fields.get("address"))
    law_firm = _clean(fields.get("law_firm"))
    law_firm_address = _clean(fields.get("law_firm_address"))
    case_number = _clean(fields.get("case_number"))

    defendant_address = to_address(address)
    defendants = []
    if defendant:
        for name in _NAME_SPLIT_RE.split(defendant):
            name = name.strip(" ,;")
            if len(name) >= 2:
                defendants.append(Party(
                    name=name, role="defendant",
                    is_business=bool(BUSINESS_MARKERS.search(name)),
                    address=defendant_address,
                ))

    plaintiffs = []
    if plaintiff:
        plaintiffs.append(Party(
            name=plaintiff, role="plaintiff",
            is_business=bool(BUSINESS_MARKERS.search(plaintiff)),
        ))

    attorney = None
    if law_firm or law_firm_address:
        attorney = Attorney(firm=law_firm, address=to_address(law_firm_address))

    return CourtRecord(
        case_number=case_number,
        plaintiffs=plaintiffs,
        defendants=defendants,
        defendant_address=defendant_address,
        attorney=attorney,
    )


def resolve_model(requested: str, host: str | None = None, warn: bool = True) -> str:
    """Match the requested model tag against what Ollama has pulled.

    Exact tag wins. When only another tag of the same model family is pulled
    (someone ran `ollama pull qwen3.5` and got `:latest` instead of `:9b`),
    that tag is used and a note says so; nothing is substituted silently,
    and the extraction's `backend` field always records the tag actually
    used. When nothing related is pulled, the requested tag is returned
    unchanged so the server's own error (with the pull command) surfaces.
    """
    models = pulled_models(host)
    if not models or requested in models:
        return requested
    family = requested.split(":")[0]
    hits = sorted(m for m in models if m.split(":")[0] == family)
    if not hits:
        return requested
    pick = f"{family}:latest" if f"{family}:latest" in hits else hits[0]
    if warn:
        print(
            f"note: model '{requested}' is not pulled; using '{pick}' from the "
            f"same family. Pin the exact tag with: ollama pull {requested}",
            file=sys.stderr,
        )
    return pick


class LocalVisionBackend:
    """Structured extraction from a page image, on your own hardware.

    Defaults are pinned for reproducibility: temperature 0, fixed seed,
    thinking off. A language model is still not deterministic the way rules
    are (a model update, or different hardware, can change output), which is
    exactly why the deterministic engine exists separately and why batch runs
    record which model produced each row.
    """

    name = "local-vision"

    def __init__(
        self,
        model: str = DEFAULT_VISION_MODEL,
        host: str | None = None,
        timeout: float = 600.0,
        temperature: float = 0.0,
        seed: int = 42,
        page: int = 1,
        dpi: int = 150,
        prompt: str = VISION_PROMPT,
    ) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.seed = seed
        self.page = page
        self.dpi = dpi
        self.prompt = prompt
        self._resolved: str | None = None

    # -- plumbing --------------------------------------------------------

    @property
    def resolved_model(self) -> str:
        if self._resolved is None:
            self._resolved = resolve_model(self.model, self.host)
        return self._resolved

    def _chat(self, b64_image: str) -> str:
        payload = {
            "model": self.resolved_model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "user", "content": self.prompt, "images": [b64_image]}
            ],
            "options": {"temperature": self.temperature, "seed": self.seed},
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read()).get("error", "")
            except Exception:
                pass
            if "not found" in detail.lower():
                raise RuntimeError(
                    f"The model '{self.resolved_model}' is not pulled on this "
                    f"machine. Run: ollama pull {self.model}"
                ) from exc
            raise RuntimeError(f"Ollama returned an error: {detail or exc}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"No local model server at {self.host}. Start Ollama (the app, "
                "or 'ollama serve' in a terminal), or set OLLAMA_HOST. Run "
                "'extract-text doctor' to check your setup."
            ) from exc
        return body.get("message", {}).get("content", "")

    # -- public API ------------------------------------------------------

    def extract_image(self, image_path, source_text: str | None = None) -> Extraction:
        """Extract from an already rendered page image (PNG or JPEG)."""
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        raw = self._chat(b64)

        flags: list[str] = []
        fields = parse_llm_json_best_effort(raw)
        if fields is None:
            fields = extract_fields_fallback(raw)
            flags.append("vision_json_fallback")
        if not any(_clean(v) for v in fields.values()):
            flags.append("vision_no_fields")

        # Strip before the record and the evidence are built, so both the
        # parsed parties and the quoted field reflect the same value.
        before = _clean(fields.get("defendant"))
        if before is not None:
            after, found_term = _strip_group_terms(before)
            if found_term:
                flags.append("vision_defendant_group_term")
            fields["defendant"] = after

        record = fields_to_record(fields)

        # Evidence: the model's raw field values. Grounding is only possible
        # when the caller supplies document text to check against; without it
        # the values stay explicitly unverified, which is what grounded=False
        # means.
        evidence: dict[str, Evidence] = {}
        norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
        normalized_source = norm(source_text) if source_text else None
        for key in VISION_FIELDS:
            value = _clean(fields.get(key))
            if value is None:
                continue
            grounded = bool(normalized_source and norm(value) in normalized_source)
            evidence[key] = Evidence(quote=value, grounded=grounded, page=self.page)

        return Extraction(
            record=record,
            method="ai",
            backend=f"{self.name}:{self.resolved_model}",
            evidence=evidence,
            flags=flags,
            document=DocumentInfo(file=os.path.basename(str(image_path))),
        )

    def extract_file(self, path, source_text: str | None = None) -> Extraction:
        """Render the page of a PDF or TIFF, then extract from the image."""
        from ..documents import render_page

        png = render_page(path, page=self.page, dpi=self.dpi)
        if png is None:
            raise RuntimeError(f"Could not render page {self.page} of {path}.")
        out = self.extract_image(png, source_text=source_text)
        out.document = DocumentInfo(file=os.path.basename(str(path)))
        return out


def available(host: str | None = None) -> bool:
    """True when a local Ollama server answers."""
    base = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def pulled_models(host: str | None = None) -> list[str]:
    """Names of the models the local Ollama server has pulled."""
    base = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=2.0) as resp:
            data = json.loads(resp.read())
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []
