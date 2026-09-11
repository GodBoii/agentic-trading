"""Fixed, causal candidate-priority experiments on minute-reduced broad tapes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


KEYS = ["exchange_segment", "security_id"]
POLICIES = ["activity", "recent_range", "fresh_movement", "renewed_volume",
            "efficient_movement", "volume_and_range", "compression_expansion", "liquidity"]


def features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["ts"] = pd.to_datetime(frame.received_at, utc=True, format="ISO8601").array.as_unit("ns").asi8 / 1e9
    frame["m"] = (frame.ts // 60).astype("int64")
    output = []
    for key, stock in frame.groupby(KEYS, sort=False):
        stock = stock.sort_values("ts").drop_duplicates("m", keep="last").set_index("m")
        stock = stock.reindex(range(int(stock.index.min()), int(stock.index.max()) + 1))
        price = stock.last_price
        returns = price.pct_change(fill_method=None)
        volume_delta = stock.day_volume.diff()
        # A counter reset is missing activity, not a quiet minute. Rolling
        # windows remain unavailable until enough valid increments arrive.
        volume = volume_delta.where(volume_delta >= 0)
        recent_range = (stock.high - stock.low) / price * 100
        range5 = (stock.high.rolling(5, min_periods=5).max() - stock.low.rolling(5, min_periods=5).min()) / price * 100
        prior_volume = volume.shift(1).rolling(5, min_periods=5).mean()
        stock["renewal"] = (volume / prior_volume.replace(0, np.nan)).clip(0, 3)
        stock["recent_range"] = recent_range
        stock["freshness"] = (recent_range / range5.replace(0, np.nan)).clip(0, 1)
        stock["efficiency5"] = (price.pct_change(5, fill_method=None).abs() / returns.abs().rolling(5, min_periods=5).sum().replace(0, np.nan)).clip(0, 1)
        stock["expansion"] = (recent_range / recent_range.shift(1).rolling(5, min_periods=5).median().replace(0, np.nan)).clip(0, 3)
        stock["value5"] = (volume * price).rolling(5, min_periods=5).sum()
        decision = (stock.index.to_numpy() + 1) * 60
        stock["decision"] = decision
        future = price.shift(-5) / price - 1
        future_path = returns.shift(-1).iloc[::-1].abs().rolling(5, min_periods=5).sum().iloc[::-1]
        stock["forward_abs"] = future.abs() * 100
        stock["forward_efficiency"] = (future.abs() / future_path.replace(0, np.nan)).clip(0, 1)
        stock["label_available"] = future.notna() & future_path.notna() & (stock.ts.shift(-5) >= decision + 290)
        stock["entry_fresh"] = (decision - stock.ts).between(0, 10)
        stock["rally"] = (stock.forward_abs >= .5) & (stock.forward_efficiency >= .6)
        stock["rally_after_spread"] = (stock.forward_abs - stock.spread_percent >= .5) & (stock.forward_efficiency >= .6)
        for column, value in zip(KEYS, key):
            stock[column] = value
        output.append(stock.reset_index())
    return pd.concat(output, ignore_index=True)


def evaluate(frame: pd.DataFrame, day: str) -> tuple[dict, pd.DataFrame]:
    f = features(frame)
    clock = pd.to_datetime(f.decision, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    minute = clock.dt.hour * 60 + clock.dt.minute
    f = f[(clock.dt.strftime("%Y-%m-%d") == day) & minute.between(565, 890) & (clock.dt.minute % 5 == 0)]
    f = f[f.entry_fresh & f.spread_percent.between(0, .2) & f.last_trade_age_seconds.between(0, 90)
          & (f.best_bid > 0) & (f.best_ask >= f.best_bid) & f.activity_rank.between(1, 100)].copy()
    f["phase"] = np.where(minute.loc[f.index] < 600, "opening", np.where(minute.loc[f.index] < 720, "morning", "afternoon"))
    weight = (101 - f.activity_rank) / 100
    f["activity"] = -f.activity_rank
    f["fresh_movement"] = f.freshness * weight
    f["renewed_volume"] = f.renewal * weight
    f["efficient_movement"] = f.efficiency5 * weight
    ranks = f.groupby("decision")[["renewal", "recent_range"]].rank(pct=True)
    f["volume_and_range"] = ranks.min(axis=1, skipna=False)
    f["compression_expansion"] = f.expansion * f.renewal
    f["liquidity"] = f.value5
    rows, selections = {}, []
    eligible_rallies = int((f.label_available & f.rally).sum())
    for name in POLICIES:
        # Missing pre-decision features rank last; they do not remove a time or outcome.
        ranked = f.assign(score=f[name].fillna(-np.inf)).sort_values(["decision", "score", "activity_rank", *KEYS], ascending=[True, False, True, True, True])
        selected = ranked.groupby("decision", sort=False).head(10)
        valid = selected[selected.label_available]
        counts = {}
        for phase in ("all", "opening", "morning", "afternoon"):
            cohort = valid if phase == "all" else valid[valid.phase == phase]
            counts[phase] = {"n": len(cohort), "rallies": int(cohort.rally.sum()),
                             "rally_rate": float(cohort.rally.mean()) if len(cohort) else None,
                             "rally_after_spread_rate": float(cohort.rally_after_spread.mean()) if len(cohort) else None,
                             "median_abs_return_pct": float(cohort.forward_abs.median()) if len(cohort) else None}
        rows[name] = {"selected": len(selected), "labelled": len(valid),
                      "median_spread_pct": float(selected.spread_percent.median()),
                      "median_value5": float(selected.value5.median()),
                      "capture_rate": int(valid.rally.sum()) / eligible_rallies if eligible_rallies else None,
                      "by_phase": counts}
        subset = selected[[*KEYS, "decision", "activity_rank", "renewal", "recent_range", "freshness", "efficiency5", "expansion", "value5", "label_available", "forward_abs", "forward_efficiency", "rally", "spread_percent"]].copy()
        subset["policy"] = name
        selections.append(subset)
    return {"day": day, "decision_times": int(f.decision.nunique()), "candidate_rows": len(f),
            "eligible_rallies": eligible_rallies, "policies": rows}, pd.concat(selections, ignore_index=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--days", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = []
    args.output.mkdir(parents=True, exist_ok=True)
    for day in args.days:
        report, rows = evaluate(pd.read_parquet(args.root / f"{day}.parquet"), day)
        reports.append(report)
        rows.to_parquet(args.output / f"{day}-selections.parquet", index=False)
        (args.output / f"{day}-summary.json").write_text(json.dumps(report, indent=2, allow_nan=False))
        print(day, {k: round(v["by_phase"]["all"]["rally_rate"], 4) for k, v in report["policies"].items()}, flush=True)
    (args.output / "comparison.json").write_text(json.dumps(reports, indent=2, allow_nan=False))
