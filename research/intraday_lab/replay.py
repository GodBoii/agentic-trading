"""Single-account offline replay with next-observation execution.

No broker adapter exists here. Top-five aggregate depth only limits order size;
it does not prove top-quote availability or model passive queues/market impact.
"""

from collections import Counter
from dataclasses import asdict
from math import floor
from typing import Iterable

from .costs import order_fees, round_trip_fees
from .domain import (ExecutionConfig, PendingEntry, PendingExit, PolicyConfig,
                     Position, Side, Signal, Tick, Trade, session_second)
from .policy import MomentumPolicy


class ReplayEngine:
    def __init__(self, policy: PolicyConfig, execution: ExecutionConfig):
        self.policy_config = policy
        self.execution = execution
        self.policy = MomentumPolicy(policy)
        self.entries: dict[int, PendingEntry] = {}
        self.positions: dict[int, Position] = {}
        self.exits: dict[int, PendingExit] = {}
        self.latest: dict[int, Tick] = {}
        self.cooldowns: dict[int, int] = {}
        self.trades: list[Trade] = []
        self.counts: Counter[str] = Counter()
        self.realized_pnl = 0.0
        self.loss_halted = False
        self.peak_equity = execution.starting_equity
        self.maximum_drawdown = 0.0
        self.last_us = 0
        self.first_day: int | None = None
        self.maximum_slots_used = 0
        self.maximum_committed_value = 0.0

    def _fill_price(self, tick: Tick, *, buy: bool) -> float:
        rate = self.execution.extra_slippage_bps / 10_000
        return tick.ask * (1 + rate) if buy else tick.bid * (1 - rate)

    def _usable(self, tick: Tick) -> bool:
        return tick.usable(self.policy_config.maximum_trade_age_seconds,
                           receipt_proxy=self.policy_config.freshness_mode == "receipt_proxy")

    def _liquidation_pnl(self) -> float:
        total = 0.0
        for security_id, position in self.positions.items():
            tick = self.latest[security_id]
            price = self._fill_price(tick, buy=position.signal.side is Side.SHORT)
            fees = float(order_fees(price, position.quantity,
                                    is_buy=position.signal.side is Side.SHORT).total)
            total += position.signal.side.sign * (price - position.entry_price) * position.quantity
            total -= position.entry_fee + fees
        return total

    def _committed_value(self) -> float:
        return (sum(item.reserved_value for item in self.entries.values())
                + sum(item.entry_price * item.quantity + item.entry_fee for item in self.positions.values()))

    def _observe_account(self) -> None:
        equity = self.execution.starting_equity + self.realized_pnl + self._liquidation_pnl()
        self.peak_equity = max(self.peak_equity, equity)
        self.maximum_drawdown = max(self.maximum_drawdown, self.peak_equity - equity)
        if equity <= self.execution.starting_equity - self.execution.maximum_daily_loss:
            if not self.loss_halted:
                self.counts["daily_loss_halt"] += 1
            self.loss_halted = True
            for security_id in list(self.entries):
                del self.entries[security_id]
                self.counts["entry_canceled_loss_halt"] += 1
        self.maximum_slots_used = max(self.maximum_slots_used, len(self.entries) + len(self.positions))
        self.maximum_committed_value = max(self.maximum_committed_value, self._committed_value())

    def _expire_entries(self, at_us: int) -> None:
        for security_id, pending in list(self.entries.items()):
            if at_us > pending.expires_us:
                del self.entries[security_id]
                self.counts["entry_expired"] += 1

    def _try_entry(self, tick: Tick) -> None:
        pending = self.entries.get(tick.security_id)
        if pending is None or tick.at_us < pending.arrival_us or tick.at_us <= pending.signal.at_us:
            return
        if not self._usable(tick):
            self.counts["entry_waiting_usable_quote"] += 1
            return
        side = pending.signal.side
        drift = abs(tick.midpoint / pending.signal.reference_midpoint - 1) * 10_000
        if drift > self.execution.maximum_entry_drift_bps or tick.spread_bps > self.policy_config.maximum_spread_bps:
            del self.entries[tick.security_id]
            self.counts["entry_canceled_drift_or_spread"] += 1
            return
        quantity_available = tick.ask_quantity_5 if side is Side.LONG else tick.bid_quantity_5
        if pending.quantity > floor(quantity_available * self.execution.aggregate_depth_fraction):
            del self.entries[tick.security_id]
            self.counts["entry_canceled_depth_proxy"] += 1
            return
        price = self._fill_price(tick, buy=side is Side.LONG)
        fee = float(order_fees(price, pending.quantity, is_buy=side is Side.LONG).total)
        planned_loss = (price * pending.quantity * (self.policy_config.stop_bps + tick.spread_bps
                        + 2 * self.execution.extra_slippage_bps) / 10_000
                        + round_trip_fees(price, price, pending.quantity, long=side is Side.LONG))
        if (price * pending.quantity > self.execution.maximum_position_value
                or planned_loss > self.execution.risk_per_trade):
            del self.entries[tick.security_id]
            self.counts["entry_canceled_revalidated_risk"] += 1
            return
        remaining = self.execution.starting_equity + self.realized_pnl + min(0.0, self._liquidation_pnl())
        committed_others = self._committed_value() - pending.reserved_value
        if price * pending.quantity + fee + committed_others > remaining:
            del self.entries[tick.security_id]
            self.counts["entry_canceled_funds"] += 1
            return
        self.positions[tick.security_id] = Position(pending.signal, tick.symbol, tick.at_us,
                                                   price, pending.quantity, fee)
        del self.entries[tick.security_id]
        self.counts["entries_filled"] += 1

    def _manage_position(self, tick: Tick) -> None:
        position = self.positions.get(tick.security_id)
        if position is None or not self._usable(tick):
            return
        side = position.signal.side
        pending = self.exits.get(tick.security_id)
        if pending is not None:
            if tick.at_us < pending.arrival_us or tick.at_us <= pending.created_us:
                return
            price = self._fill_price(tick, buy=side is Side.SHORT)
            gross = side.sign * (price - position.entry_price) * position.quantity
            fees = round_trip_fees(position.entry_price, price, position.quantity, long=side is Side.LONG)
            trade = Trade(tick.security_id, position.symbol, side.value, position.signal.at_us,
                          position.entered_us, tick.at_us, position.quantity, position.entry_price,
                          price, gross, fees, gross - fees, pending.reason,
                          (position.entered_us - position.signal.at_us) / 1000,
                          (tick.at_us - pending.created_us) / 1000)
            self.trades.append(trade)
            self.realized_pnl += trade.net_pnl
            del self.positions[tick.security_id]
            del self.exits[tick.security_id]
            self.cooldowns[tick.security_id] = tick.at_us + self.policy_config.cooldown_seconds * 1_000_000
            self.counts["exits_filled"] += 1
            return
        liquidation_quote = tick.bid if side is Side.LONG else tick.ask
        move = side.sign * (liquidation_quote / position.entry_price - 1) * 10_000
        reason = None
        if session_second(tick.at_us) >= self.execution.flatten_second:
            reason = "session_flatten"
        elif self.loss_halted:
            reason = "daily_loss"
        elif move <= -self.policy_config.stop_bps:
            reason = "stop"
        elif move >= self.policy_config.target_bps:
            reason = "target"
        elif tick.at_us - position.entered_us >= self.policy_config.horizon_seconds * 1_000_000:
            reason = "time"
        if reason is not None:
            self.exits[tick.security_id] = PendingExit(tick.at_us,
                tick.at_us + self.execution.latency_ms * 1000, reason)
            self.counts[f"exit_requested_{reason}"] += 1

    def _admit(self, signal: Signal, tick: Tick) -> None:
        cfg = self.execution
        if self.loss_halted:
            self.counts["risk_loss_halted"] += 1
            return
        if tick.security_id in self.positions or tick.security_id in self.entries:
            self.counts["risk_already_committed"] += 1
            return
        if tick.at_us < self.cooldowns.get(tick.security_id, 0):
            self.counts["risk_cooldown"] += 1
            return
        if len(self.positions) + len(self.entries) >= cfg.maximum_positions:
            self.counts["risk_slots"] += 1
            return
        # A stale held name makes portfolio P&L uncertain, so refuse more exposure.
        if any(tick.at_us - self.latest[sid].at_us > self.policy_config.maximum_gap_seconds * 1_000_000
               for sid in self.positions):
            self.counts["risk_stale_portfolio_mark"] += 1
            return
        side = signal.side
        price = self._fill_price(tick, buy=side is Side.LONG)
        depth = tick.ask_quantity_5 if side is Side.LONG else tick.bid_quantity_5
        per_share_risk = price * (self.policy_config.stop_bps + tick.spread_bps
                                  + 2 * cfg.extra_slippage_bps) / 10_000
        funds = (cfg.starting_equity + self.realized_pnl + min(0.0, self._liquidation_pnl())
                 - self._committed_value())
        quantity = min(floor(cfg.maximum_position_value / price), floor(cfg.risk_per_trade / per_share_risk),
                       floor(max(0.0, funds) / price), floor(depth * cfg.aggregate_depth_fraction))
        if quantity < 1:
            self.counts["risk_size_zero"] += 1
            return
        # Include brokerage/tax and exit allowance in risk and cash sizing.
        while quantity > 0:
            fees = round_trip_fees(price, price, quantity, long=side is Side.LONG)
            entry_fee = float(order_fees(price, quantity, is_buy=side is Side.LONG).total)
            if quantity * per_share_risk + fees <= cfg.risk_per_trade and price * quantity + entry_fee <= funds:
                break
            quantity -= 1
        if quantity < 1:
            self.counts["risk_size_zero"] += 1
            return
        cost_bps = fees / (price * quantity) * 10_000 + tick.spread_bps + 2 * cfg.extra_slippage_bps
        if self.policy_config.require_cost_room and (
            self.policy_config.target_bps < cost_bps + self.policy_config.cost_reserve_bps
        ):
            self.counts["risk_cost_room"] += 1
            return
        reserved = price * quantity + entry_fee
        self.entries[tick.security_id] = PendingEntry(signal, tick.at_us + cfg.latency_ms * 1000,
            tick.at_us + cfg.order_ttl_seconds * 1_000_000, quantity, reserved)
        self.counts["entries_reserved"] += 1

    def on_tick(self, tick: Tick) -> None:
        if tick.at_us < self.last_us:
            raise ValueError("replay observations must be ordered")
        day = (tick.at_us + 19_800_000_000) // 86_400_000_000
        if self.first_day is None:
            self.first_day = day
        elif day != self.first_day:
            raise ValueError("one engine instance handles exactly one IST session")
        self.last_us = tick.at_us
        self.counts["observations"] += 1
        if self._usable(tick):
            self.latest[tick.security_id] = tick
        self._expire_entries(tick.at_us)
        if session_second(tick.at_us) >= self.execution.entry_cutoff_second:
            self.counts["entries_canceled_cutoff"] += len(self.entries)
            self.entries.clear()
        self._observe_account()
        self._try_entry(tick)
        self._observe_account()
        self._manage_position(tick)
        signal, reason = self.policy.on_tick(tick)
        self.counts[f"policy_{reason}"] += 1
        if signal is not None and self.execution.entry_start_second <= session_second(tick.at_us) < self.execution.entry_cutoff_second:
            self._admit(signal, tick)
        self._observe_account()

    def run(self, ticks: Iterable[Tick]) -> dict:
        for tick in ticks:
            self.on_tick(tick)
        return self.summary()

    def summary(self) -> dict:
        gross = sum(trade.gross_pnl for trade in self.trades)
        fees = sum(trade.fees for trade in self.trades)
        unresolved = []
        for sid, position in sorted(self.positions.items()):
            mark = self.latest[sid]
            unresolved.append({"security_id": sid, "quantity": position.quantity,
                               "side": position.signal.side.value, "last_usable_quote_us": mark.at_us,
                               "mark_age_seconds": (self.last_us - mark.at_us) / 1_000_000,
                               "exit_pending": sid in self.exits})
        return {"policy": asdict(self.policy_config), "execution": asdict(self.execution),
                "counts": dict(sorted(self.counts.items())), "trades": len(self.trades),
                "gross_pnl": round(gross, 4), "fees": round(fees, 4),
                "net_pnl": round(self.realized_pnl, 4),
                "net_expectancy": round(self.realized_pnl / len(self.trades), 4) if self.trades else None,
                "net_win_rate": sum(t.net_pnl > 0 for t in self.trades) / len(self.trades) if self.trades else None,
                "maximum_drawdown_marked": round(self.maximum_drawdown, 4),
                "maximum_slots_used": self.maximum_slots_used,
                "maximum_committed_value": round(self.maximum_committed_value, 4),
                "unresolved_positions": unresolved, "pending_entries": len(self.entries),
                "unrealized_liquidation_estimate": round(self._liquidation_pnl(), 4),
                "promotion_eligible": False,
                "complete": not self.positions and not self.entries}
