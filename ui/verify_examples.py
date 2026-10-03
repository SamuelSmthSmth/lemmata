"""Guard the ``expected`` blurbs shown in the UI against engine drift.

The example proofs in ``ui/examples.py`` advertise a specific outcome to the
user.  This script asserts each one actually produces that outcome, so an
engine change that silently invalidates a bundled example fails loudly.

Run with:  uv run python ui/verify_examples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aether import ParseError, ProofChecker  # noqa: E402

from ui.examples import EXAMPLES  # noqa: E402

# id -> (expected kind, expect a counterexample on some failing step)
EXPECTATIONS: dict[str, tuple[str, bool]] = {
    "even-square": ("VALID", False),
    "odd-square": ("VALID", False),
    "algebraic-blunder": ("INVALID", True),
    "unguarded-division": ("WARN", False),
    "guarded-division": ("VALID", False),
    "variable-capture": ("INVALID", False),
    "false-deduction": ("INVALID", True),
    "parse-error": ("PARSE_ERROR", False),
    "mathematical-induction": ("VALID", False),
    "epsilon-delta-continuity": ("VALID", False),
    "claim-goal-verification": ("VALID", False),
    "custom-predicate-definitions": ("VALID", False),
    "complex-analysis-cauchy-riemann": ("VALID", False),
    "linear-algebra-matrix-ops": ("VALID", False),
    "set-theory-identities": ("VALID", False),
    "calculus-and-ode": ("VALID", False),
    "group-theory-shoes-and-socks": ("VALID", False),
    "modular-arithmetic-congruence": ("VALID", False),
    "step-justifications-and-lemmas": ("VALID", False),
}


def classify(source: str, strict_domains: bool = False) -> tuple[str, bool]:
    """Return (verdict, saw_counterexample) for a source string."""
    try:
        reports = ProofChecker(strict_domains=strict_domains).check_source(source)
    except ParseError:
        return "PARSE_ERROR", False

    if any(not r.is_valid for r in reports):
        verdict = "INVALID"
    elif any(r.has_warnings for r in reports):
        verdict = "VALID (with domain warnings)"
    else:
        verdict = "VALID"

    saw_cex = any(
        result.counterexample for report in reports for result in report.results
    )
    return verdict, saw_cex


def main() -> int:
    failures: list[str] = []

    for example in EXAMPLES:
        key = example["id"]
        if key not in EXPECTATIONS:
            failures.append(f"{key}: no expectation registered")
            continue
        kind, want_cex = EXPECTATIONS[key]
        verdict, saw_cex = classify(example["source"])

        if kind == "PARSE_ERROR" and verdict != "PARSE_ERROR":
            failures.append(f"{key}: expected a parse error, got {verdict}")
        elif kind == "WARN" and verdict != "VALID (with domain warnings)":
            failures.append(f"{key}: expected a warning, got {verdict}")
        elif kind in ("VALID", "INVALID") and verdict != kind:
            failures.append(f"{key}: expected {kind}, got {verdict}")

        if want_cex and not saw_cex:
            failures.append(f"{key}: expected a counterexample, none reported")

        marker = "ok " if not any(f.startswith(f"{key}:") for f in failures) else "FAIL"
        print(f"  [{marker}] {key:<20} -> {verdict}")

        # The unguarded-division example promises the strict toggle flips it.
        if kind == "WARN":
            strict_verdict, _ = classify(example["source"], strict_domains=True)
            if strict_verdict != "INVALID":
                failures.append(
                    f"{key}: strict mode should yield INVALID, got {strict_verdict}"
                )
            print(f"  [{'ok ' if strict_verdict == 'INVALID' else 'FAIL'}] "
                  f"{key:<20} -> {strict_verdict} (strict mode)")

    # The standalone proofs in examples/ are listed in the Library with the
    # verdict ui/app.py records for them; hold them to it.
    from ui.app import EXAMPLE_FILES_DIR, EXAMPLE_FILE_VERDICTS

    word = {"VALID": "VALID", "WARN": "VALID (with domain warnings)", "INVALID": "INVALID"}
    files = sorted(EXAMPLE_FILES_DIR.glob("*.aether"))
    for path in files:
        want = word[EXAMPLE_FILE_VERDICTS.get(path.name, "VALID")]
        verdict, _ = classify(path.read_text(encoding="utf-8"))
        if verdict != want:
            failures.append(f"examples/{path.name}: listed as {want}, got {verdict}")
        print(f"  [{'ok ' if verdict == want else 'FAIL'}] examples/{path.name:<28} -> {verdict}")
    for name in EXAMPLE_FILE_VERDICTS:
        if not (EXAMPLE_FILES_DIR / name).exists():
            failures.append(f"examples/{name}: has a recorded verdict but no file")

    if len(EXAMPLES) != len(EXPECTATIONS):
        failures.append(
            f"{len(EXAMPLES)} examples but {len(EXPECTATIONS)} expectations registered"
        )

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"all {len(EXAMPLES)} examples and {len(files)} example files behave as advertised")
    return 0


if __name__ == "__main__":
    sys.exit(main())
