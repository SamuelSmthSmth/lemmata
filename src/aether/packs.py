"""Course packs: the format, and the one loader and validator for it.

A pack is a JSON document of proofs keyed to a module's (or a topic's) own
numbering, each entry carrying the verdict it must produce.  The same files
feed the test suite (``tests/test_lecture_notes.py``), the web app's Library,
and, later, a pack registry's CI, so this module is the single authority on
what a valid pack is.  ``courses/pack.schema.json`` is a JSON Schema copy for
authors working outside Python; a test keeps the two in step.

Format 1::

    {
      "format": 1,
      "name": "core/mth2008",            scope/slug, lower case, stable
      "version": "1.0.0",                semver
      "title": "Real Analysis",
      "courses": ["MTH2008"],            optional: a pack may be a topic
      "summary": "...",
      "authors": ["..."],
      "license": "CC-BY-SA-4.0",
      "engine": ">=0.1",                 the engine versions the verdicts hold for
      "depends": {"core/notation": "^1"},
      "chapters": [{"id": "1", "title": "..."}],
      "entries": [{"id", "chapter", "ref", "title", "kind", "expected",
                   "source", "explanation"?, "blurb"?}]
    }

This is a library module, not part of the stable public API listed in
AGENTS.md.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PACK_FORMAT = 1

KINDS = ("proof", "trap")
VERDICTS = ("VALID", "WARN", "INVALID", "PARSE ERROR")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

REQUIRED = ("format", "name", "version", "title", "summary", "license", "chapters", "entries")
OPTIONAL = ("courses", "authors", "engine", "depends")
ENTRY_REQUIRED = ("id", "chapter", "ref", "title", "kind", "expected", "source")
ENTRY_OPTIONAL = ("explanation", "blurb")


class PackError(ValueError):
    """A pack that does not meet the format; ``errors`` lists every problem."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _is_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_pack(data: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Check *data* against format 1.

    Returns ``(pack, [])`` with optional fields filled in, or ``(None, errors)``
    naming every problem found (not just the first), each prefixed with where
    it is, e.g. ``entries[3].kind``.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, ["a pack is a JSON object"]

    for key in REQUIRED:
        if key not in data:
            errors.append(f"{key}: missing")
    unknown = set(data) - set(REQUIRED) - set(OPTIONAL)
    errors.extend(f"{key}: not a pack field" for key in sorted(unknown))

    if "format" in data and data["format"] != PACK_FORMAT:
        errors.append(f"format: expected {PACK_FORMAT}, got {data['format']!r}")
    if "name" in data and not (isinstance(data["name"], str) and NAME_RE.match(data["name"])):
        errors.append("name: must be scope/slug in lower case, e.g. core/mth2008")
    if "version" in data and not (isinstance(data["version"], str) and SEMVER_RE.match(data["version"])):
        errors.append("version: must be semver, e.g. 1.0.0")
    for key in ("title", "summary", "license"):
        if key in data and not _is_str(data[key]):
            errors.append(f"{key}: must be a non-empty string")
    for key in ("courses", "authors"):
        if key in data and not (isinstance(data[key], list) and all(_is_str(v) for v in data[key])):
            errors.append(f"{key}: must be a list of strings")
    if "engine" in data and not _is_str(data["engine"]):
        errors.append("engine: must be a version range string, e.g. >=0.1")
    if "depends" in data and not (
        isinstance(data["depends"], dict)
        and all(isinstance(k, str) and NAME_RE.match(k) and _is_str(v) for k, v in data["depends"].items())
    ):
        errors.append("depends: must map pack names to version ranges")

    chapter_ids: set[str] = set()
    chapters = data.get("chapters")
    if "chapters" in data:
        if not isinstance(chapters, list):
            errors.append("chapters: must be a list")
        else:
            for i, chapter in enumerate(chapters):
                if not (isinstance(chapter, dict) and _is_str(chapter.get("id")) and _is_str(chapter.get("title"))):
                    errors.append(f"chapters[{i}]: needs an id and a title")
                    continue
                if chapter["id"] in chapter_ids:
                    errors.append(f"chapters[{i}].id: {chapter['id']!r} is used twice")
                chapter_ids.add(chapter["id"])

    entries = data.get("entries")
    if "entries" in data:
        if not isinstance(entries, list) or not entries:
            errors.append("entries: must be a non-empty list")
        else:
            seen: set[str] = set()
            for i, entry in enumerate(entries):
                where = f"entries[{i}]"
                if not isinstance(entry, dict):
                    errors.append(f"{where}: must be an object")
                    continue
                for key in ENTRY_REQUIRED:
                    if key not in entry:
                        errors.append(f"{where}.{key}: missing")
                for key in sorted(set(entry) - set(ENTRY_REQUIRED) - set(ENTRY_OPTIONAL)):
                    errors.append(f"{where}.{key}: not an entry field")
                entry_id = entry.get("id")
                if "id" in entry:
                    if not (isinstance(entry_id, str) and SLUG_RE.match(entry_id)):
                        errors.append(f"{where}.id: must be a lower-case slug")
                    elif entry_id in seen:
                        errors.append(f"{where}.id: {entry_id!r} is used twice")
                    else:
                        seen.add(entry_id)
                for key in ("ref", "title", "source"):
                    if key in entry and not _is_str(entry[key]):
                        errors.append(f"{where}.{key}: must be a non-empty string")
                if "chapter" in entry and entry["chapter"] not in chapter_ids:
                    errors.append(f"{where}.chapter: {entry['chapter']!r} is not one of the pack's chapters")
                if "kind" in entry and entry["kind"] not in KINDS:
                    errors.append(f"{where}.kind: must be one of {', '.join(KINDS)}")
                if "expected" in entry and entry["expected"] not in VERDICTS:
                    errors.append(f"{where}.expected: must be one of {', '.join(VERDICTS)}")
                if entry.get("kind") == "trap":
                    if entry.get("expected") != "INVALID":
                        errors.append(f"{where}.expected: a trap must be INVALID")
                    if not _is_str(entry.get("explanation")):
                        errors.append(f"{where}.explanation: a trap must explain itself")
                for key in ENTRY_OPTIONAL:
                    if key in entry and not _is_str(entry[key]):
                        errors.append(f"{where}.{key}: must be a non-empty string")

    if errors:
        return None, errors
    pack = dict(data)
    pack.setdefault("courses", [])
    pack.setdefault("authors", [])
    pack.setdefault("engine", ">=0.1")
    pack.setdefault("depends", {})
    return pack, []


def load_pack(path: str | Path) -> dict[str, Any]:
    """Read and validate one pack file; raise :class:`PackError` if it is not one."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as err:
        raise PackError([f"not JSON: {err}"]) from err
    pack, errors = validate_pack(data)
    if pack is None:
        raise PackError(errors)
    return pack


def load_packs(directory: str | Path) -> list[dict[str, Any]]:
    """Every ``*.json`` pack in *directory* (schema files excluded), sorted by name."""
    packs = [
        load_pack(path)
        for path in sorted(Path(directory).glob("*.json"))
        if not path.name.endswith(".schema.json")
    ]
    return sorted(packs, key=lambda p: p["name"])


def pack_label(pack: dict[str, Any]) -> str:
    """The short name a pack goes by: its first course code, or its title."""
    courses = pack.get("courses") or []
    return courses[0] if courses else pack["title"]
