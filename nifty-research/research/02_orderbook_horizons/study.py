"""Offline quote-flow and depth ablations. Run from any working directory."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

LAB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB_ROOT))
from nifty_lab.io import capture_time, number, read_records, trading_capture, write_json

PRICE = ["ret_1_bps", "ret_5_bps", "rv_5_bps", "range_5_bps", "log_volume", "minutes_from_open"]
NEAR = ["imbalance_5", "imbalance_points_5", "imbalance_points_10", "imbalance_weighted"]
DEEP = ["imbalance_20", "imbalance_200", "imbalance_points_25", "imbalance_points_50"]
QUOTE = ["queue_imbalance_last", "queue_imbalance_mean", "weighted_mid_bps", "quote_spread_bps"]
FLOW = ["ofi_normalized_1", "ofi_normalized_5"]
PERSISTENCE = ["near_mean_3", "near_mean_5", "near_change_1", "near_deep_disagreement"]
GROUPS = {
    "price": PRICE,
    "price_near": PRICE + NEAR,
    "price_deep": PRICE + DEEP,
    "price_near_deep": PRICE + NEAR + DEEP,
    "price_quote": PRICE + QUOTE,
    "price_ofi": PRICE + FLOW,
    "price_persistence": PRICE + NEAR + PERSISTENCE,
    "price_all": PRICE + NEAR + DEEP + QUOTE + FLOW + PERSISTENCE,
}
HORIZONS = (1, 3, 5, 10)


def ofi_increment(previous: tuple[float, float, float, float],
                  current: tuple[float, float, float, float]) -> float:
    """Cont et al. equation 2, applied to observed quote snapshots."""
    pb, qb, pa, qa = previous
    b, q_b, a, q_a = current
    return (q_b * (b >= pb) - qb * (b <= pb)
            - q_a * (a <= pa) + qa * (a >= pa))


def queue_measures(bid: float, bid_size: float, ask: float, ask_size: float) -> tuple[float, float]:
    """Return normalized queue imbalance and weighted-midpoint offset in bps."""
    if not all(np.isfinite([bid, bid_size, ask, ask_size])):
        raise ValueError("Quote values must be finite")
    if bid <= 0 or ask <= bid or min(bid_size, ask_size) < 0 or bid_size + ask_size <= 0:
        raise ValueError("Quote must be uncrossed with positive total size")
    imbalance = (bid_size - ask_size) / (bid_size + ask_size)
    midpoint = (bid + ask) / 2
    weighted_midpoint = (ask * bid_size + bid * ask_size) / (bid_size + ask_size)
    return imbalance, (weighted_midpoint / midpoint - 1) * 10_000


def extract_quotes(path: Path, day: str) -> tuple[pd.DataFrame, dict]:
    audit: dict = {"invalid_quote": 0, "bad_timestamp": 0, "backwards_timestamp": 0,
                   "resets": 0, "outside_regular_session": 0}
    previous = None
    segment = 0
    rows = []
    for record in read_records(path, audit):
        try:
            stamp = capture_time(record)
        except (KeyError, TypeError, ValueError):
            audit["bad_timestamp"] += 1
            continue
        if not trading_capture(stamp, day):
            audit["outside_regular_session"] += 1
            continue
        packet = record.get("packet")
        if not isinstance(packet, dict) or packet.get("type") != "Full Data":
            continue
        depth = packet.get("depth")
        if not isinstance(depth, list) or not depth or not isinstance(depth[0], dict):
            audit["invalid_quote"] += 1
            continue
        best = depth[0]
        values = [number(best.get(key)) for key in
                  ("bid_price", "bid_quantity", "ask_price", "ask_quantity")]
        volume = number(packet.get("volume"))
        ltp = number(packet.get("LTP"))
        if any(value is None for value in values) or volume is None or ltp is None:
            audit["invalid_quote"] += 1
            continue
        bid, bq, ask, aq = values
        try:
            imbalance, offset = queue_measures(bid, bq, ask, aq)
        except ValueError:
            audit["invalid_quote"] += 1
            continue
        sid = str(packet.get("security_id"))
        sequence = record.get("event_sequence")
        reset = previous is None
        if previous is not None:
            seconds = (stamp - previous["timestamp"]).total_seconds()
            if seconds <= 0:
                audit["backwards_timestamp"] += 1
                continue
            seq_reset = (isinstance(sequence, int) and isinstance(previous["sequence"], int)
                         and sequence < previous["sequence"])
            reset = seconds > 10 or sid != previous["security_id"] or volume < previous["volume"] or seq_reset
            if reset:
                segment += 1
                audit["resets"] += 1
        quote = (bid, bq, ask, aq)
        increment = 0.0 if reset else ofi_increment(previous["quote"], quote)
        rows.append({"timestamp": stamp, "date": day, "segment": segment, "security_id": sid,
                     "ofi": increment, "queue_imbalance": imbalance, "weighted_mid_bps": offset,
                     "quote_spread_bps": (ask - bid) / ((ask + bid) / 2) * 10_000,
                     "average_queue": (bq + aq) / 2})
        previous = {"timestamp": stamp, "sequence": sequence, "volume": volume,
                    "security_id": sid, "quote": quote}
    audit["accepted_quotes"] = len(rows)
    if not rows:
        return pd.DataFrame(), audit
    raw = pd.DataFrame(rows)
    raw["minute"] = raw["timestamp"].dt.floor("min")
    bars = raw.groupby(["date", "segment", "security_id", "minute"], sort=True).agg(
        quote_ofi=("ofi", "sum"), average_queue=("average_queue", "mean"),
        queue_imbalance_last=("queue_imbalance", "last"), queue_imbalance_mean=("queue_imbalance", "mean"),
        weighted_mid_bps=("weighted_mid_bps", "last"), quote_spread_bps=("quote_spread_bps", "last"),
        quote_last_at=("timestamp", "last"), quote_count=("ofi", "size"))
    bars = bars.reset_index()
    bars["decision_at"] = bars["minute"] + pd.Timedelta(minutes=1)
    bars["ofi_normalized_1"] = bars["quote_ofi"] / bars["average_queue"]
    bars["ofi_normalized_5"] = bars.groupby(["date", "segment", "security_id"])["ofi_normalized_1"].transform(
        lambda values: values.rolling(5).sum())
    return bars.drop(columns="minute"), audit


def history_valid(group: pd.DataFrame, length: int = 6) -> pd.Series:
    complete = group["complete_minute"].rolling(length).sum().eq(length)
    contiguous = group["decision_at"].diff(length - 1).eq(pd.Timedelta(minutes=length - 1))
    return complete & contiguous


def horizon_targets(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if not isinstance(horizon, int) or horizon < 1:
        raise ValueError("Horizon must be a positive integer")
    chunks = []
    for _, group in frame.groupby(["date", "segment", "security_id"], sort=False):
        group = group.sort_values("decision_at").copy()
        endpoint = group["decision_at"].shift(-horizon)
        continuous = (endpoint - group["decision_at"]).eq(pd.Timedelta(minutes=horizon))
        future_full = group["complete_minute"].rolling(horizon).sum().shift(-horizon).eq(horizon)
        ready = history_valid(group)
        group["feature_ready"] = ready
        group["target_bps"] = (np.log(group["close"].shift(-horizon) / group["close"]) * 10_000).where(
            ready & continuous & future_full)
        group["label_at"] = endpoint.where(group["target_bps"].notna())
        chunks.append(group)
    return pd.concat(chunks, ignore_index=True)


def add_persistence(frame: pd.DataFrame) -> pd.DataFrame:
    chunks = []
    for _, group in frame.groupby(["date", "segment", "security_id"], sort=False):
        group = group.sort_values("decision_at").copy()
        group["near_mean_3"] = group["imbalance_5"].rolling(3).mean()
        group["near_mean_5"] = group["imbalance_5"].rolling(5).mean()
        group["near_change_1"] = group["imbalance_5"].diff()
        group["near_deep_disagreement"] = group["imbalance_5"] - group["imbalance_200"]
        chunks.append(group)
    return pd.concat(chunks, ignore_index=True)


def score(actual: np.ndarray, predicted: np.ndarray) -> dict:
    residual = actual - predicted
    mask = np.abs(actual) > 0.1
    return {"rows": len(actual), "rmse_bps": float(np.sqrt(np.mean(residual ** 2))),
            "mae_bps": float(np.mean(np.abs(residual))),
            "direction_accuracy": float(np.mean(np.sign(actual[mask]) == np.sign(predicted[mask])))
            if mask.any() and np.any(predicted) else None}


def day_uncertainty(values: np.ndarray, rng: np.random.Generator) -> dict:
    if not len(values):
        raise ValueError("No held-out days")
    boot = rng.choice(values, size=(10_000, len(values)), replace=True).mean(axis=1)
    signs = np.array(list(itertools.product([-1, 1], repeat=len(values))))
    p_value = float(np.mean((signs * values).mean(axis=1) >= values.mean() - 1e-12))
    return {"mean_daily_mse_improvement": float(values.mean()),
            "bootstrap_95_interval": np.quantile(boot, [0.025, 0.975]).tolist(),
            "one_sided_day_sign_flip_p": p_value}


def holm_adjust(pvalues: list[float]) -> list[float]:
    order = np.argsort(pvalues)
    adjusted = np.zeros(len(pvalues))
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, pvalues[index] * (len(pvalues) - rank)))
        adjusted[index] = running
    return adjusted.tolist()


def evaluate(frame: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, dict]:
    features = sorted({column for columns in GROUPS.values() for column in columns})
    cohort = horizon_targets(frame, horizon)
    cohort = cohort.loc[cohort["feature_ready"] & np.isfinite(cohort[features]).all(axis=1)].copy()
    folds = []
    outputs = []
    for day in sorted(cohort["date"].unique()):
        train = cohort.loc[(cohort["date"] < day) & cohort["target_bps"].notna()]
        test = cohort.loc[(cohort["date"] == day) & cohort["target_bps"].notna()].copy()
        if train["date"].nunique() < 5 or len(train) < 200 or test.empty:
            continue
        if not (train["label_at"] < test["decision_at"].min()).all():
            raise AssertionError("Training outcomes overlap test decisions")
        test["prediction_zero"] = 0.0
        test["prediction_momentum"] = test["ret_1_bps"] * horizon
        for name, columns in GROUPS.items():
            model = make_pipeline(StandardScaler(), Ridge(alpha=100))
            model.fit(train[columns], train["target_bps"])
            test[f"prediction_{name}"] = model.predict(test[columns])
        folds.append({"date": day, "train_rows": len(train), "test_rows": len(test),
                      "train_dates": sorted(train["date"].unique())})
        outputs.append(test)
    if not outputs:
        raise ValueError(f"Insufficient history for {horizon}-minute study")
    predictions = pd.concat(outputs, ignore_index=True)
    actual = predictions["target_bps"].to_numpy()
    metrics = {name: score(actual, predictions[f"prediction_{name}"].to_numpy())
               for name in ["zero", "momentum", *GROUPS]}
    comparisons = {}
    rng = np.random.default_rng(20261001 + horizon)
    price_error = (predictions["prediction_price"] - predictions["target_bps"]) ** 2
    for name in GROUPS:
        if name == "price":
            continue
        error_delta = price_error - (predictions[f"prediction_{name}"] - predictions["target_bps"]) ** 2
        by_day = error_delta.groupby(predictions["date"]).mean()
        comparisons[name] = {**day_uncertainty(by_day.to_numpy(), rng), "daily": by_day.to_dict()}
    return predictions, {"horizon_minutes": horizon, "cohort_rows": len(cohort), "folds": folds,
                         "metrics": metrics, "comparisons_vs_price": comparisons}


def run(baseline: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    cached = pd.read_parquet(baseline / "features.parquet")
    manifest = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
    quote_parts = []
    audits = []
    for session in manifest["sessions"]:
        source = Path(session["source"]) / "full_market.ndjson"
        if not source.exists():
            raise FileNotFoundError(source)
        print(f"Reading {session['date']}", flush=True)
        quotes, audit = extract_quotes(source, session["date"])
        audit["date"] = session["date"]
        expected = session["files"]["full_market"].get("sha256")
        if expected and audit["sha256"] != expected:
            raise ValueError(f"Raw archive hash changed: {source}")
        if not quotes.empty:
            quote_parts.append(quotes)
        audits.append(audit)
    quotes = pd.concat(quote_parts, ignore_index=True)
    join_keys = ["date", "segment", "security_id", "decision_at"]
    frame = cached.merge(quotes, on=join_keys, how="left", validate="one_to_one")
    if not (frame.loc[frame["quote_last_at"].notna(), "quote_last_at"]
            < frame.loc[frame["quote_last_at"].notna(), "decision_at"]).all():
        raise AssertionError("Quote feature reaches decision time")
    frame = add_persistence(frame)
    frame.to_parquet(output / "features.parquet", index=False)
    results = []
    predictions = []
    for horizon in HORIZONS:
        prediction, result = evaluate(frame, horizon)
        prediction["horizon_minutes"] = horizon
        predictions.append(prediction)
        results.append(result)
    comparisons = [comparison for result in results for comparison in result["comparisons_vs_price"].values()]
    adjusted = holm_adjust([comparison["one_sided_day_sign_flip_p"] for comparison in comparisons])
    for comparison, value in zip(comparisons, adjusted, strict=True):
        comparison["holm_p_across_28_comparisons"] = value
    summary = {"status": "exploratory", "horizons": results, "model_groups": GROUPS,
               "fitted_configurations": len(GROUPS) * len(HORIZONS),
               "total_configurations_with_baselines": (len(GROUPS) + 2) * len(HORIZONS),
               "fitted_day_models": sum(len(result["folds"]) * len(GROUPS) for result in results),
               "held_out_rows_across_horizons": sum(result["metrics"]["zero"]["rows"] for result in results),
               "source_features_sha256": hashlib.sha256((baseline / "features.parquet").read_bytes()).hexdigest(),
               "study_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "source_audits": audits}
    pd.concat(predictions, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    write_json(output / "results.json", summary)
    write_report(summary, output / "report.md")
    print(json.dumps({key: summary[key] for key in ("fitted_configurations", "fitted_day_models", "held_out_rows_across_horizons")}), flush=True)
    return summary


def write_report(summary: dict, path: Path) -> None:
    lines = ["# Observed quote flow and depth over multiple horizons", "",
             "This is an exploratory forecasting experiment, with no trade simulation or profitability claim.", "",
             f"Tested {summary['fitted_configurations']} fitted configurations and 8 baseline configurations. "
             f"Fit {summary['fitted_day_models']} day models, scoring {summary['held_out_rows_across_horizons']} horizon-rows. "
             "The same minute can occur at multiple horizons; these are not independent observations.", "",
             "Five previous dates and 200 training rows are required. Every scaler and regression uses previous dates only. "
             "Ridge alpha is fixed at 100, with no parameter selection. Each horizon compares the same complete-feature cohort. "
             "A six-minute contiguous complete history is required, and labels cannot cross missing minutes, resets or contracts.", "",
             "| Horizon | Model | Rows | RMSE bps | MAE bps | Direction accuracy |", "|---|---|---:|---:|---:|---:|"]
    for result in summary["horizons"]:
        for name, metric in result["metrics"].items():
            direction = metric["direction_accuracy"]
            lines.append(f"| {result['horizon_minutes']} | {name} | {metric['rows']} | {metric['rmse_bps']:.4f} | "
                         f"{metric['mae_bps']:.4f} | {'n/a' if direction is None else f'{direction:.3%}'} |")
    lines += ["", "Positive MSE improvement favours added features over price-only. Each day receives equal weight. "
              "Intervals resample whole dates, preserving within-day dependence. The sign-flip test assumes symmetric daily "
              "differences and independent dates, neither established by this short archive. Holm adjusts all 28 added-feature "
              "comparisons. These calculations are descriptive, and overlapping targets reduce effective sample size.", "",
              "| Horizon | Added features | Daily MSE improvement | 95% date-bootstrap interval | Holm p |",
              "|---|---|---:|---|---:|"]
    for result in summary["horizons"]:
        for name, value in result["comparisons_vs_price"].items():
            lower, upper = value["bootstrap_95_interval"]
            lines.append(f"| {result['horizon_minutes']} | {name} | {value['mean_daily_mse_improvement']:.4f} | "
                         f"[{lower:.4f}, {upper:.4f}] | {value['holm_p_across_28_comparisons']:.4f} |")
    lines += ["", "## Interpretation limits", "",
              "The Full feed contains bid/ask prices and quantities in one packet, avoiding separate-side pairing for top-quote OFI. "
              "OFI is computed from consecutive observed packets. The broker may omit intermediate exchange changes, so this is "
              "sampled quote-flow OFI, not a full exchange event stream. It is separate from inferred signed trade volume.", "",
              "The weighted midpoint uses opposite-side prices weighted by queue sizes. It is not Stoikov's fitted microprice. "
              "The baseline cache's column named microprice_bps implements a weighted midpoint; this study uses the explicit name. "
              "The full microprice requires transition estimation and should be a separate future experiment.", "",
              "The persistence features are rolling imbalance means and a change. They measure persistence of aggregate pressure, "
              "not persistence of individual orders or cancellation identity. Deeper features use the validated baseline cache, "
              "with backward two-second freshness matching.", "",
              "No midpoint forecast establishes an option edge. Spreads, taxes, latency, IV and tail losses require a separate "
              "execution-aware strategy study. The archive contains only a few regimes and is already reused in earlier work. "
              "These dates are chronologically held out within this experiment, not a fresh untouched market sample.", "",
              "Sources and precise formulas are in the study README. Raw-file hashes are checked against study 01's manifest. "
              "results.json includes every fold, feature group and date-level error difference.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=LAB_ROOT / "research/01_depth_forecast_baseline/artifacts")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "artifacts")
    args = parser.parse_args()
    run(args.baseline.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
