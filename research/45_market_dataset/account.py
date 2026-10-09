"""Deterministic delayed candle-reference account replay with explicit limitations."""

from dataclasses import dataclass
import heapq
import math

import numpy as np
import pandas as pd

from research.intraday_lab.costs import order_fees, round_trip_fees


@dataclass(frozen=True)
class AccountConfig:
    starting_equity: float = 500000.0
    maximum_positions: int = 3
    maximum_notional: float = 100000.0
    daily_realized_loss_halt: float = 2500.0

    def __post_init__(self) -> None:
        if (not all(math.isfinite(v) and v > 0 for v in [self.starting_equity,
                self.maximum_notional, self.daily_realized_loss_halt])
                or not isinstance(self.maximum_positions, int) or self.maximum_positions < 1
                or self.maximum_notional > self.starting_equity):
            raise ValueError("valid equity, position, notional and loss limits required")


def estimated_net_edge(prediction: float, reference: float, cost_per_leg_bps: float,
                       notional: float = 100000.0) -> float:
    if not all(math.isfinite(x) for x in [prediction, reference, cost_per_leg_bps, notional]):
        raise ValueError("finite forecast, reference and costs required")
    if min(reference, notional) <= 0 or cost_per_leg_bps < 0:
        raise ValueError("positive reference/budget and nonnegative cost required")
    quantity = math.floor(notional / reference)
    if quantity < 1:
        return float("-inf")
    fees = round_trip_fees(reference, reference, quantity, long=prediction >= 0)
    return abs(prediction) - fees / (reference * quantity) * 10000 - 2 * cost_per_leg_bps


def account_replay(rows: pd.DataFrame, forecast_bps: np.ndarray, horizon: int,
                   threshold_net_bps: float = 2.0, cost_per_leg_bps: float = 2.0,
                   config: AccountConfig = AccountConfig()) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Reserve capital/slots at decision, fill later, release only on scheduled exit."""
    forecasts = np.asarray(forecast_bps, dtype=float)
    needed = ["date", "security_id", "decision_us", "entry_us", f"exit_us_{horizon}",
              "decision_reference", "entry_reference", f"exit_reference_{horizon}"]
    if (horizon not in {5, 15, 30} or any(c not in rows for c in needed)
            or len(rows) != len(forecasts) or not np.isfinite(forecasts).all()
            or not math.isfinite(threshold_net_bps) or threshold_net_bps < 0
            or not math.isfinite(cost_per_leg_bps) or not 0 <= cost_per_leg_bps < 10000):
        raise ValueError("aligned forecasts, supported horizon and valid thresholds required")
    frame = rows[needed].copy()
    frame["forecast"] = forecasts
    numeric = [c for c in needed if c not in {"date", "security_id"}]
    if not np.isfinite(frame[numeric]).all().all() or (
            frame[["decision_reference", "entry_reference", f"exit_reference_{horizon}"]] <= 0).any().any():
        raise ValueError("valid causal price references required")
    if not ((frame.decision_us < frame.entry_us) & (frame.entry_us < frame[f"exit_us_{horizon}"])).all():
        raise ValueError("orders require later entry and exit times")
    if frame.duplicated(["decision_us", "security_id"]).any():
        raise ValueError("duplicate decision identities")
    frame["net_edge"] = [estimated_net_edge(p, r, cost_per_leg_bps, config.maximum_notional)
                          for p, r in zip(frame.forecast, frame.decision_reference)]
    frame = frame.sort_values(["decision_us", "net_edge", "security_id"], ascending=[True, False, True])
    trades, daily = [], []
    rejected = {"edge": 0, "capacity": 0, "daily_loss": 0, "unaffordable": 0, "cancelled_after_loss": 0}
    for date, day in frame.groupby("date", sort=True):
        cash = config.starting_equity
        realized = 0.0
        reserved = 0.0
        active: dict[int, float] = {}
        pending: dict[int, dict] = {}
        events: list[tuple[int, int, int, dict]] = []
        serial = 0
        day_trades = []
        maximum_slots = 0

        def process(until: int) -> None:
            nonlocal cash, reserved, realized, serial
            while events and events[0][0] <= until:
                _, kind, token, event = heapq.heappop(events)
                sid = event["security_id"]
                if kind == 1:
                    reserved -= config.maximum_notional
                    pending.pop(sid)
                    if realized <= -config.daily_realized_loss_halt:
                        rejected["cancelled_after_loss"] += 1
                        continue
                    side = event["side"]
                    fill = event["entry_reference"] * (1 + side * cost_per_leg_bps / 10000)
                    quantity = math.floor(min(config.maximum_notional, cash) / fill)
                    while quantity > 0 and fill * quantity + float(order_fees(fill, quantity, is_buy=side > 0).total) > cash:
                        quantity -= 1
                    if quantity < 1:
                        rejected["unaffordable"] += 1
                        continue
                    entry_fee = float(order_fees(fill, quantity, is_buy=side > 0).total)
                    collateral = fill * quantity
                    cash -= collateral + entry_fee
                    active[sid] = collateral
                    trade = {**event, "entry_price": fill, "quantity": quantity, "entry_fee": entry_fee,
                             "collateral": collateral}
                    serial += 1
                    heapq.heappush(events, (event["exit_us"], 0, serial, trade))
                else:
                    fill = event["exit_reference"] * (1 - event["side"] * cost_per_leg_bps / 10000)
                    exit_fee = float(order_fees(fill, event["quantity"], is_buy=event["side"] < 0).total)
                    gross = event["side"] * (fill - event["entry_price"]) * event["quantity"]
                    net = gross - event["entry_fee"] - exit_fee
                    cash += event["collateral"] + gross - exit_fee
                    realized += net
                    active.pop(sid)
                    record = {**event, "exit_price": fill, "gross_pnl": gross,
                              "fees": event["entry_fee"] + exit_fee, "net_pnl": net}
                    trades.append(record)
                    day_trades.append(record)

        for row in day.itertuples(index=False):
            process(int(row.decision_us))
            if row.net_edge < threshold_net_bps or row.forecast == 0:
                rejected["edge"] += 1
                continue
            if realized <= -config.daily_realized_loss_halt:
                rejected["daily_loss"] += 1
                continue
            if (len(active) + len(pending) >= config.maximum_positions or row.security_id in active
                    or row.security_id in pending or cash - reserved < config.maximum_notional):
                rejected["capacity"] += 1
                continue
            event = {"date": str(date), "security_id": int(row.security_id), "side": 1 if row.forecast > 0 else -1,
                     "decision_us": int(row.decision_us), "entry_us": int(row.entry_us),
                     "exit_us": int(getattr(row, f"exit_us_{horizon}")), "entry_reference": row.entry_reference,
                     "exit_reference": getattr(row, f"exit_reference_{horizon}"),
                     "forecast_bps": row.forecast, "estimated_net_edge_bps": row.net_edge}
            pending[event["security_id"]] = event
            reserved += config.maximum_notional
            serial += 1
            heapq.heappush(events, (event["entry_us"], 1, serial, event))
            maximum_slots = max(maximum_slots, len(active) + len(pending))
        process(2 ** 63 - 1)
        if active or pending or abs(reserved) > 1e-5 or not math.isclose(cash - config.starting_equity, realized, abs_tol=1e-5):
            raise ValueError("account capital or unresolved exposure invariant failed")
        daily.append({"date": str(date), "trades": len(day_trades), "net_pnl": realized,
                      "ending_equity": cash, "maximum_slots": maximum_slots})
    trades_frame = pd.DataFrame(trades)
    daily_frame = pd.DataFrame(daily)
    net = sum(t["net_pnl"] for t in trades)
    summary = {"sessions": len(daily), "trades": len(trades), "gross_pnl": sum(t["gross_pnl"] for t in trades),
        "fees": sum(t["fees"] for t in trades), "net_pnl": net,
        "net_win_rate": sum(t["net_pnl"] > 0 for t in trades) / len(trades) if trades else None,
        "mean_net_per_trade": net / len(trades) if trades else None, "rejections": rejected,
        "positive_sessions": sum(t["net_pnl"] > 0 for t in daily),
        "daily_reset": True, "horizon": horizon, "threshold_net_bps": threshold_net_bps,
        "cost_per_leg_bps": cost_per_leg_bps, "unresolved_positions": 0, "promotion_eligible": False,
        "execution_model": "delayed scheduled candle references, no verified bid/ask/capacity or intratrade marks"}
    return summary, trades_frame, daily_frame
