"""Tests for Abstract Algebra (Groups, Rings, Fields, Modular Arithmetic) in Aether."""

import pytest

from aether import ProofChecker, StepStatus, export_to_latex


@pytest.fixture
def checker() -> ProofChecker:
    return ProofChecker()


class TestGroupTheory:
    def test_group_identity_and_inverses(self, checker: ProofChecker):
        src = """\
Theorem: "Group identity and inverse properties"
Proof:
    Assume Group(G, op, e, inv)
    Given a : Real
    Step: op(a, e) = a
    Step: op(e, a) = a
    Step: op(a, inv(a)) = e
    Step: inv(inv(a)) = a
    Step: inv(e) = e
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_group_shoes_and_socks_theorem(self, checker: ProofChecker):
        src = """\
Theorem: "Inverse of a product in a group"
Proof:
    Assume Group(G, op, e, inv)
    Given a, b : Real
    Step: op(op(a, b), op(inv(b), inv(a))) = e
    Therefore inv(op(a, b)) = op(inv(b), inv(a))
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_group_cancellation_laws(self, checker: ProofChecker):
        src = """\
Theorem: "Left and right cancellation in group"
Proof:
    Assume Group(G, op, e, inv)
    Given a, x, y : Real
    Assume h1: op(a, x) = op(a, y)
    Therefore x = y
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_abelian_group_commutativity(self, checker: ProofChecker):
        src = """\
Theorem: "Abelian group commutativity"
Proof:
    Assume AbelianGroup(G, op, e, inv)
    Given a, b : Real
    Step: op(a, b) = op(b, a)
    Therefore op(inv(a), inv(b)) = op(inv(b), inv(a))
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)


class TestSubgroupsAndNormalSubgroups:
    def test_subgroup_intersection_identity(self, checker: ProofChecker):
        src = """\
Theorem: "Identity is in subgroup intersection"
Proof:
    Assume Group(G, op, e, inv)
    Given H1, H2 : Real
    Assume h1: Subgroup(H1, G, op, e, inv)
    Assume h2: Subgroup(H2, G, op, e, inv)
    Step: e in H1
    Step: e in H2
    Therefore e in (H1 intersect H2)
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_normal_subgroup_conjugation(self, checker: ProofChecker):
        src = """\
Theorem: "Normal subgroup conjugation property"
Proof:
    Assume Group(G, op, e, inv)
    Given N : Real
    Assume h1: NormalSubgroup(N, G, op, e, inv)
    Given g, n : Real
    Assume hg: g in G
    Assume hn: n in N
    Therefore op(op(g, n), inv(g)) in N
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)


class TestRingsAndFields:
    def test_ring_distributivity_and_zero(self, checker: ProofChecker):
        src = """\
Theorem: "Ring operations"
Proof:
    Assume Ring(R, add, mul, zero, one, neg)
    Given a, b, c : Real
    Step: mul(a, add(b, c)) = add(mul(a, b), mul(a, c))
    Step: mul(a, zero) = zero
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_field_multiplicative_inverses(self, checker: ProofChecker):
        src = """\
Theorem: "Field non-zero inverse"
Proof:
    Assume Field(F, add, mul, zero, one, neg, inv)
    Given x : Real
    Assume h1: x != zero
    Therefore mul(x, inv(x)) = one
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)


class TestModularArithmetic:
    def test_modular_congruence_syntax_and_verification(self, checker: ProofChecker):
        src = """\
Theorem: "Square of congruent integers"
Proof:
    Given a, b, m : Int
    Assume h1: a = b (mod m)
    Obtain k : Int such that a - b = m * k from h1
    Step: a = b + m * k
    Step: a^2 = b^2 (mod m)
    Therefore Congruent(a^2, b^2, m)
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        assert all(r.status == StepStatus.VALID for r in report.results)

    def test_latex_congruence_syntax_and_export(self, checker: ProofChecker):
        src = """\
Theorem: "LaTeX modular congruence"
Proof:
    Given x, y, n : Int
    Assume h1: x \\equiv y \\pmod{n}
    Therefore x = y (mod n)
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        tex = export_to_latex(src, report=report)
        assert "\\pmod" in tex
        assert "\\equiv" in tex
