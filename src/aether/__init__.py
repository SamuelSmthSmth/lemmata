"""Aether — lightweight CNL proof checker.

Entry point for the `aether` CLI command (defined in pyproject.toml).
"""

from aether.parser.parser import AetherParser, ParseError
from aether.engine.checker import ProofChecker, ProofReport, StepResult, StepStatus

__all__ = [
    "AetherParser",
    "ParseError",
    "ProofChecker",
    "ProofReport",
    "StepResult",
    "StepStatus",
    "main",
]


def main() -> None:
    import sys

    checker = ProofChecker()

    if len(sys.argv) > 1:
        path = sys.argv[1]
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
