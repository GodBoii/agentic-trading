"""Validated market observations and versioned experiment contracts."""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Literal


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


@dataclass(frozen=True, slots=True)
class Tick:
    at_us: int
    security_id: int
    symbol: str
    bid: float
    ask: float
    last: float
    vwap: float | None
    bid_quantity_5: float
    ask_quantity_5: float
    trade_age_seconds: float | None
    data_fresh: bool | None
    connection_warm: bool | None
    exchange_segment: str = "NSE_EQ"

    def __post_init__(self) -> None:
        if self.at_us <= 0 or self.security_id <= 0 or self.exchange_segment != "NSE_EQ":
            raise ValueError("positive timestamp/id and NSE cash observations required")
        for value in (self.bid, self.ask, self.last, self.bid_quantity_5, self.ask_quantity_5):
            if not isfinite(value) or value < 0:
                raise ValueError("market numbers must be finite and nonnegative")
        if self.vwap is not None and (not isfinite(self.vwap) or self.vwap <= 0):
            raise ValueError("VWAP must be positive or explicitly unknown")
        if self.trade_age_seconds is not None and (
            not isfinite(self.trade_age_seconds) or self.trade_age_seconds < 0
        ):
            raise ValueError("trade age must be nonnegative or explicitly unknown")

    @property
    def midpoint(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / self.midpoint * 10_000 if self.midpoint > 0 else float("inf")

    def usable(self, max_trade_age_seconds: float, *, receipt_proxy: bool = False) -> bool:
        valid_quote = (self.bid > 0 and self.ask >= self.bid and self.last > 0
                       and self.bid_quantity_5 > 0 and self.ask_quantity_5 > 0)
        if receipt_proxy:
            # Sensitivity only. Unknown flags and source age remain unverified.
            return valid_quote and self.data_fresh is not False and self.connection_warm is not False
        return (valid_quote and self.data_fresh is True and self.connection_warm is True
                and self.trade_age_seconds is not None
                and self.trade_age_seconds <= max_trade_age_seconds)


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    name: str = "momentum_v1"
    version: int = 1
    freshness_mode: Literal["recent_trade", "receipt_proxy"] = "recent_trade"
    require_vwap_alignment: bool = False
    require_cost_room: bool = False
    lookback_seconds: int = 300
    confirmation_seconds: int = 60
    minimum_move_bps: float = 15.0
    confirmation_move_bps: float = 3.0
    maximum_move_bps: float = 100.0
    maximum_spread_bps: float = 5.0
    maximum_gap_seconds: float = 15.0
    maximum_trade_age_seconds: float = 5.0
    target_bps: float = 30.0
    stop_bps: float = 15.0
    horizon_seconds: int = 300
    cooldown_seconds: int = 600
    cost_reserve_bps: float = 5.0

    def __post_init__(self) -> None:
        if self.freshness_mode not in {"recent_trade", "receipt_proxy"}:
            raise ValueError("unknown freshness mode")
        positive = (self.lookback_seconds, self.confirmation_seconds, self.minimum_move_bps,
                    self.maximum_move_bps, self.maximum_spread_bps, self.maximum_gap_seconds,
                    self.maximum_trade_age_seconds, self.target_bps, self.stop_bps,
                    self.horizon_seconds)
        if any(not isfinite(value) or value <= 0 for value in positive):
            raise ValueError("policy thresholds must be finite and positive")
        if self.confirmation_seconds >= self.lookback_seconds:
            raise ValueError("confirmation must be shorter than lookback")
        if self.minimum_move_bps > self.maximum_move_bps:
            raise ValueError("minimum move exceeds maximum")
        if self.cooldown_seconds < 0 or not isfinite(self.cost_reserve_bps) or self.cost_reserve_bps < 0:
            raise ValueError("cooldown and cost reserve must be nonnegative")
        if not isfinite(self.confirmation_move_bps) or self.confirmation_move_bps < 0:
            raise ValueError("confirmation move must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    starting_equity: float = 500_000.0
    maximum_position_value: float = 100_000.0
    maximum_positions: int = 3
    risk_per_trade: float = 500.0
    maximum_daily_loss: float = 2_500.0
    latency_ms: int = 250
    order_ttl_seconds: int = 15
    extra_slippage_bps: float = 1.0
    maximum_entry_drift_bps: float = 5.0
    aggregate_depth_fraction: float = 0.10
    entry_start_second: int = 9 * 3600 + 35 * 60
    entry_cutoff_second: int = 14 * 3600 + 55 * 60
    flatten_second: int = 15 * 3600 + 20 * 60

    def __post_init__(self) -> None:
        values = (self.starting_equity, self.maximum_position_value, self.risk_per_trade,
                  self.maximum_daily_loss, self.maximum_entry_drift_bps)
        if any(not isfinite(value) or value <= 0 for value in values):
            raise ValueError("account and execution limits must be finite and positive")
        if self.maximum_positions < 1 or self.latency_ms < 0 or self.order_ttl_seconds < 1:
            raise ValueError("invalid slots, latency, or TTL")
        if not isfinite(self.extra_slippage_bps) or self.extra_slippage_bps < 0:
            raise ValueError("slippage must be finite and nonnegative")
        if not isfinite(self.aggregate_depth_fraction) or not 0 < self.aggregate_depth_fraction <= 1:
            raise ValueError("aggregate depth fraction must be in (0, 1]")
        if not 0 <= self.entry_start_second < self.entry_cutoff_second < self.flatten_second < 86400:
            raise ValueError("entry and flatten schedule must be ordered within a session")


@dataclass(frozen=True, slots=True)
class Signal:
    at_us: int
    security_id: int
    side: Side
    reference_midpoint: float
    move_bps: float
    confirmation_bps: float


@dataclass(frozen=True, slots=True)
class PendingEntry:
    signal: Signal
    arrival_us: int
    expires_us: int
    quantity: int
    reserved_value: float


@dataclass(frozen=True, slots=True)
class Position:
    signal: Signal
    symbol: str
    entered_us: int
    entry_price: float
    quantity: int
    entry_fee: float


@dataclass(frozen=True, slots=True)
class PendingExit:
    created_us: int
    arrival_us: int
    reason: str


@dataclass(frozen=True, slots=True)
class Trade:
    security_id: int
    symbol: str
    side: str
    signal_us: int
    entry_us: int
    exit_us: int
    quantity: int
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    net_pnl: float
    exit_reason: str
    entry_wait_ms: float
    exit_wait_ms: float


def session_second(at_us: int) -> int:
    """IST has no DST. Inputs are UTC epoch microseconds."""
    return ((at_us // 1_000_000) + 19_800) % 86_400
