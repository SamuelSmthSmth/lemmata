"""How big a step may be: the fragments a line can be decided in, and the levels.

A fragment is the kind of reasoning that settled a line, from an identity
(expand both sides) to a quantified statement Z3 decided outright.  Its
strength orders them; a level caps the strength each kind of step may use.
The numbers are those of the design paper (stage 1 of "A Proof Kernel for
Lemmata"): 1 identities, 2 linear arithmetic and logic, 3 non-linear
arithmetic, 4 evaluation and decision procedures, 5 quantified statements.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fragment:
    """A kind of reasoning: the tactic name the audit shows, and how strong it is."""

    tactic: str
    strength: int
    #: What the line needs, finishing "this line needs …".
    needs: str
    #: What to write instead when the level does not allow it.
    advice: str = ""


HYPOTHESIS = Fragment("hypothesis", 0, "a fact already established")
INDUCTION = Fragment("induction", 0, "the induction its blocks set up")
RING = Fragment("ring", 1, "algebra on the two sides")
LINEAR = Fragment("linarith", 2, "linear arithmetic and logic")
NONLINEAR = Fragment(
    "nlinarith",
    3,
    "non-linear arithmetic (products or powers of unknowns) decided in one step",
    "Break it into steps that each multiply or square one known inequality.",
)
RESIDUES = Fragment(
    "residues",
    4,
    "checking every remainder, which is not an argument a reader can follow",
    "Split into cases (n = 2k and n = 2k + 1, or by remainder mod the divisor) and show each.",
)
QUANTIFIED = Fragment(
    "auto",
    5,
    "a statement with quantifiers decided in one step",
    "Prove it in parts: introduce each variable with Given, assume what it is for, "
    "choose any witness with [witness: …], and show the rest step by step.",
)


def evaluation(gap: str) -> Fragment:
    """A derivative, integral, sum or limit evaluated outright; *gap* says what it skipped."""
    return Fragment("calculus.eval", 4, "an evaluation done in one step", gap)


@dataclass(frozen=True)
class Policy:
    """A level: the strongest fragment a chain link and a deduction may each use."""

    name: str
    step_max: int
    deduce_max: int
    #: Tactics allowed whatever their strength.
    also: frozenset[str] = field(default_factory=frozenset)

    def allows(self, fragment: Fragment, kind: str) -> bool:
        if fragment.tactic in self.also:
            return True
        return fragment.strength <= (self.step_max if kind == "step" else self.deduce_max)


LEVELS: dict[str, Policy] = {
    # Practising written answers: as the course level, but a derivative,
    # integral, limit or series must be worked, not evaluated in one line (the
    # Show your working option, as a level).  Capping chain links at linear
    # reasoning was tried and measured: on the course packs it refused 31
    # links, all of them steps a written answer takes in one line (an
    # inequality multiplied by a positive factor, a product that cancels).
    "exam": Policy("exam", step_max=3, deduce_max=3),
    # Lecture-note proofs: links may use non-linear arithmetic, and a limit,
    # derivative, integral or series may be evaluated as the standard result
    # the notes treat it as.  Measured on the MTH2008 / MTH2010 / Notation
    # packs (133 entries), this is the only thing the notes do in one line
    # that the stricter levels refuse: 21 entries, all evaluations.
    "course": Policy("course", step_max=3, deduce_max=3, also=frozenset({"calculus.eval"})),
    # Exploring: anything the solvers can decide, as the engine has always done.
    "scratch": Policy("scratch", step_max=5, deduce_max=5),
}
