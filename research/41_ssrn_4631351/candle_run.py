"""Paper candle rule on predeclared NSE names; no broker access or fitted weights."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import floor
from pathlib import Path

import numpy as np
import pandas as pd

from research.intraday_lab.costs import order_fees

ROOT = Path(__file__).resolve().parents[2]
TRACK = Path(__file__).resolve().parent


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


def candle_directions(frame: pd.DataFrame, *, confirmed: bool) -> np.ndarray:
    """Direction after each completed candle; caller delays execution one candle."""
    close = frame.close.to_numpy(dtype=float)
    volume = frame.volume.to_numpy(dtype=float)
    typical = (frame.high.to_numpy() + frame.low.to_numpy() + close) / 3
    denominator = np.cumsum(volume)
    vwap = np.divide(np.cumsum(typical * volume), denominator,
                     out=np.full(len(close), np.nan), where=denominator > 0)
    side = np.where(np.isfinite(vwap), np.sign(close - vwap), 0).astype(int)
    if not confirmed:
        return side
    movement = np.zeros(len(close))
    movement[5:] = (close[5:] / close[:-5] - 1) * 10_000
    latest = np.zeros(len(close))
    latest[1:] = np.diff(close) / close[:-1] * 10_000
    path = pd.Series(np.abs(np.diff(close, prepend=close[0]))).rolling(5).sum().to_numpy()
    displacement = np.zeros(len(close))
    displacement[5:] = np.abs(close[5:] - close[:-5])
    efficiency = np.divide(displacement, path, out=np.zeros(len(close)), where=path > 0)
    accepted = (side * movement >= 8) & (side * latest > 0) & (efficiency >= 0.3)
    accepted[:5] = False
    return np.where(accepted, side, 0)


@dataclass(frozen=True)
class DayResult:
    date: str
    starting_equity: float
    ending_equity: float
    gross_pnl: float
    fees: float
    net_pnl: float
    trades: int
    wins: int
    maximum_intraday_drawdown_inr: float


def simulate_day(
    frame: pd.DataFrame, decisions: np.ndarray, equity: float, slippage_bps: float
) -> tuple[DayResult, list[dict]]:
    """Trade prior completed decisions at next open with adverse slippage and fees."""
    if len(frame) != len(decisions) or len(frame) < 2:
        raise ValueError("matching candles and decisions required")
    if not np.isin(decisions, [-1, 0, 1]).all() or equity <= 0 or slippage_bps < 0:
        raise ValueError("invalid directions, equity or slippage")
    opens = frame.open.to_numpy(dtype=float)
    closes = frame.close.to_numpy(dtype=float)
    targets = np.roll(decisions, 1)
    targets[0] = 0
    initial = equity
    side = quantity = 0
    entry = entry_fee = 0.0
    entry_index = -1
    gross_total = fees_total = 0.0
    peak = equity
    drawdown = 0.0
    records: list[dict] = []

    def close_position(index: int, reference: float, reason: str) -> None:
        nonlocal equity, side, quantity, gross_total, fees_total
        exit_price = reference * (1 - side * slippage_bps / 10_000)
        exit_fee = float(order_fees(exit_price, quantity, is_buy=side < 0).total)
        gross = side * (exit_price - entry) * quantity
        fees = entry_fee + exit_fee
        equity += gross - fees
        gross_total += gross
        fees_total += fees
        records.append({"entry_index": entry_index, "exit_index": index, "side": side,
                        "quantity": quantity, "entry_price": entry, "exit_price": exit_price,
                        "gross_pnl": gross, "fees": fees, "net_pnl": gross - fees,
                        "exit_reason": reason})
        side = quantity = 0

    for index, target in enumerate(targets):
        if target != side:
            if side:
                close_position(index, opens[index], "direction_change")
            if target and equity > 0:
                entry = opens[index] * (1 + target * slippage_bps / 10_000)
                quantity = floor(equity / entry)
                while quantity > 0:
                    entry_fee = float(order_fees(entry, quantity, is_buy=target > 0).total)
                    if quantity * entry + entry_fee <= equity:
                        break
                    quantity -= 1
                if quantity:
                    side, entry_index = int(target), index
        marked = equity
        if side:
            liquidation = closes[index] * (1 - side * slippage_bps / 10_000)
            exit_fee = float(order_fees(liquidation, quantity, is_buy=side < 0).total)
            marked += side * (liquidation - entry) * quantity - entry_fee - exit_fee
        peak = max(peak, marked)
        drawdown = max(drawdown, peak - marked)
    if side:
        close_position(len(frame) - 1, closes[-1], "session_close")
    day = str(frame.date.iloc[0])
    return DayResult(day, initial, equity, gross_total, fees_total, equity - initial,
                     len(records), sum(row["net_pnl"] > 0 for row in records), drawdown), records


def load_days(security_id: int) -> tuple[list[pd.DataFrame], dict]:
    paths = sorted((ROOT / "context/stocks-data/NSE" / str(security_id) / "intraday_1m").glob("*.parquet"))
    frame = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    clock = pd.to_datetime(frame.timestamp, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    frame["date"] = clock.dt.strftime("%Y-%m-%d")
    frame["minute"] = clock.dt.hour * 60 + clock.dt.minute
    frame = frame[frame.minute.between(555, 929)].sort_values(["date", "minute"])
    accepted = []
    excluded = []
    for day, group in frame.groupby("date", sort=True):
        values = group[["open", "high", "low", "close", "volume"]].to_numpy()
        valid = (np.isfinite(values).all() and (values[:, :4] > 0).all()
                 and (values[:, 4] >= 0).all()
                 and (group.high >= group[["open", "close", "low"]].max(axis=1)).all()
                 and (group.low <= group[["open", "close", "high"]].min(axis=1)).all())
        if len(group) == 375 and group.minute.nunique() == 375 and valid and group.volume.sum() > 0:
            accepted.append(group.reset_index(drop=True))
        else:
            excluded.append({"date": day, "rows": len(group), "unique_minutes": int(group.minute.nunique()), "valid": bool(valid)})
    report = {"security_id": security_id, "accepted_days": len(accepted), "excluded_days": excluded,
              "source_files": [{"path": str(p.relative_to(ROOT)), "sha256": sha256(p.read_bytes()).hexdigest()} for p in paths]}
    return accepted, report


def main() -> None:
    specification = TRACK / "candle-hypotheses.json"
    frozen = json.loads(specification.read_text(encoding="utf-8"))
    output = TRACK / "candle-runs/initial-v1"
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "plan.json", {**frozen, "hypotheses_sha256": sha256(specification.read_bytes()).hexdigest(),
                                      "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                                      "fee_source_sha256": sha256((ROOT / "research/intraday_lab/costs.py").read_bytes()).hexdigest()})
    daily_rows = []
    trade_rows = []
    for security_id in frozen["security_ids"]:
        days, report = load_days(security_id)
        write_json(output / f"coverage-{security_id}.json", report)
        for variant in frozen["variants"]:
            signals = [(day, candle_directions(day, confirmed=variant == "vwap_momentum_confirmed")) for day in days]
            for slippage in frozen["slippage_bps_per_side"]:
                equity = frozen["starting_equity_per_independent_sleeve_inr"]
                for day, decisions in signals:
                    if equity <= 0:
                        raise ValueError(f"insolvent research sleeve {security_id}/{variant}/{slippage}")
                    result, trades = simulate_day(day, decisions, equity, slippage)
                    equity = result.ending_equity
                    keys = {"security_id": security_id, "variant": variant, "slippage_bps": slippage,
                            "phase": "later_diagnostic" if result.date >= "2025-01-01" else "exploratory"}
                    daily_rows.append({**keys, **asdict(result)})
                    trade_rows.extend({**keys, "date": result.date, **row} for row in trades)
                print(json.dumps({"security_id": security_id, "variant": variant, "slippage_bps": slippage,
                                  "days": len(days), "ending_equity": round(equity, 2)}), flush=True)
    daily = pd.DataFrame(daily_rows)
    daily.to_csv(output / "daily.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(output / "trades.csv", index=False)
    if daily.empty:
        write_json(output / "aggregate.json", {"status": "no eligible full sessions", "promotion_eligible": False})
        return
    metrics = ["gross_pnl", "fees", "net_pnl", "trades", "wins"]
    aggregates = []
    for groups in (["variant", "slippage_bps", "phase"], ["security_id", "variant", "slippage_bps", "phase"]):
        for key, group in daily.groupby(groups, sort=True):
            aggregates.append({**dict(zip(groups, key)), "instrument_days": len(group),
                               **{column: float(group[column].sum()) for column in metrics},
                               "positive_days": int((group.net_pnl > 0).sum())})
    write_json(output / "aggregate.json", {"results": aggregates, "promotion_eligible": False,
                                           "independent_sleeves": True, "initial_capital_all_sleeves": 600000,
                                           "limitations": frozen["interpretation"]})


if __name__ == "__main__":
    main()
