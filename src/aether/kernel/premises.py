"""What a step may use: premise selection.

A step that cites its premises (`[using h1]`, `Since A, …`, `By h1, …`, a
result cited by name) may use those and nothing else, apart from what is
part of the setting rather than an argument: a structure assumed with
`Assume Group(G, op, e, inv)`, and the definition of a sequence the proof
declared.  A step that cites nothing may use everything in scope, as the
engine always has; the audit then names what it did use (`evidence`).
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from aether.core.ast import ExprNode, FunctionCallNode
from aether.engine.context import HypothesisInfo, ProofContext

#: Assumptions that set up a structure rather than state a fact about it.
_STRUCTURES = {"group", "abeliangroup", "ring", "field", "subgroup", "normalsubgroup"}


def cited_labels(justification: Optional[str], ctx: ProofContext) -> list[HypothesisInfo]:
    """The hypotheses a justification names by label (`h1`, `h1, h2`, `h1 and hk`)."""
    if not justification:
        return []
    raw = justification.strip().strip("[]\"'")
    raw = re.sub(r"^(by|using)\s+", "", raw, flags=re.IGNORECASE)
    found: list[HypothesisInfo] = []
    for part in re.split(r"[,;]|\band\b", raw):
        h = ctx.get_hypothesis(part.strip().strip("\"'"))
        if h is not None and not any(h is f for f in found):
            found.append(h)
    return found


def select(
    cited: list[HypothesisInfo],
    ctx: ProofContext,
    is_definition: Callable[[ExprNode, ProofContext], bool],
) -> list[HypothesisInfo]:
    """The hypotheses a step may use, given what it cites (nothing cited: all of them)."""
    everything = ctx.all_hypotheses()
    if not cited:
        return everything
    allowed = list(cited)
    for h in everything:
        if any(h is a for a in allowed):
            continue
        if _is_setting(h.proposition) or is_definition(h.proposition, ctx):
            allowed.append(h)
    return allowed


def _is_setting(prop: ExprNode) -> bool:
    return isinstance(prop, FunctionCallNode) and prop.func.lower() in _STRUCTURES


@contextmanager
def restricted(ctx: ProofContext, allowed: list[HypothesisInfo]) -> Iterator[None]:
    """Let *ctx* show only *allowed* hypotheses for the duration.

    Facts the step adds meanwhile (its own conclusion) are kept afterwards.
    While restricted, ``ctx.kernel_full_hypotheses`` holds the frames' full
    lists, for checks that are not part of the step's argument (a domain
    side condition may use anything in scope)."""
    keep = {id(h) for h in allowed}
    saved = [(frame, list(frame.hypotheses)) for frame in ctx._frames]
    for frame, hyps in saved:
        frame.hypotheses[:] = [h for h in hyps if id(h) in keep]
    ctx.kernel_full_hypotheses = saved  # type: ignore[attr-defined]
    try:
        yield
    finally:
        ctx.kernel_full_hypotheses = None  # type: ignore[attr-defined]
        for frame, hyps in saved:
            added = [h for h in frame.hypotheses if not any(h is o for o in hyps)]
            frame.hypotheses[:] = hyps + added


@contextmanager
def unrestricted(ctx: ProofContext) -> Iterator[None]:
    """Inside ``restricted``, show every hypothesis again (for side conditions)."""
    saved = getattr(ctx, "kernel_full_hypotheses", None)
    if not saved:
        yield
        return
    current = [(frame, list(frame.hypotheses)) for frame in ctx._frames]
    for frame, hyps in saved:
        frame.hypotheses[:] = hyps
    try:
        yield
    finally:
        for frame, hyps in current:
            frame.hypotheses[:] = hyps
