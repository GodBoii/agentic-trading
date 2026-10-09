"""Build an evidence-backed research index and a clearly labeled topic queue."""

from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parents[1]
TOPICS = [
    (1, "Deterministic momentum foundation", "intraday_lab", "shared causal replay, fees, reservations and first baseline"),
    (2, "Opening-range breakout", "02_opening_range", "opening discovery and directional continuation"),
    (3, "Mean reversion", "03_mean_reversion", "rolling zscore, VWAP fade and OU admissibility"),
    (4, "Order-book snapshot proxies", "04_microstructure", "aggregate imbalance, depth changes and weighted quotes"),
    (5, "Cross-sectional relative movement", "05_relative_value", "causal peer residual continuation and reversal"),
    (6, "Volatility compression", "06_volatility_compression", "Bollinger width and compressed-range expansion"),
    (7, "Indicators and candle patterns", "07_indicator_patterns", "RSI recross, Bollinger continuation and wick rejection"),
    (8, "Frozen numerical forecasting", "08_statistical_models", "ridge executable-return and logistic profit baselines"),
    (9, "Variance-ratio regimes", "09_variance_ratio", "serial-dependence descriptors and adaptive direction"),
    (10, "VWAP pullback state machines", "10_vwap_pullback", "impulse, later touch, and later recovery"),
    (11, "Exit mathematics", "11_exit_math", "account exit sensitivities and same-entry counterfactuals"),
    (12, "Execution and cost sensitivities", "12_execution_costs", "delay, slippage, depth footprint and no-trade control"),
    (13, "Fixed-pair spread models", "13_pairs_cointegration", "prior-declared pair, OLS/AR1 descriptors and hedge feasibility"),
    (14, "Intraday time-of-day information", "14_intraday_seasonality", "frozen earlier-session half-hour return information"),
    (15, "Raw-packet timestamp integrity", "15_timestamp_integrity", "quote/trade provenance, signed clock offsets and depth quantities"),
    (16, "Relative-volume surprises", "16_relative_volume", "past-session same-time volume baselines and arrival availability"),
    (17, "Regime mixture models", "17_regime_mixtures", "causal probabilistic regimes with frozen development estimates"),
    (18, "Realized volatility forecasting", "18_volatility_forecasts", "EWMA/GARCH baselines and cost-adjusted opportunity windows"),
    (19, "Kalman state estimation", "19_kalman_state", "online fair-value filtering and innovation-based signals"),
    (20, "CUSUM event detection", "20_cusum_events", "sequential change detection without future boundary selection"),
    (21, "Alternative event bars", "21_event_bars", "time, volume, value and imbalance sampling comparisons"),
    (22, "Price impact descriptors", "22_impact_descriptors", "Kyle-style response measures with explicit sampling limits"),
    (23, "Post-fill adverse selection", "23_adverse_selection", "markouts and toxicity features against calibrated fills"),
    (24, "Passive queue models", "24_passive_queues", "conservative queue simulation after appropriate event data exists"),
    (25, "Participation and impact", "25_participation_impact", "size capacity and market-impact sensitivity experiments"),
    (26, "Cross-instrument lead and lag", "26_lead_lag", "timestamp-safe market/sector response timing"),
    (27, "Opening-to-closing momentum", "27_session_momentum", "early-session information for later-session returns"),
    (28, "News arrival filters", "28_news_arrival", "structured event availability and post-announcement behavior"),
    (29, "Auction and gap mechanics", "29_auction_gaps", "opening auction evidence and causal gap continuation/rejection"),
    (30, "ETF and constituent residuals", "30_etf_residuals", "basket pricing and realistic hedge execution"),
    (31, "Futures basis", "31_futures_basis", "contract-aware fair-value residuals and two-leg costs"),
    (32, "Options volatility surfaces", "32_options_volatility", "surface consistency and expiry-specific feasibility"),
    (33, "Hedged volatility trading", "33_delta_hedging", "gamma/vega exposures with discrete hedge costs"),
    (34, "Tree model baselines", "34_boosted_trees", "frozen tabular models and proper chronological labels"),
    (35, "Temporal neural networks", "35_temporal_models", "sequence forecasting versus simple baselines on adequate data"),
    (36, "Model calibration and abstention", "36_calibration", "reliability, uncertainty and no-trade decisions"),
    (37, "Reinforcement-learning simulation", "37_rl_simulation", "simulator validation before policy reward optimization"),
    (38, "Latency and decay", "38_signal_decay", "measured information-age budgets and delayed opportunity curves"),
    (39, "Fault and recovery experiments", "39_fault_recovery", "submission uncertainty, partial fills, duplicate events and restart"),
    (40, "Multiple-hypothesis audit", "40_multiple_testing", "selection effects, sample limits and explicit diagnostic assumptions"),
]


def evidence(folder: Path) -> dict:
    if not folder.exists():
        return {"status": "queued", "account_replays": 0, "variants": 0, "runs": []}
    findings = [p for p in folder.glob("findings*.md")]
    runs = []
    for aggregate in sorted((folder / "runs").glob("*/aggregate.json")):
        run = aggregate.parent
        if not run.name.startswith("initial-"):
            continue
        if list(run.glob("invalid*.md")) or list(folder.glob(f"invalid-{run.name}.md")):
            continue
        plan_path = run / "plan.json"
        if not plan_path.exists():
            continue
        result = json.loads(aggregate.read_text())
        plan = json.loads(plan_path.read_text())
        if not isinstance(result, dict) or "policy_session_replays" not in result or "variants" not in plan:
            continue
        runs.append({"run": run.name, "account_replays": result["policy_session_replays"],
                     "variants": len({r["name"] for r in plan["variants"]}),
                     "incomplete_comparisons": [
                         {"variant": r["variant"], "mode": r["mode"], "incomplete_sessions": r["incomplete_sessions"]}
                         for r in result["results"] if r["phase"] == "all" and r["incomplete_sessions"]]})
    diagnostics = list((folder / "runs").glob("*/diagnostics.json"))
    diagnostics += [p for p in (folder / "runs").glob("*/audit.json")
                    if (p.parent / "verification.json").exists()]
    diagnostics += [p for p in (folder / "runs").glob("*/aggregate.json")
                    if isinstance(json.loads(p.read_text()), list)
                    and (p.parent / "verification.json").exists()]
    if folder.name == "intraday_lab":
        status = "foundation tested"
    elif findings and runs:
        status = "tested diagnostic"
    elif findings and diagnostics:
        status = "data/math diagnostic"
    elif runs:
        status = "run complete; review pending"
    else:
        status = "in progress"
    return {"status": status, "account_replays": sum(r["account_replays"] for r in runs),
            "variants": sum(r["variants"] for r in runs), "runs": runs,
            "findings": [str(p.relative_to(ROOT)) for p in sorted(findings)]}


def main() -> None:
    rows = []
    for number, title, name, purpose in TOPICS:
        rows.append({"id": number, "topic": title, "folder": name, "purpose": purpose,
                     **evidence(ROOT / name), "promotion_eligible": False})
    (ROOT / "program/registry.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    replays = sum(r["account_replays"] for r in rows)
    variants = sum(r["variants"] for r in rows)
    lines = ["# Trading research program", "",
             "Independent research tracks share a fixed recorded-data cohort and consistent account/fee rules. Each completed track keeps its sources, frozen methods, code, tests, raw results and findings in its own folder.", "",
             "The September30 baseline and architecture report are grouped in `intraday_lab`, the first track. Existing import paths and archived experiment evidence are preserved.", "",
             f"Current batches contain **{variants} frozen variants and {replays} policy/session account replays**, excluding the first baseline, repeatability checks and separate paired/data diagnostics. These counts measure executed experiments, not independent samples or validated strategies.", "",
             "No track is approved for live trading. Receipt-proxy results assume quote usability that our recordings do not verify. Strict results often have insufficient eligible observations. All historical dates were previously inspected, so none is a pristine final holdout.", "",
             "The strict gate checks stored trade-age and health fields. It is not independent proof of quote freshness or correct historical decoder timezone semantics. Track15 investigates those timestamp assumptions.", "",
             "## Research tracks", "", "| ID | Topic | Status | Account replays |", "|---|---|---|---:|"]
    for row in rows:
        label = row["topic"]
        if row["status"] != "queued":
            target = (ROOT / row["folder"] / "README.md").as_posix()
            label = f"[{label}]({target})"
        lines.append(f"|{row['id']:02d}|{label}|{row['status']}|{row['account_replays']}|")
    lines += ["", "Queued topics are plans, not completed research. New folders are created when implementation begins. Several require data that is not available in the current tapes.", "",
              "## Reproduce and verify", "", "From the repository root:", "", "```powershell",
              "python -m research.common.data",
              "python -m research.common.verify_program --tests --output research/program/runs/new-verification",
              "python -m research.program.build_index", "```", "",
              "The cache fixes the prior-Aug18 universe and fingerprints normalized observations. The verifier checks source/input fingerprints, expected session coverage, trade chronology, long/short P&L arithmetic, fees totals, slot bounds and unresolved exposure flags. A verified experiment can still lose money or be statistically uninformative.", "",
              "Use each track's README to run a new experiment. Output folders must be new; interrupted or invalid runs are retained and excluded. Source snapshots document code used at the time. Do not replace a losing version with a profitable-looking version under the same name.", "",
              "## Continuing research", "",
              "Three subagents can work alongside the coordinator. Assign disjoint track folders and rotate topics as agents finish. Freeze methods before evaluation, add meaningful mathematical/causality tests, and report missing prerequisites. A tiny profitable result is a hypothesis requiring independent evidence.", "",
              "The 40-topic queue sets scope for future batches. It does not schedule background execution. Research continues when this chat is running or through a separately configured automation.", "",
              "Shared source is in `common`; baseline execution is in `intraday_lab`. Production code and broker orders are outside this program."]
    (ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"topics": len(rows), "account_variants": variants, "account_replays": replays,
                      "statuses": {status: sum(r["status"] == status for r in rows)
                                   for status in sorted({r["status"] for r in rows})}}))


if __name__ == "__main__":
    main()
