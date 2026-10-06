"""No core tactic proves a trap's failing line.

A trap entry in a course pack is a proof with a deliberate mistake: its
failing line is false.  The kernel's tactics label lines rather than decide
them, but a tactic that proves a false line is unsound all the same, and the
packs' traps are the mistakes students make (gcd(n, k) = 1, lcm(n, k) = nk).
This runs each trap with the kernel at scratch and asks every core tactic
about each line the engine refused.  tests/lecture_notes/kernel_shadow.py
runs the whole corpus the same way.
"""

import json
from pathlib import Path

import pytest

from aether import ProofChecker
from aether.kernel import core, review, tactics

ROOT = Path(__file__).resolve().parents[1]
TRAPS = [
    (f"{name}/{entry['id']}", entry["source"])
    for name in ("mth2008", "mth2010", "notation")
    for entry in json.loads((ROOT / "courses" / f"{name}.json").read_text())["entries"]
    if entry["kind"] == "trap"
]


@pytest.mark.parametrize("key, source", TRAPS, ids=[k for k, _ in TRAPS])
def test_no_tactic_proves_a_trap_line(key, source, monkeypatch):
    proved: list[tuple] = []
    original = review.Kernel._review

    def spy(self, result, obligation, kind, cited, allowed, ctx, before, after, witnessed=None):
        if result.status.value == "INVALID" and not result.message.startswith("Unknown or out-of-scope justification"):
            goal = obligation
            if witnessed is not None:
                body, var, value = witnessed
                goal = review.substitute_expr(body, var, value)
            elaborated = core.elaborate(goal, ctx)
            if elaborated is not None:
                name = tactics.weakest(elaborated.prop, review._core_premises(ctx, allowed, self._chain))
                if name is not None:
                    proved.append((result.line, name, str(goal)))
        return original(self, result, obligation, kind, cited, allowed, ctx, before, after, witnessed)

    monkeypatch.setattr(review.Kernel, "_review", spy)
    ProofChecker(kernel="scratch").check_source(source)
    assert not proved, f"{key}: a tactic proves a line the trap is built on: {proved}"
