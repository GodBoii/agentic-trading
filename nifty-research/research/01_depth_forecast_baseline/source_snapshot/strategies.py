from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import ResearchConfig


@dataclass(frozen=True)
class Leg:
    option_type: str
    strike: float
    side: int
    bid: float
    ask: float
    security_id: str = ""
    expiry: str = ""

    def __post_init__(self) -> None:
        if self.option_type not in {"CE", "PE"} or self.side not in {-1, 1}:
            raise ValueError("Leg requires CE/PE and side +1/-1")
        if not all(np.isfinite(x) for x in (self.strike, self.bid, self.ask)):
            raise ValueError("Leg values must be finite")
        if self.strike <= 0 or self.bid < 0 or self.ask <= self.bid:
            raise ValueError("Invalid strike or quote")

    @property
    def entry_price(self) -> float:
        return self.ask if self.side > 0 else self.bid


@dataclass(frozen=True)
class Strategy:
    name: str
    legs: tuple[Leg, ...]
    research_only: bool = True

    def __post_init__(self) -> None:
        if self.name != "no_trade" and not self.legs:
            raise ValueError("Strategy needs legs")
        expiries = {leg.expiry for leg in self.legs}
        if len(expiries) > 1:
            raise ValueError("This version supports same-expiry structures only")

    def terminal_pnl(self, spot: np.ndarray, lot_size: int = 65) -> np.ndarray:
        if lot_size < 1 or not np.isfinite(spot).all() or np.any(spot < 0):
            raise ValueError("Invalid lot size or underlying price")
        result = np.zeros_like(spot, dtype=float)
        for leg in self.legs:
            intrinsic = np.maximum(spot - leg.strike, 0) if leg.option_type == "CE" else np.maximum(leg.strike - spot, 0)
            result += leg.side * (intrinsic - leg.entry_price) * lot_size
        return result

    def expiry_risk(self, lot_size: int = 65) -> dict:
        # Piecewise linear payoff reaches finite extrema at zero or a strike.
        strikes = [0.0] + [leg.strike for leg in self.legs]
        values = self.terminal_pnl(np.array(strikes), lot_size)
        upper_slope = sum(leg.side for leg in self.legs if leg.option_type == "CE")
        return {"max_loss_before_costs": None if upper_slope < 0 else max(0.0, -float(values.min())),
                "max_profit_before_costs": None if upper_slope > 0 else max(0.0, float(values.max())),
                "unbounded_upper_loss": upper_slope < 0,
                "net_entry_debit": sum(leg.side * leg.entry_price for leg in self.legs) * lot_size,
                "limitation": "Expiry payoff assumes every intended leg is filled. It is not margin or an intraday loss limit."}


def charge_estimate(transactions: list[tuple[int, float]], config: ResearchConfig,
                    extra_slippage: float | None = None) -> float:
    """Transactions are buy +1 or sell -1, each for one lot and one order."""
    if any(side not in {-1, 1} or not np.isfinite(price) or price < 0 for side, price in transactions):
        raise ValueError("Invalid cost transaction")
    turnover = sum(price * config.lot_size for _, price in transactions)
    sells = sum(price * config.lot_size for side, price in transactions if side < 0)
    buys = sum(price * config.lot_size for side, price in transactions if side > 0)
    brokerage = config.brokerage_per_order * len(transactions)
    exchange = turnover * config.option_exchange_rate
    sebi = turnover * config.sebi_rate
    slip = config.extra_slippage_per_leg if extra_slippage is None else extra_slippage
    if slip < 0: raise ValueError("Slippage cannot be negative")
    return (brokerage + exchange + sebi + (brokerage + exchange + sebi) * config.gst_rate
            + sells * config.option_sell_stt_rate + buys * config.option_buy_stamp_rate
            + len(transactions) * config.lot_size * slip)


def strategy_library(quotes: dict[tuple[str, float], dict], atm: float, expiry: str, width: float = 50) -> list[Strategy]:
    def leg(kind: str, strike: float, side: int) -> Leg:
        row = quotes[(kind, strike)]
        return Leg(kind, strike, side, row["bid"], row["ask"], str(row["security_id"]), expiry)
    definitions = {
        "long_call": [("CE", atm, 1)], "long_put": [("PE", atm, 1)],
        "long_straddle": [("CE", atm, 1), ("PE", atm, 1)],
        "short_straddle": [("CE", atm, -1), ("PE", atm, -1)],
        "long_strangle": [("PE", atm - width, 1), ("CE", atm + width, 1)],
        "short_strangle": [("PE", atm - width, -1), ("CE", atm + width, -1)],
        "bull_call_spread": [("CE", atm, 1), ("CE", atm + width, -1)],
        "bear_put_spread": [("PE", atm, 1), ("PE", atm - width, -1)],
        "iron_condor": [("PE", atm - 2 * width, 1), ("PE", atm - width, -1),
                        ("CE", atm + width, -1), ("CE", atm + 2 * width, 1)],
        "iron_butterfly": [("PE", atm - width, 1), ("PE", atm, -1),
                           ("CE", atm, -1), ("CE", atm + width, 1)]}
    result = [Strategy("no_trade", ())]
    for name, specs in definitions.items():
        if all((kind, strike) in quotes for kind, strike, _ in specs):
            result.append(Strategy(name, tuple(leg(*spec) for spec in specs)))
    return result
