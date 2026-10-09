from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

SPEC = importlib.util.spec_from_file_location("orderbook_horizons_study", Path(__file__).with_name("study.py"))
assert SPEC is not None and SPEC.loader is not None
STUDY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = STUDY
SPEC.loader.exec_module(STUDY)
extract_quotes = STUDY.extract_quotes
holm_adjust = STUDY.holm_adjust
horizon_targets = STUDY.horizon_targets
ofi_increment = STUDY.ofi_increment
queue_measures = STUDY.queue_measures


def test_same_price_size_change() -> None:
    assert ofi_increment((100, 10, 101, 8), (100, 15, 101, 5)) == 8


def test_improving_quotes() -> None:
    assert ofi_increment((100, 10, 101, 8), (100.5, 4, 101.5, 6)) == 12


def test_worsening_quotes() -> None:
    assert ofi_increment((100, 10, 101, 8), (99.5, 4, 100.5, 6)) == -16


def test_weighted_midpoint_identity_and_rejection() -> None:
    imbalance, offset = queue_measures(100, 30, 102, 10)
    assert imbalance == 0.5
    assert offset == pytest.approx(0.5 / 101 * 10_000)
    with pytest.raises(ValueError):
        queue_measures(102, 10, 100, 10)
    with pytest.raises(ValueError):
        queue_measures(100, 0, 102, 0)


def bars(count: int = 18) -> pd.DataFrame:
    return pd.DataFrame({"date": ["2026-08-20"] * count, "security_id": ["future"] * count,
                         "segment": [0] * count, "complete_minute": [True] * count,
                         "decision_at": pd.date_range("2026-08-20T04:00:00Z", periods=count, freq="min"),
                         "close": np.arange(count) + 100.0})


def test_label_stays_inside_segment() -> None:
    frame = bars()
    frame.loc[10:, "segment"] = 1
    output = horizon_targets(frame, 3)
    assert output.loc[6, "target_bps"] == pytest.approx(np.log(109 / 106) * 10_000)
    assert output.loc[7:14, "target_bps"].isna().all()


def test_missing_minute_invalidates_history_and_future() -> None:
    frame = bars().drop(index=9)
    output = horizon_targets(frame, 3)
    assert pd.isna(output.loc[6, "target_bps"])
    assert not output.loc[9, "feature_ready"]


def test_partial_future_or_history_invalidates_labels() -> None:
    frame = bars()
    frame.loc[9, "complete_minute"] = False
    output = horizon_targets(frame, 3)
    assert pd.isna(output.loc[6, "target_bps"])
    assert not output.loc[10, "feature_ready"]
    assert output.loc[15, "feature_ready"]


def test_holm_corrects_family_and_preserves_order() -> None:
    assert holm_adjust([0.04, 0.001, 0.6]) == pytest.approx([0.08, 0.003, 0.6])


def test_reset_does_not_invent_flow(tmp_path) -> None:
    records = []
    for sequence, size, stamp in [(10, 10, "2026-08-20T04:00:01Z"),
                                  (11, 30, "2026-08-20T04:00:02Z"),
                                  (1, 100, "2026-08-20T04:00:03Z")]:
        records.append({"captured_at_utc": stamp, "event_sequence": sequence,
                        "packet": {"type": "Full Data", "security_id": "123", "LTP": 100.5,
                                   "volume": 10, "depth": [{"bid_price": 100, "ask_price": 101,
                                                            "bid_quantity": size, "ask_quantity": 10}]}})
    path = tmp_path / "full.ndjson"
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    output, audit = extract_quotes(path, "2026-08-20")
    assert audit["resets"] == 1
    assert output["segment"].tolist() == [0, 1]
    assert output["quote_ofi"].tolist() == [20, 0]
