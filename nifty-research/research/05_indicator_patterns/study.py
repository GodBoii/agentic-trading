"""Fixed indicator hypotheses on sampled Nifty futures quotes, not live trades."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB))
from nifty_lab.io import write_json

HORIZONS = (1, 5, 15)
RULES = ("ema_8_21", "rsi_14_reversal", "bollinger_20_reversal", "donchian_20_breakout",
         "opening_15_breakout", "return_5_reversal")
TEST_START = "2026-08-04"


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    value = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    value = value.mask((loss == 0) & (gain > 0), 100)
    return value.mask((gain == 0) & (loss == 0), 50)


def build_signals(frame: pd.DataFrame) -> pd.DataFrame:
    chunks = []
    for _, segment in frame.groupby(["date", "segment", "security_id"], sort=False):
        group = segment.sort_values("decision_at").copy()
        close = group["close"]
        # Exponential histories must reset, not just wait behind a validity mask.
        # An incomplete row is isolated, and the next complete row starts anew.
        complete = group["complete_minute"].astype(bool)
        boundaries = (~complete | ~complete.shift(1, fill_value=False)
                      | group["decision_at"].diff().ne(pd.Timedelta(minutes=1)))
        indicator_run = boundaries.cumsum()
        complete_close = close.where(complete)
        mean = close.rolling(20, min_periods=20).mean()
        std = close.rolling(20, min_periods=20).std(ddof=0)
        z = (close - mean) / std.replace(0, np.nan)
        ema8 = complete_close.groupby(indicator_run).transform(
            lambda values: values.ewm(span=8, adjust=False, min_periods=21).mean())
        ema21 = complete_close.groupby(indicator_run).transform(
            lambda values: values.ewm(span=21, adjust=False, min_periods=21).mean())
        rsi14 = complete_close.groupby(indicator_run).transform(rsi)
        history_valid = group["complete_minute"].rolling(21).sum().eq(21)
        contiguous = group["decision_at"].diff(20).eq(pd.Timedelta(minutes=20))
        valid = history_valid & contiguous
        group["ema_8_21"] = np.sign(ema8 - ema21).where(valid, 0).fillna(0)
        group["rsi_14_reversal"] = pd.Series(np.where(rsi14 < 30, 1, np.where(rsi14 > 70, -1, 0)), index=group.index).where(valid, 0)
        group["bollinger_20_reversal"] = pd.Series(np.where(z < -2, 1, np.where(z > 2, -1, 0)), index=group.index).where(valid, 0)
        # Compare current completed minute with prior channel, not a channel
        # containing this minute's extremes.
        upper = group["high"].shift(1).rolling(20).max()
        lower = group["low"].shift(1).rolling(20).min()
        group["donchian_20_breakout"] = pd.Series(np.where(close > upper, 1, np.where(close < lower, -1, 0)), index=group.index).where(valid, 0)
        group["return_5_reversal"] = (-np.sign(group["ret_5_bps"])).where(valid & group["ret_5_bps"].abs().ge(2), 0).fillna(0)
        group["opening_15_breakout"] = 0.0
        opening = group[group["minutes_from_open"].between(1, 15)]
        if (len(opening) == 15 and opening["complete_minute"].all()
                and opening["decision_at"].iloc[-1] - opening["decision_at"].iloc[0] == pd.Timedelta(minutes=14)):
            mask = (group["minutes_from_open"] > 15) & complete
            group.loc[mask, "opening_15_breakout"] = np.where(close[mask] > opening["high"].max(), 1,
                                                               np.where(close[mask] < opening["low"].min(), -1, 0))
        for horizon in HORIZONS:
            continuous = group["decision_at"].shift(-horizon).sub(group["decision_at"]).eq(pd.Timedelta(minutes=horizon))
            future_complete = group["complete_minute"].rolling(horizon).sum().shift(-horizon).eq(horizon)
            group[f"target_{horizon}"] = (np.log(close.shift(-horizon) / close) * 10000).where(continuous & future_complete & group["complete_minute"])
        chunks.append(group)
    return pd.concat(chunks, ignore_index=True).sort_values("decision_at")


def sign_flip_pvalue(daily: np.ndarray) -> float | None:
    """Exact one-sided test of symmetric zero-centred date outcomes."""
    daily = daily[np.isfinite(daily)]
    if len(daily) < 3: return None
    if len(daily) > 20: raise ValueError("Exact enumeration capped at twenty days")
    observed = daily.mean()
    null = np.array([np.mean(daily * signs) for signs in itertools.product((-1, 1), repeat=len(daily))])
    return float(np.mean(null >= observed - 1e-12))


def holm(pvalues: list[float | None]) -> list[float | None]:
    result: list[float | None] = [None] * len(pvalues)
    available = sorted((value, index) for index, value in enumerate(pvalues) if value is not None)
    # All registered hypotheses count toward family size, including untestable ones.
    previous = 0.0
    for rank, (value, index) in enumerate(available):
        previous = max(previous, min(1.0, (len(pvalues) - rank) * value))
        result[index] = previous
    return result


def analyse(frame: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    rows = []; records = []; rng = np.random.default_rng(20261001)
    test = frame[frame["date"] >= TEST_START]
    for rule in RULES:
        for horizon in HORIZONS:
            busy_until = None; chosen = []
            for row in test.to_dict("records"):
                if row[rule] == 0 or (busy_until is not None and row["decision_at"] < busy_until): continue
                # Keep unresolved observations. Do not use future coverage to
                # decide whether the current signal exists.
                busy_until = row["decision_at"] + pd.Timedelta(minutes=horizon)
                result = row[rule] * row[f"target_{horizon}"]
                chosen.append({"date": row["date"], "decision_at": row["decision_at"],
                               "rule": rule, "horizon": horizon, "signal": row[rule], "signed_return_bps": result})
            ledger = pd.DataFrame(chosen)
            daily = ledger.groupby("date")["signed_return_bps"].mean().dropna() if not ledger.empty else pd.Series(dtype=float)
            priced = ledger["signed_return_bps"].dropna() if not ledger.empty else pd.Series(dtype=float)
            interval = None
            if len(daily):
                draws = rng.choice(daily.to_numpy(), size=(5000, len(daily)), replace=True).mean(axis=1)
                interval = np.quantile(draws, [0.025, 0.975]).tolist()
            rows.append({"rule": rule, "horizon_minutes": horizon, "attempts": len(chosen), "labelled": len(priced),
                         "unresolved": len(chosen) - len(priced), "days": len(daily),
                         "mean_signed_return_bps": float(priced.mean()) if len(priced) else None,
                         "equal_day_mean_bps": float(daily.mean()) if len(daily) else None,
                         "day_bootstrap_interval_bps": interval, "sign_flip_p": sign_flip_pvalue(daily.to_numpy()),
                         "daily_mean_bps": {str(k): float(v) for k, v in daily.items()},
                         "mean_minus_2bps_diagnostic": float(priced.mean() - 2) if len(priced) else None,
                         "mean_minus_5bps_diagnostic": float(priced.mean() - 5) if len(priced) else None})
            records.extend(chosen)
    corrected = holm([row["sign_flip_p"] for row in rows])
    for row, value in zip(rows, corrected): row["holm_p_18_hypotheses"] = value
    return rows, pd.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path,
        default=LAB / "research/01_depth_forecast_baseline/artifacts/features.parquet")
    args = parser.parse_args()
    output = Path(__file__).parent / "artifacts"; output.mkdir(exist_ok=True)
    original = args.input.read_bytes(); frame = build_signals(pd.read_parquet(args.input))
    rows, ledger = analyse(frame)
    write_json(output / "results.json", {"trial_count": 18, "test_start": TEST_START, "results": rows,
        "input_sha256": hashlib.sha256(original).hexdigest(),
        "limitations": ["Previously examined dates are development, not untouched confirmation", "Sampled futures quote midpoints, not executed option/futures P&L",
                        "Synthetic 2/5 bps deductions are friction diagnostics, not broker cost calculations",
                        "Exact sign test assumes symmetric independent dates; nine dates provide weak inference",
                        "Unresolved labels excluded from score but retained; informative missingness is possible"]})
    ledger.to_parquet(output / "signal-ledger.parquet", index=False)
    lines = ["# Fixed indicator and pattern hypotheses", "", "Six fixed rules at three horizons. No parameter search or best-rule promotion."
        " Dates from August 4 onward were already viewed in experiment 1 and are development data.", "",
        "| Rule | Horizon | Labelled / unresolved | Mean signed bps | Equal-day mean bps | Holm p |",
        "|---|---:|---:|---:|---:|---:|"]
    fmt = lambda x: "n/a" if x is None else f"{x:.3f}"
    for row in rows:
        lines.append(f"| {row['rule']} | {row['horizon_minutes']} | {row['labelled']} / {row['unresolved']} | {fmt(row['mean_signed_return_bps'])} | {fmt(row['equal_day_mean_bps'])} | {fmt(row['holm_p_18_hypotheses'])} |")
    lines += ["", "Positive signed midpoint return is not executable profit. No trade is represented by zero signal."
        " Signals do not overlap within a rule/horizon. Missing exit labels remain in the ledger. A two/five-bps"
        " sensitivity is available in results.json, but does not replace actual option quote replay.", "",
        "RSI uses Wilder-style exponential smoothing, 14 minutes, levels 30 and 70. Bollinger uses a 20-minute"
        " mean and population standard deviation, two standard deviations. EMA spans are 8 and 21. Donchian"
        " uses prior 20 completed minutes. Opening range needs all first 15 regular-session minutes, and becomes"
        " usable only afterward. Five-minute reversal requires a two-bps preceding move.", "",
        "## Sources", "", "[TA repository](https://github.com/bukosabino/ta) and"
        " [indicator source](https://github.com/bukosabino/ta/blob/master/ta/volatility.py) were inspected for definitions."
        " This study implements small formulas locally; it does not run untrusted repository code or claim exact library parity.", "",
        "[Lo, Mamaysky and Wang](https://www.nber.org/papers/w7613) motivate objective pattern definitions."
        " This is not a replication of their daily US-stock kernel study.", "",
        "[Bailey et al.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659) motivate preserving all trials."
        " Holm correction covers these 18 hypotheses only, not every experiment in the wider programme.", "",
        "Run `python research/05_indicator_patterns/study.py` from nifty-research."]
    lines += ["", "## Review correction, 2 October 2026", "",
        "EMA and RSI now restart their exponential histories after every incomplete or missing minute."
        " A rolling validity mask alone did not remove pre-gap smoothing state. Opening-range signals now also"
        " require a complete current minute. The already observed opening range remains usable after a later gap"
        " within the same recording segment; a recorder restart still invalidates that segment's opening range.", "",
        "Pre-correction code, results and ledger remain under artifacts/revisions/pre-gap-fix."
        " The correction changes evidence reconstruction, not indicator thresholds or the registered 18 trials."]
    (Path(__file__).parent / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert args.input.read_bytes() == original
    print(json.dumps({"trials": len(rows), "holm_passes": sum(row["holm_p_18_hypotheses"] is not None and row["holm_p_18_hypotheses"] < .05 for row in rows)}))


if __name__ == "__main__": main()
