"""Aether — lightweight CNL proof checker.

Entry point for the `aether` CLI command (defined in pyproject.toml).
"""

from aether.parser.parser import AetherParser, ParseError
from aether.engine.checker import ProofChecker, ProofReport, StepResult, StepStatus
from aether.core.latex_export import export_to_latex
from aether.core.ast import ImportNode

__all__ = [
    "AetherParser",
    "ParseError",
    "ProofChecker",
    "ProofReport",
    "StepResult",
    "StepStatus",
    "ImportNode",
    "export_to_latex",
    "main",
]


def main() -> None:
    import sys

    args = sys.argv[1:]
    latex_mode = False
    if "--latex" in args:
        latex_mode = True
        args.remove("--latex")

    checker = ProofChecker()

    if args:
        path = args[0]
        try:
            with open(path, encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            print(f"aether: cannot open {path!r}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("aether: reading from stdin (Ctrl-D to finish)…", file=sys.stderr)
        source = sys.stdin.read()

    try:
        if latex_mode:
            latex_out = export_to_latex(source)
            print(latex_out)
            return

        reports = checker.check_source(source)
        all_valid = True
        for report in reports:
            print(report.format_report())
            if not report.is_valid:
                all_valid = False
        if not all_valid:
            sys.exit(1)
    except ParseError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
