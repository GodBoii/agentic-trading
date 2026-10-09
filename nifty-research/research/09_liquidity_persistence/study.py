"""Causal, fixed-second aggregate liquidity persistence from archived 200-depth."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from nifty_lab.io import capture_time, read_records, trading_capture, write_json

SPEC = importlib.util.spec_from_file_location("orderbook_uncertainty", ROOT / "research/02_orderbook_horizons/study.py")
assert SPEC is not None and SPEC.loader is not None
UNCERTAINTY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = UNCERTAINTY
SPEC.loader.exec_module(UNCERTAINTY)

DATES = ("2026-08-03", "2026-08-19", "2026-08-20", "2026-08-21")
QUANTITIES = (650, 1300)
SECONDS = (10, 30, 60)
PERSISTENT = [f"persistent_{quantity}_{duration}" for quantity in QUANTITIES for duration in SECONDS]
CONTROLS = ["near_imbalance", "top5_imbalance", "deep_wall_count_imbalance"]


def imbalance(buy: float, sell: float) -> float:
    return (buy - sell) / (buy + sell) if buy + sell else 0.0


class Presence:
    """Track uninterrupted observed presence of size at a side/price level."""

    def __init__(self) -> None:
        self.first_seen: dict[tuple[str, float, int], pd.Timestamp] = {}
        self.previous: pd.Timestamp | None = None

    def reset(self) -> None:
        self.first_seen.clear()
        self.previous = None

    def update(self, stamp: pd.Timestamp, bids: list[tuple[float, float]],
               asks: list[tuple[float, float]], mid: float) -> dict[str, float]:
        if self.previous is not None and stamp - self.previous != pd.Timedelta(seconds=1):
            self.reset()
        active = {}
        size = {}
        for side, levels in (("bid", bids), ("ask", asks)):
            for price, quantity in levels:
                distance = mid - price if side == "bid" else price - mid
                if not 0 <= distance <= 10:
                    continue
                for threshold in QUANTITIES:
                    if quantity >= threshold:
                        key = (side, price, threshold)
                        active[key] = self.first_seen.get(key, stamp)
                        size[key] = quantity
        self.first_seen = active
        self.previous = stamp
        result = {}
        for threshold in QUANTITIES:
            for duration in SECONDS:
                selected = {key: size[key] for key, since in active.items()
                            if key[2] == threshold and (stamp - since).total_seconds() >= duration}
                buy = sum(value for key, value in selected.items() if key[0] == "bid")
                sell = sum(value for key, value in selected.items() if key[0] == "ask")
                name = f"persistent_{threshold}_{duration}"
                result[name] = imbalance(buy, sell)
                result[f"{name}_total"] = buy + sell
            transient = {key: size[key] for key, since in active.items()
                         if key[2] == threshold and (stamp - since).total_seconds() < 5}
            result[f"transient_{threshold}"] = imbalance(
                sum(value for key, value in transient.items() if key[0] == "bid"),
                sum(value for key, value in transient.items() if key[0] == "ask"))
        return result


def clean_levels(raw: list[dict], side: str) -> list[tuple[float, float]]:
    levels = [(float(level["price"]), float(level["quantity"])) for level in raw
              if isinstance(level, dict) and "price" in level and "quantity" in level
              and float(level["price"]) > 0 and float(level["quantity"]) >= 0]
    if not levels or not all(np.isfinite(pair).all() for pair in levels):
        raise ValueError("Depth has no valid finite levels")
    if any((a[0] < b[0] if side == "bid" else a[0] > b[0]) for a, b in zip(levels, levels[1:])):
        raise ValueError("Depth levels are not sorted")
    return levels


def parse_depth(path: Path, day: str) -> tuple[pd.DataFrame, dict]:
    audit: dict = {"invalid_record": 0, "backwards": 0, "reset_events": 0,
                   "grid_invalid": Counter(), "grid_valid": 0}
    sides = {}
    presence = Presence()
    previous = None
    boundary = None
    segment = 0
    rows = []

    def sample(stamp: pd.Timestamp) -> None:
        if len(sides) != 2:
            audit["grid_invalid"]["missing_side"] += 1
            presence.reset()
            return
        if any((stamp - value["timestamp"]).total_seconds() > 1 for value in sides.values()):
            audit["grid_invalid"]["stale_side"] += 1
            presence.reset()
            return
        if sides["bid"]["security_id"] != sides["ask"]["security_id"]:
            audit["grid_invalid"]["contract_mismatch"] += 1
            presence.reset()
            return
        try:
            bids = clean_levels(sides["bid"]["depth"], "bid")
            asks = clean_levels(sides["ask"]["depth"], "ask")
        except (KeyError, TypeError, ValueError):
            audit["grid_invalid"]["invalid_levels"] += 1
            presence.reset()
            return
        if bids[0][0] >= asks[0][0]:
            audit["grid_invalid"]["crossed_pair"] += 1
            presence.reset()
            return
        mid = (bids[0][0] + asks[0][0]) / 2
        near_bid = sum(quantity for price, quantity in bids if 0 <= mid - price <= 10)
        near_ask = sum(quantity for price, quantity in asks if 0 <= price - mid <= 10)
        deep_bid_count = sum(quantity >= 300 for _, quantity in bids)
        deep_ask_count = sum(quantity >= 300 for _, quantity in asks)
        metrics = presence.update(stamp, bids, asks, mid)
        rows.append({"timestamp": stamp, "date": day, "segment": segment,
                     "security_id": sides["bid"]["security_id"], "mid": mid,
                     "source_at": max(value["timestamp"] for value in sides.values()),
                     "side_age_seconds": max((stamp - value["timestamp"]).total_seconds() for value in sides.values()),
                     "near_imbalance": imbalance(near_bid, near_ask),
                     "top5_imbalance": imbalance(sum(q for _, q in bids[:5]), sum(q for _, q in asks[:5])),
                     "deep_wall_count_imbalance": imbalance(deep_bid_count, deep_ask_count),
                     "deep_wall_count": deep_bid_count + deep_ask_count,
                     "near_total": near_bid + near_ask, **metrics})
        audit["grid_valid"] += 1

    for record in read_records(path, audit):
        try:
            stamp = pd.Timestamp(capture_time(record))
        except (KeyError, TypeError, ValueError):
            audit["invalid_record"] += 1
            continue
        if not trading_capture(stamp.to_pydatetime(), day):
            continue
        if previous is not None and stamp < previous:
            audit["backwards"] += 1
            continue
        side = record.get("side")
        raw = record.get("depth")
        if side not in {"bid", "ask"} or not isinstance(raw, list):
            audit["invalid_record"] += 1
            continue
        sid = str(record.get("security_id"))
        sequence = record.get("event_sequence")
        old = sides.get(side)
        reset = ((previous is not None and (stamp - previous).total_seconds() > 10)
                 or (old is not None and old["security_id"] != sid)
                 or (old is not None and isinstance(sequence, int) and isinstance(old["sequence"], int)
                     and sequence < old["sequence"]))
        if reset:
            sides.clear()
            presence.reset()
            segment += 1
            boundary = stamp.ceil("s")
            audit["reset_events"] += 1
        if boundary is None:
            boundary = stamp.ceil("s")
        # Emit a grid using earlier packets only, before accepting this packet.
        while boundary <= stamp:
            sample(boundary)
            boundary += pd.Timedelta(seconds=1)
        sides[side] = {"timestamp": stamp, "security_id": sid, "sequence": sequence, "depth": raw}
        previous = stamp
    audit["grid_invalid"] = dict(audit["grid_invalid"])
    return pd.DataFrame(rows), audit


def minute_frame(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.copy()
    raw["minute"] = raw["timestamp"].dt.floor("min")
    raw["oldest_source_at"] = raw["timestamp"] - pd.to_timedelta(raw["side_age_seconds"], unit="s")
    aggregations = {column: (column, "last") for column in [*PERSISTENT, *CONTROLS, "transient_650", "transient_1300"]}
    aggregations.update(close=("mid", "last"), grid_seconds=("mid", "size"),
                        first_at=("timestamp", "first"), grid_at=("timestamp", "last"),
                        source_at=("source_at", "last"), oldest_source_at=("oldest_source_at", "last"))
    bars = raw.groupby(["date", "segment", "security_id", "minute"], sort=True).agg(**aggregations).reset_index()
    bars["decision_at"] = bars["minute"] + pd.Timedelta(minutes=1)
    bars["complete_minute"] = (bars["grid_seconds"].ge(55)
                               & (bars["first_at"] - bars["minute"]).dt.total_seconds().le(2)
                               & (bars["decision_at"] - bars["grid_at"]).dt.total_seconds().le(2)
                               & (bars["decision_at"] - bars["oldest_source_at"]).dt.total_seconds().le(2))
    return bars


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extraction_hash() -> str:
    """Fingerprint extraction definitions, allowing analysis-only cache reuse."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    names = {"DATES", "QUANTITIES", "SECONDS", "imbalance", "Presence", "clean_levels", "parse_depth"}
    selected = [node for node in tree.body if
                isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names
                or isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in names
                                                       for target in node.targets)]
    return hashlib.sha256(ast.dump(ast.Module(body=selected, type_ignores=[])).encode()).hexdigest()


def cache_provenance(output: Path, audits: list[dict], origin: str) -> dict:
    return {"schema_version": 1, "origin": origin,
            "seconds_sha256": file_hash(output / "seconds.parquet"),
            "source_audits_sha256": file_hash(output / "source-audits.json"),
            "extraction_sha256": extraction_hash(),
            "reader_sha256": file_hash(ROOT / "nifty_lab/io.py"),
            "baseline_manifest_sha256": file_hash(ROOT / "research/01_depth_forecast_baseline/artifacts/manifest.json"),
            "source_sha256_by_date": {audit["date"]: audit["sha256"] for audit in audits}}


def validate_cache(output: Path, raw: pd.DataFrame, audits: list[dict]) -> dict:
    required = {"timestamp", "source_at", "side_age_seconds", "date", "segment", "security_id", "mid",
                "deep_wall_count", "near_total", *PERSISTENT, *CONTROLS, "transient_650", "transient_1300"}
    if not required.issubset(raw.columns):
        raise ValueError("Legacy cache lacks actual packet times or research fields; reparse raw sources")
    provenance_path = output / "cache-provenance.json"
    if not provenance_path.is_file():
        raise ValueError("Cache has no verified provenance; reparse raw sources")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("schema_version") != 1:
        raise ValueError("Unsupported cache provenance version")
    expected = cache_provenance(output, audits, provenance.get("origin", ""))
    if provenance != expected:
        raise ValueError("Cache digest, source manifest, extraction or reader code changed; reparse raw sources")
    if raw.empty or set(raw["date"]) != set(DATES) or {audit["date"] for audit in audits} != set(DATES):
        raise ValueError("Cache/source audits do not cover the prescribed dates")
    source_age = (raw["timestamp"] - raw["source_at"]).dt.total_seconds()
    if (not source_age.between(0, 1, inclusive="right").all()
            or not raw["side_age_seconds"].between(0, 1).all()
            or not (source_age <= raw["side_age_seconds"] + 1e-6).all()):
        raise ValueError("Cache contains future or stale packet times")
    manifest = json.loads((ROOT / "research/01_depth_forecast_baseline/artifacts/manifest.json").read_text(encoding="utf-8"))
    sessions = {session["date"]: session for session in manifest["sessions"]}
    for audit in audits:
        original = sessions[audit["date"]]["files"]["depth"]
        path = Path(audit["path"])
        stat = path.stat()
        if (audit["sha256"] != original["sha256"]
                or (audit["bytes"], audit["mtime_ns"]) != (original["bytes"], original["mtime_ns"])
                or (stat.st_size, stat.st_mtime_ns) != (audit["bytes"], audit["mtime_ns"])):
            raise ValueError(f"Raw source metadata/audit differs from baseline: {path}")
    return provenance


def analyze(raw: pd.DataFrame) -> dict:
    bars = minute_frame(raw)
    results = []
    rng = np.random.default_rng(20261001)
    names = [*PERSISTENT, *CONTROLS, "transient_650", "transient_1300"]
    for horizon in (1, 3, 5):
        labelled = UNCERTAINTY.horizon_targets(bars, horizon).dropna(subset=["target_bps"])
        for name in names:
            eligible = labelled.loc[labelled[name].abs() >= 0.10].copy()
            signed = np.sign(eligible[name]) * eligible["target_bps"]
            by_day = signed.groupby(eligible["date"]).mean()
            result = {"horizon": horizon, "signal": name, "eligible_minutes": len(eligible),
                      "all_valid_minutes": len(labelled), "days": len(by_day),
                      "mean_signed_return_bps": float(signed.mean()) if len(signed) else None,
                      "positive_return_fraction": float((signed > 0).mean()) if len(signed) else None,
                      "daily_signed_return_bps": by_day.to_dict()}
            if len(by_day):
                uncertainty = UNCERTAINTY.day_uncertainty(by_day.to_numpy(), rng)
                result["daily_mean_signed_return_bps"] = uncertainty.pop("mean_daily_mse_improvement")
                result.update(uncertainty)
            # All control outcomes on the exact persistent-signal cohort.
            result["paired_cohort_controls"] = {}
            if name in PERSISTENT:
                for control in CONTROLS:
                    control_signed = np.sign(eligible[control]) * eligible["target_bps"]
                    difference = signed - control_signed
                    daily = difference.groupby(eligible["date"]).mean()
                    result["paired_cohort_controls"][control] = {
                        "mean_signed_return_bps": float(control_signed.mean()) if len(control_signed) else None,
                        "persistent_minus_control_bps": float(difference.mean()) if len(difference) else None,
                        "daily_difference": daily.to_dict()}
                    if len(daily):
                        uncertainty = UNCERTAINTY.day_uncertainty(daily.to_numpy(), rng)
                        uncertainty["daily_mean_difference_bps"] = uncertainty.pop("mean_daily_mse_improvement")
                        result["paired_cohort_controls"][control].update(uncertainty)
            results.append(result)
    tested = [result for result in results if "one_sided_day_sign_flip_p" in result]
    adjusted = UNCERTAINTY.holm_adjust([result["one_sided_day_sign_flip_p"] for result in tested])
    for result, value in zip(tested, adjusted, strict=True):
        result["holm_p_33_response_trials"] = value
    paired = [value for result in results for value in result["paired_cohort_controls"].values()
              if "one_sided_day_sign_flip_p" in value]
    adjusted = UNCERTAINTY.holm_adjust([value["one_sided_day_sign_flip_p"] for value in paired])
    for result, value in zip(paired, adjusted, strict=True):
        result["holm_p_54_paired_comparisons"] = value
    return {"response_trial_count": len(results), "paired_comparison_count": len(paired),
            "results": results, "grid_summary": raw.groupby("date").agg(
                seconds=("mid", "size"), mean_deep_wall_count=("deep_wall_count", "mean"),
                mean_near_quantity=("near_total", "mean")).reset_index().to_dict("records")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "artifacts")
    parser.add_argument("--reuse", action="store_true", help="Reuse this study's saved seconds and source audits")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.reuse:
        raw = pd.read_parquet(output / "seconds.parquet")
        audits = json.loads((output / "source-audits.json").read_text(encoding="utf-8"))
        provenance = validate_cache(output, raw, audits)
    else:
        manifest = json.loads((ROOT / "research/01_depth_forecast_baseline/artifacts/manifest.json").read_text(encoding="utf-8"))
        sessions = {session["date"]: session for session in manifest["sessions"]}
        frames = []
        audits = []
        for day in DATES:
            session = sessions[day]
            path = Path(session["source"]) / "depth_200.ndjson"
            print(f"Reading {day}, {path.stat().st_size / 1e9:.2f} GB", flush=True)
            frame, audit = parse_depth(path, day)
            if audit["sha256"] != session["files"]["depth"]["sha256"]:
                raise ValueError(f"Archive hash differs from baseline manifest: {path}")
            audit["date"] = day
            audits.append(audit)
            frames.append(frame)
        raw = pd.concat(frames, ignore_index=True)
        raw.to_parquet(output / "seconds.parquet", index=False)
        write_json(output / "source-audits.json", audits)
        provenance = cache_provenance(output, audits, "raw_parse_with_source_hash_checks")
        write_json(output / "cache-provenance.json", provenance)
        validate_cache(output, raw, audits)
    summary = analyze(raw)
    summary["source_audits"] = audits
    summary["study_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    summary["uncertainty_code_sha256"] = file_hash(ROOT / "research/02_orderbook_horizons/study.py")
    summary["cache_provenance"] = provenance
    summary["status"] = "exploratory_in_sample_response_analysis"
    write_json(output / "results.json", summary)
    lines = ["# Liquidity persistence response study", "", "Descriptive conditional returns. No trades or profitability claim.", "",
             "| Horizon | Signal | Eligible minutes | Days | Signed return bps | Holm p |", "|---|---|---:|---:|---:|---:|"]
    for result in summary["results"]:
        mean = result["mean_signed_return_bps"]
        lines.append(f"| {result['horizon']} | {result['signal']} | {result['eligible_minutes']} | {result['days']} | "
                     f"{'n/a' if mean is None else f'{mean:.4f}'} | {result.get('holm_p_33_response_trials', 'n/a')} |")
    lines += ["", "Signals use causal one-second sampled book histories, never future wall lifetime. Complete minutes require "
              "55 of 60 valid seconds and the oldest constituent packet within two seconds of the minute decision. "
              "Grid time and actual packet time remain separate. Side age at each grid is at most one second. Missing samples "
              "restart level persistence. Gaps over ten seconds, contract changes and recorder restarts reset the segment. "
              "Targets require six complete prior minutes and contiguous complete future minutes.", "",
              "Four selected long-coverage dates support descriptive response analysis, not a trained or untouched holdout study. "
              "All 33 response trials and 54 paired control comparisons are retained. Holm corrections are separate by family. "
              "Exact daily sign-flip resolution is poor with four dates; symmetry and independence are unproven. "
              "Conditional signal cohorts differ, so their raw means are not directly comparable. Paired controls use the "
              "identical persistent-signal cohort. Zero control imbalance contributes zero signed response rather than a "
              "fabricated direction. Outcomes overlap within days and have no execution-cost adjustment.", "",
              "A continuing aggregate quantity at a price can contain replacement orders. Its disappearance does not identify "
              "cancellation, execution, spoofing, or the trader. The fixed threshold 300 raw deep-wall count is included as a "
              "control, not a definition of institutional trading. Read README and findings for sources and actual conclusions.", ""]
    lines += ["Cache reuse verifies the parquet and audit digests, extraction definitions, shared reader code, "
              "baseline manifest and current raw-file size/mtime. It does not rehash all raw bytes on every reuse. "
              "A changed dependency or cache requires a new raw parse. results.json records the uncertainty-code hash "
              "and the cache's origin. The previous results remain under artifacts/revisions/pre-freshness-fix.", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"seconds": len(raw), "response_trials": summary["response_trial_count"],
                      "paired_comparisons": summary["paired_comparison_count"]}), flush=True)


if __name__ == "__main__":
    main()
