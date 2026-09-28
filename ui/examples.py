"""Pre-built Aether proof examples surfaced in the UI.

Every example in this module has been verified against the engine so that the
``expected`` blurb is accurate -- see ``ui/README.md`` for the check that
guards this.

``expected`` is a human-readable hint only; the UI never trusts it, it always
renders the engine's real verdict.
"""

from __future__ import annotations

from typing import TypedDict


class Example(TypedDict):
    id: str
    name: str
    blurb: str
    expected: str
    source: str


EXAMPLES: list[Example] = [
    {
        "id": "even-square",
        "name": "Even square theorem",
        "blurb": "Witness extraction followed by an algebraic chain and an existential conclusion.",
        "expected": "VALID - every step checks out",
        "source": (
            'Theorem: "Even square theorem"\n'
            "Proof:\n"
            "    Given n : Int\n"
            "    Assume h1: Even(n)\n"
            "    Obtain k : Int such that n = 2 * k from h1\n"
            "    Step: n^2 = (2 * k)^2\n"
            "    Step: = 4 * k^2\n"
            "    Step: = 2 * (2 * k^2)\n"
            "    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]\n"
            "    Hence MultipleOf(n^2, 4)\n"
            "QED\n"
        ),
    },
    {
        "id": "odd-square",
        "name": "Odd square theorem",
        "blurb": "The odd-parity counterpart: expand (2k + 1)^2 and factor out the 2.",
        "expected": "VALID - every step checks out",
        "source": (
            'Theorem: "Odd square theorem"\n'
            "Proof:\n"
            "    Given n : Int\n"
            "    Assume h1: Odd(n)\n"
            "    Obtain k : Int such that n = 2 * k + 1 from h1\n"
            "    Step: n^2 = (2 * k + 1)^2\n"
            "    Step: = 4 * k^2 + 4 * k + 1\n"
            "    Step: = 2 * (2 * k^2 + 2 * k) + 1\n"
            "    Therefore Odd(n^2)\n"
            "QED\n"
        ),
    },
    {
        "id": "algebraic-blunder",
        "name": "Algebraic blunder",
        "blurb": "The classic '(x + 1)^2 = x^2 + 1' mistake. Note the concrete counterexample.",
        "expected": "INVALID - SymPy reports a counterexample",
        "source": "Let x : Real\nStep: (x + 1)^2 = x^2 + 1\n",
    },
    {
        "id": "unguarded-division",
        "name": "Unguarded division",
        "blurb": (
            "Cancelling (x - 2) without ruling out x = 2. Flip Strict Domain Checking "
            "to promote the warning to a hard failure."
        ),
        "expected": "WARNING (INVALID when strict domain checking is on)",
        "source": "Let x : Real\nStep: (x^2 - 4) / (x - 2) = x + 2\n",
    },
    {
        "id": "guarded-division",
        "name": "Guarded division",
        "blurb": "Same cancellation, but the hypothesis x != 2 discharges the domain obligation.",
        "expected": "VALID - no domain warnings",
        "source": (
            "Let x : Real\n"
            "Assume h1: x != 2\n"
            "Step: (x^2 - 4) / (x - 2) = x + 2\n"
        ),
    },
    {
        "id": "variable-capture",
        "name": "Implicit variable capture",
        "blurb": "Reusing 'n' as an existential witness shadows a variable already in scope.",
        "expected": "INVALID - scope guardrail rejects the capture",
        "source": (
            "Let n : Int\n"
            "Assume h1: Even(n)\n"
            "Obtain n : Int such that n = 2 * k from h1\n"
        ),
    },
    {
        "id": "false-deduction",
        "name": "False deduction",
        "blurb": "A plausible-looking inequality that Z3 refutes with a counterexample assignment.",
        "expected": "INVALID - Z3 refutes the inequality",
        "source": (
            "Let x : Real\n"
            "Assume h1: x > 2\n"
            "Step: x^2 > 4\n"
            "Therefore x^2 > x + 10\n"
        ),
    },
    {
        "id": "parse-error",
        "name": "Parse error",
        "blurb": "The proof body is not indented, so the indenter rejects it with a line and column.",
        "expected": "PARSE ERROR - reported with line and column",
        "source": (
            'Theorem: "Missing indentation"\n'
            "Proof:\n"
            "Given n : Int\n"
            "Step: n = n\n"
            "QED\n"
        ),
    },
    {
        "id": "mathematical-induction",
        "name": "Mathematical induction",
        "blurb": "Peano induction scheme: base case at n = 0 combined with an inductive step establishing divisibility of 3^n - 1 by 2.",
        "expected": "VALID - induction scheme verified",
        "source": (
            'Theorem: "Divisibility of 3^n - 1 by 2"\n'
            "Claim: forall n : Nat, MultipleOf(3^n - 1, 2)\n"
            "Proof:\n"
            "    Base case n = 0:\n"
            "        Step: 3^0 - 1 = 0\n"
            "        Step: = 2 * 0\n"
            "        Therefore exists m : Int, 3^0 - 1 = 2 * m [witness: 0]\n"
            "        Hence MultipleOf(3^0 - 1, 2)\n"
            "    Inductive step:\n"
            "        Given k : Nat\n"
            "        Assume ih: MultipleOf(3^k - 1, 2)\n"
            "        Obtain m : Int such that 3^k - 1 = 2 * m from ih\n"
            "        Step: 3^(k + 1) - 1 = 3 * 3^k - 1\n"
            "        Step: = 3 * (2 * m + 1) - 1\n"
            "        Step: = 2 * (3 * m + 1)\n"
            "        Therefore exists q : Int, 3^(k + 1) - 1 = 2 * q [witness: 3 * m + 1]\n"
            "        Hence MultipleOf(3^(k + 1) - 1, 2)\n"
            "    Therefore forall n : Nat, MultipleOf(3^n - 1, 2)\n"
            "QED\n"
        ),
    },
    {
        "id": "epsilon-delta-continuity",
        "name": "Epsilon-delta continuity",
        "blurb": "Classic Real Analysis: proving f(x) = 3x is continuous at x = 2 using delta = epsilon / 3 with absolute value bars.",
        "expected": "VALID - continuity established",
        "source": (
            'Theorem: "Continuity of 3x at x=2"\n'
            "Claim: forall \\epsilon : Real, \\epsilon > 0 => exists \\delta : Real, \\delta > 0 and (forall x : Real, |x - 2| < \\delta => |3 * x - 6| < \\epsilon)\n"
            "Proof:\n"
            "    Given \\epsilon : Real where \\epsilon > 0\n"
            "    Let \\delta = \\epsilon / 3\n"
            "    Step: \\delta > 0\n"
            "    Subproof:\n"
            "        Given x : Real\n"
            "        Assume |x - 2| < \\delta\n"
            "        Step: |3 * x - 6| = |3 * (x - 2)|\n"
            "        Step: = 3 * |x - 2|\n"
            "        Step: < 3 * \\delta\n"
            "        Step: = \\epsilon\n"
            "    Therefore exists \\delta : Real, \\delta > 0 and (forall x : Real, |x - 2| < \\delta => |3 * x - 6| < \\epsilon) [witness: \\epsilon / 3]\n"
            "QED\n"
        ),
    },
    {
        "id": "claim-goal-verification",
        "name": "QED goal verification",
        "blurb": "Demonstrating theorem claim verification at QED: ensuring the proven facts actually establish the promised goal.",
        "expected": "VALID - QED confirms claim is established",
        "source": (
            'Theorem: "Square of even is multiple of 4"\n'
            "Claim: forall n : Int, Even(n) => MultipleOf(n^2, 4)\n"
            "Proof:\n"
            "    Given n : Int\n"
            "    Assume hn: Even(n)\n"
            "    Obtain k : Int such that n = 2 * k from hn\n"
            "    Step: n^2 = (2 * k)^2\n"
            "    Step: = 4 * k^2\n"
            "    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]\n"
            "    Hence MultipleOf(n^2, 4)\n"
            "QED\n"
        ),
    },
    {
        "id": "custom-predicate-definitions",
        "name": "Custom predicate & lemma reuse",
        "blurb": "Define a custom mathematical predicate CongruentMod and verify lemma proofs.",
        "expected": "VALID - custom predicate expanded and verified",
        "source": (
            "Define CongruentMod(a, b, m) <=> Divides(m, a - b)\n\n"
            'Lemma: "Congruence is reflexive"\n'
            "Claim: forall x : Int, forall m : Int, m != 0 => CongruentMod(x, x, m)\n"
            "Proof:\n"
            "    Given x : Int\n"
            "    Given m : Int where m != 0\n"
            "    Step: x - x = m * 0\n"
            "    Therefore exists k : Int, x - x = m * k [witness: 0]\n"
            "    Hence Divides(m, x - x)\n"
            "    Hence CongruentMod(x, x, m)\n"
            "QED\n"
        ),
    },
    {
        "id": "complex-analysis-cauchy-riemann",
        "name": "Cauchy-Riemann equations",
        "blurb": "Complex analysis: verifying that u(x,y) = x^2 - y^2 and v(x,y) = 2xy satisfy the Cauchy-Riemann equations for f(z) = z^2.",
        "expected": "VALID - Cauchy-Riemann system satisfied",
        "source": (
            'Theorem: "Cauchy-Riemann equations for z^2"\n'
            "Proof:\n"
            "    Let x, y : Real\n"
            "    Let u = x^2 - y^2\n"
            "    Let v = 2 * x * y\n"
            "    Step: diff(u, x) = 2 * x\n"
            "    Step: diff(v, y) = 2 * x\n"
            "    Step: diff(u, y) = -2 * y\n"
            "    Step: diff(v, x) = 2 * y\n"
            "    Therefore CauchyRiemann(u, v)\n"
            "QED\n"
        ),
    },
    {
        "id": "linear-algebra-matrix-ops",
        "name": "Matrix arithmetic & orthogonality",
        "blurb": "Linear algebra: matrix multiplication, determinant, trace, transpose, and orthogonal vectors.",
        "expected": "VALID - matrix equations and vector orthogonality verified",
        "source": (
            'Theorem: "Matrix arithmetic and orthogonal vectors"\n'
            "Proof:\n"
            "    Let A = [[1, 2], [3, 4]]\n"
            "    Let B = [[2, 0], [1, 2]]\n"
            "    Step: A * B = [[4, 4], [10, 8]]\n"
            "    Step: det(A) = -2\n"
            "    Step: tr(A) = 5\n"
            "    Step: A^T = [[1, 3], [2, 4]]\n"
            "    Let u = [1, 2]\n"
            "    Let v = [-2, 1]\n"
            "    Step: dot(u, v) = 0\n"
            "    Therefore Orthogonal(u, v)\n"
            "QED\n"
        ),
    },
    {
        "id": "set-theory-identities",
        "name": "Set theory operations",
        "blurb": "Set theory primitives: set union, intersection, and empty set properties.",
        "expected": "VALID - set identities verified",
        "source": (
            'Theorem: "Set intersection with empty set"\n'
            "Proof:\n"
            "    Let S : Set\n"
            "    Step: S intersect \\emptyset = \\emptyset\n"
            "    Step: S union \\emptyset = S\n"
            "QED\n"
        ),
    },
    {
        "id": "calculus-and-ode",
        "name": "Calculus and ODEs",
        "blurb": "Symbolic integration, limits, and differential equation solutions.",
        "expected": "VALID - calculus and ODE verified",
        "source": (
            'Theorem: "Definite integral and harmonic oscillator ODE"\n'
            "Proof:\n"
            "    Step: \\int_{0}^{3} x^2 dx = 9\n"
            "    Step: \\lim_{x -> 0} (sin(x) / x) = 1\n"
            "    Let c1, c2, w, t : Real\n"
            "    Let y = c1 * cos(w * t) + c2 * sin(w * t)\n"
            "    Step: diff(y, t, 2) = -w^2 * y\n"
            "    Step: diff(y, t, 2) + w^2 * y = 0\n"
            "QED\n"
        ),
    },
    {
        "id": "group-theory-shoes-and-socks",
        "name": "Group theory inverse of product",
        "blurb": "Abstract algebra: shoes-and-socks theorem in an axiomatic group.",
        "expected": "VALID - group theorem verified",
        "source": (
            'Theorem: "Inverse of a product in a group"\n'
            "Proof:\n"
            "    Assume Group(G, op, e, inv)\n"
            "    Given a, b : Real\n"
            "    Step: op(op(a, b), op(inv(b), inv(a))) = e\n"
            "    Therefore inv(op(a, b)) = op(inv(b), inv(a))\n"
            "QED\n"
        ),
    },
    {
        "id": "modular-arithmetic-congruence",
        "name": "Modular arithmetic congruence",
        "blurb": "Congruence modulo m: if a = b (mod m) then a^2 = b^2 (mod m).",
        "expected": "VALID - congruence verified",
        "source": (
            'Theorem: "Square of congruent integers"\n'
            "Proof:\n"
            "    Given a, b, m : Int\n"
            "    Assume h1: a = b (mod m)\n"
            "    Obtain k : Int such that a - b = m * k from h1\n"
            "    Step: a = b + m * k\n"
            "    Step: a^2 = b^2 (mod m)\n"
            "    Therefore Congruent(a^2, b^2, m)\n"
            "QED\n"
        ),
    },
    {
        "id": "step-justifications-and-lemmas",
        "name": "Step justifications and lemma reuse",
        "blurb": "Explicit step citations [by algebra], hypothesis labels [by ha], and lemma reuse [by EvenSquare].",
        "expected": "VALID - verified with explicit step justifications",
        "source": (
            'Lemma: "EvenSquare"\n'
            "Claim: forall n : Int, Even(n) => Even(n^2)\n"
            "\n"
            'Theorem: "EvenFourthPower"\n'
            "Proof:\n"
            "    Given a : Int\n"
            "    Assume ha: Even(a)\n"
            "    Therefore Even(a^2) [by EvenSquare]\n"
            "    Let b = a^2\n"
            "    Therefore Even(b)\n"
            "    Therefore Even(b^2) [by EvenSquare]\n"
            "    Step: a^4 = b^2 [by algebra]\n"
            "    Hence Even(a^4) [by ha]\n"
            "QED\n"
        ),
    },
]


EXAMPLES_BY_ID: dict[str, Example] = {ex["id"]: ex for ex in EXAMPLES}
