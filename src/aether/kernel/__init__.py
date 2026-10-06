"""The proof kernel: what a line may use, and how big a step it may take.

Stage 1 of the design in "A Proof Kernel for Lemmata": chain links and
deductions are checked with the premises they cite, classified by the kind of
reasoning that settled them, and held to a level (``exam``, ``course``,
``scratch``).  Opt in with ``ProofChecker(kernel="course")``; without it the
engine behaves exactly as before.
"""

from aether.kernel.policy import LEVELS, Fragment, Policy
from aether.kernel.review import Kernel

__all__ = ["Kernel", "LEVELS", "Fragment", "Policy"]
