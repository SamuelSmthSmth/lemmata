"""What each line used, and what the engine computed: the dependency audit and the trace.

``ProofChecker(dependencies=True)`` names the premises each line that checked
was proved from (``StepResult.premises``); ``trace=True`` lists the backend
calls made checking it (``StepResult.trace``).  Neither may change a verdict,
and with neither on, nothing is computed.
"""

import pytest

from aether import ProofChecker
from test_citations import CITATIONS, LEMMA, SOURCES

EVEN_SQUARE = """\
Theorem: "Even square theorem"
Proof:
    Given n : Int
    Assume h1: Even(n)
    Obtain k : Int such that n = 2 * k from h1
    Step: n^2 = (2 * k)^2
    Step: = 4 * k^2
    Step: = 2 * (2 * k^2)
    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]
    Hence MultipleOf(n^2, 4)
QED
"""

SCRATCH = """\
Let x, y : Real
Assume hx: x > 2
Assume hy: y > 0
Step: x^2 > 4
Step: x^2 + y > 4
Step: (x^2 - 4) / (x - 2) = x + 2
Step: > 4
Step: x^3 = x
"""

CASES = """\
Theorem: "n^2 + n is even"
Claim: forall n : Int, Even(n^2 + n)
Proof:
    Given n : Int
    Case Even(n):
        Obtain k : Int such that n = 2 * k
        Step: n^2 + n = 4*k^2 + 2*k
        Step: = 2 * (2*k^2 + k)
        Therefore Even(n^2 + n)
    Case Odd(n):
        Obtain k : Int such that n = 2 * k + 1
        Step: n^2 + n = 4*k^2 + 6*k + 2
        Step: = 2 * (2*k^2 + 3*k + 1)
        Therefore Even(n^2 + n)
    Therefore Even(n^2 + n)
QED
"""


def results(source: str, **options):
    reports = ProofChecker(dependencies=True, **options).check_source(source, sources=SOURCES, citations=CITATIONS)
    return {r.line: r for rep in reports for r in rep.all_results}


def used(result) -> list[tuple]:
    return [(p["kind"], p["line"], p["label"]) for p in result.premises]


@pytest.fixture(scope="module")
def even_square():
    return results(EVEN_SQUARE)


@pytest.fixture(scope="module")
def scratch():
    return results(SCRATCH)


def test_introductions_use_nothing(even_square):
    for line in (3, 4):
        assert even_square[line].premises == [] and even_square[line].premises_complete


def test_obtain_from_names_its_source(even_square):
    assert used(even_square[5]) == [("hypothesis", 4, "h1")]


def test_a_substitution_names_the_fact_substituted(even_square):
    # n^2 = (2k)^2 holds because n = 2k, which line 5 established.
    assert used(even_square[6]) == [("hypothesis", 5, None)]
    assert even_square[6].premises[0]["fact"] == "n = (2 * k)"


def test_a_chain_link_continues_the_line_before(even_square):
    assert used(even_square[7]) == [("chain", 6, None)]
    assert used(even_square[9]) == [("chain", 8, None)]


def test_a_conclusion_names_the_fact_it_restates(even_square):
    assert used(even_square[10]) == [("hypothesis", 9, None)]


def test_z3_names_its_unsat_core(scratch):
    assert used(scratch[4]) == [("hypothesis", 2, "hx")]
    # Line 4 is both the chain so far and a fact; the canonical core keeps the line before.
    assert used(scratch[5]) == [("chain", 4, None), ("hypothesis", 3, "hy")]
    assert used(scratch[7]) == [("chain", 6, None), ("hypothesis", 2, "hx")]


def test_an_identity_uses_nothing(scratch):
    # The domain side condition (x != 2, from hx) is not part of the argument.
    assert scratch[6].premises == [] and scratch[6].premises_complete


def test_a_line_that_fails_has_no_premises(scratch):
    assert scratch[8].status.value == "INVALID"
    assert scratch[8].premises == [] and not scratch[8].premises_complete


def test_since_names_what_its_premise_used():
    r = results("Let x : Real\nAssume h1: x > 3\nSince x > 2, x^2 > 4\n")
    assert used(r[3]) == [("hypothesis", 2, "h1")]
    r = results("Let x : Real\nAssume h1: x > 3\nSince h1, x > 1\n")
    assert used(r[3]) == [("hypothesis", 2, "h1")]


def test_case_blocks():
    r = results(CASES)
    # The case condition is the block's: Even(n) is line 5.
    assert used(r[6]) == [("hypothesis", 5, None)]
    assert used(r[11]) == [("hypothesis", 10, None)]
    qed = r[2]
    assert qed.premises_complete and used(qed) == [("hypothesis", 15, None)]


def test_a_block_uses_what_its_lines_use_from_outside_it():
    r = results(
        "Let x, y : Real\nAssume hy: y > 0\nSubproof:\n    Assume h: x > 2\n    Step: x^2 + y > 4\n"
        "Therefore x > 2 => x^2 + y > 4\n"
    )
    assert used(r[5]) == [("hypothesis", 2, "hy"), ("hypothesis", 4, "h")]
    # The block's own assumption is inside it; hy is what it needed from outside.
    assert used(r[3]) == [("hypothesis", 2, "hy")]
    assert used(r[6]) == [("hypothesis", 3, None)]


def test_induction_names_its_base_case_and_step():
    r = results(LEMMA)
    qed = r[2]
    assert qed.backend == "QED" and qed.premises_complete
    assert used(qed) == [("hypothesis", 4, None), ("hypothesis", 10, None)]


def test_an_earlier_theorem_is_a_result_by_name():
    r = results(LEMMA + "\nLet j : Nat\nTherefore MultipleOf(3^j - 1, 2)\n")
    last = r[max(line for line in r if line)]
    assert last.status.value == "VALID"
    assert used(last) == [("result", None, "Divisibility of 3^n - 1 by 2")]


def test_a_citation_is_named_as_such():
    r = results("Let j : Nat\nTherefore MultipleOf(3^j - 1, 2) by Lemma A\n")
    (premise,) = r[2].premises
    assert premise["kind"] == "citation"
    assert premise["key"] == "@me/lemmas/divisibility.aether"
    assert premise["label"] == "Lemma A · Divisibility of 3^n - 1 by 2"


def test_off_by_default():
    for r in ProofChecker().check_source(SCRATCH)[0].results:
        assert r.premises == [] and not r.premises_complete and r.trace == []


@pytest.mark.parametrize("kernel", [None, "course"])
@pytest.mark.parametrize("source", [EVEN_SQUARE, SCRATCH, CASES, LEMMA])
def test_verdicts_are_unchanged(source, kernel):
    def lines(checker):
        return [
            (r.line, r.status, r.backend, r.message, r.counterexample)
            for rep in checker.check_source(source)
            for r in rep.all_results
        ]

    assert lines(ProofChecker(kernel=kernel)) == lines(ProofChecker(kernel=kernel, dependencies=True, trace=True))


def test_under_the_kernel_a_cited_line_uses_what_it_cites():
    r = results("Let x : Real\nAssume h1: x > 5\nAssume h2: x > 4\nStep: x > 3 [using h2]\n", kernel="course")
    assert used(r[4]) == [("hypothesis", 3, "h2")]


def test_to_dict_carries_both():
    r = results(SCRATCH, trace=True)[5].to_dict()
    assert r["premises_complete"] is True
    assert {p["label"] for p in r["premises"]} == {"hy", None}
    assert r["trace"] and {"backend", "call", "query", "result", "ms", "depth"} <= set(r["trace"][0])


# ---------------------------------------------------------------------------
# The trace
# ---------------------------------------------------------------------------


def trace(source: str, line: int, **options):
    reports = ProofChecker(trace=True, **options).check_source(source)
    return next(r for rep in reports for r in rep.all_results if r.line == line).trace


def test_an_inequality_is_asked_of_z3():
    events = trace(SCRATCH, 4)
    asked = [e for e in events if e["call"] == "entails"]
    assert asked and asked[0]["query"] == "(x ^ 2) > 4" and asked[0]["result"] == "holds"
    checks = [e for e in events if (e["backend"], e["call"]) == ("Z3", "check")]
    assert checks and checks[-1]["result"] == "unsat" and checks[-1]["depth"] > asked[0]["depth"]


def test_an_identity_is_asked_of_sympy_and_its_side_condition_of_z3():
    events = trace(SCRATCH, 6)
    calls = [(e["backend"], e["call"], e["result"]) for e in events if e["depth"] == 0]
    assert ("Z3", "domain", "holds") in calls
    assert ("SymPy", "identity", "holds") in calls


def test_a_failure_shows_each_attempt():
    events = trace(SCRATCH, 8)
    top = [(e["backend"], e["call"], e["result"]) for e in events if e["depth"] == 0]
    assert top[:2] == [("SymPy", "identity", "fails"), ("Z3", "entails", "fails")]
    assert any(e["call"] == "check" and e["result"] == "sat" for e in events)


def test_events_are_in_the_order_their_calls_started():
    events = trace(SCRATCH, 8)
    depths = [e["depth"] for e in events]
    assert depths[0] == 0 and all(b <= a + 1 for a, b in zip(depths, depths[1:]))
    assert all(isinstance(e["ms"], float) and e["ms"] >= 0 for e in events)


def test_a_check_that_does_not_apply_is_left_out():
    # Every entailment first asks whether it is an induction; for x^2 > 4 it is not.
    assert not any(e["call"] == "induction" for e in trace(SCRATCH, 4))
    assert any(e["call"] == "induction" and e["result"] == "holds" for e in trace(LEMMA, 2))


def test_the_dependency_audit_is_traced_too():
    reports = ProofChecker(trace=True, dependencies=True).check_source(SCRATCH)
    events = reports[0].results[4].trace
    assert any(e["call"] == "core" and e["result"] == "2 used" for e in events)


def test_imports_are_not_traced():
    reports = ProofChecker(trace=True).check_source(
        'import "lemmas"\nLet x : Real\n', sources={"lemmas.aether": LEMMA}
    )
    assert reports[0].results[0].trace == []
