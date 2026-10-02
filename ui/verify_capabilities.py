"""Hold the documented CNL capability surface to account.

``ui/README.md`` and ``USER_GUIDE.md`` advertise what an Aether proof may
contain, and where the engine stops.  Those claims are easy to make and easy to
lose, so every row below is a snippet plus the verdict it must still produce:

* ``VALID``       -- the snippet checks out (and, with strict domains on, still does)
* ``WARN``        -- it checks out but leaves a domain obligation unresolved
* ``INVALID``     -- the engine rejects it (``guard`` names the component, when it matters)
* ``PARSE_ERROR`` -- the grammar does not accept it at all
* ``EMPTY``       -- nothing to check
* ``TIMEOUT``     -- the snippet did not settle inside the per-probe budget

Rows with ``guard`` set are the deliberate refusals: monotonicity, capture and
generalisation guardrails.  Rows with ``gap`` set are known *gaps* -- things the
mathematics would allow but the grammar or a backend does not do yet.  Rows with
``why`` set are rejections that are neither: the engine is right to say no, and
the note says why, so the row is not mistaken for a shortcoming.  All three are
part of the documented surface, which is why they are pinned here rather than
left to prose.

Every snippet runs in a worker process with a wall-clock budget (``--budget``,
10s by default).  Z3's soft ``timeout`` is not honoured by its model-based
quantifier instantiation, so a single query can run for minutes -- bounding the
sweep keeps this tool a fast gate, while still reporting which snippet blew the
budget instead of quietly hanging.  ``TIMEOUT`` is therefore a *documented*
result for the pins that hit it, and a failure for anything else.

Run with:  uv run python ui/verify_capabilities.py
           uv run python ui/verify_capabilities.py --markdown   # doc-ready table
           uv run python ui/verify_capabilities.py --budget 30
"""

from __future__ import annotations

import multiprocessing
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aether import ParseError, ProofChecker  # noqa: E402


@dataclass
class Probe:
    area: str
    name: str
    source: str
    expect: str
    guard: str = ""
    gap: str = ""
    why: str = ""  # correct rejection: neither a guard nor a gap
    strict: str = ""  # verdict under strict_domains=True, when it differs
    backends: tuple[str, ...] = ()


PROBES: list[Probe] = [
    # --- declarations ------------------------------------------------------
    Probe("types", "Nat / Int / Rat / Real / Complex / Bool", "Let n : Nat\nStep: n + 0 = n", "VALID"),
    Probe("types", "several names at once", "Let x, y : Real\nStep: x + y = y + x", "VALID"),
    Probe("types", "Greek names", "Let \\epsilon : Real\nAssume h: \\epsilon > 0\nStep: \\epsilon / 2 > 0", "VALID"),
    Probe("types", "a value rather than a type", "Let y = 4\nStep: y^2 = 16", "VALID"),
    Probe("types", "unknown type is refused", "Let n : Banana\nStep: n = n", "INVALID", guard="Context"),
    Probe("types", "Nat carries non-negativity", "Let n : Nat\nTherefore n >= 0", "VALID"),
    Probe("types", "Int does not", "Let n : Int\nTherefore n >= 0", "INVALID", backends=("Z3",)),
    # --- mathematical constants -------------------------------------------
    Probe("constant", "\\pi is the number", "Step: sin(\\pi) = 0", "VALID"),
    Probe("constant", "e is the number", "Step: ln(e) = 1", "VALID"),
    Probe("constant", "the solver knows a bound", "Step: pi > 3", "VALID"),
    Probe("constant", "a looser bound is not known", "Step: pi > 3.5", "INVALID",
          why="the SMT backend carries only `3.14159265 < pi < 3.14159266`, so a comparison it cannot settle is refused"),
    Probe("constant", "a declared name is a variable again", "Let pi : Real\nAssume h: pi = 5\nStep: pi^2 = 25", "VALID"),
    Probe("constant", "a structure's e stays its identity", "Assume Group(G, op, e, inv)\nGiven a : Real\nStep: op(a, e) = a", "VALID"),
    # --- expressions -------------------------------------------------------
    Probe("expr", "abs / min / max", "Let a, b : Real\nStep: max(a, b) >= min(a, b)", "VALID"),
    Probe("expr", "powers", "Let k : Int\nStep: 3^(k + 1) = 3 * 3^k", "VALID"),
    Probe("expr", "sqrt", "Let x : Real\nAssume h: x >= 0\nStep: sqrt(x^2) = x", "VALID"),
    Probe("expr", "exp / ln", "Let x : Real\nAssume h: x > 0\nStep: ln(exp(x)) = x", "VALID"),
    Probe("expr", "trig identity", "Let x : Real\nStep: sin(x)^2 + cos(x)^2 = 1", "VALID"),
    Probe("expr", "derivative", "Let x : Real\nStep: diff(x^2, x) = 2 * x", "VALID"),
    Probe("expr", "indefinite integral", "Let x : Real\nStep: integrate(2 * x, x) = x^2", "VALID"),
    Probe("expr", "definite integral", "Step: integrate(x, x, 0, 1) = 1 / 2", "VALID"),
    Probe("expr", "LaTeX integral", "Step: \\int_{0}^{1} 2 * x dx = 1", "VALID"),
    Probe("expr", "limit", "Step: lim(sin(x) / x, x, 0) = 1", "VALID"),
    Probe("expr", "LaTeX limit", "Step: \\lim_{x -> 0} sin(x) / x = 1", "VALID"),
    Probe("expr", "directional limit", 'Step: lim(1 / (x + 1), x, 0, "+") = 1', "VALID"),
    Probe("expr", "summation, functional", "Let n : Nat\nStep: sum(k, 1, n, 1) = n", "VALID"),
    Probe("expr", "summation, LaTeX", "Let n : Nat\nStep: \\sum_{k=1}^{n} 1 = n", "VALID"),
    Probe("expr", "factorial", "Let n : Nat\nStep: n! = n * (n - 1)!", "VALID"),
    Probe("expr", "a call with the wrong arity is named", "Let x : Real\nStep: abs(x, x) = x", "INVALID",
          why="the arity is reported; unchecked, `Abs(x, x)` raised a TypeError that escaped `check_source` entirely"),
    Probe("expr", "ln takes no base", "Let x : Real\nStep: ln(8, 2) = 3", "INVALID",
          why="`ln` is the natural log and takes one argument; a second used to be read silently as a base"),
    Probe("expr", "the solver knows the range of exp / sin / cos", "Let x : Real\nStep: exp(x) > 0", "VALID"),
    Probe("expr", "beyond their ranges, exp / log / trig are opaque", "Let x : Real\nAssume h: x >= 0\nStep: exp(x) >= 1 + x + x^2 / 2", "INVALID",
          gap="Z3 has no theory of exp/log/trig, only true range facts (sin and cos within [-1, 1], exp > 0, exp(t) >= 1 + t, ...), so an inequality needing more cannot be decided; the message says so instead of presenting a bare counterexample, and equalities still go to SymPy"),
    # --- sets and matrices -------------------------------------------------
    Probe("sets", "union / intersect / \\emptyset", "Let S : Set\nStep: S union \\emptyset = S\nStep: S intersect \\emptyset = \\emptyset", "VALID"),
    Probe("sets", "subset, infix", "Let A, B, C : Set\nAssume h1: A subset B\nAssume h2: B subset C\nTherefore A subset C", "VALID"),
    Probe("sets", "membership", "Let S : Set\nLet x : Real\nAssume h: x \\in S\nTherefore not (x \\notin S)", "VALID"),
    Probe("sets", "\\varnothing alias", "Let S : Set\nStep: S union \\varnothing = S", "VALID"),
    Probe("sets", "set literals", "Let S = {1, 2, 3}\nStep: 1 \\in S", "PARSE_ERROR",
          gap="no {a, b, c} notation; declare and relate instead"),
    Probe("matrix", "product / det / tr / transpose", "Let A = [[1, 2], [3, 4]]\nLet B = [[2, 0], [1, 2]]\nStep: A * B = [[4, 4], [10, 8]]\nStep: det(A) = -2\nStep: tr(A) = 5\nStep: A^T = [[1, 3], [2, 4]]", "VALID"),
    Probe("matrix", "dot and Orthogonal", "Let u = [1, 2]\nLet v = [-2, 1]\nStep: dot(u, v) = 0\nTherefore Orthogonal(u, v)", "VALID"),
    Probe("matrix", "inverse of a square matrix", "Let A = [[1, 2], [3, 4]]\nStep: inverse(A) * A = [[1, 0], [0, 1]]", "VALID"),
    Probe("matrix", "inverse(A) = the adjugate over the determinant", "Let A = [[1, 2], [3, 4]]\nStep: inverse(A) = [[-2, 1], [3 / 2, -1 / 2]]", "VALID"),
    Probe("matrix", "a wrong product is caught", "Let A = [[1, 2], [3, 4]]\nLet B = [[2, 0], [1, 2]]\nStep: A * B = [[1, 1], [1, 1]]", "INVALID", backends=("SymPy",)),
    # --- algebraic structures ---------------------------------------------
    Probe("algebra", "Group identity", "Assume Group(G, op, e, inv)\nGiven a : Real\nStep: op(a, e) = a", "VALID"),
    Probe("algebra", "Group inverse", "Assume Group(G, op, e, inv)\nGiven a : Real\nStep: op(a, inv(a)) = e", "VALID"),
    Probe("algebra", "a plain Group is not commutative", "Assume Group(G, op, e, inv)\nGiven a, b : Real\nTherefore op(a, b) = op(b, a)", "INVALID",
          why="a plain Group does not entail commutativity: the two sides reduce to different words in the free group, which is itself a group, so no solver search is needed"),
    Probe("algebra", "AbelianGroup is", "Assume AbelianGroup(G, op, e, inv)\nGiven a, b : Real\nTherefore op(a, b) = op(b, a)", "VALID"),
    Probe("algebra", "Ring distributes", "Assume Ring(R, add, mul, zero, one, neg)\nGiven a, b, c : Real\nStep: mul(a, add(b, c)) = add(mul(a, b), mul(a, c))", "VALID"),
    # --- logic, quantifiers, predicates -----------------------------------
    Probe("logic", "existential witness", "Let n : Int\nAssume h1: Even(n)\nObtain k : Int such that n = 2 * k from h1\nTherefore exists m : Int, n = 2 * m [witness: k]", "VALID"),
    Probe("logic", "and / or / not", "Let a, b : Int\nAssume h: Even(a) and Even(b)\nTherefore Even(a)", "VALID"),
    Probe("logic", "nested quantifiers", "Let f : Int\nStep: f = f\nTherefore forall n : Int, exists m : Int, m = n", "VALID"),
    Probe("logic", "forall over a free variable", "Let x : Real\nStep: x + 0 = x\nTherefore forall y : Real, y + 0 = y", "VALID"),
    Probe("logic", "biconditional in a hypothesis", "Let a : Int\nAssume h: Even(a) <=> Odd(a + 1)\nTherefore Odd(a + 1)", "INVALID",
          why="a biconditional entails neither side alone -- it also holds when both are false, so a=1 (Even(1) false, Odd(2) false) is a genuine counterexample"),
    Probe("predicate", "Even / Odd / MultipleOf / Divides", "Let n : Int\nAssume h: Even(n)\nObtain k : Int such that n = 2 * k from h\nTherefore MultipleOf(n, 2)", "VALID"),
    Probe("predicate", "Positive implies NonNegative", "Let x : Real\nAssume h: Positive(x)\nTherefore NonNegative(x)", "VALID"),
    Probe("predicate", "Congruent", "Let a, b, m : Int\nAssume h: Congruent(a, b, m)\nTherefore Divides(m, a - b)", "VALID"),
    Probe("predicate", "a = b (mod m)", "Let a, m : Int\nStep: a = a (mod m)", "VALID"),
    Probe("predicate", "\\equiv \\pmod", "Let a, b, m : Int\nStep: a \\equiv b \\pmod{m} => Congruent(a, b, m)", "VALID"),
    Probe("predicate", "Define, then use both ways", "Define MyRel(a, b) <=> a = b\n\nLet x, y : Real\nAssume h: MyRel(x, y)\nTherefore MyRel(x, y)", "VALID"),
    Probe("predicate", "an undefined predicate proves nothing", "Let x, y : Real\nAssume h: MyRel(x, y)\nStep: x = y", "INVALID", backends=("SymPy",),
          gap="unknown predicates are uninterpreted and unrelated to ="),
    # --- structure ---------------------------------------------------------
    Probe("structure", "sections of a proof", "Theorem: \"Two\"\nProof:\n    Let x : Real\n    Step: x + 0 = x\nQED\n\nTheorem: \"Three\"\nProof:\n    Let y : Real\n    Step: y * 1 = y\nQED", "VALID"),
    Probe("structure", "scratchpad, no Theorem", "Let x : Real\nStep: x + 0 = x", "VALID"),
    Probe("structure", "cases", "Let x : Real\nAssume h: x >= 0 or x < 0\nCase x >= 0:\n    Step: x >= 0\nCase x < 0:\n    Step: x < 0", "VALID"),
    Probe("structure", "induction", "Theorem: \"Sum of odds\"\nClaim: forall n : Nat, sum(k, 1, n, 2 * k - 1) = n^2\nProof:\n    Base case n = 0:\n        Step: sum(k, 1, 0, 2 * k - 1) = 0\n        Step: = 0^2\n    Inductive step:\n        Fix n : Nat\n        Assume ih: sum(k, 1, n, 2 * k - 1) = n^2\n        Step: sum(k, 1, n + 1, 2 * k - 1) = n^2 + (2 * (n + 1) - 1)\n        Step: = n^2 + 2 * n + 1\n        Step: = (n + 1)^2\n    Therefore forall n : Nat, sum(k, 1, n, 2 * k - 1) = n^2\nQED", "VALID"),
    Probe("structure", "Subproof", "Theorem: \"Implication\"\nProof:\n    Subproof:\n        Assume h: Even(4)\n        Therefore MultipleOf(4, 2)\nQED", "VALID"),
    Probe("structure", "justification [by ...]", "Let k : Int\nStep: 2 * (2 * k^2) = 4 * k^2 [by algebra]", "VALID"),
    Probe("structure", "justification [using ...]", "Let k, n : Int\nAssume h1: n = 2 * k\nStep: n = 2 * k [using h1]", "VALID"),
    Probe("structure", "Claim is discharged by QED", "Theorem: \"Goal\"\nClaim: forall n : Int, Even(n) => MultipleOf(n^2, 4)\nProof:\n    Given n : Int\n    Assume hn: Even(n)\n    Obtain k : Int such that n = 2 * k from hn\n    Step: n^2 = 4 * k^2\n    Hence MultipleOf(n^2, 4)\nQED", "VALID"),
    Probe("structure", "a Claim that is not established", "Theorem: \"Wrong goal\"\nClaim: 1 = 2\nProof:\n    Step: 1 = 1\nQED", "INVALID", guard="QED"),
    Probe("structure", "restating the forall yourself", "Theorem: \"Overstated\"\nClaim: forall n : Int, Even(n) => Even(n^2)\nProof:\n    Given n : Int\n    Assume h1: Even(n)\n    Therefore forall n : Int, Even(n) => Even(n^2)\nQED", "INVALID", guard="ScopeGuard",
          gap="prove the body under Given/Assume and let QED discharge it"),
    Probe("structure", "import", "import \"lemmas.aether\"\n\nTheorem: \"Imported\"\nProof:\n    Let x : Real\n    Step: x + 0 = x\nQED", "INVALID", guard="Library",
          gap="the engine looks in the importing file's directory, then a `base_dir`, then the process working directory; the UI passes only source text, so it has nothing to resolve against"),
    # --- the guardrails ----------------------------------------------------
    Probe("guard", "chain continues a strict inequality", "Let x : Real\nAssume h: x > 2\nStep: (x^2 - 4) / (x - 2) = x + 2\nStep: > 4", "VALID"),
    Probe("guard", "chain mixes directions", "Let x : Real\nAssume h: x >= 3\nStep: x >= 3\nStep: <= 5", "INVALID", guard="ChainGuard"),
    Probe("guard", "chained step with no anchor", "Let x : Real\nStep: > 1", "INVALID", guard="ChainGuard"),
    Probe("guard", "witness would shadow a variable", "Let k : Int\nAssume h: Even(k)\nObtain k : Int such that k = 2 * k from h", "INVALID", guard="Context"),
    Probe("guard", "generalising a constrained variable", "Let x : Real\nAssume h: x > 0\nTherefore forall x : Real, x > 0", "INVALID", guard="ScopeGuard"),
    Probe("guard", "unresolved domain obligation", "Let x : Real\nStep: (x^2 - 4) / (x - 2) = x + 2", "WARN", strict="INVALID", backends=("SymPy",)),
    Probe("guard", "an assumption can discharge it", "Let x : Real\nAssume h: x > 2\nStep: (x^2 - 4) / (x - 2) = x + 2", "VALID"),
    Probe("guard", "sqrt needs its radicand bounded", "Let x : Real\nAssume h: x >= 0\nStep: sqrt(x^2) = x", "VALID"),
    Probe("guard", "a logarithm's argument is not obliged positive", "Let x : Real\nStep: ln(x) = ln(x)", "VALID",
          gap="positivity of `ln`'s argument is not extracted, so `ln(x)` needs no `x > 0` in scope; the solver now discharges `exp(x) > 0`, so `ln(exp(x)) = x` would survive the check"),
    # --- grammar edges -----------------------------------------------------
    Probe("grammar", "hash comments", "# a comment\nLet x : Real\nStep: x + 0 = x", "VALID"),
    Probe("grammar", "slash slash comments", "// a comment\nLet x : Real\nStep: x + 0 = x", "PARSE_ERROR",
          gap="`#` and `--` each start a comment; `//` does not"),
    Probe("grammar", "CRLF line endings", "Let x : Real\r\nStep: x + 0 = x\r\n", "VALID"),
    Probe("grammar", "unicode quantifier", "Therefore \u2200 x : Real, x = x", "VALID"),
    Probe("grammar", "unicode comparison", "Let x : Real\nAssume h: x \u2264 2\nStep: x < 3", "VALID"),
    Probe("grammar", "reason: instead of by:", "Let k : Int\nStep: 2 * k + 2 * k = 4 * k [reason: algebra]", "PARSE_ERROR",
          gap="the bracket takes [by ...] or [using ...]"),
    Probe("grammar", "indentation is load-bearing", "Theorem: \"Bad\"\nProof:\nGiven n : Int\nStep: n = n\nQED", "PARSE_ERROR"),
    Probe("grammar", "unknown keyword", "Frobnicate n : Int", "PARSE_ERROR"),
    Probe("grammar", "empty source", "", "EMPTY"),
]


def check_source(source: str, strict: bool) -> tuple[str, set[str]]:
    """Run one snippet and fold its step results into a single verdict."""
    checker = ProofChecker(strict_domains=strict)
    try:
        reports = checker.check_source(source)
    except ParseError:
        return "PARSE_ERROR", set()
    results = [result for report in reports for result in report.results]
    if not results:
        return "EMPTY", set()
    statuses = [result.status.value for result in results]
    if all(status == "VALID" for status in statuses):
        verdict = "VALID"
    elif any(status == "INVALID" for status in statuses):
        verdict = "INVALID"
    else:
        verdict = "WARN"
    backends = {result.backend for result in results if result.status.value != "VALID"}
    return verdict, backends


def _worker(conn: multiprocessing.connection.Connection) -> None:
    """Serve verdicts to the parent until it closes the pipe or kills us."""
    while True:
        try:
            request = conn.recv()
        except (EOFError, KeyboardInterrupt):
            return
        if request is None:
            return
        source, strict = request
        verdict, backends = check_source(source, strict)
        conn.send((verdict, sorted(backends)))


class Sweeper:
    """Run snippets in a reusable worker, killing it when it overstays its budget."""

    def __init__(self, budget: float) -> None:
        self.budget = budget
        self.method = "fork" if "fork" in multiprocessing.get_all_start_methods() else "spawn"
        self._ctx = multiprocessing.get_context(self.method)
        self._proc: multiprocessing.process.BaseProcess | None = None
        self._conn: multiprocessing.connection.Connection | None = None
        self.timeouts: list[str] = []

    def _start(self) -> None:
        parent, child = self._ctx.Pipe()
        proc = self._ctx.Process(target=_worker, args=(child,), daemon=True)
        proc.start()
        child.close()
        self._proc, self._conn = proc, parent

    def _stop(self) -> None:
        if self._proc is not None:
            try:
                if self._conn is not None:
                    self._conn.close()
            except (OSError, ValueError):
                pass
            self._proc.terminate()
            self._proc.join(5)
            if self._proc.is_alive():
                self._proc.kill()
                self._proc.join(5)
        self._proc, self._conn = None, None

    def close(self) -> None:
        self._stop()

    def verdict(self, source: str, strict: bool, label: str) -> tuple[str, set[str]]:
        if self._proc is None:
            self._start()
        assert self._conn is not None
        try:
            self._conn.send((source, strict))
        except (BrokenPipeError, OSError):
            self._stop()
            self._start()
            assert self._conn is not None
            self._conn.send((source, strict))
        if not self._conn.poll(self.budget):
            # Z3 will happily spend minutes inside a single check(); the worker is
            # not coming back, so drop it and report the snippet as out of budget.
            self._stop()
            self.timeouts.append(label)
            return "TIMEOUT", set()
        verdict, backends = self._conn.recv()
        return verdict, set(backends)


def render_table(rows: list[tuple[str, str, str, str, str]]) -> list[str]:
    """Render *rows* as the doc-ready markdown table, header first."""
    lines = ["| Feature | Verdict | Notes |", "| --- | --- | --- |"]
    for area, name, verdict, note, strict in rows:
        detail = note or (
            "unresolved obligation is an error under strict checking" if strict else ""
        )
        lines.append(f"| {area} \u00b7 `{name}` | {verdict} | {detail} |")
    return lines


def guide_table(text: str) -> list[str]:
    """Return the capability table embedded in ``USER_GUIDE.md``, if present."""
    raw = text.splitlines()
    start = next(
        (i for i, line in enumerate(raw) if line.strip() == "| Feature | Verdict | Notes |"),
        None,
    )
    if start is None:
        return []
    table: list[str] = []
    for line in raw[start:]:
        if not line.startswith("|"):
            break
        table.append(line)
    return table


def main(argv: list[str]) -> int:
    markdown = "--markdown" in argv
    budget = 10.0
    if "--budget" in argv:
        budget = float(argv[argv.index("--budget") + 1])
    failures: list[str] = []
    rows: list[tuple[str, str, str, str, str]] = []
    sweeper = Sweeper(budget=budget)
    started = time.time()
    try:
        for probe in PROBES:
            label = f"{probe.area}/{probe.name}"
            verdict, backends = sweeper.verdict(probe.source, False, label)
            if verdict != probe.expect:
                failures.append(f"{label}: expected {probe.expect}, got {verdict}")
            if probe.strict:
                strict_verdict, _ = sweeper.verdict(probe.source, True, f"{label} (strict)")
                if strict_verdict != probe.strict:
                    failures.append(
                        f"{label}: strict expected {probe.strict}, got {strict_verdict}"
                    )
            if probe.guard and probe.guard not in backends:
                failures.append(
                    f"{label}: expected {probe.guard} to reject, backends were "
                    f"{sorted(backends) or 'none'}"
                )
            note = probe.gap or probe.guard or probe.why
            rows.append((probe.area, probe.name, verdict, note, probe.strict))
    finally:
        sweeper.close()
    elapsed = time.time() - started

    if markdown:
        for line in render_table(rows):
            print(line)
        return 1 if failures else 0

    print(f"Aether CNL capability matrix ({len(rows)} snippets in {elapsed:.1f}s, budget {budget:g}s each)")
    print("=" * 100)
    area = ""
    for _, name, verdict, note, strict in rows:
        if _ != area:
            area = _
            print(f"\n-- {area} " + "-" * (95 - len(area)))
        suffix = f"  [{note}]" if note else ""
        print(f"  {verdict:<12} {name}{suffix}")
    counts: dict[str, int] = {}
    for _, _, verdict, _, _ in rows:
        counts[verdict] = counts.get(verdict, 0) + 1
    print()
    print("  " + ", ".join(f"{count} {verdict}" for verdict, count in sorted(counts.items())))
    print(f"  {len([row for row in rows if row[3]])} documented guardrails/gaps/caveats")
    if sweeper.timeouts:
        print(f"  {len(sweeper.timeouts)} over budget (> {budget:g}s): " + "; ".join(sweeper.timeouts))

    # The guide's copy of this table is what readers actually see, so hold it to
    # the pins too: a flipped expectation that never reaches the doc is a lie in
    # the documentation, which is exactly what this tool exists to prevent.
    guide_path = Path(__file__).resolve().parent.parent / "USER_GUIDE.md"
    try:
        in_guide = guide_table(guide_path.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - only when the guide is absent
        in_guide = []
        failures.append(f"could not read {guide_path.name}: {exc}")
    if in_guide != render_table(rows):
        failures.append(
            f"{guide_path.name} capability table has drifted from the pins "
            f"({len(in_guide)} rows in the guide, {len(rows) + 2} generated); "
            f"re-run with --markdown and paste the table back in"
        )

    if failures:
        print(f"\n{len(failures)} capability claim(s) drifted:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nall capability claims hold")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
