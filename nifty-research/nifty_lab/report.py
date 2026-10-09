from __future__ import annotations

import json
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .io import write_json
from .config import ResearchConfig
from .evidence import build_evidence_bundle


def build_report(output: Path) -> None:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    forecast = json.loads((output / "forecast-results.json").read_text(encoding="utf-8"))
    replay = json.loads((output / "option-replay-results.json").read_text(encoding="utf-8"))
    build_evidence_bundle(output, ResearchConfig(**replay["config"]))
    chart_dir = output / "charts"; chart_dir.mkdir(exist_ok=True)
    comparisons = forecast.get("paired_day_comparisons", {})
    accepted = [name for name, value in comparisons.items() if value["bootstrap_95_percent_interval"][0] > 0]
    gate = {"live_execution": "blocked", "agent_execution": "blocked", "research_status": "exploratory",
            "added_feature_groups_with_positive_descriptive_interval": accepted,
            "remaining_requirements": ["Fresh untouched test dates", "Quote sizes, synchronized spot, IV and Greeks",
                                       "Event and intratrade stress coverage", "Paper execution and broker reconciliation",
                                       "Independent evaluation beyond this initial experiment"]}
    write_json(output / "evidence-gates.json", gate)
    model_rows = [{"model": name, **value} for name, value in forecast.get("metrics", {}).items()]
    models = pd.DataFrame(model_rows)
    if not models.empty:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(models["model"], models["rmse_bps"], color="#325c84")
        ax.set_xlabel("Held-out five-minute return RMSE, basis points"); ax.invert_yaxis()
        ax.set_title("Chronological evaluation on the same decision-time cohort")
        fig.tight_layout(); fig.savefig(chart_dir / "forecast-error.png", dpi=150); plt.close(fig)
    if comparisons:
        fig, ax = plt.subplots(figsize=(11, 5))
        for name, result in comparisons.items():
            daily = result["daily_improvement"]
            ax.plot(pd.to_datetime(list(daily)), list(daily.values()), marker="o", label=name)
        ax.axhline(0, color="black", linewidth=0.8); ax.set_ylabel("Price-baseline MSE minus model MSE, bps squared")
        ax.set_title("Does additional information help on each held-out date?")
        ax.tick_params(axis="x", rotation=35); ax.legend(fontsize=8)
        fig.tight_layout(); fig.savefig(chart_dir / "daily-depth-comparison.png", dpi=150); plt.close(fig)
    findings = []
    results = forecast.get("metrics", {})
    if results.get("zero", {}).get("rows", 0):
        best = min(results, key=lambda name: results[name]["rmse_bps"])
        findings.append(f"Lowest overall forecast RMSE belongs to `{best}` at {results[best]['rmse_bps']:.3f} bps.")
    near = comparisons.get("price_near_depth")
    if near:
        wins = sum(value > 0 for value in near["daily_improvement"].values())
        findings.append(f"Nearby depth improves daily MSE on {wins} of {len(near['daily_improvement'])} held-out dates. "
                        f"Its descriptive interval is {near['bootstrap_95_percent_interval'][0]:.3f} to {near['bootstrap_95_percent_interval'][1]:.3f} bps squared.")
    findings.append("No added feature group clears the positive-interval criterion." if not accepted else
                    "A descriptive positive interval requires confirmation on new dates before promotion.")
    lines = ["# Nifty research experiment 1", "", "This is an offline experiment on recorded broker data. No broker connection or live order path exists.", "",
             f"Prepared {manifest['feature_rows']:,} decision rows, including {manifest['labelled_rows']:,} labelled rows. Source file sizes and modification times remained unchanged.", "",
             *findings, "",
             "## Chronological forecast results", "",
             "The baseline uses one-minute sampled futures quote midpoints and cumulative-volume increments. It is not an exchange OHLCV feed. Each model uses the same decision-time cohort. A five-minute label must stay inside a continuous session segment. Scaling and model fitting use earlier dates only.", "",
             "| Model | Scored rows | MAE, bps | RMSE, bps | Direction accuracy |", "|---|---:|---:|---:|---:|"]
    for row in model_rows:
        accuracy = f"{row['direction_accuracy']:.1%}" if row.get("direction_accuracy") is not None else "n/a"
        lines.append(f"| {row['model']} | {row['rows']} | {row.get('mae_bps', 0):.3f} | {row.get('rmse_bps', 0):.3f} | {accuracy} |")
    lines += ["", "![Forecast error](charts/forecast-error.png)", "", "![Per-day depth comparison](charts/daily-depth-comparison.png)", "",
              "Positive daily improvement favours additional information. Overlapping labels are dependent. The confidence intervals resample dates, not individual minutes. There are too few dates for a production claim, and this experiment compares several models without multiple-testing correction.", "",
              "## Conditional option replay", "",
              "Candidates are chosen using pre-decision quotes. Simulated fills use quotes available after a one-second delay. Contracts remain fixed to exit; long legs enter at ask and exit at bid, short hedge legs enter at bid and exit at ask. Estimated taxes, fees and extra slippage are deducted. Each policy has at most one open position. An unpriced exit freezes the policy until the next date.", "",
              "| Policy | Priced trades | Unpriced exits | Conditional net INR | Stress net INR |", "|---|---:|---:|---:|---:|"]
    for name, result in replay["policies"].items():
        lines.append(f"| {name} | {result['priced_trades']} | {result['unpriced_exits']} | {result['conditional_net_pnl']:.2f} | {result['stressed_conditional_net_pnl']:.2f} |")
    lines += ["", "Missing quote sizes and exchange timestamps prevent a fill or capacity claim. P&L for priced trades does not include unknown liquidation outcomes. Closed-trade drawdown does not measure intratrade risk. The test uses a fixed threshold and horizon, not tuned exits.", "",
              "## Archive audit", "", "| Date | Accepted full packets | Derived minutes | Labelled minutes | Depth stale pairs |", "|---|---:|---:|---:|---:|"]
    for session in manifest["sessions"]:
        files = session["files"]
        lines.append(f"| {session['date']} | {files['full_market']['accepted_rows']} | {session['feature_rows']} | {session['labelled_rows']} | {files.get('depth', {}).get('stale_pair', 0)} |")
    lines += ["", "All packet reads produce SHA-256 digests and quarantine counts. Weekend/stale responses, non-full messages, crossed quotes and backwards timestamps are excluded. Segment state resets on gaps, contract changes, cumulative-volume decreases and sequence resets. Saved collector CVD is never a model input.", "",
              "## Deployment status", "", "Live execution and agent execution remain blocked. This version establishes a reproducible measurement path and a strategy payoff library. It does not train a volatility surface, consume news or execute naked short options.", "",
              "Next experiments need fresh dates and richer option fields before changing thresholds or selecting a winning policy. Keep all initial results, including losses and failed feature additions.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    package = Path(__file__).resolve().parent
    artifact_names = ["manifest.json", "features.parquet", "predictions.parquet", "forecast-results.json",
                      "option-replay-results.json", "option-replay-ledger.json", "historical-agent-evidence.json"]
    provenance = {"python": platform.python_version(), "platform": platform.platform(),
                  "dependencies": {name: version(name) for name in ("numpy", "pandas", "pyarrow", "scikit-learn", "matplotlib")},
                  "package_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(package.glob("*.py"))},
                  "artifact_sha256": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                                      for name in artifact_names if (output / name).exists()}}
    write_json(output / "provenance.json", provenance)
