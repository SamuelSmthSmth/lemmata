"""MTH2008 Real Analysis, transcribed into Aether.

Each entry is ``(name, expected_verdict, source)``.  Names carry the
definition/theorem/example number from the notes so a failure points straight
back at the page.  ``VALID`` entries are the mathematics as the notes state
it; ``INVALID`` entries are deliberate blunders a student could make next to
them, so the suite guards soundness as well as coverage.
"""

CORPUS: list[tuple[str, str, str]] = [
    # ------------------------------------------------------------------
    # 1.1 The real number system
    # ------------------------------------------------------------------
    ("1.1 field manipulations", "VALID", """\
Let a, b, c, d : Real
Step: (a + b)^2 = a^2 + 2*a*b + b^2
Step: (3*a + 2*b)*(4*c + 2*d) = 12*a*c + 6*a*d + 8*b*c + 4*b*d
Step: -a = (-1)*a
Step: a*(-b) = (-a)*b
Assume hb: b != 0
Assume hd: d != 0
Step: a/b + c/d = (a*d + b*c)/(b*d)
"""),
    ("1.1 two-element field (1.1)-(1.2)", "VALID", """\
Step: 1 + 1 = 0 (mod 2)
Step: 1 * 1 = 1 (mod 2)
Step: 0 + 1 = 1 (mod 2)
"""),
    ("Theorem 1.1 triangle inequality, by the four cases", "VALID", """\
Theorem: "The Triangle Inequality"
Claim: forall a : Real, forall b : Real, |a + b| <= |a| + |b|
Proof:
    Given a, b : Real
    Case a >= 0 and b >= 0:
        Step: |a + b| = a + b
        Step: = |a| + |b|
    Case a <= 0 and b <= 0:
        Step: |a + b| = -a + (-b)
        Step: = |a| + |b|
    Case a >= 0 and b <= 0:
        Step: a + b = |a| - |b|
        Step: |a + b| <= |a| + |b|
    Case a <= 0 and b >= 0:
        Step: a + b = -|a| + |b|
        Step: |a + b| <= |a| + |b|
    Therefore |a + b| <= |a| + |b|
QED
"""),
    ("Corollary 1.2 reverse triangle inequality", "VALID", """\
Let a, b : Real
Step: |a| = |(a - b) + b|
Step: <= |a - b| + |b|
Step: |a - b| >= |a| - |b|
Step: |b - a| = |a - b|
Step: |a - b| >= | |a| - |b| |
Step: |a + b| >= | |a| - |b| |
"""),
    ("Corollary 1.2 blunder: |a - b| <= |a| - |b|", "INVALID", """\
Let a, b : Real
Step: |a - b| <= |a| - |b|
"""),
    ("Theorem 1.4 uniqueness of the supremum", "VALID", """\
Theorem: "Uniqueness of sup"
Proof:
    Let b1, b2, x0 : Real
    Assume h1: b1 < b2
    Let \\epsilon = b2 - b1
    Step: \\epsilon > 0
    Assume h2: x0 > b2 - \\epsilon
    Step: x0 > b2 - (b2 - b1)
    Step: = b1
    Therefore x0 > b1
QED
"""),
    ("Theorem 1.5 Archimedean step: n*eps <= beta - eps", "VALID", """\
Let n : Int
Let \\epsilon, \\beta : Real
Assume h: (n + 1) * \\epsilon <= \\beta
Step: n * \\epsilon <= \\beta - \\epsilon
"""),
    ("Theorem 1.7 rationals are dense", "VALID", """\
Theorem: "Density of the rationals (closing algebra)"
Proof:
    Let a, b : Real
    Let p, q : Int
    Assume hab: a < b
    Assume hq: q > 0
    Assume h1: q * (b - a) > 1
    Assume h2: q * a < p
    Assume h3: p <= q * a + 1
    Step: p < q * a + q * (b - a)
    Step: = q * b
    Therefore a < p / q and p / q < b
QED
"""),
    ("Theorem 1.9 irrationals are dense", "VALID", """\
Let a, b, r1, r2 : Real
Assume a < r1
Assume r1 < r2
Assume r2 < b
Let t = r1 + (r2 - r1) / sqrt(2)
Step: t > r1
Step: t < r2
Therefore a < t and t < b
"""),
    ("Theorem 1.9 blunder: t < r1", "INVALID", """\
Let r1, r2 : Real
Assume r1 < r2
Let t = r1 + (r2 - r1) / sqrt(2)
Step: t < r1
"""),
    ("1.1 extended reals arithmetic", "VALID", """\
Let a : Real
Step: a + oo = oo
Step: a - oo = -oo
Step: a / oo = 0
Step: oo * oo = oo
Step: (-oo) * (-oo) = oo
Step: -oo < a
Step: a < oo
"""),
    ("1.1 blunder: oo - oo is not 0", "INVALID", """\
Step: oo - oo = 0
"""),
    # ------------------------------------------------------------------
    # 1.2 The real line
    # ------------------------------------------------------------------
    ("Example 1.17 open intervals are open", "VALID", """\
Let a, b, x0, x, \\epsilon : Real
Assume a < x0 and x0 < b
Assume \\epsilon > 0 and \\epsilon <= min(x0 - a, b - x0)
Assume |x - x0| < \\epsilon
Therefore a < x and x < b
"""),
    # ------------------------------------------------------------------
    # 2.1 Functions and limits
    # ------------------------------------------------------------------
    ("Example 2.2 sqrt defines a function", "VALID", """\
Let x : Real
Assume x >= 0
Step: sqrt(x)^2 = x
Step: sqrt(x) >= 0
Step: (-sqrt(x))^2 = x
"""),
    ("Example 2.4 product of sqrt functions", "VALID", """\
Let x : Real
Assume 1 <= x and x <= 2
Step: sqrt(4 - x^2) * sqrt(x - 1) = sqrt((4 - x^2) * (x - 1))
"""),
    ("Example 2.7 lim cx = c x0", "VALID", """\
Theorem: "Limit of cx"
Proof:
    Let c, x0 : Real
    Assume hc: c != 0
    Given \\epsilon : Real where \\epsilon > 0
    Let \\delta = \\epsilon / |c|
    Step: \\delta > 0
    Subproof:
        Given x : Real
        Assume |x - x0| < \\delta
        Step: |c * x - c * x0| = |c| * |x - x0|
        Step: < |c| * \\delta
        Step: = \\epsilon
    Therefore exists \\delta : Real, \\delta > 0 and (forall x : Real, |x - x0| < \\delta => |c * x - c * x0| < \\epsilon) [witness: \\epsilon / |c|]
QED
"""),
    ("Example 2.8 x sin(1/x) -> 0", "VALID", """\
Let x, \\epsilon : Real
Assume \\epsilon > 0
Assume hx: 0 < |x| and |x| < \\epsilon
Step: |x * sin(1/x)| = |x| * |sin(1/x)|
Step: <= |x|
Step: < \\epsilon
Step: lim(x * sin(1/x), x, 0) = 0
"""),
    ("Example 2.8 blunder: |x sin(1/x)| <= |x|/2", "INVALID", """\
Let x : Real
Assume x != 0
Step: |x * sin(1/x)| <= |x| / 2
"""),
    ("Theorem 2.9 uniqueness of limits", "VALID", """\
Let x, L1, L2, \\epsilon : Real
Assume \\epsilon > 0
Assume h1: |f(x) - L1| < \\epsilon
Assume h2: |f(x) - L2| < \\epsilon
Step: |L1 - L2| = |(L1 - f(x)) + (f(x) - L2)|
Step: <= |L1 - f(x)| + |f(x) - L2|
Step: < 2 * \\epsilon
"""),
    ("Theorem 2.10 product-limit identity", "VALID", """\
Let x, L1, L2 : Real
Step: f(x) * g(x) - L1 * L2 = f(x) * (g(x) - L2) + L2 * (f(x) - L1)
Step: |f(x)| <= |f(x) - L1| + |L1|
"""),
    ("Example 2.11 limits by Theorem 2.10", "VALID", """\
Step: lim(9 - x^2, x, 2) = 5
Step: lim(x + 1, x, 2) = 3
Step: lim((9 - x^2)/(x + 1), x, 2) = 5/3
Step: lim((9 - x^2)*(x + 1), x, 2) = 15
Step: \\lim_{x \\to 2} (9 - x^2)/(x + 1) = 5/3
"""),
    ("Example 2.11 blunder", "INVALID", """\
Step: lim((9 - x^2)/(x + 1), x, 2) = 5
"""),
    ("Examples 2.13 and 2.15 one-sided limits", "VALID", """\
Step: lim(x/|x|, x, 0, "-") = -1
Step: lim(x/|x|, x, 0, "+") = 1
Step: lim(|x|/x + x, x, 0, "+") = 1
Step: lim(|x|/x + x, x, 0, "-") = -1
Step: lim(x * sin(sqrt(x)), x, 0, "+") = 0
Step: \\lim_{x \\to 0^+} x/|x| = 1
"""),
    ("Theorem 2.16 a two-sided limit that does not exist", "INVALID", """\
Step: lim(x/|x|, x, 0) = 1
"""),
    ("Example 2.18 limits at infinity", "VALID", """\
Step: lim(1 - 1/x^2, x, oo) = 1
Step: lim(2*|x|/(1 + x), x, oo) = 2
Step: lim(1 - 1/x^2, x, -oo) = 1
Step: lim(2*|x|/(1 + x), x, -oo) = -2
Step: \\lim_{x \\to \\infty} (1 - 1/x^2) = 1
"""),
    ("Example 2.18 the epsilon argument for g", "VALID", """\
Let x, \\epsilon : Real
Assume he: \\epsilon > 0
Assume hx: x > 2 / \\epsilon
Step: x > 0
Step: |2*x/(1 + x) - 2| = 2/(1 + x)
Step: < 2/x
Step: < \\epsilon
"""),
    ("Example 2.20 infinite limits", "VALID", """\
Step: lim(1/x, x, 0, "-") = -oo
Step: lim(1/x, x, 0, "+") = oo
Step: lim(1/x^2, x, 0) = oo
Step: lim(x^2, x, oo) = oo
Step: lim(x^3, x, oo) = oo
Step: lim(x^3, x, -oo) = -oo
"""),
    ("Example 2.20 blunder: lim 1/x at 0 is not oo", "INVALID", """\
Step: lim(1/x, x, 0) = oo
"""),
    ("Examples 2.21-2.23 limits via Theorem 2.10", "VALID", """\
Step: lim(sinh(x), x, oo) = oo
Step: lim(sinh(x), x, -oo) = -oo
Step: lim(exp(-x)/x, x, oo) = 0
Step: lim(exp(2*x) - exp(x), x, oo) = oo
Step: lim((2*x^2 - x + 1)/(3*x^2 + 2*x - 1), x, oo) = 2/3
Let x : Real
Step: sinh(x) = (exp(x) - exp(-x))/2
"""),
    # ------------------------------------------------------------------
    # 2.2 Continuity
    # ------------------------------------------------------------------
    ("Example 2.28 one-sided limits of a piecewise f", "VALID", """\
Step: lim(x^2, x, 0, "+") = 0
Step: lim(x^2, x, 1, "-") = 1
Step: lim(x + 1, x, 1, "+") = 2
Step: lim(x + 1, x, 2, "-") = 3
Let x, x0 : Real
Assume 0 < x and x < 1 and 0 < x0 and x0 < 1
Step: |x^2 - x0^2| = |x - x0| * |x + x0|
Step: <= 2 * |x - x0|
"""),
    ("Example 2.30 sqrt is continuous", "VALID", """\
Let x, x0 : Real
Assume x >= 0
Assume x0 > 0
Step: |sqrt(x) - sqrt(x0)| = |x - x0| / (sqrt(x) + sqrt(x0))
Step: <= |x - x0| / sqrt(x0)
"""),
    ("Example 2.39 composite function", "VALID", """\
Let f(t) = log(t)
Let g(t) = 1/(1 - t^2)
Let x : Real
Assume -1 < x and x < 1
Step: f(g(x)) = log(1/(1 - x^2))
Step: g(x) > 0
"""),
    ("Example 2.49 2x is uniformly continuous", "VALID", """\
Let x, y, \\epsilon : Real
Assume \\epsilon > 0
Assume |x - y| < \\epsilon / 2
Step: |2*x - 2*y| = 2 * |x - y|
Step: < \\epsilon
"""),
    ("Example 2.50 x^2 is uniformly continuous on [-r, r]", "VALID", """\
Let x, y, r : Real
Assume r > 0
Assume |x| <= r and |y| <= r
Step: |x^2 - y^2| = |x - y| * |x + y|
Step: <= 2 * r * |x - y|
"""),
    ("Example 2.51 x^2 is not uniformly continuous on R", "VALID", """\
Let x, y, \\delta : Real
Assume \\delta > 0
Assume x > 1/\\delta and y > 1/\\delta
Assume |x - y| = \\delta / 2
Step: |x^2 - y^2| = |x - y| * |x + y|
Step: > (\\delta / 2) * (1/\\delta + 1/\\delta)
Step: = 1
"""),
    ("Example 2.52 cos(1/x) is not uniformly continuous", "VALID", """\
Let n : Int
Step: |cos(n * pi) - cos((n + 1) * pi)| = 2
"""),
    ("Examples 2.57-2.58 inverse functions", "VALID", """\
Let f(t) = 2*t + 4
Let g(s) = (s - 4)/2
Let x, y : Real
Step: g(f(x)) = x
Step: f(g(y)) = y
Let F(t) = t^2
Let G(s) = sqrt(s)
Let u : Real
Assume u >= 0
Step: G(F(u)) = u
Step: F(G(u)) = u
"""),
    # ------------------------------------------------------------------
    # 2.3 Differentiable functions
    # ------------------------------------------------------------------
    ("Example 2.60 d/dx x^n = n x^(n-1)", "VALID", """\
Let n : Nat
Let x, x0 : Real
Step: diff(x^n, x) = n * x^(n - 1)
Step: lim((x^3 - x0^3)/(x - x0), x, x0) = 3 * x0^2
Assume x != x0
Step: (x^3 - x0^3)/(x - x0) = x^2 + x*x0 + x0^2
"""),
    ("Example 2.60 blunder", "INVALID", """\
Let x : Real
Step: diff(x^3, x) = 3 * x^3
"""),
    ("Example 2.63 |x| has distinct one-sided derivatives at 0", "VALID", """\
Step: lim((|x| - 0)/(x - 0), x, 0, "+") = 1
Step: lim((|x| - 0)/(x - 0), x, 0, "-") = -1
"""),
    ("Theorem 2.64 product and quotient rules", "VALID", """\
Let f(t) = t^2 + 1
Let g(t) = exp(t)
Let x : Real
Step: diff(f(x) * g(x), x) = diff(f(x), x) * g(x) + f(x) * diff(g(x), x)
Step: diff(f(x) / g(x), x) = (diff(f(x), x) * g(x) - f(x) * diff(g(x), x)) / g(x)^2
"""),
    ("Example 2.66 chain rule", "VALID", """\
Let x : Real
Assume x != 0
Step: diff(sin(1/x), x) = cos(1/x) * (-1/x^2)
"""),
    ("Example 2.67 one-sided derivatives at 0", "VALID", """\
Step: lim((x^2 * sin(1/x) - 0)/(x - 0), x, 0, "+") = 0
Step: lim((x^3 - 0)/(x - 0), x, 0, "-") = 0
"""),
    ("Theorem 2.73 h(a) = h(b) in the generalised MVT", "VALID", """\
Let fa, fb, ga, gb : Real
Step: (gb - ga)*fa - (fb - fa)*ga = (gb - ga)*fb - (fb - fa)*gb
"""),
    ("Theorem 2.74 MVT for x^3 on [0, 3]", "VALID", """\
Let f(x) = x^3
Let fp(x) = 3 * x^2
Let t : Real
Step: diff(f(t), t) = fp(t)
Let c = sqrt(3)
Step: c > 0 and c < 3
Step: fp(c) = (f(3) - f(0)) / (3 - 0)
"""),
    ("Theorem 2.71 Rolle for x^2 - 2x on [0, 2]", "VALID", """\
Let f(x) = x^2 - 2*x
Let t : Real
Step: f(0) = f(2)
Step: diff(f(t), t) = 2*t - 2
Step: 2*1 - 2 = 0
"""),
    # ------------------------------------------------------------------
    # 3 Sequences and series
    # ------------------------------------------------------------------
    ("Example 3.3 (2n+1)/(n+1) -> 2", "VALID", """\
Theorem: "Example 3.3"
Proof:
    Given \\epsilon : Real where \\epsilon > 0
    Let N : Int where N >= 1 / \\epsilon and N >= 1
    Given n : Int where n >= N
    Step: |(2*n + 1)/(n + 1) - 2| = 1/(n + 1)
    Step: < 1/N
    Step: <= \\epsilon
    Step: lim((2*n + 1)/(n + 1), n, oo) = 2
QED
"""),
    ("Example 3.4 sequences diverging to +-oo", "VALID", """\
Let n, a : Real
Assume n > 0 and n >= 2 * a
Step: n/2 + 1/n > a
Step: lim(n/2 + 1/n, n, oo) = oo
Step: lim(n - n^2, n, oo) = -oo
"""),
    ("Examples 3.6-3.7 sequences of functional values", "VALID", """\
Step: lim(log(x)/x, x, oo) = 0
Step: lim(x * log(1 + 1/x), x, oo) = 1
Step: lim((1 + 1/x)^x, x, oo) = e
"""),
    ("Example 3.8 rho^n -> 0 for 0 < rho < 1", "VALID", """\
Let \\rho : Real
Assume 0 < \\rho and \\rho < 1
Step: lim(\\rho^n, n, oo) = 0
"""),
    ("Example 3.11 convergent subsequences", "VALID", """\
Step: lim(1 + 1/(2*k), k, oo) = 1
Step: lim(-1 - 1/(2*k + 1), k, oo) = -1
"""),
    ("Example 3.16 1/n is Cauchy", "VALID", """\
Let n, m, N : Int
Assume N >= 1 and n >= N and m >= N
Step: |1/n - 1/m| <= 1/n + 1/m
Step: <= 2/N
"""),
    ("Lemma 3.17 convergent implies Cauchy", "VALID", """\
Let sn, sm, s, \\epsilon : Real
Assume \\epsilon > 0
Assume |sn - s| < \\epsilon / 2
Assume |sm - s| < \\epsilon / 2
Step: |sn - sm| = |(sn - s) - (sm - s)|
Step: <= |sn - s| + |sm - s|
Step: < \\epsilon / 2 + \\epsilon / 2
Step: = \\epsilon
"""),
    ("Example 3.22 geometric series", "VALID", """\
Let r : Real
Let n : Nat
Assume r != 1
Step: sum(k, 0, n, r^k) = (1 - r^(n + 1))/(1 - r)
Assume |r| < 1
Step: sum(k, 0, oo, r^k) = 1/(1 - r)
Step: \\sum_{k=0}^{\\infty} r^k = 1/(1 - r)
"""),
    ("Example 3.22 blunder: wrong partial sum", "INVALID", """\
Let r : Real
Let n : Nat
Assume r != 1
Step: sum(k, 0, n, r^k) = (1 - r^n)/(1 - r)
"""),
    ("Example 3.27 tail of the geometric series", "VALID", """\
Let r : Real
Let m : Nat
Assume |r| < 1
Step: sum(k, m, oo, r^k) = r^m / (1 - r)
"""),
    ("Example 3.30 derivative of x^n e^(-nx)", "VALID", """\
Let x : Real
Let n : Nat
Assume n >= 1
Step: diff(x^n * exp(-n*x), x) = n * x^(n - 1) * exp(-n*x) * (1 - x)
"""),
    ("Example 3.45 partial sums of sum x^j", "VALID", """\
Let x : Real
Let n : Nat
Assume x != 1
Step: sum(j, 0, n, x^j) = (1 - x^(n + 1))/(1 - x)
Step: 1/(1 - x) - (1 - x^(n + 1))/(1 - x) = x^(n + 1)/(1 - x)
"""),
    ("Example 3.49 Weierstrass test bounds", "VALID", """\
Let x : Real
Let n : Int
Assume n >= 1
Step: 1/(x^2 + n^2) <= 1/n^2
Step: |sin(n*x)/n^2| <= 1/n^2
Step: sum(k, 1, oo, 1/k^2) = pi^2/6
"""),
    ("Example 3.50 |x/(1+x)| <= r", "VALID", """\
Let x, r : Real
Assume 0 < r and r < 1
Assume -r/(1 + r) <= x and x <= r/(1 - r)
Step: |x/(1 + x)| <= r
"""),
    # ------------------------------------------------------------------
    # 4 Lipschitz continuity
    # ------------------------------------------------------------------
    ("Example 4.15 Lipschitz constant 3", "VALID", """\
Let x, y : Real
Assume 0 <= x and x <= 1 and 0 <= y and y <= 1
Step: |x^2 - y^2| = |x - y| * |x + y|
Step: <= 2 * |x - y|
Let u, v : Real
Step: |(-3*u) - (-3*v)| = 3 * |u - v|
Let p, q : Real
Assume p > 0 and q < 0
Step: 2*|p| + 3*|q| < 3*(|p| + |q|)
Step: |p - q| = |p| + |q|
"""),
    ("Exercise 4.16 Lipschitz constant of ln(x^2 + k^2)", "VALID", """\
Let x, k : Real
Assume k > 0
Step: diff(ln(x^2 + k^2), x) = 2*x/(x^2 + k^2)
Step: |2*x/(x^2 + k^2)| <= 1/k
"""),
    ("Exercise 4.16 blunder: constant 1/(2k)", "INVALID", """\
Let x, k : Real
Assume k > 0
Step: |2*x/(x^2 + k^2)| <= 1/(2*k)
"""),
    # ------------------------------------------------------------------
    # 5 Integrability
    # ------------------------------------------------------------------
    ("Example 5.12 integral of a constant", "VALID", """\
Let a, b, c : Real
Step: integrate(c, x, a, b) = c*(b - a)
Let n : Nat
Step: sum(i, 1, n, x(i) - x(i - 1)) = x(n) - x(0)
"""),
    ("Example 5.14 integral of log", "VALID", """\
Let n : Nat
Assume n >= 2
Step: integrate(log(x), x, 1, n) = n*log(n) - n + 1
"""),
    ("Theorems 5.21-5.22 fundamental theorem of calculus", "VALID", """\
Let x : Real
Step: diff(integrate(t^2 + sin(t), t, 0, x), x) = x^2 + sin(x)
Step: integrate(3*t^2, t, 1, 2) = 2^3 - 1^3
Step: \\int_{1}^{2} 3*t^2 dt = 7
"""),
    ("Theorem 5.24 substitution formula", "VALID", """\
Step: integrate(2*x*cos(x^2), x, 0, sqrt(pi)) = integrate(cos(u), u, 0, pi)
"""),
]
