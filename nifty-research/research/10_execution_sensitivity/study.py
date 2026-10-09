"""Latency and missing-quote sensitivity; fills remain conditional."""
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
from nifty_lab.strategies import charge_estimate


def replay(predictions: pd.DataFrame, books: dict, policy: str, structure: str, latency: int) -> tuple[list[dict], dict]:
    config = ResearchConfig(); counts = Counter(); records = []; busy = None
    for row in predictions.sort_values("decision_at").to_dict("records"):
        at = row["decision_at"]
        if busy is not None and at < busy: continue
        signal = row[f"prediction_{policy}"]
        if not math.isfinite(signal): counts["invalid_signal"] += 1; continue
        if abs(signal) < 2: counts["no_trade"] += 1; continue
        entry_at = at + pd.Timedelta(seconds=latency)
        exit_at = entry_at + pd.Timedelta(minutes=5)
        if exit_at.tz_convert("Asia/Kolkata").time() >= time(15,30): counts["close_gate"] += 1; continue
        book = books.get(row["date"])
        if book is None: counts["missing_session"] += 1; continue
        candidate = choose_directional(book.snapshot(at), row["close"], signal, structure)
        if candidate is None: counts["missing_candidate"] += 1; continue
        entry = book.snapshot(entry_at)
        if not all(leg.security_id in entry for leg in candidate.legs): counts["missing_entry"] += 1; continue
        for leg in candidate.legs:
            quote = entry[leg.security_id]
            if (quote["expiry"], quote["strike"], quote["option_type"]) != (leg.expiry, leg.strike, leg.option_type):
                raise ValueError(f"Contract identity changed before delayed entry: {leg.security_id}")
        strategy = replace(candidate, legs=tuple(replace(leg, bid=entry[leg.security_id]["bid"], ask=entry[leg.security_id]["ask"])
                                                for leg in candidate.legs))
        debit = strategy.expiry_risk()["net_entry_debit"]
        if debit <= 0 or (structure == "vertical" and debit >= 3250): counts["invalid_debit"] += 1; continue
        busy = exit_at
        quotes = book.snapshot(exit_at)
        record = {"date": row["date"], "decision_at": at.isoformat(), "entry_at": entry_at.isoformat(),
                  "exit_at": exit_at.isoformat(), "contracts": [leg.security_id for leg in strategy.legs],
                  "policy": policy, "structure": structure, "latency_seconds": latency, "status": "unpriced_exit"}
        if not all(leg.security_id in quotes for leg in strategy.legs):
            busy = at.tz_convert("Asia/Kolkata").normalize() + pd.Timedelta(days=1)
            counts["unpriced_exit"] += 1; records.append(record); continue
        gross, transactions = mark_to_market(strategy, quotes, config)
        roundtrip_half_spread = sum(((entry[leg.security_id]["ask"]-entry[leg.security_id]["bid"])
                                     + (quotes[leg.security_id]["ask"]-quotes[leg.security_id]["bid"])) / 2 * config.lot_size
                                    for leg in strategy.legs)
        estimated_cost_without_slip = charge_estimate(transactions, config, 0)
        record.update(status="priced", gross_pnl=gross, estimated_cost_without_slip=estimated_cost_without_slip,
                      roundtrip_half_spread=roundtrip_half_spread, order_count=len(transactions),
                      entry_quote_age_max_seconds=max((entry_at-entry[leg.security_id]["timestamp"]).total_seconds() for leg in strategy.legs),
                      exit_quote_age_max_seconds=max((exit_at-quotes[leg.security_id]["timestamp"]).total_seconds() for leg in strategy.legs),
                      net_by_slippage={str(slip): gross-charge_estimate(transactions,config,slip) for slip in (.1,.5,1.)})
        counts["priced"] += 1; records.append(record)
    return records, dict(counts)


def paired_comparison(first: list[dict], second: list[dict]) -> dict:
    key = lambda r: (r["date"], r["decision_at"], r["policy"], r["structure"], tuple(r["contracts"]))
    a = {key(r): r for r in first if r["status"] == "priced"}
    b = {key(r): r for r in second if r["status"] == "priced"}
    common = sorted(a.keys() & b.keys())
    return {"common_priced_entries": len(common),
            "net_difference_on_common_entries": sum(b[k]["net_by_slippage"]["0.1"]-a[k]["net_by_slippage"]["0.1"] for k in common),
            "interpretation": "Paired common priced subset only; missing outcomes and changed trade schedules are excluded"}


def main() -> None:
    baseline = LAB / "research/01_depth_forecast_baseline/artifacts"
    predictions = pd.read_parquet(baseline / "predictions.parquet")
    options = {path.parent.name: pd.read_parquet(path) for path in (baseline / "sessions").glob("*/options.parquet")
               if path.parent.name in set(predictions["date"])}
    output = Path(__file__).parent / "artifacts"; output.mkdir(exist_ok=True)
    all_records = []; comparisons = {}; runs = {}; results = []
    for age in (2, 5):
        books = {day: QuoteBook(frame, age) for day, frame in options.items()}
        for policy in ("momentum", "price_near_depth"):
            for structure in ("single", "vertical"):
                for latency in (1, 3, 5):
                    records, counts = replay(predictions, books, policy, structure, latency)
                    run = f"{policy}_{structure}_age{age}_latency{latency}"; runs[run] = records
                    all_records.extend({**r, "quote_age_limit_seconds": age} for r in records)
                    priced = [r for r in records if r["status"] == "priced"]
                    results.append({"id":run, "policy":policy, "structure":structure, "quote_age_limit_seconds":age,
                        "latency_seconds":latency, "counts":counts, "gross_pnl":sum(r["gross_pnl"] for r in priced),
                        "estimated_cost_without_slip":sum(r["estimated_cost_without_slip"] for r in priced),
                        "half_spread_paid_vs_mid_diagnostic":sum(r["roundtrip_half_spread"] for r in priced),
                        "net_by_slippage":{str(slip):sum(r["net_by_slippage"][str(slip)] for r in priced) for slip in (.1,.5,1.)}})
                    if latency > 1:
                        base = f"{policy}_{structure}_age{age}_latency1"
                        comparisons[f"{base}_vs_{run}"] = paired_comparison(runs[base], records)
    result = {"quote_replay_configurations":24, "cost_scenarios_per_configuration":3, "total_cost_scenarios":72,
              "results":results, "paired":comparisons, "predictions_sha256":hashlib.sha256((baseline/'predictions.parquet').read_bytes()).hexdigest(),
              "limitations":["Recorded receipt time is not original exchange quote time", "Missing sizes and market impact prevent actual fill claims",
                             "Relaxing quote age cannot recover missing data or demonstrate tradable liquidity", "Partial-exit unknowns remain in ledger",
                             "Different latency settings change both prices and schedule; paired subsets are descriptive",
                             "No selecting the best friction assumption as a strategy improvement"]}
    write_json(output / "results.json",result); write_json(output / "ledger.json",all_records)
    lines = ["# Execution sensitivity", "", "24 conditional quote replays, each valued at three extra-slippage settings."
        " Entry identities are fixed at decision time. Five-minute holding period; quote ages 2 and 5 seconds; latencies 1, 3 and 5 seconds.", "",
        "| Policy / structure | Quote age | Latency | Priced / unknown | Gross INR | Net, 0.10 slip | Net, 0.50 slip | Net, 1.00 slip |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in results:
        n=row['net_by_slippage']; c=row['counts']
        lines.append(f"| {row['policy']} / {row['structure']} | {row['quote_age_limit_seconds']} | {row['latency_seconds']} | {c.get('priced',0)} / {c.get('unpriced_exit',0)} | {row['gross_pnl']:.2f} | {n['0.1']:.2f} | {n['0.5']:.2f} | {n['1.0']:.2f} |")
    lines += ["", "Bid/ask spread is already deducted through the execution-side quotes. The half-spread diagnostic measures"
        " the difference from hypothetical midpoint fills; it must not be deducted again. Extra slippage is INR points per"
        " unit per transaction. Estimated charges use current lab assumptions applicable to these archive dates.", "",
        "Increasing slippage always reduces P&L on the same ledger. Latency need not have a monotone effect in a small sample."
        " Apparent improvement when allowing older quotes is an execution-assumption change, not new alpha.", "",
        "## Sources", "", "[HftBacktest primary repository](https://github.com/nkaz001/hftbacktest) and"
        " [fill-model documentation](https://hftbacktest.readthedocs.io/en/latest/order_fill.html) show the role of queue"
        " position, feed latency and incomplete fill evidence. This study uses only a conditional aggressive-quote"
        " model because queue position and sizes are unavailable. The repo's crypto examples are not Nifty validations.", "",
        "[Dhan Full feed format](https://dhanhq.co/docs/v2/live-market-feed/) distinguishes last-trade time from"
        " quote receipt time. [NSE fee circular](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf)"
        " grounds lab transaction-charge assumptions.", "", "Run `python research/10_execution_sensitivity/study.py` from nifty-research."]
    (Path(__file__).parent/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({"configurations":24,"cost_scenarios":72,"nonnegative_base_net":sum(r['net_by_slippage']['0.1']>=0 for r in results)}))


if __name__ == '__main__': main()
