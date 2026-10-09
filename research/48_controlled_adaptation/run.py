"""Run frozen adaptation comparisons against the shared delayed-execution account."""

from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from .experiment import chronological_forecasts

TRACK = Path(__file__).resolve().parent


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")


def errors(actual: np.ndarray, predicted: np.ndarray) -> dict:
    mae = float(np.mean(np.abs(actual - predicted)))
    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    nonzero = actual != 0
    return {"rows": len(actual), "mae_bps": mae, "rmse_bps": rmse,
            "direction_accuracy_nonzero": float(np.mean(np.sign(actual[nonzero]) == np.sign(predicted[nonzero]))) if nonzero.any() else None,
            "zero_forecast_mae_bps": float(np.mean(np.abs(actual))),
            "zero_forecast_rmse_bps": float(np.sqrt(np.mean(actual ** 2)))}


def main() -> None:
    dataset = import_module("research.45_market_dataset.dataset")
    account = import_module("research.45_market_dataset.account")
    df, _sequences, manifest = dataset.load_dataset()
    output = TRACK / "runs/initial-v1"
    output.mkdir(parents=True, exist_ok=False)
    hypotheses = TRACK / "hypotheses.json"
    specification = json.loads(hypotheses.read_text(encoding="utf-8"))
    hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in TRACK.glob("*.py")}
    write_json(output / "plan.json", {**specification, "specification_sha256": sha256(hypotheses.read_bytes()).hexdigest(),
                                      "source_hashes": hashes, "dataset_manifest": manifest,
                                      "shared_account_sha256": sha256(Path(account.__file__).read_bytes()).hexdigest(),
                                      "features": list(dataset.FEATURES_CONTEXT)})
    summary_rows = []
    deployment_records = []
    snapshots = {}

    def utility(validation: pd.DataFrame, prediction: np.ndarray, horizon: int) -> float:
        summary, _trades, _daily = account.account_replay(validation, prediction, horizon,
                                                        threshold_net_bps=2.0, cost_per_leg_bps=2.0)
        return float(summary["net_pnl"] / len(validation))

    for horizon in (15, 5, 30):
        started = time.perf_counter()
        work = df.copy().reset_index(drop=True)
        work["target"] = work[f"target_gross_bps_{horizon}"]
        work["label_end"] = pd.to_datetime(work[f"exit_us_{horizon}"], unit="us", utc=True).astype(str)
        result = chronological_forecasts(work, list(dataset.FEATURES_CONTEXT), horizon, utility, controlled=horizon == 15)
        deployment_records.extend(result.deployment_log)
        snapshots.update(result.models)
        predictions = work[["date", "security_id", "decision_us", "target"]].copy()
        for method, forecast in result.predictions.items():
            predictions[method] = forecast
            for split, mask in (
                ("validation_2024", work.date.str.startswith("2024-")),
                ("historical_test_2025_2026", work.date >= "2025-01-01"),
                ("historical_test_2025", work.date.str.startswith("2025-")),
                ("historical_test_2026", work.date.str.startswith("2026-")),
            ):
                part = work.loc[mask].reset_index(drop=True)
                predicted = forecast[mask.to_numpy()]
                if not len(part):
                    continue
                metrics = errors(part.target.to_numpy(), predicted)
                for cost in specification["evaluation_cost_bps_per_side"]:
                    summary, trades, daily = account.account_replay(part, predicted, horizon,
                                                                  threshold_net_bps=2.0, cost_per_leg_bps=cost)
                    key = f"h{horizon}-{method}-{split}-cost{cost:g}"
                    trades.to_csv(output / f"trades-{key}.csv", index=False)
                    daily.to_csv(output / f"daily-{key}.csv", index=False)
                    row = {"horizon": horizon, "method": method, "split": split, **metrics, **summary}
                    summary_rows.append(row)
                    print(json.dumps({"horizon": horizon, "method": method, "split": split,
                                      "cost_per_leg_bps": cost, "mae_bps": metrics["mae_bps"],
                                      "trades": summary["trades"], "net_pnl": summary["net_pnl"]}), flush=True)
        predictions.to_parquet(output / f"predictions-h{horizon}.parquet", index=False)
        print(json.dumps({"event": "horizon_finished", "horizon": horizon,
                          "elapsed_seconds": round(time.perf_counter() - started, 1)}), flush=True)
        write_json(output / "summary.json", {"results": summary_rows, "promotion_eligible": False})
        write_json(output / "deployment-log.json", deployment_records)
        write_json(output / "models.json", snapshots)


if __name__ == "__main__":
    main()
