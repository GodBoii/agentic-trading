"""Frozen standard NSE cash intraday tariff, effective research date 2026-09-30.

Source: https://dhan.co/pricing/. Per-order approximations require contract-note
reconciliation before deployment. No BSE, delivery, derivatives, or financing.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class FeeBreakdown:
    brokerage: Decimal
    exchange: Decimal
    sebi: Decimal
    ipft: Decimal
    gst: Decimal
    stt: Decimal
    stamp: Decimal

    @property
    def total(self) -> Decimal:
        return sum((self.brokerage, self.exchange, self.sebi, self.ipft,
                    self.gst, self.stt, self.stamp), Decimal(0))


def _round(value: Decimal, quantum: str = "0.01") -> Decimal:
    return value.quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


def order_fees(price: float, quantity: int, *, is_buy: bool) -> FeeBreakdown:
    value = Decimal(str(price)) * quantity
    if not value.is_finite() or value <= 0 or quantity < 1:
        raise ValueError("finite positive price and positive quantity required")
    brokerage = _round(min(Decimal(20), value * Decimal("0.0003")))
    exchange = _round(value * Decimal("0.000030699"))
    sebi = _round(value * Decimal("0.000001"))
    ipft = _round(value * Decimal("0.000000001"))
    gst = _round((brokerage + exchange + sebi + ipft) * Decimal("0.18"))
    stt = Decimal(0) if is_buy else _round(value * Decimal("0.00025"), "1")
    stamp = _round(value * Decimal("0.00003"), "1") if is_buy else Decimal(0)
    return FeeBreakdown(brokerage, exchange, sebi, ipft, gst, stt, stamp)


def round_trip_fees(entry_price: float, exit_price: float, quantity: int, *, long: bool) -> float:
    return float(order_fees(entry_price, quantity, is_buy=long).total
                 + order_fees(exit_price, quantity, is_buy=not long).total)
