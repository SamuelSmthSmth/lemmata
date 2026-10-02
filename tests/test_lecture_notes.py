"""The lecture-note corpora: MTH2008 Real Analysis and MTH2010 Algebra.

Every entry is a piece of the notes transcribed into Aether (or a blunder a
student could make next to it) together with the verdict it must produce.
``tests/lecture_notes/run_corpus.py`` runs the same entries with per-entry
wall-clock budgets and full reports, which is the better tool while working
on a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aether import ParseError, ProofChecker

sys.path.insert(0, str(Path(__file__).parent / "lecture_notes"))

from corpus_algebra import CORPUS as ALGEBRA  # noqa: E402
from corpus_notation_and_soundness import CORPUS as NOTATION  # noqa: E402
from corpus_real_analysis import CORPUS as REAL_ANALYSIS  # noqa: E402

ENTRIES = (
    [pytest.param(src, expect, id=f"MTH2008 {name}") for name, expect, src in REAL_ANALYSIS]
    + [pytest.param(src, expect, id=f"MTH2010 {name}") for name, expect, src in ALGEBRA]
    + [pytest.param(src, expect, id=f"notation {name}") for name, expect, src in NOTATION]
)


@pytest.fixture(scope="module")
def checker() -> ProofChecker:
    # Building the parser dominates a small check, so one checker serves all.
    return ProofChecker()


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


@pytest.mark.parametrize("source, expected", ENTRIES)
def test_lecture_note_entry(checker: ProofChecker, source: str, expected: str) -> None:
    got, report = _verdict(checker, source)
    assert got == expected, f"expected {expected}, got {got}\n{report}"
