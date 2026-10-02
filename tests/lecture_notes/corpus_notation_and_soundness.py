"""The notes' own notation, and the traps the new features must not fall into.

Two halves:

* proofs written the way the typeset notes write them -- Unicode symbols,
  bounded quantifiers (``forall ε > 0, exists δ > 0, ...``), ``∞``, ``n!``,
  ``a⁻¹`` -- which must check exactly as their ASCII spellings do;
* deliberate blunders around every feature added for the notes (infinity,
  range facts, case splits SymPy leaves open, gcd, group words, carriers).
  Each would be *accepted* by a careless implementation.
"""

CORPUS: list[tuple[str, str, str]] = [
    # ------------------------------------------------------------------
    # The notes' notation
    # ------------------------------------------------------------------
    ("Theorem 1.1 in Unicode", "VALID", """\
Theorem: "Triangle inequality"
Claim: ∀ a ∈ ℝ, ∀ b ∈ ℝ, |a + b| ≤ |a| + |b|
Proof:
    Let a, b : ℝ
    Step: |a + b| ≤ |a| + |b|
QED
"""),
    ("Definition 2.6 shape: forall eps > 0, exists delta > 0", "VALID", """\
Theorem: "lim 3x = 6 at x = 2, epsilon-delta"
Claim: ∀ ε > 0, ∃ δ > 0, ∀ x ∈ ℝ, |x − 2| < δ ⇒ |3·x − 6| < ε
Proof:
    Given ε : ℝ where ε > 0
    Let δ = ε / 3
    Subproof:
        Given x : ℝ
        Assume |x − 2| < δ
        Step: |3·x − 6| = 3·|x − 2|
        Step: < 3·δ
        Step: = ε
    Therefore ∃ δ > 0, ∀ x ∈ ℝ, |x − 2| < δ ⇒ |3·x − 6| < ε [witness: ε / 3]
QED
"""),
    ("Example 2.20 with ∞ and \\infty", "VALID", """\
Step: lim(1/x, x, 0, "+") = ∞
Step: \\lim_{x \\to 0^-} 1/x = -\\infty
Step: lim(x², x, -∞) = ∞
"""),
    ("Example 3.22 geometric series in Unicode", "VALID", """\
Let r ∈ ℝ
Assume |r| < 1
Step: \\sum_{k=0}^{\\infty} r^k = 1/(1 − r)
"""),
    ("|S_n| = n! written with the postfix bang", "VALID", """\
Let n : ℕ
Assume n ≥ 1
Step: n! = n·(n − 1)!
Step: 5! = 120
"""),
    ("Remark 4 with superscript inverses", "VALID", """\
Assume Group(G, op, e, inv)
Given a, b : G
Step: (a·b)⁻¹ = b⁻¹·a⁻¹
Step: a·a⁻¹ = e
Step: a²·a³ = a⁵
Step: a⁰ = e
"""),
    ("Elements declared with ∈", "VALID", """\
Assume Group(G, op, e, inv)
Let g ∈ G
Step: g·e = g
Step: e·g = g
"""),
    ("Bounded quantifier over a group carrier", "VALID", """\
Theorem: "Every element has an inverse"
Claim: Group(G, op, e, inv) => ∀ a ∈ G, ∃ b ∈ G, op(a, b) = e
Proof:
    Assume Group(G, op, e, inv)
    Given a : G
    Therefore exists b : G, op(a, b) = e [witness: inv(a)]
QED
"""),
    ("Logical connectives in Unicode", "VALID", """\
Let x : ℝ
Assume h: x > 2 ∧ x < 5
Therefore x > 1 ∨ x < -1
Therefore ¬(x = 0)
Therefore x ≠ 0
"""),
    ("Greek letters typed directly", "VALID", """\
Let α, β : ℝ
Assume α < β
Step: (α + β)/2 < β
Step: α < (α + β)/2
"""),
    ("sinh, arctan, floor and binomial", "VALID", """\
Let x : ℝ
Step: cosh(x)^2 - sinh(x)^2 = 1
Step: tan(atan(x)) = x
Step: floor(7/2) = 3
Step: binomial(5, 2) = 10
"""),
    # ------------------------------------------------------------------
    # Soundness traps
    # ------------------------------------------------------------------
    ("trap: oo is not a real number", "INVALID", """\
Let a : Real
Step: oo - 1 < oo - 2
"""),
    ("trap: -oo is below every real, not above", "INVALID", """\
Let a : Real
Step: -oo > a
"""),
    ("trap: oo * 0 is indeterminate", "INVALID", """\
Step: oo * 0 = 0
"""),
    ("trap: a declared oo is an ordinary variable", "INVALID", """\
Let oo : Real
Step: oo > 5
"""),
    ("trap: limits at infinity have one side only", "INVALID", """\
Step: lim(1/x, x, oo, "+") = 0
"""),
    ("trap: sin(1/x) has no limit at 0", "INVALID", """\
Step: lim(sin(1/x), x, 0) = 0
"""),
    ("trap: geometric series needs |r| < 1", "INVALID", """\
Let r : Real
Step: sum(k, 0, oo, r^k) = 1/(1 - r)
"""),
    ("trap: partial geometric sum needs r != 1", "INVALID", """\
Let r : Real
Let n : Nat
Step: sum(k, 0, n, r^k) = (1 - r^(n + 1))/(1 - r)
"""),
    ("trap: rho^n -> 0 needs rho < 1", "INVALID", """\
Let \\rho : Real
Assume \\rho > 1
Step: lim(\\rho^n, n, oo) = 0
"""),
    ("trap: |sin| <= 1 does not give |sin| <= 1/2", "INVALID", """\
Let x : Real
Step: |sin(x)| <= 1/2
"""),
    ("trap: exp > 0 does not give exp > 1", "INVALID", """\
Let x : Real
Step: exp(x) > 1
"""),
    ("trap: log is not bounded below by its argument", "INVALID", """\
Let x : Real
Assume x > 0
Step: log(x) >= x - 1
"""),
    ("trap: symbolic gcd is not 1", "INVALID", """\
Let n, k : Int
Step: gcd(n, k) = 1
"""),
    ("trap: symbolic lcm is not the product", "INVALID", """\
Let n, k : Int
Step: lcm(n, k) = n * k
"""),
    ("trap: wrong factorial", "INVALID", """\
Step: 4! = 12
"""),
    ("trap: Congruent mod 0 is equality", "INVALID", """\
Let a : Int
Step: a + 1 = a (mod 0)
"""),
    ("trap: congruence does not survive division", "INVALID", """\
Let i, k, n : Int
Assume h: 2 * i = 2 * k (mod n)
Therefore i = k (mod n)
"""),
    ("trap: (ab)^-1 is not a^-1 b^-1 in a group", "INVALID", """\
Assume Group(G, op, e, inv)
Given a, b : G
Step: (a * b)^-1 = a^-1 * b^-1
"""),
    ("but (ab)^-1 = a^-1 b^-1 in an abelian group", "VALID", """\
Assume AbelianGroup(G, op, e, inv)
Given a, b : G
Step: (a * b)^-1 = a^-1 * b^-1
"""),
    ("trap: a^2 b^2 is not (ab)^2 in a group", "INVALID", """\
Assume Group(G, op, e, inv)
Given a, b : G
Step: a^2 * b^2 = (a * b)^2
"""),
    ("trap: real variables still commute under *", "VALID", """\
Assume Group(G, op, e, inv)
Let x, y : Real
Step: x * y = y * x
"""),
    ("a hypothesis can make two words equal", "VALID", """\
Assume Group(G, op, e, inv)
Given a, b : G
Assume h: op(a, b) = op(b, a)
Step: op(op(a, b), inv(a)) = b
"""),
    ("trap: an undeclared type is still refused", "INVALID", """\
Given a : Widget
"""),
    ("trap: bounded exists keeps its guard", "INVALID", """\
Let x : Real
Therefore exists d > 0, d < 0
"""),
    ("trap: bounded forall keeps its guard", "INVALID", """\
Therefore forall x > 0, x > 1
"""),
    ("trap: a sum that divides by zero is undefined", "INVALID", """\
Step: sum(k, -1, 1, 1/k) = 0
"""),
]
