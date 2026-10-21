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

from ..parties import (  # noqa: F401
    _GROUP_TERM_RE,
    _strip_group_terms,
    drop_plaintiff_matches,
    is_placeholder,
)
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


# The graders' format, added 2026-10-20 for fine-tuning: every party as a
# list, the defendant's address in parts, and the plaintiff attorney's block
# as lines plus an address, each following the rules in GRADING.md. A model
# trained on the graders' labels learns this shape, so the prompt it is
# trained and run with has to ask for it. The attorney items are optional:
# a training example whose label says nothing about the attorney block is
# shown the prompt without them, so the model is never taught to answer
# "no attorney" where nobody looked.
_LISTS_HEAD = """\
You are a researcher extracting structured information from the first page of a court document in a housing (eviction) case.

Read the page image and return what it prints, as printed:
	1.	plaintiffs — The landlord or company bringing the case, usually at the top of the caption before the defendants. One entry per plaintiff, the name only: leave out the description after it ("a Washington limited liability company", "its successors and/or assigns") and any trailing comma.
	2.	defendants — Every named defendant, one entry per person. Leave out placeholders and group words ("all other occupants", "John Doe", "Jane Doe", "et al."). Never add a surname the page does not show. An alias stays in its person's entry, written "a/k/a" ("PAT EXAMPLE a/k/a PATRICIA EXAMPLE"). A business the defendant does business as ("d/b/a") is an entry of its own.
	3.	defendant_address — The defendant's address, in the caption or after "TO:", never the attorney's address. Street without the unit; the unit on its own ("Apt 5", "#12"); then city, state, and ZIP. If the page gives two, use the address of the property the case is about; if that is unclear, the first one."""

_LISTS_ATTORNEYS = """
	4.	attorneys — The plaintiff's attorney signature block, usually at the bottom right: every attorney's name and the firm or office name, one entry each, without "Attorney for Plaintiff" or the bar number. Empty if the plaintiff signed for itself.
	5.	attorney_address — That block's address on one line, as printed (street, suite, city, state, ZIP), without the phone number."""

_LISTS_RULES = """

Rules:
	•	Extract only what the page prints. Do not infer, guess, or look anything up.
	•	Use [] for a missing list and "" for a missing value.
	•	Output must be valid JSON with no additional text.

Output format:

"""

_LISTS_SHAPE = {
    "plaintiffs": [],
    "defendants": [],
    "defendant_address": {"street": "", "unit": "", "city": "", "state": "", "zip": ""},
}
_LISTS_SHAPE_ATTORNEYS = {"attorneys": [], "attorney_address": ""}


def lists_prompt(attorneys: bool = True) -> str:
    """The graders'-format prompt, with or without the attorney items."""
    shape = {**_LISTS_SHAPE, **(_LISTS_SHAPE_ATTORNEYS if attorneys else {})}
    return (_LISTS_HEAD + (_LISTS_ATTORNEYS if attorneys else "") + _LISTS_RULES
            + json.dumps(shape, indent=2) + "\n")


LISTS_PROMPT = lists_prompt()
LISTS_FIELDS = ("plaintiffs", "defendants", "defendant_address", "attorneys",
                "attorney_address")

# a line of the attorney box that names the office rather than a person
_FIRM_RE = re.compile(r"\b(?:Law|Legal|Offices?|Attorneys?|PLLC|P\.?L\.?L\.?C\.?|"
                      r"P\.?S\.?|P\.?C\.?)(?:\W|$)", re.IGNORECASE)


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


def _clean_list(value) -> list[str]:
    """A list field as a list of cleaned names; a model that answers one
    string where a list was asked gets it split on semicolons or new lines."""
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"\s*;\s*|\n", value)
    out = []
    for item in value if isinstance(value, list) else [value]:
        item = _clean(item if isinstance(item, str) else None)
        if item:
            item = re.sub(r"[\s,;]+$", "", item)
            if item:
                out.append(item)
    return out


def _address_parts(addr) -> Address | None:
    """The graders'-format address, or a one-string address split the way
    the original prompt's answer is split."""
    from ..deterministic.summons import parse_address

    keys = ("street", "unit", "city", "state", "zip")
    if isinstance(addr, dict):
        parts = {k: _clean(addr.get(k)) for k in keys}
        if not any(parts.values()):
            return None
        street = " ".join(v for v in (parts["street"], parts["unit"]) if v)
        tail = " ".join(v for v in (parts["state"], parts["zip"]) if v)
        raw = ", ".join(v for v in (street, parts["city"], tail) if v)
        return Address(raw=raw, **parts)
    raw = _clean(addr) if isinstance(addr, str) else None
    if raw is None:
        return None
    parsed = parse_address(raw)
    if not parsed:
        return Address(raw=raw)
    return Address(raw=raw, **{k: parsed[k] or None for k in keys})


def list_fields_to_record(fields: dict) -> CourtRecord:
    """Map the graders'-format fields into the shared schema."""
    from ..deterministic.patterns import BUSINESS_MARKERS

    defendant_address = _address_parts(fields.get("defendant_address"))
    defendants = []
    for name in _clean_list(fields.get("defendants")):
        if is_placeholder(name):
            continue  # "JOHN DOE", or "JANE DOE" with a surname
        name = _strip_group_terms(name)[0]
        if len(name) >= 2:
            defendants.append(Party(
                name=name, role="defendant",
                is_business=bool(BUSINESS_MARKERS.search(name)),
                address=defendant_address,
            ))
    plaintiffs = [
        Party(name=name, role="plaintiff", is_business=bool(BUSINESS_MARKERS.search(name)))
        for name in _clean_list(fields.get("plaintiffs"))
    ]

    attorney = None
    lines = _clean_list(fields.get("attorneys"))
    office = fields.get("attorney_address")
    office = _clean(office) if isinstance(office, str) else None
    if lines or office:
        # one box holds attorneys and firm together, as the graders enter it;
        # the firm is the line that reads as an office, the rest are people
        firms = [n for n in lines if _FIRM_RE.search(n) or BUSINESS_MARKERS.search(n)]
        people = [n for n in lines if n not in firms]
        attorney = Attorney(
            names="; ".join(people) or None,
            firm=firms[0] if firms else None,
            address=Address(raw=office) if office else None,
        )

    return CourtRecord(
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
        prompt: str | None = None,
        prompt_format: str = "v1",
    ) -> None:
        # "v1" is Cheng Ren's benchmarked prompt; "lists" the graders'
        # format, which a model fine-tuned on their labels is run with
        if prompt_format not in ("v1", "lists"):
            raise ValueError(f"prompt_format must be 'v1' or 'lists', not {prompt_format!r}")
        self.prompt_format = prompt_format
        if prompt is None:
            prompt = LISTS_PROMPT if prompt_format == "lists" else VISION_PROMPT
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

        if self.prompt_format == "lists":
            return self._lists_extraction(raw, image_path)

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
        kept, dropped = drop_plaintiff_matches(
            [p.name for p in record.defendants], [p.name for p in record.plaintiffs])
        if dropped:
            flags.append("defendant_matches_plaintiff")
            record.defendants = [p for p in record.defendants if p.name in kept]

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

    def _lists_extraction(self, raw: str, image_path) -> Extraction:
        """The graders'-format answer as an extraction. There is no regex
        fallback for this shape: nested lists do not survive one, and a
        broken answer is better flagged than half-read."""
        flags: list[str] = []
        fields = parse_llm_json_best_effort(raw)
        if not isinstance(fields, dict):
            fields = {}
            flags.append("vision_json_unparsed")
        record = list_fields_to_record(fields)
        if not (record.plaintiffs or record.defendants or record.defendant_address
                or record.attorney):
            flags.append("vision_no_fields")
        if any(_strip_group_terms(n)[1] for n in _clean_list(fields.get("defendants"))):
            flags.append("vision_defendant_group_term")
        kept, dropped = drop_plaintiff_matches(
            [p.name for p in record.defendants], [p.name for p in record.plaintiffs])
        if dropped:
            flags.append("defendant_matches_plaintiff")
            record.defendants = [p for p in record.defendants if p.name in kept]

        evidence: dict[str, Evidence] = {}
        quotes = {
            "plaintiff": "; ".join(p.name for p in record.plaintiffs),
            "defendant": "; ".join(p.name for p in record.defendants),
            "address": record.defendant_address.raw if record.defendant_address else "",
            "attorneys": "; ".join(_clean_list(fields.get("attorneys"))),
            "law_firm_address": (record.attorney.address.raw
                                 if record.attorney and record.attorney.address else ""),
        }
        for key, value in quotes.items():
            if value:
                evidence[key] = Evidence(quote=value, grounded=False, page=self.page)

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


DEFAULT_OPENAI_HOST = "http://127.0.0.1:1234"


class OpenAIVisionBackend(LocalVisionBackend):
    """The vision lane through a local server that speaks the OpenAI chat
    API (`/v1/chat/completions`): LM Studio, or `mlx_vlm.server`. This is
    how a fine-tuned model is served, since Ollama does not load LoRA
    adapters. The host must be this machine; a model trained on court
    records can repeat names from them, so it is never served to a network.
    """

    name = "openai-vision"

    def __init__(self, model: str, host: str | None = None, **kwargs) -> None:
        host = (host or os.environ.get("EXTRACT_TEXT_OPENAI_HOST") or DEFAULT_OPENAI_HOST)
        if not re.match(r"^https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?/?$", host):
            raise ValueError(f"OpenAI-style host must be this machine, not {host}")
        super().__init__(model=model, host=host, **kwargs)

    @property
    def resolved_model(self) -> str:
        return self.model

    def _chat(self, b64_image: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "temperature": self.temperature,
            "seed": self.seed,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": self.prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
            ]}],
            # thinking off, as in the Ollama lane; LM Studio and mlx_vlm
            # read this from the chat template arguments
            "chat_template_kwargs": {"enable_thinking": False},
        }
        request = urllib.request.Request(
            f"{self.host}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"The model server returned an error: {exc}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"No OpenAI-style model server at {self.host}. Start one "
                "(LM Studio: lms server start), or set EXTRACT_TEXT_OPENAI_HOST."
            ) from exc
        choices = body.get("choices") or [{}]
        return (choices[0].get("message") or {}).get("content") or ""


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
