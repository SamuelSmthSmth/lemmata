"""Algebraic and logical checking engine for Aether."""

from aether.engine.context import (
    ProofContext,
    VarInfo,
    HypothesisInfo,
    DomainObligation,
    ChainState,
    ContextError,
    VariableCaptureError,
    MonotonicityError,
    ChainError,
    GeneralizationError,
)
from aether.engine.algebra import (
    AlgebraResult,
    ast_to_sympy,
    extract_domain_obligations,
    verify_algebraic_equality,
)
from aether.engine.logic import (
    LogicResult,
    ast_to_z3,
    verify_entailment,
    check_domain_obligation,
    expand_prelude_predicate,
)
from aether.engine.checker import (
    ProofChecker,
    ProofReport,
    StepResult,
    StepStatus,
)

__all__ = [
    "ProofContext",
    "VarInfo",
    "HypothesisInfo",
    "DomainObligation",
    "ChainState",
    "ContextError",
    "VariableCaptureError",
    "MonotonicityError",
    "ChainError",
    "GeneralizationError",
    "AlgebraResult",
    "ast_to_sympy",
    "extract_domain_obligations",
    "verify_algebraic_equality",
    "LogicResult",
    "ast_to_z3",
    "verify_entailment",
    "check_domain_obligation",
    "expand_prelude_predicate",
    "ProofChecker",
    "ProofReport",
    "StepResult",
    "StepStatus",
]
