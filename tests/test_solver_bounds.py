"""Z3 is bounded by work, not time, so a verdict does not depend on the machine."""

from __future__ import annotations

import inspect

from aether.engine import logic


def test_every_solver_is_bounded_by_work() -> None:
    source = inspect.getsource(logic)
    assert source.count("z3.Solver()") == 1, "solvers are made by new_solver(), which sets the rlimit"
    assert 'set("timeout", timeout_ms)' not in source


def test_the_work_limit_stops_a_hopeless_query_on_any_machine() -> None:
    import z3

    x, y, z = z3.Reals("x y z")
    solver = logic.new_solver(100)
    # x^3 + y^3 = z^3 over small positive integers written as reals: no
    # solution exists (Fermat, n = 3), but z3's nonlinear real arithmetic
    # cannot show it cheaply.  It must give up on work, not on the clock.
    solver.add(x > 0, y > 0, z > 0, x * x * x + y * y * y == z * z * z, z3.Or([x == i for i in range(1, 40)]), z3.Or([y == i for i in range(1, 40)]), z3.Or([z == i for i in range(1, 60)]))
    assert solver.check() == z3.unknown
    assert "resource limit" in solver.reason_unknown()


def test_a_caller_cannot_bring_back_a_short_wall_clock() -> None:
    assert logic.SOLVER_BACKSTOP_MS >= 5000
    assert logic.SOLVER_RLIMIT >= 100_000


def test_a_budget_raised_as_an_exception_is_unknown():
    """The WebAssembly Z3 can raise its resource limit instead of answering
    unknown; check_solver must treat both the same, not crash the check."""
    import z3

    from aether.engine.logic import check_solver, new_solver

    class Raising(z3.Solver):
        def check(self, *args):
            raise z3.Z3Exception(b"max. resource limit exceeded")

    solver = new_solver(1000)
    solver.__class__ = Raising
    assert check_solver(solver) == z3.unknown

    class Broken(z3.Solver):
        def check(self, *args):
            raise z3.Z3Exception(b"invalid argument")

    solver = new_solver(1000)
    solver.__class__ = Broken
    try:
        check_solver(solver)
    except z3.Z3Exception:
        pass
    else:
        raise AssertionError("an error that is not the budget must still surface")
