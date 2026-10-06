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
usage: lemmata [--used] [--trace] [--latex] [FILE]

Check a proof written in Lemmata's notation, step by step, and print the
audit; exit status 1 if any step is invalid.  Reads FILE, or standard input
when no file is given.  (`aether` is the same command, under its old name.)

  --used      after the audit, list what each line was proved from
  --trace     after the audit, list each call made to SymPy and Z3 per line,
              with its answer and time
  --latex     print the proof as a LaTeX document instead of checking it
  --version   print the version
  --help      print this message
"""


def format_audit_trail(report: ProofReport, used: bool = False, trace: bool = False) -> str:
    """What each line was proved from (``used``) and the backend calls that
    checked it (``trace``), as the CLI prints them after the audit.  The app's
    Trace tab shows the same log."""
    lines = ["", "What each line used" if used and not trace else "Trace" if trace and not used else "What each line used, and the trace"]
    for result in report.all_results:
        status = result.status.value
        lines.append(f"  L{result.line if result.line is not None else '?':<4} {result.statement}  [{status}]")
        if used and status != "INVALID":
            names = []
            for p in result.premises:
                name = "the line before" if p["kind"] == "chain" else p.get("label")
                where = f"L{p['line']}" if p.get("line") is not None else p["kind"]
                names.append(f"{where} {name}: {p['fact']}" if name else f"{where}: {p['fact']}")
            if names:
                lines.extend(f"        used {n}" for n in names)
            elif result.premises_complete:
                lines.append("        used nothing earlier")
            if not result.premises_complete:
                lines.append("        (possibly more: the engine could not recover everything this line used)")
        if trace:
            for e in result.trace:
                indent = "  " * int(e.get("depth") or 0)
                lines.append(f"        {e['ms']:>7.1f} ms {indent}{e['backend']:<6} {e['call']:<9} {e['query']}  -> {e['result']}")
    return "\n".join(lines)


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
    used = "--used" in args
    tracing = "--trace" in args
    args = [a for a in args if a not in ("--used", "--trace")]

    checker = ProofChecker(dependencies=used, trace=tracing)

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
            if used or tracing:
                print(format_audit_trail(report, used=used, trace=tracing))
            if not report.is_valid:
                all_valid = False
        if not all_valid:
            sys.exit(1)
    except ParseError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
