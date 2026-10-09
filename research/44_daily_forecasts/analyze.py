"""Descriptive day-block uncertainty for an already frozen prediction file."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from research.common.data import file_hash
from .methods import metrics
from .run import TRACK, write_json


def block_mean_interval(values: np.ndarray, *, seed: int = 44,
                        repetitions: int = 2000, block_length: int = 5) -> dict:
    """Circular moving day blocks; preserve all stocks within each daily mean."""
    if values.ndim != 1 or len(values) < block_length or not np.isfinite(values).all():
        raise ValueError("finite daily loss differences required")
    random = np.random.default_rng(seed)
    draws = []
    for _ in range(repetitions):
        starts = random.integers(0, len(values), size=(len(values) + block_length - 1) // block_length)
        indexes = ((starts[:, None] + np.arange(block_length)) % len(values)).ravel()[:len(values)]
        draws.append(float(values[indexes].mean()))
    low, high = np.quantile(draws, [0.025, 0.975])
    return {"mean": float(values.mean()), "descriptive_95pct_interval": [float(low), float(high)],
            "daily_blocks": len(values), "block_length": block_length,
            "bootstrap_repetitions": repetitions, "seed": seed}


def analyze(run_name: str) -> Path:
    run = (TRACK / "runs" / run_name).resolve()
    if not run.is_relative_to(TRACK / "runs"):
        raise ValueError("run must be inside this track")
    output = run / "descriptive-uncertainty.json"
    if output.exists():
        raise ValueError("preserve existing analysis evidence")
    predictions = run / "predictions.parquet"
    data = pd.read_parquet(predictions)
    models = [c for c in data.columns if c not in {"security_id", "feature_date", "target_date",
              "target_bps", "entry_reference", "exit_reference"}]
    report = {"analysis_kind": "posthoc_descriptive_uncertainty_no_model_selection",
              "prediction_sha256": file_hash(predictions), "analysis_source_sha256": file_hash(Path(__file__)),
              "promotion_eligible": False, "paired_daily_mse_differences": {}, "year_metrics": {}}
    for other in ["training_mean", "momentum_ridge", "equal_ensemble"]:
        delta = (data.target_bps - data.weighted_ensemble) ** 2 - (data.target_bps - data[other]) ** 2
        daily = delta.groupby(data.target_date).mean().to_numpy()
        report["paired_daily_mse_differences"][f"weighted_minus_{other}"] = block_mean_interval(daily)
    for year, rows in data.groupby(data.target_date.str[:4]):
        report["year_metrics"][year] = {model: metrics(rows.target_bps.to_numpy(),
            rows[model].to_numpy(), rows.training_mean.to_numpy()) for model in models}
    write_json(output, report)
    print(output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="initial-v1")
    analyze(parser.parse_args().run_name)
