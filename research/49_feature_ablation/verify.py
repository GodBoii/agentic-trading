"""Independent numeric model reproduction and exact account-ledger checks."""

import argparse
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.common.data import file_hash
from research.intraday_lab.costs import round_trip_fees

d = importlib.import_module("research.45_market_dataset.dataset")
TRACK = Path(__file__).resolve().parent


def expected_files(spec: dict) -> tuple[set[str], set[str]]:
    predictions = {f"predictions-{phase}-h{horizon}.parquet"
                   for phase in ("validation", "evaluation") for horizon in spec["horizons"]}
    accounts = {f"{phase}-h{horizon}-{name}-cost{cost}"
                for phase in ("validation", "evaluation") for horizon in spec["horizons"]
                for name in ("price_vwap", "own_volume", "peer_context", "full_context", "training_mean")
                for cost in spec["costs_per_leg_bps"]}
    return predictions, accounts


def require_coverage(run: Path, spec: dict) -> None:
    predictions, accounts = expected_files(spec)
    if {p.name for p in run.glob("predictions-*.parquet")} != predictions:
        raise ValueError("prediction file coverage differs from frozen plan")
    for prefix in ("trades", "daily"):
        expected = {f"{prefix}-{stem}.csv" for stem in accounts}
        if {p.name for p in run.glob(f"{prefix}-*.csv")} != expected:
            raise ValueError(f"{prefix} account coverage differs from frozen plan")


def main(output_name: str = "verification-v2.json") -> None:
    run = TRACK / "runs/initial-v1"
    if Path(output_name).name != output_name or not output_name.endswith(".json"):
        raise ValueError("simple JSON output filename required")
    output = run / output_name
    if output.exists():
        raise ValueError("preserve existing verification evidence")
    plan = json.loads((run / "plan.json").read_text())
    results = json.loads((run / "results.json").read_text())
    if file_hash(run / "models-freeze.json") != results["models_sha256"]:
        raise ValueError("frozen numeric model fingerprint changed")
    require_coverage(run, plan["specification"])
    for path, key in [(TRACK / "run.py", "run_source_sha256"),
                      (TRACK / "specification.json", "specification_sha256"),
                      (Path(d.__file__), "dataset_source_sha256"),
                      (TRACK.parent / "45_market_dataset/account.py", "account_source_sha256")]:
        if file_hash(path) != plan[key]:
            raise ValueError(f"frozen source changed: {path}")
    rows, _, manifest = d.load_dataset()
    if json.loads((run / "input-manifest.json").read_text()) != manifest:
        raise ValueError("saved input manifest differs from shared dataset")
    models = json.loads((run / "models-freeze.json").read_text())
    _, expected_accounts = expected_files(plan["specification"])
    result_accounts = {f"{r['phase']}-h{r['horizon']}-{r['model']}-cost{r['cost_per_leg_bps']}": r
                       for r in results["account_results"]}
    if set(result_accounts) != expected_accounts or len(results["account_results"]) != len(expected_accounts):
        raise ValueError("result-summary coverage differs from frozen plan")
    compared = 0
    largest_error = 0.0
    for prediction_file in run.glob("predictions-*.parquet"):
        phase, horizon_string = prediction_file.stem.replace("predictions-", "").split("-h")
        horizon = int(horizon_string)
        saved = pd.read_parquet(prediction_file)
        bounds = plan["specification"][phase]
        actual = rows.loc[rows.date.between(*bounds)].reset_index(drop=True)
        if not np.array_equal(saved.decision_us, actual.decision_us) or not np.array_equal(saved.security_id, actual.security_id):
            raise ValueError("prediction row identities changed")
        if not np.array_equal(saved[f"target_gross_bps_{horizon}"], actual[f"target_gross_bps_{horizon}"]):
            raise ValueError("prediction targets changed")
        for name in ["price_vwap", "own_volume", "peer_context", "full_context"]:
            model = models[f"h{horizon}_{name}"]
            rebuilt = ((actual[model["features"]].to_numpy() - model["mean"]) / model["scale"]) @ np.asarray(model["coefficients"]) + model["intercept"]
            error = float(np.max(np.abs(rebuilt - saved[name].to_numpy())))
            if error > 1e-8:
                raise ValueError("ridge model-state reproduction failed")
            largest_error = max(largest_error, error)
            compared += len(actual)
        outcomes = actual[f"target_gross_bps_{horizon}"].to_numpy()
        for name in ["price_vwap", "own_volume", "peer_context", "full_context", "training_mean"]:
            record = [r for r in results["forecast_metrics"] if r["horizon"] == horizon
                      and r["phase"] == phase and r["model"] == name]
            if len(record) != 1 or record[0]["rows"] != len(actual):
                raise ValueError("forecast metric identity/count mismatch")
            rmse = float(np.sqrt(np.mean((outcomes - saved[name].to_numpy()) ** 2)))
            if not np.isclose(rmse, record[0]["rmse_bps"], rtol=0, atol=1e-9):
                raise ValueError("forecast result RMSE differs from saved predictions")
    checked_trades = 0
    checked_accounts = 0
    for trade_file in run.glob("trades-*.csv"):
        daily_file = trade_file.with_name(trade_file.name.replace("trades-", "daily-"))
        daily = pd.read_csv(daily_file)
        try:
            trades = pd.read_csv(trade_file)
        except pd.errors.EmptyDataError:
            trades = pd.DataFrame()
        if trades.empty:
            if not (daily.trades == 0).all() or not np.allclose(daily.net_pnl, 0):
                raise ValueError("empty trades conflict with daily accounting")
        else:
            gross = trades.side * (trades.exit_price - trades.entry_price) * trades.quantity
            if not np.allclose(gross, trades.gross_pnl, rtol=0, atol=1e-6):
                raise ValueError("gross trade arithmetic mismatch")
            fees = [round_trip_fees(t.entry_price, t.exit_price, int(t.quantity), long=t.side == 1)
                    for t in trades.itertuples()]
            if not np.allclose(fees, trades.fees, rtol=0, atol=1e-6):
                raise ValueError("per-order fee arithmetic mismatch")
            if not np.allclose(gross - trades.fees, trades.net_pnl, rtol=0, atol=1e-6):
                raise ValueError("net accounting mismatch")
            if not ((trades.decision_us < trades.entry_us) & (trades.entry_us < trades.exit_us)).all():
                raise ValueError("trade timing invalid")
            for _, group in trades.groupby(["date", "security_id"]):
                group = group.sort_values("entry_us")
                if (group.entry_us.to_numpy()[1:] < group.exit_us.to_numpy()[:-1]).any():
                    raise ValueError("overlapping instrument exposure")
            net = trades.groupby("date").net_pnl.sum().reindex(daily.date, fill_value=0).to_numpy()
            if not np.allclose(net, daily.net_pnl, rtol=0, atol=1e-6):
                raise ValueError("daily trade reconciliation failed")
        if not (daily.maximum_slots <= 3).all() or not np.allclose(daily.ending_equity - 500000, daily.net_pnl, rtol=0, atol=1e-6):
            raise ValueError("account capital or slot invariant failed")
        stem = trade_file.stem.replace("trades-", "", 1)
        summary = result_accounts[stem]
        if summary["trades"] != len(trades) or summary["sessions"] != len(daily):
            raise ValueError("account summary count differs from saved ledger")
        for column in ["gross_pnl", "fees", "net_pnl"]:
            actual_total = float(trades[column].sum()) if not trades.empty else 0.0
            if not np.isclose(actual_total, summary[column], rtol=0, atol=1e-6):
                raise ValueError("account summary total differs from saved ledger")
        checked_trades += len(trades)
        checked_accounts += 1
    report = {"verified_accounts": checked_accounts, "trade_rows": checked_trades,
              "numeric_predictions_reproduced": compared, "largest_prediction_error_bps": largest_error,
              "dataset_artifacts": manifest["artifacts"], "source_model_ledger_checks": "pass",
              "exact_planned_coverage_and_saved_result_reconciliation": "pass",
              "models_sha256": results["models_sha256"],
              "promotion_eligible": False}
    d.write_json(output, report)
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-name", default="verification-v2.json")
    main(parser.parse_args().output_name)
