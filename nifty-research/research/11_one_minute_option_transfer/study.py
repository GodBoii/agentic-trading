"""Transfer chronological one-minute futures forecasts into conditional option outcomes."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import time
import hashlib
import json
import math
from pathlib import Path
import sys

import pandas as pd

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB))
from nifty_lab.config import ResearchConfig
from nifty_lab.io import write_json
from nifty_lab.replay import QuoteBook, choose_directional, mark_to_market
from nifty_lab.strategies import Strategy, charge_estimate

POLICIES = ("price", "price_near", "momentum")
THRESHOLDS = (.5, 1., 2.)
STRUCTURES = ("single", "vertical")
CONFIG = ResearchConfig(horizon_minutes=1, option_quote_age_seconds=2.)


def check_identity(strategy: Strategy, quotes: dict[str, dict], phase: str) -> None:
    for leg in strategy.legs:
        quote = quotes[leg.security_id]
        if (quote["expiry"], quote["strike"], quote["option_type"]) != (leg.expiry, leg.strike, leg.option_type):
            raise ValueError(f"Contract identity changed at {phase}: {leg.security_id}")


def replay(predictions: pd.DataFrame, books: dict[str, QuoteBook], policy: str,
           structure: str, threshold: float) -> tuple[list[dict], dict]:
    if policy not in POLICIES or structure not in STRUCTURES or threshold not in THRESHOLDS:
        raise ValueError("Unregistered policy, structure or threshold")
    if predictions["horizon_minutes"].ne(1).any():
        raise ValueError("This study only accepts one-minute forecasts")
    counts: Counter = Counter(); ledger = []; busy_until = None
    for row in predictions.sort_values("decision_at").to_dict("records"):
        at = row["decision_at"]
        counts["decision_rows"] += 1
        if busy_until is not None and at < busy_until:
            counts["blocked_by_exposure"] += 1; continue
        signal = row[f"prediction_{policy}"]
        if not math.isfinite(signal) or not math.isfinite(row["close"]) or row["close"] <= 0:
            counts["invalid_evidence"] += 1; continue
        if abs(signal) < threshold:
            counts["no_trade_signal"] += 1; continue
        counts["threshold_signals"] += 1
        entry_at = at + pd.Timedelta(seconds=1)
        exit_at = at + pd.Timedelta(minutes=1)
        if exit_at.tz_convert("Asia/Kolkata").time() >= time(15, 30):
            counts["session_close_gate"] += 1; continue
        book = books.get(row["date"])
        if book is None:
            counts["missing_option_session"] += 1; continue
        candidate = choose_directional(book.snapshot(at), row["close"], signal, structure)
        if candidate is None:
            counts["missing_candidate"] += 1; continue
        entry_quotes = book.snapshot(entry_at)
        if not all(leg.security_id in entry_quotes for leg in candidate.legs):
            counts["missing_entry_quotes"] += 1; continue
        check_identity(candidate, entry_quotes, "delayed_entry")
        strategy = replace(candidate, legs=tuple(replace(leg, bid=entry_quotes[leg.security_id]["bid"],
            ask=entry_quotes[leg.security_id]["ask"]) for leg in candidate.legs))
        debit = strategy.expiry_risk(CONFIG.lot_size)["net_entry_debit"]
        if debit <= 0 or (structure == "vertical" and debit >= 50 * CONFIG.lot_size):
            counts["invalid_debit"] += 1; continue
        busy_until = exit_at
        counts["entered"] += 1
        record = {"date": row["date"], "decision_at": at.isoformat(), "entry_at": entry_at.isoformat(),
            "exit_at": exit_at.isoformat(), "policy": policy, "structure": structure,
            "threshold_bps": threshold, "signal_bps": float(signal), "strategy": strategy.name,
            "contracts": [leg.__dict__ for leg in strategy.legs], "entry_debit": debit,
            "entry_quote_age_max_seconds": max((entry_at-entry_quotes[leg.security_id]["timestamp"]).total_seconds()
                                                for leg in strategy.legs), "status": "unpriced_exit"}
        exit_quotes = book.snapshot(exit_at)
        if not all(leg.security_id in exit_quotes for leg in strategy.legs):
            busy_until = at.tz_convert("Asia/Kolkata").normalize() + pd.Timedelta(days=1)
            counts["unpriced_exit"] += 1; ledger.append(record); continue
        check_identity(strategy, exit_quotes, "exit")
        gross, transactions = mark_to_market(strategy, exit_quotes, CONFIG)
        charges = charge_estimate(transactions, CONFIG, extra_slippage=0.)
        half_spread = sum(((entry_quotes[leg.security_id]["ask"]-entry_quotes[leg.security_id]["bid"])
            + (exit_quotes[leg.security_id]["ask"]-exit_quotes[leg.security_id]["bid"]))
            * CONFIG.lot_size / 2 for leg in strategy.legs)
        record.update(status="priced", gross_pnl=gross, estimated_charges_excluding_slippage=charges,
            roundtrip_half_spread_diagnostic=half_spread, order_count=len(transactions),
            exit_quote_age_max_seconds=max((exit_at-exit_quotes[leg.security_id]["timestamp"]).total_seconds()
                                           for leg in strategy.legs),
            net_pnl=gross-charge_estimate(transactions, CONFIG),
            stressed_net_pnl=gross-charge_estimate(transactions, CONFIG, extra_slippage=.5))
        counts["priced"] += 1; ledger.append(record)
    return ledger, dict(counts)


def summarize(ledger: list[dict], counts: dict) -> dict:
    priced = [row for row in ledger if row["status"] == "priced"]
    daily = {}
    for row in ledger:
        day = daily.setdefault(row["date"], {"priced": 0, "unpriced_exit": 0, "conditional_net_pnl": 0.})
        day[row["status"]] += 1
        if row["status"] == "priced": day["conditional_net_pnl"] += row["net_pnl"]
    return {"counts": counts, "daily": daily, "complete_valuation": not counts.get("unpriced_exit", 0),
        "gross_pnl_priced_subset": sum(row["gross_pnl"] for row in priced),
        "estimated_charges_priced_subset": sum(row["estimated_charges_excluding_slippage"] for row in priced),
        "conditional_net_pnl": sum(row["net_pnl"] for row in priced),
        "stressed_conditional_net_pnl": sum(row["stressed_net_pnl"] for row in priced),
        "half_spread_diagnostic_priced_subset": sum(row["roundtrip_half_spread_diagnostic"] for row in priced),
        "mean_net_pnl_priced_subset": sum(row["net_pnl"] for row in priced)/len(priced) if priced else None,
        "max_entry_debit": max((row["entry_debit"] for row in ledger), default=0.)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    source = LAB / "research/02_orderbook_horizons/artifacts/predictions.parquet"
    predictions = pd.read_parquet(source)
    predictions = predictions.loc[predictions["horizon_minutes"].eq(1)].copy()
    if predictions.empty: raise ValueError("No one-minute predictions")
    if predictions.duplicated(["date", "decision_at"]).any(): raise ValueError("Duplicate one-minute decision")
    if not predictions["prediction_zero"].eq(0).all(): raise ValueError("Zero reference changed")
    baseline = LAB / "research/01_depth_forecast_baseline/artifacts/sessions"
    books = {}; option_sources = {}
    for day in sorted(predictions["date"].unique()):
        path = baseline / day / "options.parquet"
        if path.exists():
            frame = pd.read_parquet(path)
            books[day] = QuoteBook(frame, CONFIG.option_quote_age_seconds)
            option_sources[day] = {"relative_path": str(path.relative_to(LAB)), "sha256": sha256(path), "rows": len(frame)}
    results = []; records = []
    for policy in POLICIES:
        for threshold in THRESHOLDS:
            for structure in STRUCTURES:
                ledger, counts = replay(predictions, books, policy, structure, threshold)
                key = f"{policy}_{structure}_threshold{threshold:g}"
                results.append({"id": key, "policy": policy, "structure": structure, "threshold_bps": threshold,
                                **summarize(ledger, counts)})
                records.extend({"configuration_id": key, **row} for row in ledger)
    result = {"status": "post_selection_exploratory_conditional_quote_replay", "run_date": "2026-10-02",
        "execution_available": False, "registered_configurations": 18, "thresholds_bps": THRESHOLDS,
        "config": CONFIG.to_dict(), "entry_latency_seconds": 1, "holding_seconds": 59,
        "exit_seconds_after_forecast_label": 0, "source_rows": len(predictions),
        "source_dates": sorted(predictions["date"].unique()), "source_sha256": sha256(source),
        "study_sha256": sha256(Path(__file__)), "dependencies_sha256": {name: sha256(LAB / name)
            for name in ("nifty_lab/replay.py", "nifty_lab/strategies.py", "nifty_lab/config.py")},
        "option_sources": option_sources, "results": results,
        "no_trade_reference": {"positions": 0, "gross_pnl": 0., "costs": 0., "net_pnl": 0.},
        "limitations": ["One-minute horizon and nearby depth selected after viewing study02; no untouched confirmation",
            "Source predictions only save the common cohort with known future labels; not all possible live decisions",
            "Scheduled exit matches decision+60-second forecast label; one-second entry latency leaves 59 seconds exposure",
            "Recorded bid/ask lack saved size and exchange quote time; quoted fills remain conditional",
            "Futures midpoint chooses ATM proxy because synchronized spot is unavailable",
            "Unpriced exits remain in ledger and stop entries for that date; priced subset is not whole-policy P&L",
            "Each policy has its own trade schedule; aggregate P&L differences do not isolate feature attribution",
            "Brokerage and statutory charges are estimated with archive-date rates, no contract-note rounding",
            "No parameter winner selected, no margin or intratrade-loss validation, no live execution"]}
    output = Path(__file__).parent / "artifacts"
    write_json(output / "results.json", result); write_json(output / "ledger.json", records)
    lines = ["# One-minute forecasts transferred to options", "",
        f"All 18 fixed configurations use {len(predictions)} chronological out-of-sample forecast rows on {predictions['date'].nunique()} previously viewed dates. "
        "Nearby depth and the one-minute horizon were selected after study02. This is development research.", "",
        "Thresholds of 0.5, 1 and 2 bps are registered together. No best threshold is promoted. "
        "Price-only, price plus nearby depth and momentum each select a long option or a 50-point debit spread. "
        "Contracts are selected at decision time, priced after one second and closed 60 seconds after the decision using the same identities. "
        "The 59-second exposure interval ends at the underlying one-minute forecast label. Zero forecasts produce no trades and zero costs.", "",
        "| Policy | Threshold bps | Structure | Entered | Priced / unknown | Gross INR | Charges INR | Net INR | Stressed net INR |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for row in results:
        c = row['counts']
        lines.append(f"| {row['policy']} | {row['threshold_bps']:g} | {row['structure']} | {c.get('entered',0)} | "
            f"{c.get('priced',0)} / {c.get('unpriced_exit',0)} | {row['gross_pnl_priced_subset']:.2f} | "
            f"{row['estimated_charges_priced_subset']:.2f} | {row['conditional_net_pnl']:.2f} | {row['stressed_conditional_net_pnl']:.2f} |")
    lines += ["", "Gross already uses ask for buys and bid for sells. Charges include estimated brokerage, exchange/IPFT, SEBI, GST, "
        "sale-premium STT and buy-side stamp duty. Net also subtracts 0.10 points per unit per transaction; the stressed column uses 0.50. "
        "The half-spread diagnostic is saved separately and is never deducted a second time.", "",
        "Unknown exits remain open in the conditional ledger and block re-entry for the rest of that date. "
        "Their final P&L and full costs are unknown. Therefore each net figure covers the priced subset only, even when positive. "
        "Blocked, missing-candidate, missing-entry and no-signal counts plus date outcomes are in results.json.", "",
        "The input forecast file also omits decisions without known future underlying labels. This coverage selection existed before "
        "option replay. A subsequent prospective collector must preserve every causal prediction, including missing outcomes.", "",
        "A smaller forecast error need not produce option profit. Option movement, bid/ask spread, order count and charges decide "
        "economic transfer. Different policies take different schedules and contracts, so subtracting their net totals does not "
        "establish a causal nearby-depth benefit. No trade is the zero-cost reference. No configuration is approved for trading.", "",
        "Source definitions and fee references are in README.md. Input, dependency and study hashes are in results.json. "
        "Run `python research/11_one_minute_option_transfer/study.py` from nifty-research."]
    (Path(__file__).parent / "report.md").write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({"configurations": len(results), "source_rows": len(predictions),
        "positive_priced_subset_net_configurations": sum(row['conditional_net_pnl'] > 0 for row in results)}))


if __name__ == '__main__': main()
