#!/usr/bin/env python3
"""Watch Ollama's library for a vision model worth benchmarking.

MAINTENANCE.md schedules a model review and `.github/workflows/model-watch.yml`
opens the issue that carries its checklist. Both fire monthly. This script asks
the first question on that checklist cheaply enough to ask it daily:

    Has a vision-capable local model appeared that we have not seen before?

It reads the vision-tagged listing on ollama.com, compares it against the last
state it recorded, and names only what changed. Two kinds of change matter:

- a model family that was not there before, and
- a new parameter size on a family already known, which is the likelier
  signal, since a strong large model shipping a small variant is exactly the
  event that would move the pinned default.

Usage:

    python3 python/scripts/model_watch.py report     # print only if news; cached
    python3 python/scripts/model_watch.py list       # the full current listing
    python3 python/scripts/model_watch.py ack        # accept current as baseline

`report` is the mode meant for automation. It is deliberately quiet: it keeps
a timestamp and skips the network entirely if it has looked within
CACHE_HOURS, it prints nothing at all when nothing is new, and it exits 0 on
any failure so it can never become the reason a tool that calls it breaks.
Nothing it prints is a decision. A candidate still has to go through the
five-step review procedure in MAINTENANCE.md before it can displace the pin.

The size buckets below encode MAINTENANCE.md's eligibility rule, which is that
the package default must run in 16 GB of memory. Parameter count is a proxy
for that (a 14B model quantized to 4 bits lands near 9 GB), so the bucket is a
sorting hint for triage, not a substitute for checking the real download size.

State lives outside the repository, under XDG_CACHE_HOME or ~/.cache, so that
running this never shows up in `git status`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

LISTING_URL = "https://ollama.com/search?c=vision"
TIMEOUT_SECONDS = 12
CACHE_HOURS = 20

# Largest parameter count, in billions, that we would still call a plausible
# package default. See the module docstring for why this is a proxy.
PACKAGE_MAX_B = 14.0

# Above this, the model is not runnable on a normal workstation at 4-bit, so
# it is noise for this project even though it carries the vision tag.
WORKSTATION_MAX_B = 40.0

CAPABILITIES = ("vision", "tools", "thinking", "audio", "embedding")

USER_AGENT = "extract-text model_watch (https://github.com/; maintenance script)"


def state_path() -> Path:
    """Where the last-seen listing is recorded."""
    root = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(root) / "extract-text" / "model-watch.json"


def pinned_default() -> str:
    """The model tag the package currently ships, read from the source itself.

    Read rather than duplicated, so this script cannot drift from the pin it
    is supposed to be watching.
    """
    source = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "extract_text"
        / "ai"
        / "vision.py"
    )
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r'DEFAULT_VISION_MODEL\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "unknown"


def fetch_listing(url: str = LISTING_URL) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_listing(html: str) -> dict[str, dict]:
    """Pull one record per model family out of the listing page.

    The page is server-rendered HTML with no JSON behind it, so this strips
    tags from each list item and reads the visible text. That is brittle by
    nature: if the markup changes, this returns fewer models or none, and the
    caller treats an empty parse as "no news" rather than as "everything is
    new." Failing quiet is the right failure here.
    """
    models: dict[str, dict] = {}
    for chunk in html.split("<li")[1:]:
        href = re.search(r'href="/library/([a-z0-9._-]+)"', chunk)
        if not href:
            continue
        name = href.group(1)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chunk)).strip()

        caps = [c for c in CAPABILITIES if re.search(rf"\b{c}\b", text)]
        if "vision" not in caps:
            continue

        sizes = sorted(
            {s.lower() for s in re.findall(r"\b(\d+(?:\.\d+)?[bm])\b", text)},
            key=size_to_billions,
        )
        models[name] = {"sizes": sizes, "caps": caps}
    return models


def size_to_billions(size: str) -> float:
    """'27b' -> 27.0, '270m' -> 0.27. Returns inf on anything unparseable."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([bm])", size.lower())
    if not match:
        return float("inf")
    value = float(match.group(1))
    return value / 1000 if match.group(2) == "m" else value


def classify(sizes: list[str]) -> str:
    """Which review bucket a family falls into, by its smallest listed size."""
    if not sizes:
        return "unknown"
    smallest = min(size_to_billions(s) for s in sizes)
    if smallest <= PACKAGE_MAX_B:
        return "package"
    if smallest <= WORKSTATION_MAX_B:
        return "workstation"
    return "too-large"


def load_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(models: dict[str, dict]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models": models,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def hours_since_check(state: dict) -> float:
    stamp = state.get("checked")
    if not stamp:
        return float("inf")
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return float("inf")
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def diff(old: dict[str, dict], new: dict[str, dict]) -> tuple[list, list]:
    """New families, and new sizes on families we already knew about."""
    new_families = []
    new_sizes = []
    for name, record in sorted(new.items()):
        if name not in old:
            new_families.append((name, record))
            continue
        gained = [s for s in record["sizes"] if s not in old[name].get("sizes", [])]
        if gained:
            new_sizes.append((name, gained, record))
    return new_families, new_sizes


def describe(name: str, record: dict) -> str:
    sizes = ", ".join(record["sizes"]) or "size not listed"
    caps = "/".join(record["caps"])
    return f"{name} ({sizes}) [{caps}] -> {classify(record['sizes'])}"


def cmd_list(_args) -> int:
    models = parse_listing(fetch_listing())
    if not models:
        print("No vision models parsed. The listing markup may have changed.")
        return 1
    pin = pinned_default()
    print(f"Vision-capable models on ollama.com  (pinned default: {pin})")
    print(f"Package-eligible means smallest size <= {PACKAGE_MAX_B:g}B.\n")
    for group in ("package", "workstation", "too-large", "unknown"):
        rows = [
            (n, r) for n, r in sorted(models.items()) if classify(r["sizes"]) == group
        ]
        if not rows:
            continue
        print(f"-- {group} ({len(rows)})")
        for name, record in rows:
            sizes = ", ".join(record["sizes"]) or "size not listed"
            print(f"   {name:<22} {sizes:<28} {'/'.join(record['caps'])}")
        print()
    return 0


def cmd_ack(_args) -> int:
    models = parse_listing(fetch_listing())
    if not models:
        print("Nothing parsed; baseline not changed.")
        return 1
    save_state(models)
    print(f"Baseline recorded: {len(models)} vision models. {state_path()}")
    return 0


def cmd_report(args) -> int:
    """Quiet by design. Prints only when something is new."""
    state = load_state()
    if not args.force and hours_since_check(state) < CACHE_HOURS:
        return 0

    try:
        models = parse_listing(fetch_listing())
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0

    if not models:
        return 0

    known = state.get("models")
    if not known:
        save_state(models)
        return 0

    new_families, new_sizes = diff(known, models)
    save_state(models)

    # "unknown" means the card listed no size, not that the model is large.
    # glm-ocr is the live example. Surface those; only silence the ones we
    # positively know are too big to run here.
    candidates = [(n, r) for n, r in new_families if classify(r["sizes"]) != "too-large"]
    size_news = [
        (n, g, r) for n, g, r in new_sizes if classify(r["sizes"]) == "package"
    ]
    if not candidates and not size_news:
        return 0

    pin = pinned_default()
    print("extract-text model watch: new vision-capable local models since last check.")
    print(f"Pinned default is {pin}. Nothing here is a decision; MAINTENANCE.md")
    print("carries the five-step review a candidate has to pass to displace it.\n")

    for name, record in candidates:
        print(f"  NEW    {describe(name, record)}")
    for name, gained, record in size_news:
        sizes = ", ".join(gained)
        print(f"  SIZE   {name} added {sizes} (now: {', '.join(record['sizes'])})")

    print("\n  Review:  python3 python/scripts/model_watch.py list")
    print("  Silence: python3 python/scripts/model_watch.py ack")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    report = sub.add_parser("report", help="print only if something is new (cached)")
    report.add_argument("--force", action="store_true", help="ignore the cache window")
    report.set_defaults(func=cmd_report)

    sub.add_parser("list", help="print the full current listing").set_defaults(
        func=cmd_list
    )
    sub.add_parser("ack", help="record the current listing as the baseline").set_defaults(
        func=cmd_ack
    )

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
