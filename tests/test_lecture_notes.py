"""The course packs in ``courses/``: MTH2008 Real Analysis, MTH2010 Algebra, notation.

Every entry is a piece of the notes transcribed into Aether (or a blunder a
student could make next to it, a "trap") together with the verdict it must
produce.  The same files feed the UI's Library, so a pack can never advertise
a proof the engine does not check.  ``tests/lecture_notes/run_corpus.py`` runs
the same entries with per-entry wall-clock budgets and full reports, which is
the better tool while working on a failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aether import ParseError, ProofChecker
from aether.packs import entry_level, kernel_for, load_packs, pack_label

COURSES = Path(__file__).resolve().parent.parent / "courses"


def _entries():
    """Every course-pack entry, as a pytest param named after its pack and reference."""
    for pack in load_packs(COURSES):
        for entry in pack["entries"]:
            level = entry_level(pack, entry)
            yield pytest.param(
                entry["source"],
                entry["expected"],
                level,
                id=f"{pack_label(pack)} {entry['ref']} {entry['title']}" + ("" if level == "off" else f" @{level}"),
            )


ENTRIES = list(_entries())


def test_every_trap_explains_itself() -> None:
    """Spot-the-error shows the explanation after the student finds the line."""
    for pack in load_packs(COURSES):
        chapters = {c["id"] for c in pack["chapters"]}
        for entry in pack["entries"]:
            assert entry["chapter"] in chapters, entry["id"]
            if entry["kind"] == "trap":
                assert entry["expected"] == "INVALID" and entry.get("explanation"), entry["id"]


_CHECKERS: dict[str, ProofChecker] = {}


def checker_at(level: str) -> ProofChecker:
    # Building the parser dominates a small check, so one checker per level serves all.
    if level not in _CHECKERS:
        _CHECKERS[level] = ProofChecker(kernel=kernel_for(level))
    return _CHECKERS[level]


def _verdict(checker: ProofChecker, source: str) -> tuple[str, str]:
    try:
        reports = checker.check_source(source)
    except ParseError as err:
        return "PARSE", str(err)
    text = "\n".join(r.format_report() for r in reports)
    if not all(r.is_valid for r in reports):
        return "INVALID", text
    if any(r.has_warnings for r in reports):
        return "WARN", text
    return "VALID", text


@pytest.mark.parametrize("source, expected, level", ENTRIES)
def test_lecture_note_entry(source: str, expected: str, level: str) -> None:
    got, report = _verdict(checker_at(level), source)
    assert got == expected, f"expected {expected}, got {got}\n{report}"
