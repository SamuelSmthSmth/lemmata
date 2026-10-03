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


USAGE = """\
usage: lemmata [--latex] [FILE]

Check a proof written in Lemmata's notation, step by step, and print the
audit; exit status 1 if any step is invalid.  Reads FILE, or standard input
when no file is given.  (`aether` is the same command, under its old name.)

  --latex     print the proof as a LaTeX document instead of checking it
  --version   print the version
  --help      print this message
"""


def main() -> None:
    import os
    import sys

    args = sys.argv[1:]
    prog = os.path.basename(sys.argv[0]) or "lemmata"
    if "--help" in args or "-h" in args:
        print(USAGE, end="")
        return
    if "--version" in args:
        from importlib.metadata import PackageNotFoundError, version

        try:
            print(f"{prog} {version('aether')}")
        except PackageNotFoundError:
            print(f"{prog} (development)")
        return
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
            print(f"{prog}: cannot open {path!r}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"{prog}: reading from stdin (Ctrl-D to finish)…", file=sys.stderr)
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
