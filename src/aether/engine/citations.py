"""Citing results by name: `by Theorem 1.1`, `By the triangle inequality, ...`.

The caller (the app) hands ``ProofChecker.check_source`` a *citation index*:
the names a student may cite, each pointing at the source that proves the
result -- an installed pack's entry (``@core/mth2008/theorem-1-1.aether``) or
a workspace file.  Names are matched after normalising (case, spacing,
dashes, a leading "the"), never fuzzily: an unknown name is reported with the
nearest names as suggestions, and a name that points at more than one result
is reported as ambiguous, with the candidates, rather than guessed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

_DASHES = re.compile(r"[‐-―−]")
_SPACE = re.compile(r"\s+")


def normalise(name: str) -> str:
    """The form names are compared in: lower case, plain dashes, one space, no leading "the"."""
    text = _DASHES.sub("-", name.strip().strip("\"'").lower())
    text = _SPACE.sub(" ", text)
    return text[4:] if text.startswith("the ") else text


@dataclass(frozen=True)
class Target:
    """One citable result: what to call it, and the source that proves it."""

    label: str
    key: str


def _targets(value: Any, cited: str) -> list[Target]:
    """A citation index value: a key, a list of keys, or [label, key] / {label, key} entries."""
    items = value if isinstance(value, (list, tuple)) else [value]
    out: list[Target] = []
    for item in items:
        if isinstance(item, str):
            out.append(Target(label=cited, key=item))
        elif isinstance(item, Mapping) and "key" in item:
            out.append(Target(label=str(item.get("label") or cited), key=str(item["key"])))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            out.append(Target(label=str(item[0]), key=str(item[1])))
    unique: dict[str, Target] = {}
    for target in out:
        unique.setdefault(target.key, target)
    return list(unique.values())


class CitationIndex:
    """The names a proof may cite, normalised, each with its target(s)."""

    def __init__(self, citations: Mapping[str, Any]):
        self._by_name: dict[str, list[Target]] = {}
        self._display: dict[str, str] = {}
        for name, value in citations.items():
            norm = normalise(name)
            if not norm:
                continue
            for target in _targets(value, name):
                bucket = self._by_name.setdefault(norm, [])
                if all(t.key != target.key for t in bucket):
                    bucket.append(target)
            self._display.setdefault(norm, name)

    def __bool__(self) -> bool:
        return bool(self._by_name)

    def lookup(self, cited: str) -> list[Target]:
        return self._by_name.get(normalise(cited), [])

    def suggestions(self, cited: str, limit: int = 3) -> list[str]:
        close = difflib.get_close_matches(normalise(cited), list(self._by_name), n=limit, cutoff=0.6)
        return [self._display[c] for c in close]


# What a citation of a result looks like, as opposed to a label (`h1`) or a
# method (`algebra`): a named kind of result, or a number like 2.18.
_RESULT_WORDS = re.compile(
    r"\b(theorem|lemma|corollary|proposition|example|definition|remark|exercise|inequality|rule|formula|identity|principle|property|test)\b|\d+\.\d+",
    re.IGNORECASE,
)


def looks_like_a_result(cited: str) -> bool:
    return bool(_RESULT_WORDS.search(cited))


def split_parts(justification: str) -> list[str]:
    """`Theorem 1.1 and h1, algebra` -> ["Theorem 1.1", "h1", "algebra"]."""
    raw = justification.strip().strip("[]")
    for prefix in ("by ", "using "):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):]
    return [p.strip().strip("\"'") for p in re.split(r"[,;]|\band\b", raw) if p.strip().strip("\"'")]


def unknown_message(cited: str, index: Optional[CitationIndex]) -> str:
    message = f"No result called '{cited}' is installed or in this workspace."
    if index:
        near = index.suggestions(cited)
        if near:
            message += " Did you mean " + " or ".join(f"'{n}'" for n in near) + "?"
    return message


def ambiguous_message(cited: str, targets: list[Target]) -> str:
    names = ", ".join(f"'{t.label}'" for t in targets)
    return f"'{cited}' could mean more than one result ({names}); cite it by its full name."
