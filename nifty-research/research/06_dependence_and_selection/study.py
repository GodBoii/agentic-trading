"""Sensitivity to dependent labels and researcher selection on viewed dates."""
from __future__ import annotations

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


def bootstrap_interval(values: np.ndarray, repetitions: int = 10000) -> list[float]:
    if not len(values) or not np.isfinite(values).all(): raise ValueError("Finite nonempty observations required")
    rng = np.random.default_rng(20261001)
    # Bound memory even for thousands of minute observations.
    draws = np.concatenate([rng.choice(values, (min(1000, repetitions - start), len(values)), replace=True).mean(axis=1)
                            for start in range(0, repetitions, 1000)])
    return np.quantile(draws, [.025, .975]).tolist()


def exact_family_test(daily: np.ndarray) -> dict:
    """Paired day-sign randomisation with one max statistic for all candidates."""
    if daily.ndim != 2 or daily.shape[0] < 3 or daily.shape[0] > 20 or not np.isfinite(daily).all():
        raise ValueError("Need 3-20 complete date blocks and finite hypotheses")
    observed = daily.mean(axis=0)
    null = np.array([(daily * np.asarray(signs)[:, None]).mean(axis=0)
                     for signs in itertools.product((-1, 1), repeat=len(daily))])
    maxima = null.max(axis=1)
    return {"observed": observed.tolist(),
            "raw_p": [(null[:, i] >= mean - 1e-12).mean().item() for i, mean in enumerate(observed)],
            "max_stat_adjusted_p": [(maxima >= mean - 1e-12).mean().item() for mean in observed],
            "assumption": "Symmetric independent date-level null; exploratory, not White's full stationary-bootstrap Reality Check"}


def null_search_simulation() -> list[dict]:
    """Illustrate selection on synthetic independent zero-mean daily returns."""
    rng = np.random.default_rng(20261001); results = []
    for candidates in (1, 10, 40, 100):
        train = rng.normal(size=(10000, 9, candidates)); test = rng.normal(size=(10000, 9, candidates))
        averages = train.mean(axis=1); winner = averages.argmax(axis=1)
        selected_train = averages[np.arange(len(train)), winner]
        selected_test = test.mean(axis=1)[np.arange(len(test)), winner]
        results.append({"searched_candidates": candidates, "mean_selected_training_return": float(selected_train.mean()),
                        "mean_selected_fresh_return": float(selected_test.mean()),
                        "training_mean_above_0_5_fraction": float((selected_train > .5).mean())})
    return results


def main() -> None:
    baseline = LAB / "research/01_depth_forecast_baseline/artifacts/predictions.parquet"
    frame = pd.read_parquet(baseline).dropna(subset=["target_bps"])
    models = ["price_near_depth", "price_all_depth", "price_depth_estimated_flow"]
    base_error = (frame["prediction_price"] - frame["target_bps"]) ** 2
    differences = pd.DataFrame({model: base_error - (frame[f"prediction_{model}"] - frame["target_bps"]) ** 2 for model in models})
    differences["date"] = frame["date"]
    daily = differences.groupby("date")[models].mean()
    result = {"mode": "exploratory", "source_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
              "date_count": len(daily), "minute_count": len(frame), "registered_comparisons": 3,
              "dependence": {}, "family_test": exact_family_test(daily.to_numpy()),
              "model_order": models, "synthetic_search": null_search_simulation()}
    for model in models:
        row = differences[model].to_numpy(); date_values = daily[model].to_numpy()
        # A nonoverlapping subset avoids every-horizon overlapping targets.
        indices = []; busy = None
        for index, record in frame.sort_values("decision_at").iterrows():
            if busy is not None and record["decision_at"] < busy: continue
            indices.append(index); busy = record["decision_at"] + pd.Timedelta(minutes=5)
        sampled = differences.loc[indices].groupby("date")[model].mean()
        result["dependence"][model] = {"minute_iid_interval": bootstrap_interval(row),
            "equal_date_interval": bootstrap_interval(date_values), "equal_date_mean": float(date_values.mean()),
            "minute_weighted_mean": float(row.mean()), "nonoverlap_rows": len(indices),
            "nonoverlap_equal_date_interval": bootstrap_interval(sampled.to_numpy()),
            "nonoverlap_equal_date_mean": float(sampled.mean()),
            "leave_one_date_out_mean_range": [float(np.delete(date_values, i).mean()) for i in range(len(date_values))],
            "interpretation": "Minute-IID interval shown as an inadequate comparator; day-level intervals are primary"}
    output = Path(__file__).parent / "artifacts"; write_json(output / "results.json", result)
    lines = ["# Dependence and search-selection study", "", "This study re-examines previously viewed baseline predictions. No new market evidence is created.", "",
             "| Added features | Minute-IID interval | Date interval | Nonoverlap date interval | Family p |",
             "|---|---|---|---|---:|"]
    fmt = lambda xs: f"{xs[0]:.3f} to {xs[1]:.3f}"
    for i, model in enumerate(models):
        row = result["dependence"][model]
        lines.append(f"| {model} | {fmt(row['minute_iid_interval'])} | {fmt(row['equal_date_interval'])} | {fmt(row['nonoverlap_equal_date_interval'])} | {result['family_test']['max_stat_adjusted_p'][i]:.3f} |")
    lines += ["", "Improvement is price-model MSE minus candidate MSE, in bps squared. Positive favours added features."
        " Minute-weighted and equal-date estimands differ; they must not be described as identical confidence intervals."
        " Day sign randomisation uses one common sign per date across models. It requires date-level symmetry and independence."
        " It is an exploratory max-statistic correction for three models, not a complete White Reality Check or PBO estimate.", "",
        "## Synthetic search", "", "| Candidates searched | Selected training mean | Fresh mean |", "|---:|---:|---:|"]
    for row in result["synthetic_search"]:
        lines.append(f"| {row['searched_candidates']} | {row['mean_selected_training_return']:.3f} | {row['mean_selected_fresh_return']:.3f} |")
    lines += ["", "Synthetic returns are independent standard-normal observations, not Nifty data or INR returns."
        " The example shows why choosing the best of forty backtests can produce an attractive training number under a zero-edge null.", "",
        "## Sources", "", "[Bailey et al., backtest overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659)", "",
        "[Politis and Romano's stationary bootstrap](https://doi.org/10.1080/01621459.1994.10476870)", "",
        "[ARCH resampling implementation](https://github.com/bashtage/arch/tree/main/arch/bootstrap)", "",
        "[Statsmodels multiple-testing methods](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)", "",
        "Methods implemented locally and tested. Public repos were inspected as sources rather than downloaded and executed.", "",
        "Run `python research/06_dependence_and_selection/study.py` from nifty-research."]
    (Path(__file__).parent / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"models": models, "family_p": result["family_test"]["max_stat_adjusted_p"], "dates": len(daily)}))


if __name__ == "__main__": main()
