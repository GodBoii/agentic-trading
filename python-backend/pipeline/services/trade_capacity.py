"""Account capital and concurrent intraday trade policy."""

from __future__ import annotations

import math
from typing import Any


def positive_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) and number > 0 else 0.0


def available_balance(funds: dict[str, Any]) -> float:
    for key in ("availabelBalance", "availableBalance", "withdrawableBalance"):
        if funds.get(key) not in (None, ""):
            return positive_number(funds[key])
    return 0.0


def account_capital(funds: dict[str, Any]) -> float:
    # Allocating margin must not shrink the account's capacity tier.
    return max(
        available_balance(funds) + positive_number(funds.get("utilizedAmount")),
        positive_number(funds.get("sodLimit")),
    )


def trade_slot_limit(capital: float) -> int:
    capital = positive_number(capital)
    if capital == 0:
        return 0
    if capital < 2000:
        return 3
    return 5 if capital <= 5000 else 10


def effective_trade_slot_limit(capital: float, manual_amount: float | None = None) -> int:
    tier = trade_slot_limit(capital)
    if manual_amount is None:
        return tier
    amount = positive_number(manual_amount)
    return min(tier, int(capital // amount)) if amount else 0
