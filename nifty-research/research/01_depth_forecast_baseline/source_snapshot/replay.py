from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import time
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ResearchConfig
from .io import write_json
from .strategies import Strategy, charge_estimate, strategy_library


class QuoteBook:
    """Backward-only lookup. Captured option quotes do not establish fill size."""

    def __init__(self, frame: pd.DataFrame, max_age_seconds: float):
        self.max_age_ns = int(max_age_seconds * 1e9)
        self.by_id = {}
        for sid, group in frame.groupby("security_id", sort=False):
            ordered = group.sort_values("timestamp", kind="stable")
            self.by_id[str(sid)] = (ordered["timestamp"].dt.as_unit("ns").astype("int64").to_numpy(), ordered.to_dict("records"))

    def snapshot(self, at: pd.Timestamp) -> dict[str, dict]:
        result = {}; instant = at.value
        for sid, (times, rows) in self.by_id.items():
            index = int(np.searchsorted(times, instant, side="right")) - 1
            if index >= 0 and 0 <= instant - times[index] <= self.max_age_ns:
                result[sid] = rows[index]
        return result


def choose_directional(snapshot: dict[str, dict], reference: float, prediction: float,
                       structure: str) -> Strategy | None:
    if not snapshot: return None
    expiry = min(row["expiry"] for row in snapshot.values())
    quotes = {(row["option_type"], row["strike"]): row for row in snapshot.values() if row["expiry"] == expiry}
    strikes = sorted({strike for _, strike in quotes})
    atm = min(strikes, key=lambda strike: abs(strike - reference))
    name = ("long_call" if prediction > 0 else "long_put") if structure == "single" else (
        "bull_call_spread" if prediction > 0 else "bear_put_spread")
    return next((candidate for candidate in strategy_library(quotes, atm, expiry) if candidate.name == name), None)


def mark_to_market(strategy: Strategy, exit_quotes: dict[str, dict], config: ResearchConfig) -> tuple[float, list[tuple[int, float]]]:
    transactions = []; pnl = 0.0
    for leg in strategy.legs:
        quote = exit_quotes[leg.security_id]
        if (quote["expiry"], quote["strike"], quote["option_type"]) != (leg.expiry, leg.strike, leg.option_type):
            raise ValueError("Contract identity changed while position was open")
        close_price = quote["bid"] if leg.side > 0 else quote["ask"]
        pnl += leg.side * (close_price - leg.entry_price) * config.lot_size
        transactions.extend([(leg.side, leg.entry_price), (-leg.side, close_price)])
    return pnl, transactions


def replay_policy(predictions: pd.DataFrame, books: dict[str, QuoteBook], config: ResearchConfig,
                  policy: str, structure: str) -> tuple[list[dict], dict]:
    attempts = []; counts: Counter = Counter(); busy_until = None
    for row in predictions.sort_values("decision_at").to_dict("records"):
        at = row["decision_at"]
        if busy_until is not None and at < busy_until: continue
        signal = row[f"prediction_{policy}"]
        if abs(signal) < config.entry_threshold_bps or signal == 0:
            counts["no_trade_signal"] += 1; continue
        entry_at = at + pd.Timedelta(seconds=1)
        exit_at = entry_at + pd.Timedelta(minutes=config.horizon_minutes)
        if exit_at.tz_convert("Asia/Kolkata").time() >= time(15, 30):
            counts["blocked_by_session_close"] += 1
            continue
        book = books.get(row["date"])
        if book is None:
            counts["missing_option_session"] += 1; continue
        # Select contract identities using information available at decision time.
        strategy = choose_directional(book.snapshot(at), row["close"], signal, structure)
        if strategy is None:
            counts["missing_candidate_quotes"] += 1; continue
        entry_quotes = book.snapshot(entry_at)
        if not all(leg.security_id in entry_quotes for leg in strategy.legs):
            counts["missing_entry_quotes"] += 1; continue
        strategy = replace(strategy, legs=tuple(replace(leg, bid=entry_quotes[leg.security_id]["bid"],
                                                       ask=entry_quotes[leg.security_id]["ask"]) for leg in strategy.legs))
        debit = strategy.expiry_risk(config.lot_size)["net_entry_debit"]
        if debit <= 0 or (structure == "vertical" and debit >= 50 * config.lot_size):
            counts["invalid_debit"] += 1; continue
        busy_until = exit_at
        exit_quotes = book.snapshot(exit_at)
        attempt = {"policy": policy, "structure": structure, "date": row["date"], "decision_at": at.isoformat(),
                   "entry_at": entry_at.isoformat(), "exit_at": exit_at.isoformat(), "strategy": strategy.name,
                   "signal_bps": float(signal), "entry_debit": debit,
                   "contracts": [leg.__dict__ for leg in strategy.legs], "status": "unpriced_exit"}
        if not all(leg.security_id in exit_quotes for leg in strategy.legs):
            # Exposure exists in this conditional simulation. Do not discard it
            # then pretend the policy was flat and free to take another trade.
            busy_until = at.tz_convert("Asia/Kolkata").normalize() + pd.Timedelta(days=1)
            counts["unpriced_exit"] += 1; attempts.append(attempt); continue
        gross, transactions = mark_to_market(strategy, exit_quotes, config)
        costs = charge_estimate(transactions, config)
        attempt.update(status="priced", gross_pnl=gross, estimated_costs=costs, net_pnl=gross - costs,
                       stressed_net_pnl=gross - charge_estimate(transactions, config, extra_slippage=0.50),
                       exit_quotes={leg.security_id: {key: exit_quotes[leg.security_id][key]
                                    for key in ("bid", "ask", "timestamp")} for leg in strategy.legs})
        counts["priced"] += 1; attempts.append(attempt)
    return attempts, dict(counts)


def replay(output: Path, config: ResearchConfig) -> dict:
    predictions_path = output / "predictions.parquet"
    if not predictions_path.exists(): raise ValueError("Evaluate forecasts before option replay")
    predictions = pd.read_parquet(predictions_path)
    books = {}
    for day in sorted(predictions["date"].unique()):
        path = output / "sessions" / day / "options.parquet"
        if path.exists(): books[day] = QuoteBook(pd.read_parquet(path), config.option_quote_age_seconds)
    attempts = []; policies = {}
    for policy in ("momentum", "price", "price_near_depth", "price_all_depth", "price_depth_estimated_flow"):
        for structure in ("single", "vertical"):
            ledger, counts = replay_policy(predictions, books, config, policy, structure)
            attempts.extend(ledger)
            priced = [entry for entry in ledger if entry["status"] == "priced"]
            nets = np.array([entry["net_pnl"] for entry in priced])
            cumulative = np.r_[0.0, np.cumsum(nets)]
            key = f"{policy}_{structure}"
            policies[key] = {"counts": counts, "priced_trades": len(priced),
                             "unpriced_exits": counts.get("unpriced_exit", 0),
                             "conditional_net_pnl": float(nets.sum()),
                             "mean_net_pnl": float(nets.mean()) if len(nets) else None,
                             "win_fraction": float((nets > 0).mean()) if len(nets) else None,
                             "closed_trade_drawdown": float(np.max(np.maximum.accumulate(cumulative) - cumulative)),
                             "stressed_conditional_net_pnl": float(sum(entry["stressed_net_pnl"] for entry in priced)),
                             "max_entry_debit": max((entry["entry_debit"] for entry in ledger), default=0),
                             "complete_valuation": not counts.get("unpriced_exit", 0)}
    summary = {"status": "conditional_quote_replay", "config": config.to_dict(), "policies": policies,
               "limitations": ["Quotes lack size, exchange timestamp and fill evidence; all quoted fills are conditional",
                               "Signals use futures as an ATM proxy because synchronous spot is absent",
                               "Only single long options and debit spreads replayed; naked short structures are payoff research only",
                               "One-second latency, one lot, fixed five-minute holding period, no overnight positions",
                               "Unpriced exits remain visible and halt that policy for the rest of that date",
                               "Drawdown uses closed trades, excludes intratrade adverse excursion and unpriced exposure",
                               "Net P&L is not a return on capital or an executable-profit claim",
                               "Fees are estimates; confirm rates and contract-note rounding before any live use"]}
    write_json(output / "option-replay-results.json", summary)
    write_json(output / "option-replay-ledger.json", attempts)
    return summary
