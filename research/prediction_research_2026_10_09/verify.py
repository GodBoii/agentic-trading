"""Check new shared-engine runs and the separate candle/daily diagnostics."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.common.data import ROOT, file_hash
from research.common.verify_program import verify_run
from research.intraday_lab.costs import round_trip_fees


def verify_candles() -> dict:
    track = ROOT / "research/41_ssrn_4631351"
    output = track / "candle-runs/initial-v1"
    plan = json.loads((output / "plan.json").read_text())
    for path, expected in ((track / "candle_run.py", plan["source_sha256"]),
                           (track / "candle-hypotheses.json", plan["hypotheses_sha256"]),
                           (ROOT / "research/intraday_lab/costs.py", plan["fee_source_sha256"])):
        if file_hash(path) != expected:
            raise ValueError(f"candle source/specification fingerprint changed: {path}")
    accepted_days = 0
    source_files = set()
    for coverage in output.glob("coverage-*.json"):
        record = json.loads(coverage.read_text())
        accepted_days += record["accepted_days"]
        for source in record["source_files"]:
            path = ROOT / source["path"]
            if file_hash(path) != source["sha256"]:
                raise ValueError(f"candle source data fingerprint changed: {path}")
            source_files.add(str(path))
    daily = pd.read_csv(output / "daily.csv")
    trades = pd.read_csv(output / "trades.csv")
    keys = ["security_id", "variant", "slippage_bps", "date"]
    if len(daily) != accepted_days * len(plan["variants"]) * len(plan["slippage_bps_per_side"]):
        raise ValueError("candle scenario/session coverage incomplete")
    if daily.duplicated(keys).any() or set(daily.security_id) != set(plan["security_ids"]):
        raise ValueError("candle scenario identity coverage mismatch")
    gross = trades.side * (trades.exit_price - trades.entry_price) * trades.quantity
    if not np.allclose(gross, trades.gross_pnl, rtol=0, atol=1e-6):
        raise ValueError("candle gross PnL arithmetic mismatch")
    fees = np.asarray([round_trip_fees(row.entry_price, row.exit_price, int(row.quantity), long=row.side == 1)
                       for row in trades.itertuples()])
    if not np.allclose(fees, trades.fees, rtol=0, atol=1e-6):
        raise ValueError("candle per-order charges do not match frozen tariff")
    if not np.allclose(trades.gross_pnl - trades.fees, trades.net_pnl, rtol=0, atol=1e-6):
        raise ValueError("candle net PnL arithmetic mismatch")
    sums = trades.groupby(keys)[["gross_pnl", "fees", "net_pnl"]].sum()
    expected = daily.set_index(keys)[["gross_pnl", "fees", "net_pnl"]]
    if not np.allclose(sums.reindex(expected.index, fill_value=0), expected, rtol=0, atol=1e-6):
        raise ValueError("candle daily/trade ledger reconciliation failed")
    if not ((trades.entry_index >= 1) & (trades.exit_index >= trades.entry_index)
            & (trades.exit_index <= 374)).all():
        raise ValueError("candle execution chronology invalid")
    for _, rows in daily.groupby(keys[:3]):
        rows = rows.sort_values("date")
        if not np.isclose(rows.starting_equity.iloc[0], plan["starting_equity_per_independent_sleeve_inr"]):
            raise ValueError("candle starting capital mismatch")
        if not np.allclose(rows.starting_equity.iloc[1:], rows.ending_equity.iloc[:-1], rtol=0, atol=1e-6):
            raise ValueError("candle compounded capital continuity failed")
        if not np.allclose(rows.ending_equity - rows.starting_equity, rows.net_pnl, rtol=0, atol=1e-6):
            raise ValueError("candle daily capital arithmetic failed")
    return {"kind": "independent_compounding_candle_sleeves", "checked_daily_rows": len(daily),
            "checked_trade_rows": len(trades), "unique_eligible_instrument_days": accepted_days,
            "input_files_verified": len(source_files), "per_order_fees": "pass",
            "source_input_fingerprints_and_accounting": "pass", "promotion_eligible": False}


def verify_daily() -> dict:
    run = ROOT / "research/44_daily_forecasts/runs/initial-v1"
    manifest = json.loads((run / "manifest.json").read_text())
    results = json.loads((run / "results.json").read_text())
    for source in manifest["inputs"]:
        if file_hash(ROOT / source["path"]) != source["sha256"]:
            raise ValueError("daily-history input fingerprint mismatch")
    for relative, digest in manifest["source_hashes"].items():
        if file_hash(run / "source" / relative) != digest:
            raise ValueError("daily-history source snapshot mismatch")
    if file_hash(run / "manifest.json") != results["manifest_sha256"] or file_hash(
            run / "model-freeze.json") != results["model_freeze_sha256"]:
        raise ValueError("daily-history manifest/model freeze mismatch")
    predictions = pd.read_parquet(run / "predictions.parquet")
    if not (predictions.feature_date < predictions.target_date).all():
        raise ValueError("daily-history feature timing invalid")
    if predictions.duplicated(["security_id", "target_date"]).any():
        raise ValueError("daily-history prediction identities duplicated")
    if len(predictions) != manifest["cohort"]["evaluation"]["rows"]:
        raise ValueError("daily-history prediction cohort mismatch")
    return {"kind": "daily_bar_forecast_and_reference_price_diagnostic", "prediction_rows": len(predictions),
            "evaluation_dates": predictions.target_date.nunique(), "input_files_verified": len(manifest["inputs"]),
            "feature_chronology_and_fingerprints": "pass", "promotion_eligible": False}


def main() -> None:
    output = Path(__file__).parent / "verification.json"
    if output.exists():
        raise ValueError("preserve the existing verification; choose a new report version")
    shared = [verify_run(ROOT / "research" / name / "runs/initial-v1")
              for name in ["41_ssrn_4631351", "42_weighted_ensemble", "43_github_methods"]]
    report = {"shared_engine_runs": shared, "new_policy_session_replays": sum(r["policy_session_replays"] for r in shared),
              "candle_diagnostic": verify_candles(), "daily_forecast": verify_daily(), "promotion_eligible": False,
              "interpretation": "Checks verify saved arithmetic, provenance and coverage, not true fills or predictive significance"}
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
