"""Offline, conditional quote replay and explicitly synthetic hedging experiments."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import time
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB))
from nifty_lab.config import ResearchConfig
from nifty_lab.io import write_json
from nifty_lab.strategies import Leg, Strategy, charge_estimate, strategy_library

HERE = Path(__file__).resolve().parent
INPUT = LAB / "research/01_depth_forecast_baseline/artifacts"
NAMES = ("long_call", "long_put", "long_straddle", "short_straddle", "long_strangle",
         "short_strangle", "bull_call_spread", "bear_put_spread", "iron_condor",
         "iron_butterfly", "bull_put_credit", "bear_call_credit")
HORIZONS = (5, 15, 30)


class IndexedBook:
    """Receipt-time backward lookup, with quote validity checked at construction."""

    def __init__(self, frame: pd.DataFrame, age_seconds: float = 2):
        if not math.isfinite(age_seconds) or age_seconds <= 0:
            raise ValueError("Quote age must be positive")
        self.age_ns = int(age_seconds * 1e9)
        self.by_id = {}
        for sid, group in frame.groupby("security_id", sort=False):
            group = group.sort_values("timestamp", kind="stable")
            identities = group[["expiry", "strike", "option_type"]].drop_duplicates()
            if len(identities) != 1:
                raise ValueError(f"Contract identity changes for {sid}")
            bids, asks = group["bid"].to_numpy(), group["ask"].to_numpy()
            if not (np.isfinite(bids).all() and np.isfinite(asks).all()
                    and (bids >= 0).all() and (asks > bids).all()):
                raise ValueError(f"Invalid quotes for {sid}")
            identity = identities.iloc[0].to_dict()
            self.by_id[str(sid)] = (group["timestamp"].dt.as_unit("ns").astype("int64").to_numpy(),
                                   bids, asks, identity)

    def snapshot(self, at: pd.Timestamp, ids: tuple[str, ...] | None = None) -> dict[str, dict]:
        result = {}
        for sid in self.by_id if ids is None else ids:
            if sid not in self.by_id:
                continue
            stamps, bids, asks, identity = self.by_id[sid]
            index = int(np.searchsorted(stamps, at.value, side="right")) - 1
            if index >= 0 and 0 <= at.value - stamps[index] <= self.age_ns:
                result[sid] = dict(identity, security_id=sid, bid=float(bids[index]),
                                   ask=float(asks[index]), timestamp=pd.Timestamp(stamps[index], tz="UTC"))
        return result


def candidates(snapshot: dict[str, dict], reference: float) -> dict[str, Strategy]:
    if not snapshot or not math.isfinite(reference) or reference <= 0:
        return {}
    expiry = min(row["expiry"] for row in snapshot.values())
    quotes = {(row["option_type"], row["strike"]): row for row in snapshot.values()
              if row["expiry"] == expiry}
    strikes = sorted({strike for _, strike in quotes})
    atm = min(strikes, key=lambda strike: (abs(strike - reference), strike))
    result = {item.name: item for item in strategy_library(quotes, atm, expiry) if item.name != "no_trade"}
    for credit, debit in (("bull_put_credit", "bear_put_spread"),
                          ("bear_call_credit", "bull_call_spread")):
        if debit in result:
            result[credit] = Strategy(credit, tuple(replace(leg, side=-leg.side) for leg in result[debit].legs))
    return result


def reprice(strategy: Strategy, quotes: dict[str, dict]) -> Strategy | None:
    legs = []
    for leg in strategy.legs:
        row = quotes.get(leg.security_id)
        if row is None:
            return None
        if (row["expiry"], row["strike"], row["option_type"]) != (leg.expiry, leg.strike, leg.option_type):
            raise ValueError("Fixed contract identity changed")
        legs.append(replace(leg, bid=row["bid"], ask=row["ask"]))
    return replace(strategy, legs=tuple(legs))


def liquidation(strategy: Strategy, quotes: dict[str, dict], config: ResearchConfig,
                extra_slippage: float | None = None) -> tuple[float, float] | None:
    if reprice(strategy, quotes) is None:
        return None
    pnl, transactions = 0.0, []
    for leg in strategy.legs:
        row = quotes[leg.security_id]
        price = row["bid"] if leg.side > 0 else row["ask"]
        pnl += leg.side * (price - leg.entry_price) * config.lot_size
        transactions.extend(((leg.side, leg.entry_price), (-leg.side, price)))
    costs = charge_estimate(transactions, config, extra_slippage=extra_slippage)
    return pnl, costs


def entry_economic(strategy: Strategy, lot_size: int) -> bool:
    debit = strategy.expiry_risk(lot_size)["net_entry_debit"] / lot_size
    if strategy.name in {"iron_condor", "iron_butterfly", "bull_put_credit", "bear_call_credit"}:
        widths = max(leg.strike for leg in strategy.legs) - min(leg.strike for leg in strategy.legs)
        if strategy.name == "iron_condor":
            widths = 50.0
        if strategy.name == "iron_butterfly":
            widths /= 2
        return -widths < debit < 0
    if strategy.name in {"bull_call_spread", "bear_put_spread"}:
        return 0 < debit < max(leg.strike for leg in strategy.legs) - min(leg.strike for leg in strategy.legs)
    return True


def replay_day(rows: list[dict], book: IndexedBook, name: str, horizon: int,
               config: ResearchConfig) -> tuple[list[dict], dict]:
    attempts, counts = [], Counter()
    busy_until = None
    for row in rows:
        at = row["decision_at"]
        if busy_until is not None and at <= busy_until:
            counts["busy"] += 1
            continue
        entry_at = at + pd.Timedelta(seconds=1)
        exit_at = entry_at + pd.Timedelta(minutes=horizon)
        if exit_at.tz_convert("Asia/Kolkata").time() >= time(15, 30):
            counts["session_close"] += 1
            continue
        # Never inspect target labels, future coverage or future quotes at entry.
        strategy = candidates(book.snapshot(at), float(row["close"])).get(name)
        if strategy is None:
            counts["candidate_missing"] += 1
            continue
        ids = tuple(leg.security_id for leg in strategy.legs)
        strategy = reprice(strategy, book.snapshot(entry_at, ids))
        if strategy is None:
            counts["entry_missing"] += 1
            continue
        if not entry_economic(strategy, config.lot_size):
            counts["invalid_entry_economics"] += 1
            continue
        busy_until = exit_at
        risk = strategy.expiry_risk(config.lot_size)
        event = dict(date=row["date"], strategy=name, horizon_minutes=horizon,
                     decision_at=at.isoformat(), entry_at=entry_at.isoformat(), exit_at=exit_at.isoformat(),
                     status="unpriced_exit", contracts=[leg.__dict__ for leg in strategy.legs],
                     expiry_risk=risk, margin=None, capacity=None,
                     entry_quote_times={sid: str(book.snapshot(entry_at, ids)[sid]["timestamp"]) for sid in ids})
        # Thirty-second hypothetical liquidation marks are a sampled path, not a continuous MAE.
        marks, missing = [], 0
        for stamp in pd.date_range(entry_at, exit_at, freq="30s"):
            value = liquidation(strategy, book.snapshot(stamp, ids), config)
            if value is None:
                missing += 1
            else:
                gross, costs = value
                marks.append(gross - costs)
        event.update(sampled_marks=len(marks), missing_path_marks=missing,
                     sampled_mae_rupees=min([0.0] + marks), sampled_mfe_rupees=max([0.0] + marks),
                     sampled_path_complete=missing == 0)
        exits = book.snapshot(exit_at, ids)
        valuation = liquidation(strategy, exits, config)
        if valuation is None:
            counts["unpriced_exit"] += 1
            attempts.append(event)
            break  # Unknown exposure stays open; no later trade on this date.
        gross, costs = valuation
        stressed = liquidation(strategy, exits, config, 0.5)
        event.update(status="priced", gross_pnl=gross, estimated_costs=costs, net_pnl=gross-costs,
                     stressed_net_pnl=stressed[0]-stressed[1],
                     exit_quotes={sid: exits[sid] for sid in ids})
        counts["priced"] += 1
        attempts.append(event)
    return attempts, dict(counts)


def summarize(ledger: list[dict], counts: dict) -> dict:
    priced = [row for row in ledger if row["status"] == "priced"]
    nets = np.array([row["net_pnl"] for row in priced])
    cumulative = np.r_[0.0, np.cumsum(nets)]
    daily = {}
    for row in priced:
        daily[row["date"]] = daily.get(row["date"], 0) + row["net_pnl"]
    tail = np.sort(nets)[:max(1, math.ceil(0.05 * len(nets)))]
    return dict(counts=counts, priced_trades=len(priced), unpriced_exits=len(ledger)-len(priced),
                conditional_net_pnl=float(nets.sum()), mean_net_pnl=float(nets.mean()) if len(nets) else None,
                win_fraction=float((nets>0).mean()) if len(nets) else None,
                closed_trade_drawdown=float(np.max(np.maximum.accumulate(cumulative)-cumulative)),
                worst_trade=float(nets.min()) if len(nets) else None,
                worst_5pct_mean=float(tail.mean()) if len(nets) else None,
                stressed_conditional_net_pnl=sum(row["stressed_net_pnl"] for row in priced),
                worst_sampled_mae=min((row["sampled_mae_rupees"] for row in ledger), default=None),
                incomplete_paths=sum(not row["sampled_path_complete"] for row in ledger),
                daily_pnl=daily, margin="UNAVAILABLE", capacity="UNAVAILABLE",
                complete_valuation=len(ledger)==len(priced))


def paired_hedge_comparisons(ledgers: dict[str, list[dict]]) -> list[dict]:
    """Compare identical entry times only; report missing paired valuation."""
    output = []
    for naked, hedged in (("short_straddle", "iron_butterfly"),
                          ("short_strangle", "iron_condor"),
                          ("long_call", "bull_call_spread"),
                          ("long_put", "bear_put_spread")):
        for horizon in HORIZONS:
            left = {row["entry_at"]: row for row in ledgers[f"{naked}_{horizon}m"]}
            right = {row["entry_at"]: row for row in ledgers[f"{hedged}_{horizon}m"]}
            shared = sorted(left.keys() & right.keys())
            valued = [stamp for stamp in shared if left[stamp]["status"] == right[stamp]["status"] == "priced"]
            output.append(dict(unhedged=naked, hedged=hedged, horizon_minutes=horizon,
                               common_entries=len(shared), priced_pairs=len(valued),
                               unknown_pairs=len(shared)-len(valued),
                               unhedged_net=sum(left[stamp]["net_pnl"] for stamp in valued),
                               hedged_net=sum(right[stamp]["net_pnl"] for stamp in valued),
                               incremental_hedged_net=sum(right[stamp]["net_pnl"]-left[stamp]["net_pnl"] for stamp in valued),
                               mean_incremental_cost=(float(np.mean([right[stamp]["estimated_costs"]-
                                                      left[stamp]["estimated_costs"] for stamp in valued])) if valued else None),
                               unhedged_worst_sampled_mae=min((left[stamp]["sampled_mae_rupees"] for stamp in valued),default=None),
                               hedged_worst_sampled_mae=min((right[stamp]["sampled_mae_rupees"] for stamp in valued),default=None),
                               limitation="Only shared entry times and priced pairs; never infer complete-account or margin benefit"))
    return output


def normal_cdf(x: np.ndarray) -> np.ndarray:
    return np.array([0.5 * (1+math.erf(float(value)/math.sqrt(2))) for value in x])


def bs_call_delta(spot: np.ndarray, strike: float, tau: float, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    if tau <= 0:
        return np.maximum(spot-strike, 0), (spot>strike).astype(float)
    vol = sigma * math.sqrt(tau)
    d1 = (np.log(spot/strike)+0.5*sigma*sigma*tau)/vol
    delta = normal_cdf(d1)
    return spot*delta-strike*normal_cdf(d1-vol), delta


def synthetic_hedging(seed: int = 20261001, samples: int = 2000) -> dict:
    """Short one ATM call, hedge fractional generic underlying under a known GBM."""
    rng = np.random.default_rng(seed)
    sigma, steps, maturity, spot0 = 0.20, 390, 1/252, 24000.0
    dt = maturity/steps
    shocks = rng.standard_normal((samples, steps))
    increments = -0.5*sigma*sigma*dt + sigma*math.sqrt(dt)*shocks
    paths = np.c_[np.full(samples, spot0), spot0*np.exp(np.cumsum(increments, axis=1))]
    premium = float(bs_call_delta(np.array([spot0]), spot0, maturity, sigma)[0][0])
    results = []
    for frequency in (1, 5, 15, 30, 60):
        for cost_rate in (0.0, 0.00001, 0.0005):
            holdings = np.zeros(samples)
            cash = np.full(samples, premium)
            total_cost = np.zeros(samples)
            for step in range(0, steps, frequency):
                _, delta = bs_call_delta(paths[:,step], spot0, maturity-step*dt, sigma)
                trade = delta-holdings
                cost = np.abs(trade)*paths[:,step]*cost_rate
                cash -= trade*paths[:,step]+cost
                total_cost += cost
                holdings = delta
            unwind_cost = np.abs(holdings)*paths[:,-1]*cost_rate
            pnl = cash+holdings*paths[:,-1]-np.maximum(paths[:,-1]-spot0,0)-unwind_cost
            total_cost += unwind_cost
            results.append(dict(rebalance_minutes=frequency, proportional_cost_each_side=cost_rate,
                                mean_pnl_points=float(pnl.mean()), std_pnl_points=float(pnl.std(ddof=1)),
                                worst_5pct_mean_points=float(np.sort(pnl)[:samples//20].mean()),
                                mean_cost_points=float(total_cost.mean()),
                                mean_absolute_error_points=float(np.abs(pnl).mean())))
    return dict(status="SYNTHETIC_ONLY", seed=seed, paths=samples, volatility=sigma, initial_spot=spot0,
                maturity_years=maturity, initial_option_premium_points=premium, results=results,
                assumptions=["Known constant volatility, zero rate, lognormal paths, no jumps, fractional underlying units",
                             "Generic proportional cost on each hedge buy/sell, not actual Indian futures contract-note costs",
                             "No bid/ask, integer futures lots, margin, basis, liquidity or market impact",
                             "Uses no recorded Nifty data; cannot establish empirical hedge performance"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    output = HERE / "artifacts"
    output.mkdir(exist_ok=True)
    config = ResearchConfig()
    frame = pd.read_parquet(INPUT / "features.parquet")
    # Complete current minute only; target_bps and label_at never affect eligibility.
    eligible = frame.loc[frame["complete_minute"] & frame["close"].notna()].sort_values("decision_at")
    ledgers = {f"{name}_{horizon}m": [] for name in NAMES for horizon in HORIZONS}
    counters = {key: Counter() for key in ledgers}
    provenance = [{"path": str((INPUT/"features.parquet").resolve()), "sha256": sha256(INPUT/"features.parquet")}]
    for day, group in eligible.groupby("date", sort=True):
        source = INPUT / "sessions" / day / "options.parquet"
        if not source.exists():
            continue
        quotes = pd.read_parquet(source)
        book = IndexedBook(quotes, config.option_quote_age_seconds)
        del quotes
        provenance.append(dict(path=str(source.resolve()), sha256=sha256(source)))
        rows = group[["date", "decision_at", "close"]].to_dict("records")
        for name in NAMES:
            for horizon in HORIZONS:
                key = f"{name}_{horizon}m"
                ledger, counts = replay_day(rows, book, name, horizon, config)
                ledgers[key].extend(ledger)
                counters[key].update(counts)
        print(f"Completed {day}", flush=True)
    policies = {key: summarize(ledger, dict(counters[key])) for key, ledger in ledgers.items()}
    summary = dict(status="EXPLORATORY_CONDITIONAL_QUOTE_REPLAY", trial_count=36, policies=policies,
                   config=config.to_dict(), dates=sorted(eligible["date"].unique()),
                   protocol=dict(structures=list(NAMES), horizons_minutes=list(HORIZONS),
                                 decision_clock="Available complete minute closes, fixed policy always attempts its structure",
                                 entry_latency_seconds=1, max_quote_age_seconds=2, one_lot=True,
                                 path_sampling_seconds=30, contract_selection="Nearest available strike to futures at decision time",
                                 missing_exit="Retain unknown position and halt policy for remaining date"),
                   limitations=["No ranking or optimisation on these dates; all 36 trials are exploratory",
                                "All structures have conditional quoted fills only; no atomic multi-leg fill or size evidence",
                                "Short-option margin unavailable; no return on capital or solvency inference",
                                "Futures is an ATM proxy, synchronized index spot is missing",
                                "30-second sampled MAE can miss worse intratrade losses; missing marks weaken risk evidence",
                                "Unpriced exits make closed P&L an incomplete account outcome",
                                "Costs estimate separate orders, no settlement or exercise, no overnight positions"])
    write_json(output / "results.json", summary)
    write_json(output / "ledger.json", ledgers)
    write_json(output / "provenance.json", provenance)
    write_json(output / "synthetic-hedging.json", synthetic_hedging())
    write_json(output / "paired-hedge-comparisons.json", paired_hedge_comparisons(ledgers))
    table = ["| Structure | Hold min | Priced | Unknown exits | Net INR, priced only | Worst sampled MAE INR | Incomplete paths |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for key, result in policies.items():
        table.append(f"| {key.rsplit('_',1)[0]} | {key.rsplit('_',1)[1][:-1]} | {result['priced_trades']} | {result['unpriced_exits']} | {result['conditional_net_pnl']:.2f} | {result['worst_sampled_mae'] or 0:.2f} | {result['incomplete_paths']} |")
    (output / "table.md").write_text("\n".join(table)+"\n", encoding="utf-8")
    print(json.dumps({"trial_count":36,"priced_trades":sum(x["priced_trades"] for x in policies.values()),
                      "unpriced_exits":sum(x["unpriced_exits"] for x in policies.values())}), flush=True)


if __name__ == "__main__":
    main()
