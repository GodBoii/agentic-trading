"""Check saved adaptation deployments and realized account accounting."""

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .model import RidgeModel

TRACK = Path(__file__).resolve().parent


def main() -> None:
    output = TRACK / "runs/initial-v1"
    plan = json.loads((output / "plan.json").read_text(encoding="utf-8"))
    for name, digest in plan["source_hashes"].items():
        if sha256((TRACK / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"frozen research source changed: {name}")
    models = json.loads((output / "models.json").read_text(encoding="utf-8"))
    records = json.loads((output / "deployment-log.json").read_text(encoding="utf-8"))
    for digest, payload in models.items():
        model = RidgeModel(np.array(payload["mean"]), np.array(payload["scale"]),
                           np.array(payload["coefficients"]), payload["intercept"],
                           payload["training_rows"], payload["last_label_end"], payload["method"])
        if model.digest != digest:
            raise ValueError("saved model snapshot hash mismatch")
    controlled = [r for r in records if r["policy"] == "controlled_selector"]
    switches = 0
    prior_digest = None
    for record in records:
        boundary = pd.Timestamp(record["month"] + "-01").tz_localize("Asia/Kolkata").tz_convert("UTC")
        if not pd.Timestamp(record["last_training_label_end"]) < boundary:
            raise ValueError("future label used for monthly deployment")
        if record["deployment_model_sha256"] not in models:
            raise ValueError("deployment model snapshot missing")
    for record in controlled:
        if "scores" in record:
            first = pd.Timestamp(record["validation_dates"][0]).tz_localize("Asia/Kolkata").tz_convert("UTC")
            for digest in [record["incumbent_before_sha256"], *record["shadow_model_hashes"].values()]:
                if not pd.Timestamp(models[digest]["last_label_end"]) < first:
                    raise ValueError("incumbent/challenger training overlaps validation")
            if not pd.Timestamp(record["last_validation_label_end"]) < pd.Timestamp(record["month"] + "-01").tz_localize("Asia/Kolkata").tz_convert("UTC"):
                raise ValueError("unmatured validation outcome used")
        if record["decision"] == "switch_mae_and_cost_gate":
            switches += 1
            candidate = record["scores"][record["chosen_shadow_method"]]
            incumbent = record["scores"]["actual_incumbent"]
            if not (candidate["mae"] <= incumbent["mae"] * 0.99 and candidate["net_utility"] >= max(0.0, incumbent["net_utility"])):
                raise ValueError("saved switch failed declared error/cost gate")
        elif prior_digest is not None and record["deployment_model_sha256"] != prior_digest:
            raise ValueError("model changed despite rejected switch")
        prior_digest = record["deployment_model_sha256"]
    summaries = json.loads((output / "summary.json").read_text(encoding="utf-8"))["results"]
    for summary in summaries:
        key = f"h{summary['horizon']}-{summary['method']}-{summary['split']}-cost{summary['cost_per_leg_bps']:g}"
        daily = pd.read_csv(output / f"daily-{key}.csv")
        if not np.isclose(daily.net_pnl.sum(), summary["net_pnl"], atol=1e-6):
            raise ValueError("summary differs from daily account ledger")
        if summary["trades"]:
            trades = pd.read_csv(output / f"trades-{key}.csv")
            if not np.allclose(trades.net_pnl, trades.gross_pnl - trades.fees, atol=1e-6):
                raise ValueError("trade fee accounting differs")
            if not ((trades.decision_us < trades.entry_us) & (trades.entry_us < trades.exit_us)).all():
                raise ValueError("invalid execution order")
            if not np.isclose(trades.net_pnl.sum(), summary["net_pnl"], atol=1e-6):
                raise ValueError("summary differs from trade account ledger")
    result = {"verified": True, "deployments": len(records), "model_snapshots": len(models),
              "controlled_boundaries": len(controlled), "accepted_switches": switches,
              "account_evaluations": len(summaries), "checks": ["frozen_code", "model_snapshot_hashes", "training_label_maturity",
                  "actual_incumbent_holdout", "challenger_holdout", "no_refit_after_rejected_switch", "error_and_nonnegative_cost_gate", "delayed_execution", "fee_and_daily_accounting"]}
    (output / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
