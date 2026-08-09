"""Build and evaluate the leakage-safe Stage 2 quality filter."""

from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from pipeline.research.stage2_quality_replay import (  # noqa: E402
    EXIT_PROFILES,
    FEATURE_SCHEMA_VERSION,
    QualityPolicy,
    apply_policy,
    extract_day_features,
    policy_dict,
    summarize,
)


def _input_manifest(day_dirs: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for day_dir in day_dirs:
        for path in [day_dir / "setup-events.jsonl", *((day_dir / "one-second").rglob("*.parquet"))]:
            stat = path.stat()
            rows.append(
                {
                    "path": str(path.resolve()),
                    "size": stat.st_size,
                    "modified_ns": stat.st_mtime_ns,
                }
            )
    return sorted(rows, key=lambda row: row["path"])


def _confirmed_selection(frame: pd.DataFrame, policy: QualityPolicy) -> pd.Series:
    entry = pd.to_datetime(frame["entry_time"], format="mixed")
    cutoff_hour, cutoff_minute = map(int, policy.entry_cutoff.split(":"))
    before_cutoff = (entry.dt.hour < cutoff_hour) | (
        (entry.dt.hour == cutoff_hour) & (entry.dt.minute < cutoff_minute)
    )
    return (
        frame["confirmation_holds"].astype(bool)
        & (frame["confirmation_gap_seconds"] <= policy.confirmation_max_gap_seconds)
        & before_cutoff
    )


def _summaries_by_date(frames: dict[str, pd.DataFrame], policy: QualityPolicy) -> tuple[list[dict[str, Any]], dict[str, pd.DataFrame]]:
    summaries = []
    evaluated = {}
    for market_date, features in frames.items():
        confirmed = features.copy()
        confirmed["confirmed_selected"] = _confirmed_selection(confirmed, policy)
        filtered = apply_policy(features, policy)
        evaluated[market_date] = filtered
        summaries.extend(
            [
                {"market_date": market_date, "model": "current_raw", **summarize(features, prefix="baseline")},
                {
                    "market_date": market_date,
                    "model": "event_time_integrity",
                    **summarize(confirmed, "confirmed_selected", prefix="improved"),
                },
                {
                    "market_date": market_date,
                    "model": policy.name,
                    **summarize(filtered, "selected", prefix="improved"),
                },
            ]
        )
    return summaries, evaluated


def _plot_comparison(summary: pd.DataFrame, output: Path) -> None:
    dates = sorted(summary["market_date"].unique())
    preferred = ["current_raw", "event_time_integrity", "quality_v3"]
    models = [model for model in preferred if model in set(summary["model"])]
    colors = {"current_raw": "#8795a5", "event_time_integrity": "#6d5bd0", "quality_v3": "#16856b"}
    fig, axes = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    x = np.arange(len(dates)); width = 0.24
    for index, model in enumerate(models):
        local = summary[summary["model"] == model].set_index("market_date").reindex(dates)
        offset = (index - (len(models) - 1) / 2) * width
        axes[0].bar(x + offset, local["signals"], width, label=model, color=colors[model])
        axes[1].bar(x + offset, local["win_percent_when_resolved"], width, label=model, color=colors[model])
    axes[0].set_ylabel("Signals")
    axes[1].set_ylabel("Target-first rate when resolved (%)")
    axes[1].axhline(50, color="#c84b4b", linewidth=0.8, linestyle="--")
    axes[1].set_xticks(x, dates)
    axes[1].set_xlabel("Market date")
    axes[0].legend(loc="upper left", frameon=False, ncol=3)
    for axis in axes:
        axis.grid(True, axis="y", color="#e4e7eb", linewidth=0.6)
    fig.suptitle("Stage 2 candidate filtering: signal count and scalp resolution")
    fig.tight_layout()
    fig.savefig(output, dpi=145, bbox_inches="tight")
    plt.close(fig)


def _plot_score_diagnostics(evaluated: dict[str, pd.DataFrame], output: Path) -> None:
    all_rows = pd.concat(evaluated.values(), ignore_index=True)
    bins = [0, 50, 55, 60, 65, 70, 75, 80, 101]
    all_rows["score_bin"] = pd.cut(all_rows["quality_score"], bins=bins, right=False)
    grouped = all_rows.groupby("score_bin", observed=True).agg(
        signals=("event_id", "size"),
        mean_gross=("improved_gross_return_percent", "mean"),
        target_rate=("improved_outcome", lambda values: 100 * (values == "TARGET_FIRST").mean()),
        stop_rate=("improved_outcome", lambda values: 100 * (values == "STOP_FIRST").mean()),
    )
    labels = [str(value) for value in grouped.index]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    axes[0].bar(x, grouped["signals"], color="#315b9c")
    axes[0].set_ylabel("Candidate events")
    axes[1].plot(x, grouped["target_rate"], marker="o", color="#16856b", label="Target first")
    axes[1].plot(x, grouped["stop_rate"], marker="o", color="#c84b4b", label="Stop first")
    axes[1].axhline(50, color="#8795a5", linewidth=0.8, linestyle="--")
    axes[1].set_ylabel("All-signal rate (%)")
    axes[1].set_xlabel("Quality score range")
    axes[1].set_xticks(x, labels)
    axes[1].legend(loc="upper left", frameon=False)
    for axis in axes:
        axis.grid(True, color="#e4e7eb", linewidth=0.6)
    fig.suptitle("Quality score calibration diagnostics")
    fig.tight_layout()
    fig.savefig(output, dpi=145, bbox_inches="tight")
    plt.close(fig)


def _gate_counts(evaluated: dict[str, pd.DataFrame]) -> dict[str, dict[str, int]]:
    output = {}
    for market_date, frame in evaluated.items():
        counter: Counter[str] = Counter()
        for value in frame["gate_failures"]:
            counter.update(reason for reason in str(value).split("|") if reason)
        output[market_date] = dict(counter.most_common())
    return output


def _exit_profile_summaries(evaluated: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for market_date, frame in evaluated.items():
        for model, selected in (
            ("current_raw", pd.Series(True, index=frame.index)),
            ("quality_v3", frame["selected"].astype(bool)),
        ):
            local = frame[selected]
            for profile_name in EXIT_PROFILES:
                outcomes = local[f"{profile_name}_outcome"]
                resolved = outcomes.isin(["TARGET_FIRST", "STOP_FIRST"])
                rows.append(
                    {
                        "market_date": market_date,
                        "model": model,
                        "exit_profile": profile_name,
                        "signals": int(len(local)),
                        "resolved": int(resolved.sum()),
                        "win_percent_when_resolved": round(
                            100 * int((outcomes == "TARGET_FIRST").sum()) / max(1, int(resolved.sum())),
                            2,
                        ),
                        "mean_gross_return_percent": round(
                            float(local[f"{profile_name}_gross_return_percent"].mean()), 5
                        )
                        if len(local)
                        else None,
                        "mean_net_return_percent": round(
                            float(local[f"{profile_name}_net_return_percent"].mean()), 5
                        )
                        if len(local)
                        else None,
                    }
                )
    return rows


def _plot_exit_profiles(rows: list[dict[str, Any]], output: Path) -> None:
    frame = pd.DataFrame(rows)
    frame = frame[frame["model"] == "quality_v3"]
    dates = sorted(frame["market_date"].unique())
    profiles = list(EXIT_PROFILES)
    x = np.arange(len(profiles))
    width = 0.8 / max(1, len(dates))
    fig, axes = plt.subplots(2, 1, figsize=(15, 10), sharex=True)
    for index, market_date in enumerate(dates):
        local = frame[frame["market_date"] == market_date].set_index("exit_profile").reindex(profiles)
        offset = (index - (len(dates) - 1) / 2) * width
        axes[0].bar(x + offset, local["mean_gross_return_percent"], width, label=market_date)
        axes[1].bar(x + offset, local["mean_net_return_percent"], width, label=market_date)
    for axis, label in zip(axes, ["Mean gross return (%)", "Mean conservative net return (%)"]):
        axis.axhline(0, color="#56616f", linewidth=0.8)
        axis.set_ylabel(label)
        axis.grid(True, axis="y", color="#e4e7eb", linewidth=0.6)
    axes[0].legend(loc="upper left", frameon=False)
    axes[1].set_xticks(x, profiles, rotation=20, ha="right")
    axes[1].set_xlabel("Predeclared exit profile")
    fig.suptitle("Quality-v3 events: exit-profile sensitivity")
    fig.tight_layout()
    fig.savefig(output, dpi=145, bbox_inches="tight")
    plt.close(fig)


def _build_html(summary: list[dict[str, Any]], policy: QualityPolicy, output: Path) -> None:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['market_date'])}</td><td>{html.escape(row['model'])}</td>"
        f"<td>{row['signals']}</td><td>{row['unique_stocks']}</td>"
        f"<td>{row['target_first']}</td><td>{row['stop_first']}</td><td>{row['neither']}</td>"
        f"<td>{row['win_percent_when_resolved'] if row['win_percent_when_resolved'] is not None else '—'}</td>"
        f"<td>{row['mean_gross_return_percent'] if row['mean_gross_return_percent'] is not None else '—'}</td>"
        f"<td>{row['mean_net_return_percent'] if row['mean_net_return_percent'] is not None else '—'}</td>"
        "</tr>"
        for row in summary
    )
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stage 2 quality backtest</title><style>body{{font-family:system-ui,sans-serif;margin:24px;background:#f7f8fa;color:#17212b}}main{{max-width:1450px;margin:auto}}img{{width:100%;height:auto;background:#fff;border:1px solid #dce1e7;margin:18px 0 42px}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{padding:8px;border-bottom:1px solid #e4e7eb;text-align:right}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}code{{background:#e9edf2;padding:2px 5px}}</style></head><body><main>
<h1>Stage 2 quality-filter backtest</h1><p>Candidate events are read from immutable shadow recordings. Evaluation occurs at the saved event time; indicators and candle patterns use the previous fully closed minute, and live features use no later observations.</p>
<p>Policy: <code>{html.escape(json.dumps(policy_dict(policy), separators=(',', ':')))}</code></p>
<table><thead><tr><th>Date</th><th>Model</th><th>Signals</th><th>Stocks</th><th>Target first</th><th>Stop first</th><th>Neither</th><th>Resolved win %</th><th>Mean gross %</th><th>Mean net %</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Comparison</h2><img src="charts/comparison.png" alt="Signal count and target-first comparison by date and model">
<h2>Score diagnostics</h2><img src="charts/score-diagnostics.png" alt="Candidate count and outcome rate by quality score">
<h2>Exit-profile sensitivity</h2><img src="charts/exit-profiles.png" alt="Gross and conservative net return by predeclared exit profile">
<p><a href="backtest-summary.json">Machine-readable summary</a> · <a href="all-evaluated-events.csv">All evaluated events</a></p>
</main></body></html>"""
    output.write_text(document, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", nargs="+", required=True)
    parser.add_argument("--results-dir", type=Path, default=Path(__file__).resolve().parents[2] / "results")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rebuild-features", action="store_true")
    parser.add_argument("--minimum-score", type=float, default=65.0)
    args = parser.parse_args()
    policy = replace(QualityPolicy(), minimum_score=args.minimum_score)
    output = args.output or args.results_dir / "research" / "stage2-quality-v3"
    output.mkdir(parents=True, exist_ok=True)
    cache_dir = output / "feature-cache"
    charts_dir = output / "charts"
    cache_dir.mkdir(exist_ok=True)
    charts_dir.mkdir(exist_ok=True)
    day_dirs = [args.results_dir / "stage2" / market_date for market_date in args.dates]
    before = _input_manifest(day_dirs)
    frames = {}
    for market_date, day_dir in zip(args.dates, day_dirs):
        cache_path = cache_dir / f"{market_date}.parquet"
        if cache_path.exists() and not args.rebuild_features:
            print(f"Loading derived feature cache for {market_date}", flush=True)
            frame = pd.read_parquet(cache_path)
            versions = set(frame.get("feature_schema_version", pd.Series(dtype=int)).dropna())
            if versions != {FEATURE_SCHEMA_VERSION}:
                print(
                    f"Rebuilding stale feature cache for {market_date}: "
                    f"found={sorted(versions)} expected={FEATURE_SCHEMA_VERSION}",
                    flush=True,
                )
                frame = extract_day_features(day_dir, policy)
                frame.to_parquet(cache_path, index=False, compression="zstd")
        else:
            print(f"Extracting leakage-safe features for {market_date}", flush=True)
            frame = extract_day_features(day_dir, policy)
            frame.to_parquet(cache_path, index=False, compression="zstd")
        frames[market_date] = frame
    after = _input_manifest(day_dirs)
    if before != after:
        raise RuntimeError("Input recording metadata changed during the backtest")
    summary_rows, evaluated = _summaries_by_date(frames, policy)
    summary_frame = pd.DataFrame(summary_rows)
    all_evaluated = pd.concat(evaluated.values(), ignore_index=True)
    summary_frame.to_csv(output / "model-comparison.csv", index=False)
    all_evaluated.to_csv(output / "all-evaluated-events.csv", index=False)
    exit_profile_rows = _exit_profile_summaries(evaluated)
    pd.DataFrame(exit_profile_rows).to_csv(output / "exit-profile-comparison.csv", index=False)
    _plot_comparison(summary_frame, charts_dir / "comparison.png")
    _plot_score_diagnostics(evaluated, charts_dir / "score-diagnostics.png")
    _plot_exit_profiles(exit_profile_rows, charts_dir / "exit-profiles.png")
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "dates": args.dates,
        "policy": policy_dict(policy),
        "input_preserved": before == after,
        "input_manifest_entries": len(before),
        "summary": summary_rows,
        "gate_failure_counts": _gate_counts(evaluated),
        "exit_profile_summary": exit_profile_rows,
        "methodology": {
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "candidate_source": "persisted Intra-Finder shadow events",
            "confirmation": "saved confirmed event time; indicators use the previous fully closed one-minute candle",
            "lookahead_in_features": False,
            "outcome_horizon_minutes": policy.horizon_minutes,
            "target_percent": policy.target_percent,
            "stop_percent": policy.stop_percent,
        },
    }
    (output / "backtest-summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (output / "input-manifest.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    _build_html(summary_rows, policy, output / "index.html")
    print(json.dumps({"output": str(output.resolve()), "summary": summary_rows}, indent=2))


if __name__ == "__main__":
    main()
