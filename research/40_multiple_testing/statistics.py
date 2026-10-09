"""Small exact diagnostics. Assumptions and sample limits remain explicit."""

from itertools import product
from math import isfinite


def sign_flip_tail(values: list[float]) -> float:
    """One-sided exact sign-flip tail under independent symmetric null errors.

    The financial observations here do not establish those assumptions; results
    are sensitivity diagnostics, not valid strategy-discovery certificates.
    """
    if not values or len(values) > 20 or any(not isfinite(v) for v in values):
        raise ValueError("need1 to20 finite session values")
    observed = sum(values)
    favorable = sum(sum(sign * value for sign, value in zip(signs, values)) >= observed - 1e-9
                    for signs in product((-1, 1), repeat=len(values)))
    return favorable / (2 ** len(values))


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    if any(not isfinite(p) or not 0 <= p <= 1 for p in pvalues):
        raise ValueError("pvalues must be finite and between zero and one")
    order = sorted(range(len(pvalues)), key=lambda index: pvalues[index])
    adjusted = [1.0] * len(pvalues)
    ceiling = 1.0
    for rank in range(len(order), 0, -1):
        index = order[rank - 1]
        ceiling = min(ceiling, pvalues[index] * len(order) / rank)
        adjusted[index] = ceiling
    return adjusted
