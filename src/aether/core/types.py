"""Mathematical types, domains, and standard sets in Aether."""

from enum import Enum


class MathType(str, Enum):
    Nat = "Nat"
    Int = "Int"
    Rat = "Rat"
    Real = "Real"
    Complex = "Complex"
    Bool = "Bool"
    Vector = "Vector"
    Matrix = "Matrix"
    Set = "Set"
    #: A member of a structure's carrier (``Given a : G`` after ``Assume Group(G, ...)``).
    Element = "Element"


# Aliases accepted by the parser → canonical MathType name.
# Keys are lowercased before lookup.
_ALIASES: dict[str, MathType] = {
    # Naturals
    "nat": MathType.Nat,
    "nats": MathType.Nat,
    "natural": MathType.Nat,
    "naturals": MathType.Nat,
    "\\mathbb{n}": MathType.Nat,
    "\\nat": MathType.Nat,
    "n": MathType.Nat,
    # Integers
    "int": MathType.Int,
    "ints": MathType.Int,
    "integer": MathType.Int,
    "integers": MathType.Int,
    "\\mathbb{z}": MathType.Int,
    "\\int": MathType.Int,
    "z": MathType.Int,
    # Rationals
    "rat": MathType.Rat,
    "rats": MathType.Rat,
    "rational": MathType.Rat,
    "rationals": MathType.Rat,
    "\\mathbb{q}": MathType.Rat,
    "q": MathType.Rat,
    # Reals
    "real": MathType.Real,
    "reals": MathType.Real,
    "\\mathbb{r}": MathType.Real,
    "r": MathType.Real,
    # Complex
    "complex": MathType.Complex,
    "\\mathbb{c}": MathType.Complex,
    "c": MathType.Complex,
    # Bool
    "bool": MathType.Bool,
    "boolean": MathType.Bool,
    "prop": MathType.Bool,
    # Vector
    "vector": MathType.Vector,
    "vectors": MathType.Vector,
    # Matrix
    "matrix": MathType.Matrix,
    "matrices": MathType.Matrix,
    # Set
    "set": MathType.Set,
    "sets": MathType.Set,
}


def normalize_type_name(raw_name: str) -> MathType:
    """Normalize a user-provided type name, symbol, or LaTeX token into a canonical MathType.

    Raises ``ValueError`` if the name is not recognised.
    """
    key = raw_name.strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    # Try canonical names case-insensitively (e.g. 'Real', 'INT')
    for mt in MathType:
        if mt.value.lower() == key:
            return mt
    raise ValueError(f"Unknown type: {raw_name!r}")
