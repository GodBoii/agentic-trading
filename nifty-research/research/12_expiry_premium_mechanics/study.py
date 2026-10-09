"""Offline quote-shape and fixed-contract expiry mechanics diagnostics.

Inputs remain read-only. Bid/ask bounds are conditional quote diagnostics,
never evidence of obtainable fills, capacity or executable arbitrage.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
INPUT = LAB / "research/01_depth_forecast_baseline/artifacts"
PREMIUM_INPUT = LAB / "research/03_volatility_premiums/artifacts"
SKEW_ALLOWANCES = (0.25, 2.0)
RATE_ASSUMPTIONS = (0.0, 0.10)
QUOTE_AGE_SECONDS = 2.0
TOLERANCE = 1e-8


def load_helpers(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load helper module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hedging = load_helpers("expiry_hedging", LAB / "research/04_options_hedging/study.py")
volatility = load_helpers("expiry_volatility", LAB / "research/03_volatility_premiums/study.py")


def receipt_validity(quotes: list[dict], at: pd.Timestamp, max_skew: float) -> str:
    """Use receipt times only; exchange quote-origin timestamps are unavailable."""
    if not quotes:
        return "missing_quotes"
    if max_skew <= 0 or not math.isfinite(max_skew):
        raise ValueError("Positive receipt-skew allowance required")
    expiries = {quote["expiry"] for quote in quotes}
    if len(expiries) != 1:
        return "mixed_expiry_rejected"
    kinds = {quote["option_type"] for quote in quotes}
    if not kinds.issubset({"CE", "PE"}):
        return "invalid_quote_rejected"
    stamps = [quote["timestamp"] for quote in quotes]
    ages = [(at-stamp).total_seconds() for stamp in stamps]
    if any(age < 0 for age in ages):
        return "future_quote_rejected"
    if any(age > QUOTE_AGE_SECONDS for age in ages):
        return "stale_receipt_rejected"
    if (max(stamps)-min(stamps)).total_seconds() > max_skew:
        return "receipt_skew_rejected"
    if any(not math.isfinite(quote[key]) for quote in quotes for key in ("strike", "bid", "ask")):
        return "invalid_quote_rejected"
    if any(quote["strike"] <= 0 or not 0 <= quote["bid"] < quote["ask"] for quote in quotes):
        return "invalid_quote_rejected"
    return "receipt_valid_only"


def discounted_years(expiry: str, at: pd.Timestamp) -> float:
    deadline = pd.Timestamp(expiry+" 15:30:00", tz="Asia/Kolkata").tz_convert("UTC")
    return (deadline-at).total_seconds()/(365*86400)


def bound_check(quotes: list[dict], weights: list[float], bound: float,
                upper: bool, at: pd.Timestamp, max_skew: float, family: str,
                rate: float) -> dict:
    """Check whether a bid/ask interval is disjoint from a payoff bound.

    Available acquisition pays asks on bought legs and receives bids on sold
    legs. Available sale receives bids for positive-position legs and pays
    asks to cover negative-position legs. These are quote-side values only.
    """
    if len(quotes) != len(weights) or not all(math.isfinite(weight) for weight in weights):
        raise ValueError("Finite weights matching every quote required")
    status = receipt_validity(quotes, at, max_skew)
    result = dict(date=at.tz_convert("Asia/Kolkata").date().isoformat(), decision_at=at,
                  expiry=quotes[0]["expiry"], dte_calendar=(pd.Timestamp(quotes[0]["expiry"])-pd.Timestamp(at.tz_convert("Asia/Kolkata").date())).days,
                  family=family, option_type=quotes[0]["option_type"],
                  strikes=[quote["strike"] for quote in quotes], security_ids=[str(quote["security_id"]) for quote in quotes],
                  weights=weights, receipt_times=[quote["timestamp"].isoformat() for quote in quotes],
                  max_receipt_skew_seconds=max_skew, assumed_rate=rate, status=status,
                  bound=bound, upper=upper, midpoint_value=None, quote_side_value=None,
                  midpoint_violation=None, conditional_quote_violation=None, violation_gap_points=None)
    if status != "receipt_valid_only":
        return result
    mid = sum(weight*(quote["bid"]+quote["ask"])/2 for quote,weight in zip(quotes,weights,strict=True))
    side = sum(weight*quote[("bid" if weight >= 0 else "ask") if upper else
                            ("ask" if weight >= 0 else "bid")]
               for quote,weight in zip(quotes,weights,strict=True))
    gap = side-bound if upper else bound-side
    mid_gap = mid-bound if upper else bound-mid
    violated = gap > TOLERANCE
    midpoint_violated = mid_gap > TOLERANCE
    result.update(midpoint_value=mid, quote_side_value=side, midpoint_violation=midpoint_violated,
                  conditional_quote_violation=violated, violation_gap_points=max(0.0,gap),
                  status="conditional_quote_bound_violation" if violated else (
                      "midpoint_only_violation" if midpoint_violated else "within_quoted_bound"))
    return result


def shape_checks(snapshot: dict[str, dict], at: pd.Timestamp, max_skew: float,
                 rate: float = 0.0) -> list[dict]:
    """All adjacent verticals and consecutive triples, separately by expiry/type."""
    groups: dict[tuple[str,str],list[dict]] = {}
    for quote in snapshot.values():
        groups.setdefault((quote["expiry"],quote["option_type"]),[]).append(quote)
    output = []
    for (expiry,kind), quotes in sorted(groups.items()):
        years = discounted_years(expiry, at)
        if years <= 0:
            continue
        ordered = sorted(quotes,key=lambda quote: quote["strike"])
        if len({quote["strike"] for quote in ordered}) != len(ordered):
            raise ValueError("Duplicate same-expiry strike identity")
        weights = [1.0,-1.0] if kind == "CE" else [-1.0,1.0]
        for low,high in zip(ordered,ordered[1:]):
            pair = [low,high]
            cap = (high["strike"]-low["strike"])*math.exp(-rate*years)
            output.append(bound_check(pair,weights,0.0,False,at,max_skew,"vertical_lower_monotonic",rate))
            output.append(bound_check(pair,weights,cap,True,at,max_skew,"vertical_upper",rate))
        for low,middle,high in zip(ordered,ordered[1:],ordered[2:]):
            left_weight = (high["strike"]-middle["strike"])/(high["strike"]-low["strike"])
            output.append(bound_check([low,middle,high],[left_weight,-1.0,1-left_weight],
                                      0.0,False,at,max_skew,"butterfly_convexity",rate))
    return output


def iv_wing_snapshot(snapshot: dict[str,dict], at: pd.Timestamp, max_skew: float) -> dict:
    """Local OTM wing difference under common-parity forward, not fixed-delta skew."""
    pair = volatility.same_expiry_pair(snapshot, at, max_skew=max_skew)
    result = dict(date=at.tz_convert("Asia/Kolkata").date().isoformat(),decision_at=at,
                  max_receipt_skew_seconds=max_skew,status="no_matched_pairs")
    if pair is None:
        return result
    result.update(expiry=pair["expiry"],dte_calendar=(pd.Timestamp(pair["expiry"])-pd.Timestamp(result["date"])).days)
    if not pair["parity_intersection"]:
        result["status"] = "parity_interval_rejected"
        return result
    options = [quote for quote in snapshot.values() if quote["expiry"] == pair["expiry"]]
    validity = receipt_validity(options,at,max_skew)
    if validity != "receipt_valid_only":
        result["status"] = validity
        return result
    put_wings = [quote for quote in options if quote["option_type"] == "PE" and quote["strike"] < pair["forward"]]
    call_wings = [quote for quote in options if quote["option_type"] == "CE" and quote["strike"] > pair["forward"]]
    if not put_wings or not call_wings:
        result["status"] = "missing_otm_wings"
        return result
    put = min(put_wings,key=lambda quote:quote["strike"])
    call = max(call_wings,key=lambda quote:quote["strike"])
    try:
        p_iv = volatility.implied_volatility((put["bid"]+put["ask"])/2,pair["forward"],put["strike"],pair["years"],kind="PE")
        c_iv = volatility.implied_volatility((call["bid"]+call["ask"])/2,pair["forward"],call["strike"],pair["years"],kind="CE")
    except ValueError:
        result["status"] = "invalid_black_iv"
        return result
    result.update(status="conditional_midpoint_iv",forward=pair["forward"],put_strike=put["strike"],
                  call_strike=call["strike"],put_iv=p_iv,call_iv=c_iv,
                  put_minus_call_iv_percentage_points=(p_iv-c_iv)*100,
                  iv_slope_percentage_points_per100strike=(c_iv-p_iv)*10000/(call["strike"]-put["strike"]))
    return result


def fixed_straddle_observation(row: dict, book, max_skew: float) -> dict:
    """Revalidate study03's exact IDs and quotes, retaining rejected observations."""
    result = dict(row,max_receipt_skew_seconds=max_skew,status="missing_quote")
    calls_puts = []
    for stamp in (row["decision_at"],row["entry_at"],row["exit_at"]):
        snapshot = book.snapshot(stamp)
        ids = (str(row["call_id"]),str(row["put_id"]))
        if any(sid not in snapshot for sid in ids):
            return result
        quotes = [snapshot[sid] for sid in ids]
        if any((quote["expiry"],quote["strike"],quote["option_type"]) !=
               (row["expiry"],row["strike"],kind) for quote,kind in zip(quotes,("CE","PE"),strict=True)):
            raise ValueError("Fixed straddle identity changed")
        validity = receipt_validity(quotes,stamp,max_skew)
        if validity != "receipt_valid_only":
            result["status"] = validity
            return result
        calls_puts.append(quotes)
    entry,closing = calls_puts[1],calls_puts[2]
    entry_mid = sum((quote["bid"]+quote["ask"])/2 for quote in entry)
    closing_mid = sum((quote["bid"]+quote["ask"])/2 for quote in closing)
    if not np.isclose(entry_mid,row["entry_mid"],rtol=0,atol=1e-8) or not np.isclose(closing_mid-entry_mid,row["mid_change"],rtol=0,atol=1e-8):
        raise ValueError("Study03 fixed-straddle provenance mismatch")
    result.update(status="conditional_fixed_straddle",entry_spread_points=sum(quote["ask"]-quote["bid"] for quote in entry),
                  exit_spread_points=sum(quote["ask"]-quote["bid"] for quote in closing),
                  compression_fraction=-row["mid_change"]/entry_mid,
                  abs_move_fraction=row["abs_futures_change_points"]/entry_mid,
                  move_bucket="below10pctpremium" if row["abs_futures_change_points"] < .1*entry_mid else "atleast10pctpremium",
                  compressed=float(row["mid_change"] < 0),
                  entry_receipt_times=[quote["timestamp"].isoformat() for quote in entry],
                  exit_receipt_times=[quote["timestamp"].isoformat() for quote in closing])
    return result


def equal_day_table(frame: pd.DataFrame, dimensions: list[str], metrics: list[str]) -> list[dict]:
    """Means of within-date means; preserve every populated date's contribution."""
    if frame.empty:
        return []
    output=[]
    for keys,part in frame.groupby(dimensions,dropna=False,sort=True):
        if not isinstance(keys,tuple):
            keys=(keys,)
        daily=part.groupby("date")[metrics].mean()
        means=daily.mean()
        result={key: value.item() if isinstance(value,np.generic) else value for key,value in zip(dimensions,keys,strict=True)}
        result.update(rows=len(part),days=part["date"].nunique(),dates=sorted(part["date"].unique()),
                      day_equal={key:float(value) if pd.notna(value) else None for key,value in means.items()},
                      daily_rows={str(day):int(count) for day,count in part.groupby("date").size().items()},
                      daily_means={str(day):{key:float(value) if pd.notna(value) else None for key,value in values.items()}
                                   for day,values in daily.iterrows()})
        output.append(result)
    return output


def sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def run() -> None:
    output=HERE/"artifacts"
    output.mkdir(parents=True,exist_ok=True)
    features=pd.read_parquet(INPUT/"features.parquet")
    prior_iv=pd.read_parquet(PREMIUM_INPUT/"parity_iv.parquet")
    prior_straddles=pd.read_parquet(PREMIUM_INPUT/"straddle_observations.parquet")
    checks,wing_rows,straddle_rows,activity=[],[],[],[]
    provenance=[INPUT/"features.parquet",PREMIUM_INPUT/"parity_iv.parquet",PREMIUM_INPUT/"straddle_observations.parquet",PREMIUM_INPUT/"results.json"]
    coverage=Counter()
    for day,group in features.groupby("date",sort=True):
        source=INPUT/"sessions"/day/"options.parquet"
        if not source.is_file():
            coverage["dates_missing_option_cache"]+=1
            continue
        provenance.append(source)
        quotes=pd.read_parquet(source)
        book=hedging.IndexedBook(quotes,QUOTE_AGE_SECONDS)
        receipt_counts=quotes.groupby(quotes["timestamp"].dt.floor("min")).size()
        cached_expiry=min(quotes["expiry"].unique())
        dte=(pd.Timestamp(cached_expiry)-pd.Timestamp(day)).days
        for row in group.sort_values("decision_at").to_dict("records"):
            if not row["complete_minute"]:
                continue
            at=row["decision_at"]
            snapshot=book.snapshot(at)
            coverage["complete_minute_decisions"]+=1
            coverage["empty_fresh_snapshots"]+=not bool(snapshot)
            for skew in SKEW_ALLOWANCES:
                for rate in RATE_ASSUMPTIONS:
                    checks.extend(shape_checks(snapshot,at,skew,rate))
                wing_rows.append(iv_wing_snapshot(snapshot,at,skew))
            spreads=[quote["ask"]-quote["bid"] for quote in snapshot.values() if quote["expiry"]==cached_expiry]
            activity.append(dict(date=day,decision_at=at,dte_calendar=dte,expiry_group="expiry" if dte==0 else "nonexpiry",
                                 futures_volume_units=row["volume"],abs_futures_ret1_bps=abs(row["ret_1_bps"]) if pd.notna(row["ret_1_bps"]) else np.nan,
                                 captured_option_receipts=int(receipt_counts.get(at-pd.Timedelta(minutes=1),0)),
                                 fresh_option_ids=len(spreads),captured_neighborhood_spread_points=float(np.mean(spreads)) if spreads else np.nan))
        for row in prior_straddles[prior_straddles["date"]==day].to_dict("records"):
            for skew in SKEW_ALLOWANCES:
                straddle_rows.append(fixed_straddle_observation(row,book,skew))
        print(f"Completed {day}",flush=True)
    shape=pd.DataFrame(checks)
    wings=pd.DataFrame(wing_rows)
    premiums=pd.DataFrame(straddle_rows)
    activity_frame=pd.DataFrame(activity)
    shape.to_parquet(output/"quote_shape_checks.parquet",index=False)
    wings.to_parquet(output/"local_iv_wings.parquet",index=False)
    premiums.to_parquet(output/"fixed_straddle_observations.parquet",index=False)
    activity_frame.to_parquet(output/"sampled_activity.parquet",index=False)
    valid_shape=shape[shape["conditional_quote_violation"].notna()].copy()
    valid_shape["conditional_quote_violation"]=valid_shape["conditional_quote_violation"].astype(float)
    valid_shape["midpoint_violation"]=valid_shape["midpoint_violation"].astype(float)
    valid_premiums=premiums[premiums["status"]=="conditional_fixed_straddle"].copy()
    valid_premiums["expiry_group"]=np.where(valid_premiums["dte_calendar"]==0,"expiry","nonexpiry")
    valid_wings=wings[wings["status"]=="conditional_midpoint_iv"]
    activity_day_counts=activity_frame.groupby("date").size()
    activity_min60=activity_frame[activity_frame["date"].isin(activity_day_counts[activity_day_counts>=60].index)]
    prior_iv=prior_iv.copy()
    prior_iv["iv_bidask_width"]=prior_iv["iv_ask"]-prior_iv["iv_bid"]
    prior_iv["expiry_group"]=np.where(prior_iv["dte_calendar"]==0,"expiry","nonexpiry")
    premium_metrics=["entry_mid","entry_spread_points","mid_change","compression_fraction","compressed", "abs_futures_change_points",
                     "abs_move_fraction","long_net_rupees","short_net_rupees"]
    result=dict(created_date="2026-10-02",status="EXPLORATORY_QUOTE_DIAGNOSTICS_ONLY",
                protocol=dict(quote_receipt_age_seconds=QUOTE_AGE_SECONDS,receipt_skew_allowances_seconds=list(SKEW_ALLOWANCES),
                              assumed_rates=list(RATE_ASSUMPTIONS),strike_cohort="Adjacent captured strikes and consecutive triples, same expiry and type",
                              premium_cohort="Revalidated study03 IDs and fixed strikes, selected only from its parity-valid priced subset",
                              quote_origin_timestamps="UNAVAILABLE",quote_sizes="UNAVAILABLE",atomic_fills="UNAVAILABLE",
                              futures_activity="Recorded volume increments and absolute minute return; option receipts are not exchange trade counts"),
                coverage=dict(coverage),
                shape_statuses=shape.groupby(["max_receipt_skew_seconds","assumed_rate","family","status"]).size().reset_index(name="rows").to_dict("records"),
                quote_shape_families=equal_day_table(valid_shape,["max_receipt_skew_seconds","assumed_rate","dte_calendar","option_type","family"],
                                                   ["midpoint_violation","conditional_quote_violation","violation_gap_points"]),
                wing_statuses=wings.groupby(["max_receipt_skew_seconds","status"]).size().reset_index(name="rows").to_dict("records"),
                wing_dte=equal_day_table(valid_wings,["max_receipt_skew_seconds","dte_calendar"],
                                        ["put_minus_call_iv_percentage_points","iv_slope_percentage_points_per100strike"]),
                fixed_straddle_statuses=premiums.groupby(["max_receipt_skew_seconds","status"]).size().reset_index(name="rows").to_dict("records"),
                premiums_by_dte=equal_day_table(valid_premiums,["max_receipt_skew_seconds","horizon","dte_calendar"],premium_metrics),
                premiums_expiry_vs_nonexpiry=equal_day_table(valid_premiums,["max_receipt_skew_seconds","horizon","expiry_group"],premium_metrics),
                premiums_by_move=equal_day_table(valid_premiums,["max_receipt_skew_seconds","horizon","expiry_group","move_bucket"],premium_metrics),
                activity_by_dte=equal_day_table(activity_frame,["dte_calendar"], ["futures_volume_units","abs_futures_ret1_bps","captured_option_receipts","fresh_option_ids","captured_neighborhood_spread_points"]),
                activity_expiry_vs_nonexpiry=equal_day_table(activity_frame,["expiry_group"], ["futures_volume_units","abs_futures_ret1_bps","captured_option_receipts","fresh_option_ids","captured_neighborhood_spread_points"]),
                activity_min60minutes_sensitivity=equal_day_table(activity_min60,["expiry_group"], ["futures_volume_units","abs_futures_ret1_bps","captured_option_receipts","fresh_option_ids","captured_neighborhood_spread_points"]),
                inherited_iv_by_dte=equal_day_table(prior_iv,["dte_calendar"],["iv","iv_bidask_width"]),
                inherited_iv_expiry_vs_nonexpiry=equal_day_table(prior_iv,["expiry_group"],["iv","iv_bidask_width"]),
                limitation="Few dates, uneven session times and selected parity-valid subset; all observations overlap. No causal expiry effect, no independent strategy trials or executable arbitrage claims.",
                inputs=[dict(path=str(path.resolve()),sha256=sha256(path)) for path in provenance],
                source_hashes={str(path.resolve()):sha256(path) for path in [Path(__file__),Path(hedging.__file__),Path(volatility.__file__)]})
    result["family_counts"]=dict(quote_shape_rate_skew_type_combinations=3*2*2*2,
                                populated_quote_shape_dte_families=len(result["quote_shape_families"]),
                                populated_premium_dte_horizon_skew_families=len(result["premiums_by_dte"]),
                                populated_premium_move_families=len(result["premiums_by_move"]),
                                independent_validation_dates=0)
    (output/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    write_tables(result,output)
    print(json.dumps(dict(shape_checks=len(shape),wing_attempts=len(wings),fixed_straddle_revalidations=len(premiums),activity_minutes=len(activity_frame))),flush=True)


def write_tables(result: dict, output: Path) -> None:
    lines=["# All expiry mechanics numerical results","","Day-equal values average each date's mean. Every populated family remains in results.json.","",
           "## Quote shape status counts","","| Skew s | Rate | Family | Status | Rows |","|---:|---:|---|---|---:|"]
    for row in result["shape_statuses"]:
        lines.append(f"| {row['max_receipt_skew_seconds']} | {row['assumed_rate']} | {row['family']} | {row['status']} | {row['rows']} |")
    lines += ["","## Fixed-strike premiums by DTE","","| Skew s | Hold min | DTE | Rows | Days | Day-equal mid change | Compression % | Entry spread | Abs futures move | Long net INR | Short net INR |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["premiums_by_dte"]:
        value=row["day_equal"]
        lines.append(f"| {row['max_receipt_skew_seconds']} | {row['horizon']} | {row['dte_calendar']} | {row['rows']} | {row['days']} | {value['mid_change']:.3f} | {100*value['compression_fraction']:.3f} | {value['entry_spread_points']:.3f} | {value['abs_futures_change_points']:.3f} | {value['long_net_rupees']:.2f} | {value['short_net_rupees']:.2f} |")
    lines += ["","## Expiry versus nonexpiry premiums","","| Skew s | Hold min | Group | Rows | Days | Dates | Day-equal mid change | Compression % | Compressed fraction |",
              "|---:|---:|---|---:|---:|---|---:|---:|---:|"]
    for row in result["premiums_expiry_vs_nonexpiry"]:
        value=row["day_equal"]
        lines.append(f"| {row['max_receipt_skew_seconds']} | {row['horizon']} | {row['expiry_group']} | {row['rows']} | {row['days']} | {', '.join(row['dates'])} | {value['mid_change']:.3f} | {100*value['compression_fraction']:.3f} | {value['compressed']:.3f} |")
    lines += ["","## Sampled activity","","| Group | Minutes | Dates | Future volume per min | Abs return bps | Option receipts per min | Fresh IDs | Captured spread points |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["activity_expiry_vs_nonexpiry"]:
        value=row["day_equal"]
        lines.append(f"| {row['expiry_group']} | {row['rows']} | {row['days']} | {value['futures_volume_units']:.2f} | {value['abs_futures_ret1_bps']:.3f} | {value['captured_option_receipts']:.2f} | {value['fresh_option_ids']:.2f} | {value['captured_neighborhood_spread_points']:.3f} |")
    (output/"numerical-results.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__ == "__main__":
    run()
