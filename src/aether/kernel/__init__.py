"""The proof kernel: what a line may use, which rule shows it, and how big a step it may take.

The design is "A Proof Kernel for Lemmata".  A line that cites its premises
is checked with those alone (``premises``).  Inside the typed core (``core``)
the weakest tactic that proves the line is the verdict (``tactics``); outside
it, named rules show derivatives, integrals, limits and sums (``calculus``),
groups and rings (``structures``) and quantified statements (``logic_rules``).
Each line is then held to a level (``policy``: ``exam``, ``course``,
``scratch``); ``review`` puts these together.  Opt in with
``ProofChecker(kernel="course")``; without it the engine behaves exactly as
before.
"""

from aether.kernel.policy import LEVELS, Fragment, Policy
from aether.kernel.review import Kernel

__all__ = ["Kernel", "LEVELS", "Fragment", "Policy"]
