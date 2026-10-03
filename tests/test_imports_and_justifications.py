"""Unit and integration tests for Multi-File Proof Libraries and Explicit Step Justifications."""

from pathlib import Path
import pytest

from aether import ProofChecker, StepStatus, ImportNode


@pytest.fixture
def checker() -> ProofChecker:
    return ProofChecker()


class TestStepJustifications:
    def test_valid_step_justification_with_hypothesis_label(self, checker: ProofChecker):
        src = """\
Theorem: "Justified step theorem"
Proof:
    Given x, y : Real
    Assume h1: x = y + 1
    Step: x = y + 1 [by h1]
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        step = report.results[2]
        assert step.status == StepStatus.VALID
        assert "justified by h1" in step.message

    def test_invalid_step_justification_out_of_scope(self, checker: ProofChecker):
        src = """\
Theorem: "Out of scope justification"
Proof:
    Given x : Real
    Step: x + 0 = x [by non_existent_label]
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        step = report.results[1]
        assert step.status == StepStatus.INVALID
        assert step.backend == "ScopeGuard"
        assert "Unknown or out-of-scope justification: 'non_existent_label'" in step.message

    def test_algebra_keyword_justification(self, checker: ProofChecker):
        src = """\
Theorem: "Algebra keyword justification"
Proof:
    Given k : Int
    Step: 4 * k^2 = 2 * (2 * k^2) [by algebra]
QED
"""
        report = checker.check_source(src)[0]
        assert report.is_valid, report.format_report()
        step = report.results[1]
        assert step.status == StepStatus.VALID
        assert step.backend == "SymPy"
        assert "justified by algebra" in step.message

    def test_algebra_keyword_fails_when_not_algebraic(self, checker: ProofChecker):
        src = """\
Theorem: "Algebra keyword failure"
Proof:
    Given x : Real
    Step: x + 1 = x + 2 [by algebra]
QED
"""
        report = checker.check_source(src)[0]
        assert not report.is_valid
        step = report.results[1]
        assert step.status == StepStatus.INVALID
        assert "Algebraic verification failed for step [by algebra]" in step.message

    def test_deduce_justification_with_lemma_name(self, checker: ProofChecker):
        src = """\
Lemma: "SquareNonNeg"
Claim: forall x : Real, x^2 >= 0

Theorem: "Use lemma justification"
Proof:
    Given a : Real
    Therefore a^2 >= 0 [by SquareNonNeg]
QED
"""
        reports = checker.check_source(src)
        assert len(reports) == 2
        thm_report = reports[1]
        assert thm_report.is_valid, thm_report.format_report()
        deduce_step = thm_report.results[1]
        assert deduce_step.status == StepStatus.VALID
        assert "justified by SquareNonNeg" in deduce_step.message


class TestMultiFileImports:
    def test_import_relative_file_and_lemma_reuse(self, tmp_path: Path):
        lib_file = tmp_path / "parity_lemmas.aether"
        lib_file.write_text(
            """\
Theorem: "EvenSquare"
Claim: forall n : Int, Even(n) => Even(n^2)
Proof:
    Given n : Int
    Assume h1: Even(n)
    Obtain k : Int such that n = 2 * k from h1
    Step: n^2 = (2 * k)^2
    Step: = 2 * (2 * k^2)
    Therefore exists m : Int, n^2 = 2 * m [witness: 2 * k^2]
    Hence Even(n^2)
QED
""",
            encoding="utf-8",
        )

        main_file = tmp_path / "main_proof.aether"
        main_file.write_text(
            """\
import "parity_lemmas.aether"

Theorem: "EvenFourthPower"
Claim: forall a : Int, Even(a) => Even(a^4)
Proof:
    Given a : Int
    Assume ha: Even(a)
    Therefore Even(a^2) [by EvenSquare]
    Let b = a^2
    Therefore Even(b)
    Therefore Even(b^2) [by EvenSquare]
    Step: a^4 = b^2
    Hence Even(a^4)
QED
""",
            encoding="utf-8",
        )

        checker = ProofChecker(base_dir=tmp_path)
        reports = checker.check_file(main_file)
        assert any(r.is_valid for r in reports)
        thm_report = next(r for r in reports if r.theorem_name == "EvenFourthPower")
        assert thm_report.is_valid, thm_report.format_report()

    def test_import_shared_function_definitions(self, tmp_path: Path):
        lib_file = tmp_path / "func_lib.aether"
        lib_file.write_text(
            """\
Let square(x) = x^2
Let cube(x) = x^3
""",
            encoding="utf-8",
        )

        main_file = tmp_path / "use_func.aether"
        main_file.write_text(
            """\
import "func_lib.aether"

Let a : Real
Assume ha: a = 3
Step: square(a) = 9
Step: cube(a) = 27
""",
            encoding="utf-8",
        )

        checker = ProofChecker(base_dir=tmp_path)
        reports = checker.check_file(main_file)
        assert len(reports) >= 1
        main_rep = reports[-1]
        assert main_rep.is_valid, main_rep.format_report()
        # Verify function steps succeeded
        step_square = [r for r in main_rep.results if "square(a)" in str(r.statement)][0]
        assert step_square.status == StepStatus.VALID

    def test_import_missing_file_diagnostic(self, tmp_path: Path):
        main_file = tmp_path / "missing_import.aether"
        main_file.write_text('import "nonexistent_lib.aether"\n', encoding="utf-8")

        checker = ProofChecker(base_dir=tmp_path)
        reports = checker.check_file(main_file)
        assert len(reports) == 1
        imp_res = reports[0].results[0]
        assert imp_res.status == StepStatus.INVALID
        assert imp_res.backend == "Library"
        assert "Import not found: 'nonexistent_lib.aether'" in imp_res.message

    def test_cyclic_import_detection(self, tmp_path: Path):
        file_a = tmp_path / "a.aether"
        file_b = tmp_path / "b.aether"

        file_a.write_text('import "b.aether"\nTheorem "A":\nProof:\n    Step: 1 = 1\nQED\n', encoding="utf-8")
        file_b.write_text('import "a.aether"\nTheorem "B":\nProof:\n    Step: 2 = 2\nQED\n', encoding="utf-8")

        checker = ProofChecker(base_dir=tmp_path)
        reports = checker.check_file(file_a)
        # Should detect cyclic import without infinite recursion
        all_results = [res for rep in reports for res in rep.results]
        cyclic_steps = [res for res in all_results if "Cyclic import detected" in res.message]
        assert len(cyclic_steps) > 0
        assert cyclic_steps[0].status == StepStatus.INVALID

    def test_transitive_imports(self, tmp_path: Path):
        f_base = tmp_path / "base.aether"
        f_base.write_text(
            """\
Theorem: "BaseLemma"
Claim: forall x : Real, x + 0 = x
""",
            encoding="utf-8",
        )

        f_mid = tmp_path / "mid.aether"
        f_mid.write_text(
            """\
import "base.aether"

Theorem: "MidLemma"
Claim: forall y : Real, y * 1 = y
""",
            encoding="utf-8",
        )

        f_top = tmp_path / "top.aether"
        f_top.write_text(
            """\
import "mid.aether"

Let z : Real
Step: z + 0 = z [by BaseLemma]
Step: z * 1 = z [by MidLemma]
""",
            encoding="utf-8",
        )

        checker = ProofChecker(base_dir=tmp_path)
        reports = checker.check_file(f_top)
        top_rep = reports[-1]
        assert top_rep.is_valid, top_rep.format_report()


LEMMA = """\
Theorem: "Even times even is even"
Claim: forall a : Int, Even(a) => Even(a * 2)
Proof:
    Given a : Int
    Assume h: Even(a)
    Obtain k : Int such that a = 2 * k from h
    Step: a * 2 = 2 * (2 * k)
    Hence Even(a * 2)
QED
"""

USES_LEMMA = """\
import "lemmas.aether"

Theorem: "Uses the lemma"
Proof:
    Given n : Int
    Assume h: Even(n)
    Therefore Even(n * 2)
QED
"""


class TestWorkspaceSources:
    """Imports resolved against files held in memory (the browser workspace)."""

    def test_a_sibling_file_is_imported(self, checker: ProofChecker):
        reports = checker.check_source(USES_LEMMA, sources={"lemmas.aether": LEMMA})
        assert all(r.is_valid for r in reports), "\n".join(r.format_report() for r in reports)
        assert "Imported 'lemmas.aether'" in reports[-1].results[0].message

    def test_a_relative_import_resolves_from_the_importers_folder(self, checker: ProofChecker):
        nested = USES_LEMMA.replace('"lemmas.aether"', '"../shared/lemmas.aether"')
        reports = checker.check_source(
            nested,
            file_path="sheets/week1.aether",
            sources={"shared/lemmas.aether": LEMMA, "sheets/week1.aether": nested},
        )
        assert all(r.is_valid for r in reports), "\n".join(r.format_report() for r in reports)

    def test_a_missing_workspace_file_is_named(self, checker: ProofChecker):
        reports = checker.check_source(USES_LEMMA, sources={"other.aether": LEMMA})
        message = reports[-1].results[0].message
        assert "Import not found: 'lemmas.aether'" in message and "the workspace" in message

    def test_a_cycle_inside_the_workspace_is_reported(self, checker: ProofChecker):
        a = 'import "b.aether"\nLet x : Real\nStep: x = x\n'
        b = 'import "a.aether"\nLet y : Real\nStep: y = y\n'
        reports = checker.check_source(a, file_path="a.aether", sources={"a.aether": a, "b.aether": b})
        assert "Cyclic import" in reports[-1].results[0].message

    def test_the_workspace_wins_over_a_file_on_disk(self, checker: ProofChecker, tmp_path: Path, monkeypatch):
        (tmp_path / "lemmas.aether").write_text('Theorem: "Broken"\nProof:\n    Step: 1 = 2\nQED\n')
        monkeypatch.chdir(tmp_path)
        reports = checker.check_source(USES_LEMMA, sources={"lemmas.aether": LEMMA})
        assert all(r.is_valid for r in reports)

    def test_an_edited_workspace_file_is_re_read(self, checker: ProofChecker):
        broken = LEMMA.replace("Step: a * 2 = 2 * (2 * k)", "Step: a * 2 = 3 * k")
        assert not checker.check_source(USES_LEMMA, sources={"lemmas.aether": broken})[-1].results[0].status == StepStatus.VALID
        assert checker.check_source(USES_LEMMA, sources={"lemmas.aether": LEMMA})[-1].results[0].status == StepStatus.VALID


CONDITIONAL = """\
Theorem: "Bigger"
Proof:
    Let x : Real
    Assume h: x > 2
    Therefore x > 1
QED
"""


class TestExportedClaimsKeepTheirHypotheses:
    """A proven conclusion is lent out with the assumptions it was proved under."""

    def test_an_imported_conclusion_does_not_hold_for_any_variable_of_that_name(self, checker: ProofChecker):
        main = 'import "lib.aether"\nLet x : Real\nStep: x > 1\n'
        step = checker.check_source(main, sources={"lib.aether": CONDITIONAL})[-1].results[-1]
        assert step.status == StepStatus.INVALID, step.message

    def test_it_still_applies_where_its_hypotheses_hold(self, checker: ProofChecker):
        main = 'import "lib.aether"\nLet y : Real\nAssume y > 2\nStep: y > 1 [by Bigger]\n'
        reports = checker.check_source(main, sources={"lib.aether": CONDITIONAL})
        assert all(r.is_valid for r in reports), "\n".join(r.format_report() for r in reports)

    def test_the_same_holds_between_theorems_in_one_file(self, checker: ProofChecker):
        src = CONDITIONAL + 'Theorem: "Abuse"\nProof:\n    Let x : Real\n    Therefore x > 1\nQED\n'
        abuse = checker.check_source(src)[-1]
        assert abuse.theorem_name == "Abuse" and not abuse.is_valid, abuse.format_report()

    def test_a_lemma_proved_under_a_hypothesis_is_reusable(self, checker: ProofChecker):
        lemma = LEMMA.replace('Claim: forall a : Int, Even(a) => Even(a * 2)\n', "")
        reports = checker.check_source(USES_LEMMA.replace("Therefore Even(n * 2)", "Therefore Even(n * 2) [by Even times even is even]"), sources={"lemmas.aether": lemma})
        assert all(r.is_valid for r in reports), "\n".join(r.format_report() for r in reports)

    def test_a_conclusion_about_a_witness_is_not_lent_out(self):
        thm = ProofChecker()._parser.parse(
            'Theorem: "W"\nProof:\n    Given n : Int\n    Assume h: Even(n)\n'
            "    Obtain k : Int such that n = 2 * k from h\n    Therefore n = 2 * k\nQED\n"
        ).theorems[0]
        claim = thm.proof.statements[-1].claim
        assert ProofChecker._close_claim(thm, claim) is None


class TestImportExtension:
    def test_the_extension_may_be_left_off(self, checker: ProofChecker):
        reports = checker.check_source(USES_LEMMA.replace('"lemmas.aether"', '"lemmas"'), sources={"lemmas.aether": LEMMA})
        assert all(r.is_valid for r in reports), "\n".join(r.format_report() for r in reports)

    def test_an_exact_name_is_tried_first(self, checker: ProofChecker):
        broken = 'Theorem: "Broken"\nProof:\n    Step: 1 = 2\nQED\n'
        reports = checker.check_source(
            USES_LEMMA.replace('"lemmas.aether"', '"lemmas"'),
            sources={"lemmas": LEMMA, "lemmas.aether": broken},
        )
        assert reports[-1].results[0].status == StepStatus.VALID

    def test_on_disk_too(self, tmp_path: Path):
        (tmp_path / "lemmas.aether").write_text(LEMMA, encoding="utf-8")
        main = tmp_path / "main.aether"
        main.write_text(USES_LEMMA.replace('"lemmas.aether"', '"lemmas"'), encoding="utf-8")
        reports = ProofChecker(base_dir=tmp_path).check_file(main)
        assert all(r.is_valid for r in reports), "\n".join(r.format_report() for r in reports)

    def test_pack_style_paths_resolve(self, checker: ProofChecker):
        main = 'import "@core/demo/even-times-even"\n' + USES_LEMMA.split("\n", 1)[1]
        reports = checker.check_source(main, sources={"@core/demo/even-times-even.aether": LEMMA})
        assert all(r.is_valid for r in reports), "\n".join(r.format_report() for r in reports)
