from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location("liquidity_persistence_study", Path(__file__).with_name("study.py"))
assert SPEC is not None and SPEC.loader is not None
STUDY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = STUDY
SPEC.loader.exec_module(STUDY)


def test_persistence_measures_seconds_and_resets_on_missing_grid() -> None:
    presence = STUDY.Presence()
    start = pd.Timestamp("2026-08-20T04:00:00Z")
    for second in range(11):
        metrics = presence.update(start + pd.Timedelta(seconds=second), [(100, 1300)], [(102, 65)], 101)
    assert metrics["persistent_650_10"] == 1
    assert metrics["persistent_650_30"] == 0
    metrics = presence.update(start + pd.Timedelta(seconds=13), [(100, 1300)], [(102, 65)], 101)
    assert metrics["persistent_650_10"] == 0


def test_near_price_filter_and_disappearance_restart() -> None:
    presence = STUDY.Presence()
    start = pd.Timestamp("2026-08-20T04:00:00Z")
    for second in range(31):
        metrics = presence.update(start + pd.Timedelta(seconds=second), [(80, 2000)], [(102, 1300)], 101)
    assert metrics["persistent_1300_30"] == -1
    presence.update(start + pd.Timedelta(seconds=31), [(100, 65)], [(102, 65)], 101)
    metrics = presence.update(start + pd.Timedelta(seconds=32), [(100, 65)], [(102, 1300)], 101)
    assert metrics["persistent_1300_30"] == 0


def packets(seconds: int) -> list[dict]:
    rows = []
    for second in range(seconds):
        for side, price, fraction in [("bid", 100, 0.1), ("ask", 102, 0.2)]:
            stamp = pd.Timestamp("2026-08-20T04:00:00Z") + pd.Timedelta(seconds=second + fraction)
            rows.append({"captured_at_utc": stamp.isoformat(), "side": side, "security_id": "123",
                         "event_sequence": second * 2 + (1 if side == "bid" else 2),
                         "depth": [{"price": price, "quantity": 1300}]})
    return rows


def save(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_future_packets_cannot_change_earlier_features(tmp_path: Path) -> None:
    first = tmp_path / "first.ndjson"
    second = tmp_path / "second.ndjson"
    save(first, packets(40))
    later = packets(60)
    for row in later[80:]:
        row["depth"][0]["quantity"] = 999_999
    save(second, later)
    short, _ = STUDY.parse_depth(first, "2026-08-20")
    long, _ = STUDY.parse_depth(second, "2026-08-20")
    pd.testing.assert_frame_equal(short, long.loc[long["timestamp"] <= short["timestamp"].max()].reset_index(drop=True))
    assert (short["source_at"] < short["timestamp"]).all()


def test_stale_and_crossed_side_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "raw.ndjson"
    rows = packets(5)
    for row in rows:
        if row["side"] == "ask":
            row["depth"][0]["price"] = 99
    save(path, rows)
    output, audit = STUDY.parse_depth(path, "2026-08-20")
    assert output.empty
    assert audit["grid_invalid"]["crossed_pair"] > 0
    save(path, [row for row in packets(10) if row["side"] == "bid" or row["event_sequence"] == 2])
    output, audit = STUDY.parse_depth(path, "2026-08-20")
    assert audit["grid_invalid"]["stale_side"] > 0


def test_invalid_ordering_rejected() -> None:
    with pytest.raises(ValueError):
        STUDY.clean_levels([{"price": 100, "quantity": 65}, {"price": 101, "quantity": 65}], "bid")


@pytest.mark.parametrize("gap_seconds", [12, 30])
def test_recorder_restart_and_capture_gap_reset_presence(tmp_path: Path, gap_seconds: int) -> None:
    path = tmp_path / "reset.ndjson"
    initial = packets(12)
    restarted = packets(5)
    for row in restarted:
        stamp = pd.Timestamp(row["captured_at_utc"]) + pd.Timedelta(seconds=gap_seconds)
        row["captured_at_utc"] = stamp.isoformat()
    save(path, initial + restarted)
    output, audit = STUDY.parse_depth(path, "2026-08-20")
    assert audit["reset_events"] == 1
    assert output["segment"].max() == 1
    assert output.loc[output["segment"] == 1, "persistent_650_10_total"].eq(0).all()


@pytest.mark.parametrize("last_second, complete", [(58, False), (59, True)])
def test_minute_freshness_uses_actual_oldest_packet(last_second: int, complete: bool) -> None:
    start = pd.Timestamp("2026-08-20T04:00:00Z")
    rows = []
    for second in range(1, last_second + 1):
        stamp = start + pd.Timedelta(seconds=second)
        row = {"timestamp": stamp, "source_at": stamp - pd.Timedelta(seconds=0.2),
               "side_age_seconds": 0.4, "date": "2026-08-20", "segment": 0,
               "security_id": "123", "mid": 101.0}
        row.update({column: 0.0 for column in [*STUDY.PERSISTENT, *STUDY.CONTROLS,
                                              "transient_650", "transient_1300"]})
        rows.append(row)
    bars = STUDY.minute_frame(pd.DataFrame(rows))
    assert bool(bars.loc[0, "complete_minute"]) is complete
    assert bars.loc[0, "grid_at"] == start + pd.Timedelta(seconds=last_second)
    assert bars.loc[0, "source_at"] == bars.loc[0, "grid_at"] - pd.Timedelta(seconds=0.2)
    assert bars.loc[0, "oldest_source_at"] == bars.loc[0, "grid_at"] - pd.Timedelta(seconds=0.4)


def cache_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "source_at", "side_age_seconds", "date", "segment",
                                 "security_id", "mid", "deep_wall_count", "near_total",
                                 *STUDY.PERSISTENT, *STUDY.CONTROLS, "transient_650", "transient_1300"])


def test_cache_without_source_timing_or_provenance_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="actual packet times"):
        STUDY.validate_cache(tmp_path, pd.DataFrame(), [])
    with pytest.raises(ValueError, match="no verified provenance"):
        STUDY.validate_cache(tmp_path, cache_frame(), [])


@pytest.mark.parametrize("field", ["seconds_sha256", "source_audits_sha256", "extraction_sha256",
                                   "reader_sha256", "baseline_manifest_sha256"])
def test_cache_dependency_or_digest_change_is_rejected(tmp_path: Path, field: str) -> None:
    (tmp_path / "seconds.parquet").write_bytes(b"cache fixture")
    (tmp_path / "source-audits.json").write_text("[]", encoding="utf-8")
    provenance = STUDY.cache_provenance(tmp_path, [], "test fixture")
    provenance[field] = "changed"
    (tmp_path / "cache-provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        STUDY.validate_cache(tmp_path, cache_frame(), [])
