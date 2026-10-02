"""MTH2010 Algebra (Groups; Cosets and Quotient Groups), transcribed into Aether.

Same shape as :mod:`corpus_real_analysis`: ``(name, expected_verdict, source)``.
"""

CORPUS: list[tuple[str, str, str]] = [
    # ------------------------------------------------------------------
    # 1. Groups
    # ------------------------------------------------------------------
    ("Example 1.1.1 (Z, +): inverse of n is -n", "VALID", """\
Let n : Int
Step: n + (-n) = 0
Step: n + 0 = n
"""),
    ("Example 1.1.2 Z_n addition is well defined", "VALID", """\
Let i, j, k, l, n : Int
Assume hk: i = k (mod n)
Assume hl: j = l (mod n)
Therefore i + j = k + l (mod n)
"""),
    ("Example 1.1.3 |S_n| = n! and the k-cycle count", "VALID", """\
Step: factorial(3) = 6
Step: 4! = 24
Let n : Nat
Assume n >= 1
Step: n! = n * (n - 1)!
Step: (4 * 3 * 2) / 3 = 8
"""),
    ("Example 1.1.4 D_4 relations as arithmetic of exponents", "VALID", """\
Step: 2 + 2 = 0 (mod 2)
"""),
    ("Remark (Basic Properties) 3: (a^-1)^-1 = a", "VALID", """\
Theorem: "Inverse of an inverse"
Proof:
    Assume Group(G, op, e, inv)
    Given a : G
    Step: op(inv(a), a) = e
    Therefore inv(inv(a)) = a
QED
"""),
    ("Remark (Basic Properties) 4: (ab)^-1 = b^-1 a^-1", "VALID", """\
Theorem: "Shoes and socks"
Proof:
    Assume Group(G, op, e, inv)
    Given a, b : G
    Step: op(op(a, b), op(inv(b), inv(a))) = e
    Therefore inv(op(a, b)) = op(inv(b), inv(a))
QED
"""),
    ("Remark (Basic Properties) 5: cancellation", "VALID", """\
Theorem: "Left cancellation"
Proof:
    Assume Group(G, op, e, inv)
    Given a, u, v : G
    Assume h: op(a, u) = op(a, v)
    Step: u = op(inv(a), op(a, u))
    Step: = op(inv(a), op(a, v))
    Step: = v
QED
"""),
    ("Remark (Basic Properties) 1: the identity is unique", "VALID", """\
Theorem: "Uniqueness of the identity"
Proof:
    Assume Group(G, op, e, inv)
    Given f : G
    Assume hf: forall x : G, op(x, f) = x
    Step: op(e, f) = e
    Step: op(e, f) = f
    Therefore f = e
QED
"""),
    ("Remark (Basic Properties) 4, in the notes' notation", "VALID", """\
Theorem: "Shoes and socks, multiplicatively"
Proof:
    Assume Group(G, op, e, inv)
    Given a, b : G
    Step: (a * b) * (b^-1 * a^-1) = e
    Therefore (a * b)^-1 = b^-1 * a^-1
QED
"""),
    ("Example 1.3 notation: a^2 a^3 = a^5 in a group", "VALID", """\
Assume Group(G, op, e, inv)
Given a : G
Step: a^2 * a^3 = a^5
Step: a * a^-1 = e
Step: (a^-1)^-1 = a
"""),
    ("A plain group is not assumed abelian", "INVALID", """\
Assume Group(G, op, e, inv)
Given a, b : G
Step: op(a, b) = op(b, a)
"""),
    ("Example 1.3.6 ord([k]_n) divides out: n' [k]_n = [0]_n", "VALID", """\
Let k, n, d, k1, n1 : Int
Assume hk: k = d * k1
Assume hn: n = d * n1
Step: n1 * k = d * n1 * k1
Step: = n * k1
Therefore n1 * k = 0 (mod n)
"""),
    ("Example 1.3.6 ord([2]_8) = 4", "VALID", """\
Step: 4 * 2 = 0 (mod 8)
Step: not Congruent(3 * 2, 0, 8)
Step: not Congruent(2 * 2, 0, 8)
Step: not Congruent(1 * 2, 0, 8)
Step: 8 / gcd(8, 2) = 4
"""),
    ("Example 1.4.2 Z_8 = <[3]_8> = <[5]_8>", "VALID", """\
Step: gcd(3, 8) = 1
Step: gcd(5, 8) = 1
Step: 3 * 3 = 1 (mod 8)
Step: 5 * 5 = 1 (mod 8)
Step: 3 + 5 = 0 (mod 8)
"""),
    ("Example 1.4.3 ord(x^k) = n / gcd(n, k)", "VALID", """\
Step: 12 / gcd(12, 8) = 3
Step: lcm(4, 6) = 12
"""),
    ("Example 1.6.1 f(k) = [k]_n is a homomorphism", "VALID", """\
Let r, s, n : Int
Step: r + s = r + s (mod n)
Step: r + n = r (mod n)
"""),
    ("Example 1.6.2 phi(k) = mk is an injective homomorphism", "VALID", """\
Theorem: "phi(k) = mk"
Proof:
    Let m, k1, k2 : Int
    Step: m * (k1 + k2) = m * k1 + m * k2
    Assume hm: m != 0
    Assume h: m * k1 = m * k2
    Step: m * (k1 - k2) = 0
    Therefore k1 = k2
QED
"""),
    ("Example 1.6.4 the parity map on D_2n", "VALID", """\
Let i, k : Int
Assume hk: Odd(k)
Step: i + 1 = i + k (mod 2)
"""),
    ("Remark (Image and Kernel): the kernel is closed under products", "VALID", """\
Theorem: "Kernel closed under products"
Proof:
    Assume Group(G, op, e, inv)
    Assume Group(H, star, eH, invH)
    Assume hom: forall x : G, forall y : G, f(op(x, y)) = star(f(x), f(y))
    Given g1, g2 : G
    Assume k1: f(g1) = eH
    Assume k2: f(g2) = eH
    Step: f(op(g1, g2)) = star(f(g1), f(g2))
    Step: = star(eH, eH)
    Step: = eH
QED
"""),
    ("Remark (Image and Kernel): the kernel is closed under inverses", "VALID", """\
Theorem: "Kernel closed under inverses"
Proof:
    Assume Group(G, op, e, inv)
    Assume Group(H, star, eH, invH)
    Assume hom: forall x : G, forall y : G, f(op(x, y)) = star(f(x), f(y))
    Assume he: f(e) = eH
    Given g : G
    Assume k: f(g) = eH
    Step: eH = f(e)
    Step: = f(op(g, inv(g)))
    Step: = star(f(g), f(inv(g)))
    Step: = star(eH, f(inv(g)))
    Step: = f(inv(g))
QED
"""),
    # ------------------------------------------------------------------
    # 2. Left cosets and quotient groups
    # ------------------------------------------------------------------
    ("Lemma 2.1 R is reflexive", "VALID", """\
Assume Group(G, op, e, inv)
Assume Subgroup(H, G, op, e, inv)
Given x : G
Step: op(inv(x), x) = e
Therefore op(inv(x), x) in H
"""),
    ("Lemma 2.1 R is symmetric", "VALID", """\
Theorem: "R is symmetric"
Proof:
    Assume Group(G, op, e, inv)
    Assume Subgroup(H, G, op, e, inv)
    Given x, y : G
    Assume h: op(inv(x), y) in H
    Step: inv(op(inv(x), y)) = op(inv(y), x)
    Therefore op(inv(y), x) in H
QED
"""),
    ("Lemma 2.1 R is transitive", "VALID", """\
Theorem: "R is transitive"
Proof:
    Assume Group(G, op, e, inv)
    Assume Subgroup(H, G, op, e, inv)
    Given x, y, z : G
    Assume h1: op(inv(x), y) in H
    Assume h2: op(inv(y), z) in H
    Step: op(op(inv(x), y), op(inv(y), z)) = op(inv(x), z)
    Therefore op(inv(x), z) in H
QED
"""),
    ("Example 2.1.1 Euclidean division: a R r in Z/nZ", "VALID", """\
Let a, k, n, r : Int
Assume a = k * n + r
Step: a = r (mod n)
Step: -a + r = (-k) * n
"""),
    ("Theorem 2.2 Lagrange, numerically (D_6 and <r>)", "VALID", """\
Step: 6 = 3 * 2
Step: 24 / 4 = 6
"""),
    ("Definition 2.3 subgroups of abelian groups are normal", "VALID", """\
Assume AbelianGroup(G, op, e, inv)
Given x, h : G
Step: op(op(x, h), inv(x)) = h
"""),
    ("Example 2.2.3 kernels are normal: f(x h x^-1) = e", "VALID", """\
Theorem: "Kernels are normal"
Proof:
    Assume Group(G, op, e, inv)
    Assume Group(K, star, eK, invK)
    Assume hom: forall x : G, forall y : G, f(op(x, y)) = star(f(x), f(y))
    Assume hinv: forall x : G, f(inv(x)) = invK(f(x))
    Given x, h : G
    Assume kh: f(h) = eK
    Step: f(op(op(x, h), inv(x))) = star(f(op(x, h)), f(inv(x)))
    Step: = star(star(f(x), f(h)), invK(f(x)))
    Step: = star(star(f(x), eK), invK(f(x)))
    Step: = eK
QED
"""),
    ("Example 2.5.4 conjugating r^2 in D_8 (exponent arithmetic)", "VALID", """\
Let j : Int
Step: j + 2 - j = 2
Step: 1 - 2*j = 1 + 2*(-j)
"""),
    ("Corollary 2.9 counting with the first isomorphism theorem", "VALID", """\
Step: factorial(3) = 3 * 2
Step: factorial(4) / 12 = 2
"""),
]
