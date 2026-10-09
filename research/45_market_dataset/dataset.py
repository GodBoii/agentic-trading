"""Validate chronological candle history and construct strictly causal inputs."""

from collections.abc import Iterator
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.common.data import file_hash

TRACK = Path(__file__).resolve().parent
ROOT = TRACK.parents[1]
CACHE = TRACK / "cache" / "initial-v1"
FEATURES_PRICE = ("ret1", "ret5", "ret15", "ret30", "vol30", "vwapdev", "efficiency30",
                  "body_bps", "range_bps", "volume_local_ratio", "session_return")
FEATURES_CONTEXT = FEATURES_PRICE + ("same_slot_rvol", "overnight_gap", "peer_return5",
    "peer_return15", "peer_return30", "residual_return5", "residual_return15",
    "residual_return30", "minute_sin", "minute_cos")
HORIZONS = (5, 15, 30)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def normalized_bars(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError("minute candles lack required columns")
    result = frame[list(required)].copy()
    if not np.isfinite(result.timestamp).all():
        raise ValueError("minute timestamp must be finite")
    clock = pd.to_datetime(result.timestamp, unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    result["date"] = clock.dt.strftime("%Y-%m-%d")
    result["minute"] = clock.dt.hour * 60 + clock.dt.minute
    result["weekday"] = clock.dt.weekday
    result["bucket_us"] = (result.timestamp.astype("int64") // 60) * 60_000_000
    values = result[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)
    result["valid"] = (np.isfinite(values).all(axis=1) & (values[:, :4] > 0).all(axis=1)
        & (values[:, 4] >= 0) & (values[:, 1] >= values[:, :4].max(axis=1))
        & (values[:, 2] <= values[:, :4].min(axis=1)))
    return result.loc[result.minute.between(555, 929) & (result.weekday < 5)].sort_values(
        ["date", "minute"]).reset_index(drop=True)


def eligible_sessions(frame: pd.DataFrame) -> Iterator[tuple[str, pd.DataFrame]]:
    for date, group in frame.groupby("date", sort=True):
        if (len(group) == 375 and group.minute.nunique() == 375 and group.valid.all()
                and group.volume.sum() > 0):
            yield str(date), group.reset_index(drop=True)


def causal_day_features(day: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Feature values at row t depend solely on bars through t."""
    c, o, h, l, v = (day[name].astype(float).reset_index(drop=True)
                     for name in ["close", "open", "high", "low", "volume"])
    one = c.pct_change(fill_method=None) * 10000
    typical = (h + l + c) / 3
    vwap = (typical * v).cumsum() / v.cumsum().where(v.cumsum() > 0)
    prior_volume = v.shift(1).rolling(30, min_periods=1).mean()
    local_ratio = v / prior_volume.where(prior_volume > 0)
    feature = pd.DataFrame({
        "ret1": one, "ret5": c.pct_change(5, fill_method=None) * 10000,
        "ret15": c.pct_change(15, fill_method=None) * 10000,
        "ret30": c.pct_change(30, fill_method=None) * 10000,
        "vol30": one.rolling(30, min_periods=30).std(ddof=0),
        "vwapdev": (c / vwap - 1) * 10000,
        "efficiency30": (c - c.shift(30)).abs() / c.diff().abs().rolling(30).sum().where(
            c.diff().abs().rolling(30).sum() > 0),
        "body_bps": (c / o - 1) * 10000, "range_bps": (h - l) / c * 10000,
        "volume_local_ratio": local_ratio, "session_return": (c / o.iloc[0] - 1) * 10000})
    # Flat prices have a defined zero path efficiency, not an unavailable state.
    flat = c.diff().abs().rolling(30).sum() == 0
    feature.loc[flat, "efficiency30"] = 0.0
    sequence_channels = np.column_stack([one, feature.body_bps, feature.range_bps,
                                        np.log1p(local_ratio), feature.vwapdev]).astype(np.float32)
    return feature, sequence_channels


def build() -> Path:
    if CACHE.exists():
        raise ValueError("preserve existing cache; choose a newly versioned specification")
    spec_path = TRACK / "specification.json"
    spec = json.loads(spec_path.read_text())
    CACHE.mkdir(parents=True)
    write_json(CACHE / "specification.json", spec)
    manifest = {"specification_sha256": file_hash(spec_path), "dataset_source_sha256": file_hash(Path(__file__)),
                "selection": [], "inputs": [], "coverage": [], "promotion_eligible": False}
    root = ROOT / "context/stocks-data/NSE"
    # The cohort is selected from 2022 only before later feature or outcome construction.
    for path in sorted(root.glob("*/intraday_1m/2022.parquet")):
        bars = normalized_bars(pd.read_parquet(path))
        values = [float((((day.high + day.low + day.close) / 3) * day.volume).sum())
                  for date, day in eligible_sessions(bars) if date.startswith("2022-")]
        manifest["selection"].append({"security_id": int(path.parent.parent.name), "sessions": len(values),
            "median_turnover": float(np.median(values)) if values else 0.0, "path": path.relative_to(ROOT).as_posix(),
            "sha256": file_hash(path)})
    candidates = [row for row in manifest["selection"] if row["sessions"] >= spec["minimum_selection_sessions"]]
    selected = sorted(candidates, key=lambda row: (-row["median_turnover"], row["security_id"]))[:spec["cohort_count"]]
    if len(selected) != spec["cohort_count"]:
        raise ValueError("insufficient eligible 2022 instruments")
    manifest["selected"] = selected
    write_json(CACHE / "selection-freeze.json", {"selected": selected, "specification_sha256": manifest["specification_sha256"]})
    print(json.dumps({"event": "cohort_frozen", "ids": [r["security_id"] for r in selected]}), flush=True)
    rows, sequences = [], []
    for selected_row in selected:
        security_id = selected_row["security_id"]
        paths = sorted(p for p in (root / str(security_id) / "intraday_1m").glob("*.parquet")
                       if p.stem.isdigit() and 2022 <= int(p.stem) <= 2026)
        frames = []
        for path in paths:
            digest = file_hash(path)
            frames.append(normalized_bars(pd.read_parquet(path)))
            if file_hash(path) != digest:
                raise ValueError("candle source changed during reading")
            manifest["inputs"].append({"path": path.relative_to(ROOT).as_posix(), "sha256": digest})
        bars = pd.concat(frames, ignore_index=True)
        eligible = list(eligible_sessions(bars))
        # Each baseline uses only already completed previous sessions.
        prior_slot_volumes: list[np.ndarray] = []
        previous_close, previous_date = None, None
        accepted_rows = 0
        for date, day in eligible:
            features, channels = causal_day_features(day)
            volume = day.volume.to_numpy(dtype=float)
            expected = np.mean(prior_slot_volumes[-20:], axis=0) if len(prior_slot_volumes) >= 5 else None
            recent_previous = previous_date is not None and (pd.Timestamp(date) - pd.Timestamp(previous_date)).days <= 7
            gap = (float(day.open.iloc[0]) / previous_close - 1) * 10000 if recent_previous else None
            for minute in spec["decision_minutes"]:
                index = minute - 555
                seq = channels[index - 29:index + 1]
                f = features.iloc[index]
                if (expected is None or expected[index] <= 0 or gap is None or seq.shape != (30, 5)
                        or not np.isfinite(seq).all() or not np.isfinite(f.to_numpy()).all()):
                    continue
                entry_index = index + 2
                if entry_index + max(HORIZONS) >= len(day):
                    continue
                row = {"date": date, "security_id": security_id, "minute": minute,
                    "decision_us": int(day.bucket_us.iloc[index]) + 60_000_000,
                    "entry_us": int(day.bucket_us.iloc[entry_index]),
                    "decision_reference": float(day.close.iloc[index]),
                    "entry_reference": float(day.open.iloc[entry_index]),
                    "same_slot_rvol": float(volume[index] / expected[index]), "overnight_gap": float(gap),
                    "minute_sin": float(np.sin(2 * np.pi * (minute - 555) / 375)),
                    "minute_cos": float(np.cos(2 * np.pi * (minute - 555) / 375)),
                    "seq_index": len(sequences), **{name: float(f[name]) for name in FEATURES_PRICE}}
                for horizon in HORIZONS:
                    exit_index = entry_index + horizon
                    exit_price = float(day.open.iloc[exit_index])
                    row[f"exit_reference_{horizon}"] = exit_price
                    row[f"exit_us_{horizon}"] = int(day.bucket_us.iloc[exit_index])
                    row[f"target_gross_bps_{horizon}"] = (exit_price / row["entry_reference"] - 1) * 10000
                rows.append(row)
                sequences.append(seq)
                accepted_rows += 1
            prior_slot_volumes.append(volume)
            previous_close, previous_date = float(day.close.iloc[-1]), date
        manifest["coverage"].append({"security_id": security_id, "observed_regular_sessions": bars.date.nunique(),
            "eligible_full_sessions": len(eligible), "constructed_rows": accepted_rows})
        print(json.dumps({"event": "instrument_features", "id": security_id, "rows": accepted_rows}), flush=True)
    panel = pd.DataFrame(rows)
    # Leave out the stock itself, require synchronized peer observations.
    peer_counts = panel.groupby("decision_us").security_id.transform("count") - 1
    for horizon in HORIZONS:
        summed = panel.groupby("decision_us")[f"ret{horizon}"].transform("sum")
        panel[f"peer_return{horizon}"] = (summed - panel[f"ret{horizon}"]) / peer_counts.where(peer_counts >= 4)
        panel[f"residual_return{horizon}"] = panel[f"ret{horizon}"] - panel[f"peer_return{horizon}"]
    valid = np.isfinite(panel[list(FEATURES_CONTEXT)]).all(axis=1)
    panel = panel.loc[valid].sort_values(["decision_us", "security_id"]).reset_index(drop=True)
    sequence = np.asarray(sequences, dtype=np.float32)[panel.seq_index.to_numpy()]
    panel["seq_index"] = np.arange(len(panel))
    panel.to_parquet(CACHE / "rows.parquet", index=False)
    np.save(CACHE / "sequence.npy", sequence, allow_pickle=False)
    manifest["artifacts"] = {name: file_hash(CACHE / name) for name in ["rows.parquet", "sequence.npy", "selection-freeze.json"]}
    manifest["features_price"] = list(FEATURES_PRICE)
    manifest["features_context"] = list(FEATURES_CONTEXT)
    manifest["sequence_shape"] = list(sequence.shape)
    manifest["rows_before_peer_admission"] = len(rows)
    manifest["phases"] = {name: {"rows": int(panel.date.between(*bounds).sum()),
        "dates": int(panel.loc[panel.date.between(*bounds), "date"].nunique())}
        for name, bounds in spec["dates"].items()}
    manifest["source_snapshots"] = {path.name: file_hash(path) for path in TRACK.glob("*.py")}
    for path in TRACK.glob("*.py"):
        destination = CACHE / "source" / path.name
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(path.read_bytes())
    write_json(CACHE / "manifest.json", manifest)
    print(json.dumps({"event": "dataset_completed", "rows": len(panel), "phases": manifest["phases"]}), flush=True)
    return CACHE


def load_dataset() -> tuple[pd.DataFrame, np.ndarray, dict]:
    manifest = json.loads((CACHE / "manifest.json").read_text())
    for name, digest in manifest["artifacts"].items():
        if file_hash(CACHE / name) != digest:
            raise ValueError(f"dataset artifact changed: {name}")
    rows = pd.read_parquet(CACHE / "rows.parquet")
    sequence = np.load(CACHE / "sequence.npy", mmap_mode="r", allow_pickle=False)
    if len(rows) != len(sequence) or not np.array_equal(rows.seq_index, np.arange(len(rows))):
        raise ValueError("sequence row alignment changed")
    return rows, sequence, manifest


if __name__ == "__main__":
    build()
