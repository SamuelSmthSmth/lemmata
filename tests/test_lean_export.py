""""Show me in Lean": a checked proof as a Lean 4 + Mathlib skeleton.

The skeletons are compiled against Mathlib by the `lean` CI job (lean/generate.py);
these tests pin the translation itself, and how its lines line up with the
source's, without needing Lean.
"""

import pytest

from aether import ParseError
from aether.core.lean_export import export_to_lean, lean_name, slug

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

EVEN_SQUARE_LEAN = """\
/-- Even square theorem -/
theorem even_square_theorem :
    ∀ n : ℤ, Even n → (4 : ℤ) ∣ n ^ 2 := by
  intro n
  intro h1
  obtain ⟨k, h5⟩ : ∃ k : ℤ, n = 2 * k := by
    sorry  -- from h1
  have s6 : n ^ 2 = 2 * (2 * k ^ 2) := by
    calc n ^ 2 = (2 * k) ^ 2 := by first | (subst_vars; ring; done) | (ring; done) | (simp only [*]; ring; done) | linarith | sorry  -- Kernel: subst
      _ = 4 * k ^ 2 := by first | (ring; done) | (norm_num; done) | (field_simp; ring; done) | linarith | (rfl; done) | decide | sorry  -- Kernel: ring
      _ = 2 * (2 * k ^ 2) := by first | (ring; done) | (norm_num; done) | (field_simp; ring; done) | linarith | (rfl; done) | decide | sorry  -- Kernel: ring
  have s9 : ∃ m : ℤ, n ^ 2 = 4 * m := ⟨(k ^ 2 : ℤ), by first | (subst_vars; ring; done) | (ring; done) | (simp only [*]; ring; done) | linarith | sorry⟩  -- Kernel: subst
  have s10 : (4 : ℤ) ∣ n ^ 2 := by
    first | assumption | linarith | omega | (simp_all; done) | sorry  -- Kernel: hypothesis
  exact s10
"""


def body(source: str, **kwargs) -> str:
    """The skeleton without its file header and namespace."""
    lean = export_to_lean(source, **kwargs).lean
    lines = lean.splitlines()
    start = lines.index("namespace Lemmata") + 2
    end = lines.index("end Lemmata")
    return "\n".join(lines[start:end]).strip("\n") + "\n"


def test_the_even_square_theorem_in_full():
    assert body(EVEN_SQUARE) == EVEN_SQUARE_LEAN


def test_the_file_is_a_whole_lean_file():
    lean = export_to_lean(EVEN_SQUARE).lean
    assert lean.startswith("import Mathlib\n")
    assert "namespace Lemmata" in lean and lean.rstrip().endswith("end Lemmata")


def test_rows_line_the_lean_up_with_the_source():
    export = export_to_lean(EVEN_SQUARE)
    lean = export.lean.splitlines()
    rows = {r["line"]: r for r in export.rows if r["line"] is not None}
    # Each step's row holds the Lean it became.
    assert rows[3]["source"].strip() == "Given n : Int"
    assert lean[rows[3]["lean_from"] - 1].strip() == "intro n"
    assert lean[rows[7]["lean_from"] - 1].strip().startswith("_ = 4 * k ^ 2")
    # Rows are in Lean's order and cover every Lean line exactly once.
    covered = [n for r in export.rows for n in range(r["lean_from"], r["lean_to"] + 1)]
    assert covered == list(range(1, len(lean) + 1))
    assert rows[10]["status"] == "VALID"


def test_a_failing_step_is_marked_in_its_row_and_its_comment():
    export = export_to_lean("Let x : Real\nStep: (x + 1)^2 = x^2 + 1")
    (row,) = [r for r in export.rows if r["line"] == 2]
    assert row["status"] == "INVALID"
    assert "sorry  -- did not check" in export.lean


def test_a_scratchpad_states_what_it_shows():
    lean = body("Let x, y : Real\nAssume x > 2\nStep: (x^2 - 4) / (x - 2) = x + 2\nStep: > 4")
    assert "example :\n    ∀ x : ℝ, ∀ y : ℝ, x > 2 → (x ^ 2 - 4) / (x - 2) > 4 := by" in lean
    assert "_ > 4 := by first | linarith |" in lean and "| sorry  -- Kernel: linarith" in lean
    assert lean.rstrip().endswith("exact s3")


def test_induction_closes_with_lean_induction():
    source = """\
Theorem: "Divisibility of 3^n - 1 by 2"
Claim: forall n : Nat, MultipleOf(3^n - 1, 2)
Proof:
    Base case n = 0:
        Step: 3^0 - 1 = 2 * 0
        Hence MultipleOf(3^0 - 1, 2)

    Inductive step:
        Given k : Nat
        Assume ih: MultipleOf(3^k - 1, 2)
        Obtain m : Int such that 3^k - 1 = 2 * m from ih
        Step: 3^(k+1) - 1 = 3 * (3^k - 1) + 2
        Step: = 2 * (3 * m + 1)
        Hence MultipleOf(3^(k+1) - 1, 2)
QED
"""
    lean = body(source)
    assert "∀ n : ℕ, (2 : ℤ) ∣ 3 ^ n - 1 := by" in lean
    assert "have s8 : ∀ k : ℕ, (2 : ℤ) ∣ 3 ^ k - 1 → (2 : ℤ) ∣ 3 ^ (k + 1) - 1 := by" in lean
    assert lean.rstrip().endswith("intro n\n  induction n with\n  | zero => exact s4\n  | succ k ih => exact s8 k ih")


def test_a_group_is_mathlibs_group():
    source = """\
Theorem: "Left cancellation"
Proof:
    Assume Group(G, op, e, inv)
    Given a, u, v : G
    Assume h: op(a, u) = op(a, v)
    Step: u = op(inv(a), op(a, u))
    Step: = op(inv(a), op(a, v))
    Step: = v
QED
"""
    lean = body(source)
    assert "theorem left_cancellation {G : Type*} [Group G] :" in lean
    assert "∀ a : G, ∀ u : G, ∀ v : G, a * u = a * v → u = v := by" in lean
    assert "calc u = a⁻¹ * (a * u) := by first | (group; done) |" in lean
    assert ":= by first | (simp_all; done) |" in lean and "-- Kernel: group axioms and hypotheses" in lean


def test_cases_split_with_rcases_and_bullets():
    source = """\
Theorem: "Squares"
Proof:
    Let x : Real
    Case x >= 0:
        Assume hp: x >= 0
        Step: x * x >= 0
    Case x < 0:
        Step: x * x >= 0
QED
"""
    lean = body(source)
    assert "obtain hc4 | hc7 : x ≥ 0 ∨ x < 0 := by" in lean
    assert "· -- Case x ≥ 0" in lean and "have hp : x ≥ 0 := hc4" in lean
    assert lean.count("exact s") >= 3


def test_definitions_about_functions_take_function_arguments():
    source = """\
Definition 2.6 (Continuity): Continuous(f, a) <=> forall ε > 0, exists δ > 0, forall x : Real, abs(x - a) < δ => abs(f(x) - f(a)) < ε
Let g(x) = 3 * x
Theorem: "3x is continuous at 2"
Claim: Continuous(g, 2)
Proof:
    Given ε : Real
    Assume h1: ε > 0
    Therefore exists d > 0, forall x : Real, abs(x - 2) < d => abs(g(x) - g(2)) < ε [witness: ε / 3]
QED
"""
    lean = body(source)
    assert "def Continuous (f : ℝ → ℝ) (a : ℝ) : Prop :=" in lean
    assert "∀ ε : ℝ, ε > 0 → ∃ δ : ℝ, δ > 0 ∧ ∀ x : ℝ, |x - a| < δ → |f x - f a| < ε" in lean
    assert "noncomputable def g (x : ℝ) : ℝ :=\n  3 * x" in lean
    # The claim's definition is unfolded by `intro`, as Lemmata unfolds it.
    assert "theorem t_3x_is_continuous_at_2 :\n    Continuous g 2 := by\n  intro ε\n  intro h1" in lean


def test_abstract_functions_and_predicates_are_bound_by_the_statement():
    lean = body("Given f : Real -> Real\nAssume forall x : Real, f(x) > 0\nTherefore f(2) > 0")
    assert "∀ f : ℝ → ℝ, (∀ x : ℝ, f x > 0) → f 2 > 0 := by" in lean
    lean = body("Let x : Real\nAssume P(x)\nTherefore P(x)")
    assert "example (P : ℝ → Prop) :" in lean


def test_notation_goes_to_mathlibs():
    lean = body(
        "Let x : Real\nLet n : Int\n"
        "Step: sqrt(x^2) = abs(x)\nStep: Congruent(n^2, 1, 4)\nStep: lim(x/|x|, x, 0, \"+\") = 1\n"
        "Step: lim(1 - 1/x^2, x, oo) = 1\nStep: diff(x^3, x) = 3 * x^2\nStep: integrate(x, x, 0, 1) = 1/2\n"
        "Step: det([[1, 2], [3, 4]]) = -2"
    )
    assert "Real.sqrt (x ^ 2) = |x|" in lean
    assert "(n ^ 2 : ℤ) ≡ 1 [ZMOD 4]" in lean
    assert "Filter.Tendsto (fun x : ℝ => x / |x|) (nhdsWithin 0 (Set.Ioi 0)) (nhds (1 : ℝ))" in lean
    assert "Filter.Tendsto (fun x : ℝ => 1 - 1 / x ^ 2) Filter.atTop (nhds (1 : ℝ))" in lean
    assert "deriv (fun x : ℝ => x ^ 3) x = 3 * x ^ 2" in lean
    assert "intervalIntegral (fun x : ℝ => x) 0 1 MeasureTheory.volume = (1 : ℝ) / 2" in lean
    assert "Matrix.det (!![1, 2; 3, 4] : Matrix (Fin 2) (Fin 2) ℝ) = -2" in lean


def test_what_has_no_faithful_translation_is_a_typed_sorry_and_is_listed():
    export = export_to_lean("Let a : Real\nStep: a + oo = oo")
    assert "(sorry : Prop)" in export.lean
    assert export.untranslated == [{"line": 2, "what": "∞, which is not a real number"}]


def test_division_is_exact_as_in_lemmata():
    # Lean's `/` on ℕ and ℤ rounds down; Lemmata's never does.
    assert "have s1 : (1 : ℝ) / 2 + (1 : ℝ) / 2 = 1 := by" in body("Step: 1/2 + 1/2 = 1")
    assert "(2 * n + 1 : ℝ) / (n + 1)" in body("Let n : Int\nAssume n > 0\nStep: (2*n + 1)/(n + 1) < 2")


def test_inverses_bind_as_lean_reads_them():
    lean = body(
        "Theorem: \"t\"\nProof:\n    Assume Group(G, op, e, inv)\n    Given x : G\n    Step: inv(op(x, x)) = op(inv(x), inv(x))\nQED"
    )
    assert "(x * x)⁻¹ = x⁻¹ * x⁻¹" in lean


def test_names_lean_reserves_are_quoted():
    assert lean_name("at") == "«at»" and lean_name("epsilon") == "ε" and lean_name("lambda") == "«λ»"
    assert slug("3x is continuous") == "t_3x_is_continuous"


def test_a_parse_error_is_raised_not_exported():
    with pytest.raises(ParseError):
        export_to_lean("Theorem: \"Bad\"\nProof:\nGiven n : Int\nQED")


def test_a_step_the_kernel_checked_tries_its_tactic_and_falls_back_to_sorry():
    lean = body("Let x : Real\nAssume h: x > 2\nTherefore x > 1")
    assert "first | linarith |" in lean and "| sorry  -- Kernel: linarith" in lean


def test_a_calculus_step_stays_sorry():
    # Lean's deriv goal needs lemmas, not one tactic: the rule is named, not tried.
    lean = body("Let x : Real\nStep: diff(x^3, x) = 3*x^2")
    assert "sorry  -- Kernel: power rule" in lean
    assert "first |" not in lean


def test_the_header_says_how_the_steps_are_proved():
    lean = export_to_lean("Let x : Real\nStep: x = x").lean
    assert "Each step tries the Lean tactic for the rule" in lean
