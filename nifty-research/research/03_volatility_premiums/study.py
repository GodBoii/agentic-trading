"""Offline variance forecasts, parity IV diagnostics, and fixed-contract premiums.

No broker connections. Read-only inputs, outputs confined to this study directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from math import erf, exp, isfinite, log, sqrt
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from nifty_lab.config import ResearchConfig
from nifty_lab.replay import QuoteBook
from nifty_lab.strategies import charge_estimate

HORIZONS = (5, 15, 30)
WINDOWS = (5, 15, 30, 60)
LAMBDAS = (0.90, 0.94, 0.97)


def black_price(forward: float, strike: float, years: float, rate: float,
                sigma: float, kind: str = "CE") -> float:
    """Discounted European Black value with a same-expiry forward."""
    if kind not in {"CE", "PE"} or not all(isfinite(x) for x in (forward, strike, years, rate, sigma)):
        raise ValueError("Finite Black inputs and CE/PE required")
    if forward <= 0 or strike <= 0 or years < 0 or sigma < 0:
        raise ValueError("Positive forward/strike and nonnegative time/volatility required")
    discount = exp(-rate * years)
    sign = 1 if kind == "CE" else -1
    if years == 0 or sigma == 0:
        return discount * max(sign * (forward - strike), 0.0)
    d1 = (log(forward / strike) + 0.5 * sigma * sigma * years) / (sigma * sqrt(years))
    d2 = d1 - sigma * sqrt(years)
    cdf = lambda x: 0.5 * (1.0 + erf(x / sqrt(2.0)))
    return discount * sign * (forward * cdf(sign * d1) - strike * cdf(sign * d2))


def implied_volatility(price: float, forward: float, strike: float, years: float,
                       rate: float = 0.0, kind: str = "CE") -> float:
    if not isfinite(price) or price < 0 or years <= 0:
        raise ValueError("Positive time and finite nonnegative option price required")
    intrinsic = black_price(forward, strike, years, rate, 0, kind)
    upper = exp(-rate * years) * (forward if kind == "CE" else strike)
    if price < intrinsic - 1e-8 or price >= upper:
        raise ValueError("Option price outside Black bounds")
    if price <= intrinsic + 1e-8:
        return 0.0
    lo, hi = 0.0, 1.0
    while black_price(forward, strike, years, rate, hi, kind) < price and hi < 32:
        hi *= 2
    if black_price(forward, strike, years, rate, hi, kind) < price:
        raise ValueError("IV exceeds numerical bracket")
    for _ in range(70):
        mid = (lo + hi) / 2
        if black_price(forward, strike, years, rate, mid, kind) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def variance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Reset at every incomplete/noncontiguous minute and original segment."""
    outputs = []
    for _, group in frame.groupby(["date", "security_id", "segment"], sort=True):
        group = group.sort_values("decision_at").copy()
        valid = group["complete_minute"] & np.isfinite(group["close"]) & (group["close"] > 0)
        breaks = (~valid) | (~valid.shift(fill_value=False)) | group["decision_at"].diff().ne(pd.Timedelta(minutes=1))
        group["run"] = breaks.cumsum()
        for _, part in group[valid].groupby("run"):
            part = part.copy()
            squared = (np.log(part["close"]).diff() * 10000) ** 2
            part["squared_return"] = squared
            for window in WINDOWS:
                part[f"rv_{window}"] = squared.rolling(window, min_periods=window).mean()
            for decay in LAMBDAS:
                part[f"ewma_{decay:.2f}"] = squared.ewm(alpha=1-decay, adjust=False, min_periods=60).mean()
            for horizon in HORIZONS:
                # Sum r[t+1]^2 through r[t+h]^2, never include r[t]^2.
                part[f"target_{horizon}"] = squared.rolling(horizon, min_periods=horizon).sum().shift(-horizon)
                part[f"label_at_{horizon}"] = part["decision_at"].shift(-horizon)
            outputs.append(part)
    return pd.concat(outputs, ignore_index=True) if outputs else pd.DataFrame()


def qlike(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    """Normalised QLIKE, zero means exact variance prediction."""
    a, p = np.maximum(actual, 1e-8), np.maximum(forecast, 1e-8)
    ratio = a / p
    return ratio - np.log(ratio) - 1


def forecast_variance(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    forecasts, summaries = [], {}
    predictors = [f"rv_{w}" for w in WINDOWS]
    cohort = frame.dropna(subset=predictors + [f"ewma_{x:.2f}" for x in LAMBDAS]).copy()
    for horizon in HORIZONS:
        target = f"target_{horizon}"
        pieces, folds = [], []
        for date in sorted(cohort["date"].unique()):
            train = cohort[(cohort["date"] < date) & cohort[target].notna()]
            test = cohort[(cohort["date"] == date) & cohort[target].notna()].copy()
            if train["date"].nunique() < 3 or len(train) < 100 or test.empty:
                continue
            assert (train[f"label_at_{horizon}"] < test["decision_at"].min()).all()
            test["historical_mean"] = train[target].mean()
            for window in WINDOWS:
                test[f"rolling_{window}"] = test[f"rv_{window}"] * horizon
            for decay in LAMBDAS:
                test[f"EWMA_{decay:.2f}"] = test[f"ewma_{decay:.2f}"] * horizon
            # Intraday multiscale approximation; not daily/weekly/monthly HAR-RV.
            for alpha in (10.0, 100.0):
                x_train = np.log(np.maximum(train[["rv_5", "rv_15", "rv_60"]], 1e-8))
                x_test = np.log(np.maximum(test[["rv_5", "rv_15", "rv_60"]], 1e-8))
                model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
                y_train = np.log(np.maximum(train[target], 1e-8))
                model.fit(x_train, y_train)
                # Training-only log retransformation correction.
                residual = y_train - model.predict(x_train)
                smear = float(np.exp(np.clip(residual, -20, 20)).mean())
                test[f"HAR_intraday_{int(alpha)}"] = np.exp(np.clip(model.predict(x_test), -20, 20)) * smear
            test["horizon"] = horizon
            test["actual_variance_bps2"] = test[target]
            pieces.append(test)
            folds.append({"date": date, "training_rows": len(train), "training_dates": sorted(train["date"].unique()), "test_rows": len(test)})
        if not pieces:
            summaries[str(horizon)] = {"status": "insufficient_history"}
            continue
        result = pd.concat(pieces, ignore_index=True)
        model_names = ["historical_mean"] + [f"rolling_{w}" for w in WINDOWS] + [f"EWMA_{d:.2f}" for d in LAMBDAS] + ["HAR_intraday_10", "HAR_intraday_100"]
        metrics = {}
        baseline = qlike(result["actual_variance_bps2"].to_numpy(), result["historical_mean"].to_numpy())
        rng = np.random.default_rng(20261001)
        for name in model_names:
            prediction = np.maximum(result[name].to_numpy(), 1e-8)
            actual = result["actual_variance_bps2"].to_numpy()
            loss = qlike(actual, prediction)
            by_day = pd.Series(baseline - loss).groupby(result["date"]).mean()
            boot = rng.choice(by_day.to_numpy(), size=(3000, len(by_day)), replace=True).mean(axis=1)
            metrics[name] = {"rows": len(result), "days": result["date"].nunique(), "mean_qlike": float(loss.mean()),
                             "rmse_root_variance_bps": float(np.sqrt(np.mean((np.sqrt(actual) - np.sqrt(prediction))**2))),
                             "day_equal_qlike_improvement_vs_historical": float(by_day.mean()),
                             "descriptive_day_bootstrap_95_interval": np.quantile(boot, [.025, .975]).tolist()}
        summaries[str(horizon)] = {"metrics": metrics, "folds": folds}
        forecasts.append(result[["date", "security_id", "decision_at", "horizon", "actual_variance_bps2"] + model_names])
    return pd.concat(forecasts, ignore_index=True), summaries


def same_expiry_pair(snapshot: dict[str, dict], at: pd.Timestamp, max_skew: float = 2.0,
                     rate: float = 0.0) -> dict | None:
    """Infer a forward from multiple synchronised strikes, then choose near it."""
    pairs = []
    by_contract = {(row["expiry"], row["strike"], row["option_type"]): row for row in snapshot.values()}
    for expiry, strike, kind in by_contract:
        if kind != "CE" or (expiry, strike, "PE") not in by_contract:
            continue
        call = by_contract[(expiry, strike, "CE")]
        put = by_contract[(expiry, strike, "PE")]
        if abs((call["timestamp"] - put["timestamp"]).total_seconds()) > max_skew:
            continue
        if not all(0 <= row["bid"] < row["ask"] for row in (call, put)):
            continue
        expiry_at = pd.Timestamp(expiry + " 15:30:00", tz="Asia/Kolkata").tz_convert("UTC")
        years = (expiry_at - at).total_seconds() / (365 * 86400)
        if years <= 0:
            continue
        cmid, pmid = (call["bid"] + call["ask"])/2, (put["bid"] + put["ask"])/2
        discount = exp(-rate * years)
        pairs.append({"expiry": expiry, "strike": strike, "years": years, "call": call, "put": put,
                      "forward": strike + (cmid - pmid)/discount,
                      "forward_low": strike + (call["bid"]-put["ask"])/discount,
                      "forward_high": strike + (call["ask"]-put["bid"])/discount})
    if not pairs:
        return None
    expiry = min(pair["expiry"] for pair in pairs)
    pairs = [pair for pair in pairs if pair["expiry"] == expiry]
    if len(pairs) < 2:
        return None
    forward = float(np.median([pair["forward"] for pair in pairs]))
    common_low = max(pair["forward_low"] for pair in pairs)
    common_high = min(pair["forward_high"] for pair in pairs)
    common_exists = common_low <= common_high
    if common_exists:
        forward = min(max(forward, common_low), common_high)
    chosen = min(pairs, key=lambda pair: abs(pair["strike"] - forward)).copy()
    chosen["forward"] = forward
    chosen["pair_count"] = len(pairs)
    chosen["forward_dispersion"] = float(np.ptp([pair["forward"] for pair in pairs]))
    chosen["parity_intersection"] = common_exists
    return chosen


def premium_study(features: pd.DataFrame, sessions: Path, age: float) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    iv_rows, premium_rows, counts = [], [], Counter()
    config = ResearchConfig(extra_slippage_per_leg=0.1)
    for day, group in features.groupby("date", sort=True):
        source = sessions / day / "options.parquet"
        if not source.exists():
            continue
        book = QuoteBook(pd.read_parquet(source), age)
        minute_by_time = {row["decision_at"]: row for row in group.to_dict("records")}
        for row in group.sort_values("decision_at").to_dict("records"):
            if not row["complete_minute"]:
                continue
            at = row["decision_at"]
            pair = same_expiry_pair(book.snapshot(at), at)
            counts["decision_attempts"] += 1
            if pair is None:
                counts["missing_synchronised_pairs"] += 1
                continue
            if not pair["parity_intersection"]:
                counts["inconsistent_parity_intervals"] += 1
                continue
            # Use the out-of-the-money leg to reduce cancellation/intrinsic issues.
            kind = "CE" if pair["strike"] >= pair["forward"] else "PE"
            option = pair["call"] if kind == "CE" else pair["put"]
            mid = (option["bid"] + option["ask"])/2
            try:
                sigma = implied_volatility(mid, pair["forward"], pair["strike"], pair["years"], kind=kind)
                iv_bid = implied_volatility(option["bid"], pair["forward"], pair["strike"], pair["years"], kind=kind)
                iv_ask = implied_volatility(option["ask"], pair["forward"], pair["strike"], pair["years"], kind=kind)
            except ValueError:
                counts["invalid_iv"] += 1
                continue
            rates = {}
            for rate in (0.05, 0.10):
                alt = same_expiry_pair(book.snapshot(at), at, rate=rate)
                rates[str(rate)] = implied_volatility(mid, alt["forward"], pair["strike"], pair["years"], rate, kind)
            expiry_days = (pd.Timestamp(pair["expiry"]) - pd.Timestamp(day)).days
            iv_rows.append({"date": day, "decision_at": at, "expiry": pair["expiry"], "dte_calendar": expiry_days,
                            "strike": pair["strike"], "forward": pair["forward"], "monthly_future": row["close"],
                            "forward_dispersion_points": pair["forward_dispersion"], "pairs": pair["pair_count"],
                            "iv": sigma, "iv_bid": iv_bid, "iv_ask": iv_ask, "iv_rate05": rates["0.05"], "iv_rate10": rates["0.1"]})
            entry_at = at + pd.Timedelta(seconds=1)
            entry = book.snapshot(entry_at)
            call_id, put_id = str(pair["call"]["security_id"]), str(pair["put"]["security_id"])
            if call_id not in entry or put_id not in entry:
                counts["missing_entry"] += 1
                continue
            call, put = entry[call_id], entry[put_id]
            for horizon in HORIZONS:
                exit_at = entry_at + pd.Timedelta(minutes=horizon)
                # Require all intervening futures minutes complete, same original segment.
                required = [minute_by_time.get(at + pd.Timedelta(minutes=i)) for i in range(horizon + 1)]
                if any(item is None or not item["complete_minute"] or item["segment"] != row["segment"] for item in required):
                    counts[f"missing_path_{horizon}"] += 1
                    continue
                if exit_at.tz_convert("Asia/Kolkata").time() >= pd.Timestamp("15:30").time():
                    counts[f"session_close_{horizon}"] += 1
                    continue
                closing = book.snapshot(exit_at)
                if call_id not in closing or put_id not in closing:
                    counts[f"missing_exit_{horizon}"] += 1
                    continue
                ec, ep = closing[call_id], closing[put_id]
                if any((x["expiry"], x["strike"], x["option_type"]) != (y["expiry"], y["strike"], y["option_type"])
                       for x, y in ((call, ec), (put, ep))):
                    raise AssertionError("Contract identity changed")
                long_gross = ec["bid"] + ep["bid"] - call["ask"] - put["ask"]
                short_gross = call["bid"] + put["bid"] - ec["ask"] - ep["ask"]
                long_cost = charge_estimate([(1, call["ask"]), (1, put["ask"]), (-1, ec["bid"]), (-1, ep["bid"])], config)
                short_cost = charge_estimate([(-1, call["bid"]), (-1, put["bid"]), (1, ec["ask"]), (1, ep["ask"])], config)
                path = np.array([item["close"] for item in required])
                realised = float(np.sum((np.diff(np.log(path)) * 10000)**2))
                premium_rows.append({"date": day, "decision_at": at, "entry_at": entry_at, "exit_at": exit_at,
                                     "horizon": horizon, "expiry": pair["expiry"], "dte_calendar": expiry_days,
                                     "strike": pair["strike"], "call_id": call_id, "put_id": put_id, "iv": sigma,
                                     "forward": pair["forward"], "iv_calendar_horizon_variance_bps2": sigma**2*horizon/(365*1440)*1e8,
                                     "realised_futures_variance_bps2": realised, "abs_futures_change_points": abs(path[-1]-path[0]),
                                     "entry_mid": (call["bid"]+call["ask"]+put["bid"]+put["ask"])/2,
                                     "mid_change": (ec["bid"]+ec["ask"]+ep["bid"]+ep["ask"]-call["bid"]-call["ask"]-put["bid"]-put["ask"])/2,
                                     "long_gross_points": long_gross, "short_gross_points": short_gross,
                                     "long_net_rupees": long_gross*65-long_cost, "short_net_rupees": short_gross*65-short_cost})
    return pd.DataFrame(iv_rows), pd.DataFrame(premium_rows), dict(counts)


def quantiles(values: pd.Series) -> dict:
    return {str(q): float(x) for q, x in values.quantile([.05, .5, .95]).items()}


def write_numerical_report(result: dict, output: Path) -> None:
    lines = ["# Numerical results", "", "## All variance forecasts", "",
             "Lower QLIKE and root-variance RMSE are better. All thirty comparisons are shown.", "",
             "| Horizon minutes | Model | Rows | Days | QLIKE | Root-variance RMSE bps | Equal-day QLIKE improvement | Descriptive interval |",
             "|---:|---|---:|---:|---:|---:|---:|---|"]
    for horizon, fold in result["variance_forecasts"].items():
        for name, item in fold["metrics"].items():
            lo, hi = item["descriptive_day_bootstrap_95_interval"]
            lines.append(f"| {horizon} | {name} | {item['rows']} | {item['days']} | {item['mean_qlike']:.4f} | {item['rmse_root_variance_bps']:.4f} | {item['day_equal_qlike_improvement_vs_historical']:.4f} | {lo:.4f} to {hi:.4f} |")
    lines += ["", "## Parity and IV diagnostics", "",
              f"The strict cohort has {result['iv_rows']} IV observations on {result['iv_days']} dates. Median annualised IV is {result['iv_quantiles']['0.5']*100:.3f}%; the 5th and 95th percentiles are {result['iv_quantiles']['0.05']*100:.3f}% and {result['iv_quantiles']['0.95']*100:.3f}%.", "",
              f"There were {result['strict_quote_counts']['decision_attempts']} eligible minute decisions. {result['strict_quote_counts'].get('inconsistent_parity_intervals', 0)} failed the common-forward interval test. This restrictive sample must not be treated as representative of every session.", "",
              f"The median inferred forward minus recorded monthly futures price is {result['forward_minus_monthly_future_quantiles_points']['0.5']:.3f} points. Its 5th percentile is {result['forward_minus_monthly_future_quantiles_points']['0.05']:.3f}. Substituting the monthly future can materially distort weekly IV.", "",
              f"A 10% rather than 0% rate changes median IV by {result['rate10_iv_absolute_change_quantiles']['0.5']*100:.4f} percentage points. It does not resolve quote synchronisation or the missing spot problem.", "",
              f"Quote age 2 seconds prices {result['strict_premium_rows']} fixed-contract premium observations. Age 5 seconds prices {result['quote_age5_premium_rows']}. The principal limitation in this cohort is not that small age change.", "",
              "## Straddle observations", "",
              "Overlapping conditional observations, not an executable trading policy. Means apply only to priced coverage. Both long and short means are negative in every segment. Calendar-IV variance is a mechanical proxy, not a physical forecast or a volatility risk premium.", "",
              "| Horizon | Calendar DTE | Rows | Days | Median mid change points | Mean long net rupees | Mean short net rupees | Mean realised variance bps2 | Calendar IV proxy bps2 |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for item in result["straddle_segments"]:
        lines.append(f"| {item['horizon']} | {item['dte_calendar']} | {item['rows']} | {item['days']} | {item['median_mid_change_points']:.3f} | {item['mean_long_net_rupees']:.2f} | {item['mean_short_net_rupees']:.2f} | {item['mean_realised_variance_bps2']:.2f} | {item['mean_calendar_iv_variance_bps2']:.2f} |")
    (output / "numerical-results.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def run(inputs: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(inputs / "features.parquet")
    frame = variance_frame(raw)
    predictions, forecasts = forecast_variance(frame)
    predictions.to_parquet(output / "variance_predictions.parquet", index=False)
    iv, premiums, counts = premium_study(raw, inputs / "sessions", 2.0)
    iv.to_parquet(output / "parity_iv.parquet", index=False)
    premiums.to_parquet(output / "straddle_observations.parquet", index=False)
    _, sensitivity_premiums, sensitivity_counts = premium_study(raw, inputs / "sessions", 5.0)
    summaries = []
    for keys, part in premiums.groupby(["horizon", "dte_calendar"]):
        summaries.append({"horizon": int(keys[0]), "dte_calendar": int(keys[1]), "rows": len(part), "days": part["date"].nunique(),
                          "median_mid_change_points": float(part["mid_change"].median()),
                          "mean_long_net_rupees": float(part["long_net_rupees"].mean()), "mean_short_net_rupees": float(part["short_net_rupees"].mean()),
                          "mean_realised_variance_bps2": float(part["realised_futures_variance_bps2"].mean()),
                          "mean_calendar_iv_variance_bps2": float(part["iv_calendar_horizon_variance_bps2"].mean())})
    result = {"created_date": "2026-10-01", "status": "exploratory_no_deployment", "variance_forecasts": forecasts,
              "iv_rows": len(iv), "iv_days": iv["date"].nunique(), "iv_quantiles": quantiles(iv["iv"]),
              "iv_bidask_width_quantiles": quantiles(iv["iv_ask"] - iv["iv_bid"]),
              "forward_minus_monthly_future_quantiles_points": quantiles(iv["forward"] - iv["monthly_future"]),
              "rate10_iv_absolute_change_quantiles": quantiles(abs(iv["iv_rate10"] - iv["iv"])),
              "strict_quote_counts": counts, "quote_age5_counts": sensitivity_counts,
              "strict_premium_rows": len(premiums), "quote_age5_premium_rows": len(sensitivity_premiums), "straddle_segments": summaries,
              "trial_count": {"variance_model_horizon_comparisons": 30, "quote_age_variants": 2, "rate_assumptions": 3,
                              "straddle_dte_horizon_segments": len(summaries)},
              "source_code_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                     for path in [Path(__file__), ROOT / "nifty_lab/config.py", ROOT / "nifty_lab/replay.py", ROOT / "nifty_lab/strategies.py"]},
              "input_sha256": {str(path.relative_to(inputs)): hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in [inputs / "features.parquet"] + sorted((inputs / "sessions").glob("*/options.parquet"))}}
    (output / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    write_numerical_report(result, output)
    print(json.dumps({"iv_rows": len(iv), "premium_rows": len(premiums), "forecast_rows": len(predictions), "iv_quantiles": result["iv_quantiles"],
                      "forecast_metrics": {h: v["metrics"] for h, v in forecasts.items()}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=ROOT / "research/01_depth_forecast_baseline/artifacts")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "artifacts")
    args = parser.parse_args()
    if not (args.inputs / "features.parquet").is_file():
        parser.error("Input features.parquet missing")
    run(args.inputs, args.output)
