"""A comment may stand on its own line anywhere.

A line holding only a comment used to be two newlines in a row to the
parser: in a proof block that was a parse error, and between `Theorem:` and
`Proof:` it emptied the theorem.  Now it belongs to the newline before it.
"""

import pytest

from aether import ProofChecker

PROOF = 'Theorem: "T"\nProof:\n    Let n ∈ ℤ\n    Step: n = n\nQED\n'


@pytest.mark.parametrize(
    "source",
    [
        "# above\n" + PROOF,
        PROOF.replace("Proof:\n", "# between\nProof:\n"),
        PROOF.replace("Proof:\n", "Proof:\n    # first in the block\n"),
        PROOF.replace("    Step:", "    # in the middle\n    Step:"),
        PROOF.replace("    Step:", "    -- a dash comment\n    Step:"),
        PROOF.replace("    Step:", "\n    # after a blank line\n\n    Step:"),
        PROOF + "# below",
    ],
)
def test_a_comment_line_anywhere_changes_nothing(source):
    results = [r.status.value for rep in ProofChecker().check_source(source) for r in rep.results]
    assert results == ["VALID", "VALID"]
