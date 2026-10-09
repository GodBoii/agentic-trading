from importlib import import_module

import numpy as np
import pandas as pd

experiment = import_module("research.48_controlled_adaptation.experiment")


def history() -> pd.DataFrame:
    dates = pd.bdate_range("2022-01-03", "2025-06-30")
    x = np.sin(np.arange(len(dates)) / 3)
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "x": x,
                         "target": np.where(dates.year < 2024, 2 * x, -2 * x),
                         "label_end": (dates.tz_localize("Asia/Kolkata") + pd.Timedelta(hours=15)).tz_convert("UTC").astype(str)})


def test_actual_incumbent_holdout_and_monthly_immutability() -> None:
    result = experiment.chronological_forecasts(history(), ["x"], 15, lambda *_: 0.0)
    controlled = [r for r in result.deployment_log if r["policy"] == "controlled_selector"]
    assert controlled[0]["decision"] == "waiting_initial_60date_validation"
    eligible = [r for r in controlled if "scores" in r]
    assert eligible
    assert any(r["decision"] == "switch_mae_and_cost_gate" for r in eligible)
    assert any(r["decision"] == "waiting_unseen60date_validation" for r in controlled)
    for row in eligible:
        first = pd.Timestamp(row["validation_dates"][0]).tz_localize("Asia/Kolkata").tz_convert("UTC")
        incumbent = result.models[row["incumbent_before_sha256"]]
        assert pd.Timestamp(incumbent["last_label_end"]) < first
        for digest in row["shadow_model_hashes"].values():
            assert pd.Timestamp(result.models[digest]["last_label_end"]) < first
    for row in controlled:
        boundary = pd.Timestamp(row["month"] + "-01").tz_localize("Asia/Kolkata").tz_convert("UTC")
        assert pd.Timestamp(row["last_training_label_end"]) < boundary
    for previous, current in zip(controlled, controlled[1:]):
        if current["decision"] != "switch_mae_and_cost_gate":
            assert current["deployment_model_sha256"] == previous["deployment_model_sha256"]


def test_future_labels_cannot_change_earlier_predictions_or_switches() -> None:
    original = history()
    changed = original.copy()
    changed.loc[changed.date >= "2025-01-01", "target"] += 100_000
    left = experiment.chronological_forecasts(original, ["x"], 15, lambda *_: 0.0)
    right = experiment.chronological_forecasts(changed, ["x"], 15, lambda *_: 0.0)
    past = original.date.between("2024-01-01", "2024-12-31").to_numpy()
    for method in left.predictions:
        assert np.array_equal(left.predictions[method][past], right.predictions[method][past])
    old_logs = [r for r in left.deployment_log if r["month"] < "2025-01"]
    altered_logs = [r for r in right.deployment_log if r["month"] < "2025-01"]
    assert old_logs == altered_logs
