"""Compare predeclared exits on a shared, causal option-entry schedule."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import time
import importlib.util
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
spec = importlib.util.spec_from_file_location("options_hedging_helpers", LAB / "research/04_options_hedging/study.py")
helpers = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = helpers
spec.loader.exec_module(helpers)
from nifty_lab.config import ResearchConfig
from nifty_lab.io import write_json

INPUT = LAB / "research/01_depth_forecast_baseline/artifacts"
HORIZONS = (5, 15, 30)
STRUCTURES = ("single", "vertical")


@dataclass(frozen=True)
class ExitPolicy:
    name: str
    stop_fraction: float | None = None
    target_fraction: float | None = None
    trailing_fraction: float | None = None
    thesis_reversal: bool = False


POLICIES = (ExitPolicy("time"), ExitPolicy("stop10_target20", .10, .20),
            ExitPolicy("stop20_target40", .20, .40), ExitPolicy("stop30_target60", .30, .60),
            ExitPolicy("trailing20", trailing_fraction=.20), ExitPolicy("thesis_reversal", thesis_reversal=True))


def entry_schedule(frame: pd.DataFrame) -> list[dict]:
    """Thirty-one minute spacing is independent of exit outcomes and coverage."""
    rows, next_at = [], None
    for row in frame.sort_values("decision_at").to_dict("records"):
        at = row["decision_at"]
        if next_at is not None and at < next_at:
            continue
        signal = row["ret_5_bps"]
        if not row["complete_minute"] or not np.isfinite(signal) or abs(signal) < 2:
            continue
        # Common known max-hold eligibility keeps the cohort shared across exits.
        if (at + pd.Timedelta(minutes=30, seconds=2)).tz_convert("Asia/Kolkata").time() >= time(15,30):
            continue
        rows.append(dict(date=row["date"], decision_at=at, close=row["close"], signal_bps=signal))
        next_at = at + pd.Timedelta(minutes=31)
    return rows


def first_trigger(path: list[dict], policy: ExitPolicy, debit: float, direction: int,
                  deadline: pd.Timestamp) -> tuple[pd.Timestamp, str, float | None]:
    """First observed trigger, followed later by actual repricing, never threshold fills."""
    if debit <= 0 or direction not in {-1,1}:
        raise ValueError("Positive entry debit and direction required")
    peak = 0.0
    for mark in path:
        at = mark["timestamp"]
        if at > deadline:
            break
        gross = mark["gross_pnl"]
        if gross is not None:
            peak = max(peak, gross)
            if policy.stop_fraction is not None and gross <= -policy.stop_fraction*debit:
                return at, "stop", -policy.stop_fraction*debit
            if policy.target_fraction is not None and gross >= policy.target_fraction*debit:
                return at, "target", policy.target_fraction*debit
            if policy.trailing_fraction is not None and gross <= peak-policy.trailing_fraction*debit:
                return at, "trailing", peak-policy.trailing_fraction*debit
        if policy.thesis_reversal and mark["thesis_ret_1_bps"] is not None:
            if direction*mark["thesis_ret_1_bps"] <= -2:
                return at, "thesis", None
    return deadline, "time", None


def thesis_at(frame: pd.DataFrame, at: pd.Timestamp) -> float | None:
    times=frame["decision_at"].dt.as_unit("ns").astype("int64").to_numpy()
    index = int(np.searchsorted(times, at.value, side="right"))-1
    if index < 0:
        return None
    row=frame.iloc[index]
    value=row["ret_1_bps"]
    if pd.Timedelta(0) <= at-row["decision_at"] <= pd.Timedelta(seconds=60) and np.isfinite(value):
        return float(value)
    return None


def make_path(strategy, book, entry_at: pd.Timestamp, features: pd.DataFrame,
              config: ResearchConfig) -> list[dict]:
    ids = tuple(leg.security_id for leg in strategy.legs)
    result=[]
    clock=pd.date_range(entry_at, entry_at+pd.Timedelta(minutes=30),freq="5s")
    feature_times=features["decision_at"].dt.as_unit("ns").astype("int64").to_numpy()
    returns=features["ret_1_bps"].to_numpy()
    positions=np.searchsorted(feature_times,clock.as_unit("ns").astype("int64"),side="right")-1
    for stamp,index in zip(clock,positions,strict=True):
        value=helpers.liquidation(strategy,book.snapshot(stamp,ids),config)
        thesis=None
        if index>=0 and 0 <= stamp.value-feature_times[index] <= 60*1e9 and np.isfinite(returns[index]):
            thesis=float(returns[index])
        result.append(dict(timestamp=stamp,gross_pnl=value[0] if value else None,
                           net_liquidation=value[0]-value[1] if value else None,
                           thesis_ret_1_bps=thesis))
    return result


def evaluate_exit(strategy, book, row: dict, path: list[dict], policy: ExitPolicy,
                  horizon: int, config: ResearchConfig) -> dict:
    entry_at=row["decision_at"]+pd.Timedelta(seconds=1)
    debit=strategy.expiry_risk(config.lot_size)["net_entry_debit"]
    deadline=entry_at+pd.Timedelta(minutes=horizon)
    trigger_at,reason,threshold=first_trigger(path,policy,debit,1 if row["signal_bps"]>0 else -1,deadline)
    exit_at=trigger_at+pd.Timedelta(seconds=1)
    visible=[mark for mark in path if mark["timestamp"]<=trigger_at]
    missing=sum(mark["gross_pnl"] is None for mark in visible)
    nets=[mark["net_liquidation"] for mark in visible if mark["net_liquidation"] is not None]
    result=dict(date=row["date"],policy=policy.name,strategy=strategy.name,horizon_minutes=horizon,
                entry_at=entry_at.isoformat(),trigger_at=trigger_at.isoformat(),exit_at=exit_at.isoformat(),
                exit_reason=reason,status="unpriced_exit",signal_bps=row["signal_bps"],
                entry_debit=debit,threshold_gross_pnl=threshold,
                contracts=[leg.__dict__ for leg in strategy.legs],missing_monitor_samples=missing,
                sampled_mae_rupees=min([0.0]+nets),sampled_mfe_rupees=max([0.0]+nets),
                sampled_monitor_complete=missing==0)
    ids=tuple(leg.security_id for leg in strategy.legs)
    quotes=book.snapshot(exit_at,ids)
    valuation=helpers.liquidation(strategy,quotes,config)
    if valuation is None:
        return result
    gross,costs=valuation
    stressed=helpers.liquidation(strategy,quotes,config,0.5)
    result.update(status="priced",gross_pnl=gross,estimated_costs=costs,net_pnl=gross-costs,
                  stressed_net_pnl=stressed[0]-stressed[1],
                  held_seconds=(exit_at-entry_at).total_seconds(),
                  stop_overshoot_rupees=max(0.0,threshold-gross) if reason in {"stop","trailing"} else None,
                  target_shortfall_rupees=max(0.0,threshold-gross) if reason=="target" else None,
                  sampled_mae_rupees=min(result["sampled_mae_rupees"],gross-costs),
                  sampled_mfe_rupees=max(result["sampled_mfe_rupees"],gross-costs),
                  exit_quotes=quotes)
    return result


def summary(ledger: list[dict], counts: dict) -> dict:
    result=helpers.summarize(ledger,counts)
    priced=[row for row in ledger if row["status"]=="priced"]
    result.update(gross_pnl_priced=sum(row["gross_pnl"] for row in priced),
                  costs_priced=sum(row["estimated_costs"] for row in priced),
                  exit_reasons=dict(Counter(row["exit_reason"] for row in ledger)),
                  stop_overshoots=sum((row.get("stop_overshoot_rupees") or 0)>0 for row in priced),
                  worst_stop_overshoot=max((row.get("stop_overshoot_rupees") or 0 for row in priced),default=0),
                  incomplete_monitoring=sum(not row["sampled_monitor_complete"] for row in ledger),
                  mean_hold_seconds=float(np.mean([row["held_seconds"] for row in priced])) if priced else None)
    return result


def paired(ledgers: dict[str,list[dict]]) -> list[dict]:
    result=[]
    for structure in STRUCTURES:
        for horizon in HORIZONS:
            baseline={row["entry_at"]:row for row in ledgers[f"{structure}_{horizon}m_time"]}
            for policy in POLICIES[1:]:
                alternative={row["entry_at"]:row for row in ledgers[f"{structure}_{horizon}m_{policy.name}"]}
                common=baseline.keys()&alternative.keys()
                valued=[stamp for stamp in common if baseline[stamp]["status"]==alternative[stamp]["status"]=="priced"]
                differences=[alternative[stamp]["net_pnl"]-baseline[stamp]["net_pnl"] for stamp in valued]
                result.append(dict(structure=structure,horizon_minutes=horizon,exit_policy=policy.name,
                                   common_entries=len(common),priced_pairs=len(valued),unknown_pairs=len(common)-len(valued),
                                   incremental_net_pnl=sum(differences),
                                   mean_incremental_net_pnl=float(np.mean(differences)) if differences else None,
                                   improved_pairs=sum(value>0 for value in differences)))
    return result


def main() -> None:
    output=HERE/"artifacts"
    output.mkdir(exist_ok=True)
    config=ResearchConfig()
    frame=pd.read_parquet(INPUT/"features.parquet")
    # Drop forward labels before any policy sees this table.
    frame=frame[["date","decision_at","close","ret_5_bps","ret_1_bps","complete_minute"]]
    keys=[f"{structure}_{horizon}m_{policy.name}" for structure in STRUCTURES for horizon in HORIZONS for policy in POLICIES]
    ledgers={key:[] for key in keys}
    counts={key:Counter() for key in keys}
    provenance=[dict(path=str((INPUT/"features.parquet").resolve()),sha256=helpers.sha256(INPUT/"features.parquet"))]
    for day,features in frame.groupby("date",sort=True):
        source=INPUT/"sessions"/day/"options.parquet"
        if not source.exists():
            continue
        features=features.sort_values("decision_at").reset_index(drop=True)
        schedule=entry_schedule(features)
        book=helpers.IndexedBook(pd.read_parquet(source),config.option_quote_age_seconds)
        provenance.append(dict(path=str(source.resolve()),sha256=helpers.sha256(source)))
        halted=set()
        for row in schedule:
            available=helpers.candidates(book.snapshot(row["decision_at"]),row["close"])
            for structure in STRUCTURES:
                name=("long_call" if row["signal_bps"]>0 else "long_put") if structure=="single" else (
                    "bull_call_spread" if row["signal_bps"]>0 else "bear_put_spread")
                strategy=available.get(name)
                groupkeys=[key for key in keys if key.startswith(structure+"_") and key not in halted]
                if strategy is None:
                    for key in groupkeys: counts[key]["candidate_missing"]+=1
                    continue
                ids=tuple(leg.security_id for leg in strategy.legs)
                entry_at=row["decision_at"]+pd.Timedelta(seconds=1)
                strategy=helpers.reprice(strategy,book.snapshot(entry_at,ids))
                if strategy is None or not helpers.entry_economic(strategy,config.lot_size):
                    for key in groupkeys: counts[key]["entry_unavailable_or_invalid"]+=1
                    continue
                path=make_path(strategy,book,entry_at,features,config)
                for horizon in HORIZONS:
                    for policy in POLICIES:
                        key=f"{structure}_{horizon}m_{policy.name}"
                        if key in halted:
                            counts[key]["halted_unknown_exposure"]+=1
                            continue
                        event=evaluate_exit(strategy,book,row,path,policy,horizon,config)
                        # Adapt only the summary field name expected by the shared read-only helper.
                        event["sampled_path_complete"]=event["sampled_monitor_complete"]
                        ledgers[key].append(event)
                        counts[key][event["status"]]+=1
                        if event["status"]=="unpriced_exit": halted.add(key)
        print(f"Completed {day}: {len(schedule)} entry opportunities",flush=True)
    results=dict(status="EXPLORATORY_CONDITIONAL_QUOTE_REPLAY",trial_count=36,
                 policies={key:summary(ledger,dict(counts[key])) for key,ledger in ledgers.items()},
                 config=config.to_dict(),entry_threshold_bps=2,entry_spacing_minutes=31,
                 monitoring_seconds=5,entry_latency_seconds=1,exit_latency_seconds=1,
                 threshold_basis="Gross whole-position liquidation P&L divided by positive entry debit",
                 limitations=["Entry schedule fixed independently of exit results, full 30-minute outcomes or quote coverage",
                              "Receipt-time quotes only; no quote sizes, guaranteed fills or atomic spread exits",
                              "Missing monitoring samples cannot establish actual first threshold touch",
                              "Unknown exit retains exposure and halts only that configuration for its date",
                              "Repeated dates and configurations are exploratory; no optimal threshold selected",
                              "Thesis uses backward-only fresh minute return, never forward labels"])
    write_json(output/"results.json",results)
    write_json(output/"ledger.json",ledgers)
    write_json(output/"paired-comparisons.json",paired(ledgers))
    write_json(output/"provenance.json",provenance)
    table=["| Structure | Hold | Exit | Priced | Unknown | Gross INR | Costs INR | Net INR | Worst sampled MAE | Worst stop overshoot |",
           "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key,value in results["policies"].items():
        structure,hold,name=key.split("_",2)
        table.append(f"| {structure} | {hold} | {name} | {value['priced_trades']} | {value['unpriced_exits']} | {value['gross_pnl_priced']:.2f} | {value['costs_priced']:.2f} | {value['conditional_net_pnl']:.2f} | {value['worst_sampled_mae'] or 0:.2f} | {value['worst_stop_overshoot']:.2f} |")
    (output/"table.md").write_text("\n".join(table)+"\n",encoding="utf-8")
    print(f"Completed {len(keys)} configurations",flush=True)


if __name__=="__main__": main()
