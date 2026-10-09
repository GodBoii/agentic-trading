from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nifty_lab.config import ResearchConfig
from nifty_lab.experiment import GROUPS, walk_forward
from nifty_lab.ingest import book_features, minute_features, read_depth, read_market, read_options
from nifty_lab.io import source_fingerprint, trading_capture
from nifty_lab.replay import QuoteBook, choose_directional, mark_to_market, replay_policy
from nifty_lab.strategies import Leg, Strategy, charge_estimate, strategy_library


def write_rows(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def packet(stamp: str, volume: int = 1000, seq: int = 1, sid: int = 1) -> dict:
    return {"captured_at_utc": stamp, "event_sequence": seq,
            "packet": {"type": "Full Data", "security_id": sid, "LTP": 101, "LTQ": 10,
                       "volume": volume, "OI": 100, "LTT": "09:15:01",
                       "depth": [{"bid_price": 100, "ask_price": 101, "bid_quantity": 20, "ask_quantity": 10}]}}


def test_market_resets_and_volume_conservation(tmp_path):
    rows = [packet("2026-08-20T03:45:01+00:00"), packet("2026-08-20T03:45:02+00:00", 1020, 2),
            packet("2026-08-20T03:45:30+00:00", 1400, 3), packet("2026-08-20T03:45:31+00:00", 1410, 4),
            packet("2026-08-20T03:45:32+00:00", 1420, 1)]
    path = write_rows(tmp_path / "market.ndjson", rows); before = path.read_bytes()
    frame, audit = read_market(path, "2026-08-20", ResearchConfig())
    assert frame["volume_increment"].tolist() == [0, 20, 0, 10, 0]
    assert frame["segment"].tolist() == [0, 0, 1, 1, 2]
    assert frame["estimated_cvd"].tolist() == [0, 20, 0, 10, 0]
    assert audit["resets"] == 2 and audit["ambiguous_volume_rows"] == 1
    assert path.read_bytes() == before and len(audit["sha256"]) == 64


def test_weekend_and_crossed_quote_are_quarantined(tmp_path):
    weekend = write_rows(tmp_path / "weekend.ndjson", [packet("2026-08-23T03:45:01+00:00")])
    frame, audit = read_market(weekend, "2026-08-23", ResearchConfig())
    assert frame.empty and audit["outside_regular_session"] == 1
    bad = packet("2026-08-20T03:45:01+00:00")
    bad["packet"]["depth"][0]["ask_price"] = 99
    frame, audit = read_market(write_rows(tmp_path / "bad.ndjson", [bad]), "2026-08-20", ResearchConfig())
    assert frame.empty and audit["invalid_quote"] == 1


def test_malformed_rows_are_reported(tmp_path):
    path = tmp_path / "broken.ndjson"
    path.write_text("not-json\n" + json.dumps(packet("2026-08-20T03:45:01+00:00")), encoding="utf-8")
    frame, audit = read_market(path, "2026-08-20", ResearchConfig())
    assert len(frame) == 1 and audit["malformed"] == 1 and audit["malformed_examples"][0]["line"] == 1


def test_depth_requires_fresh_sides_and_ordered_prices(tmp_path):
    def depth(stamp, side, prices):
        return {"captured_at_utc": stamp, "side": side, "security_id": 1,
                "depth": [{"price": price, "quantity": 10} for price in prices]}
    path = write_rows(tmp_path / "depth.ndjson", [depth("2026-08-20T03:45:01+00:00", "bid", [100, 99]),
        depth("2026-08-20T03:45:03+00:00", "ask", [101, 102]),
        depth("2026-08-20T03:45:03.1+00:00", "bid", [100, 99]),
        depth("2026-08-20T03:45:04.5+00:00", "ask", [102, 101])])
    frame, audit = read_depth(path, "2026-08-20", ResearchConfig())
    assert len(frame) == 1 and audit["stale_pair"] == 1 and audit["invalid_book"] == 1


def market_frame(start="2026-08-20T03:45:00+00:00", minutes=20):
    times = pd.date_range(start, periods=minutes * 60, freq="s")
    return pd.DataFrame({"timestamp": times, "date": times.tz_convert("Asia/Kolkata").strftime("%Y-%m-%d"),
        "segment": 0, "security_id": "1", "mid": 100 + np.arange(len(times)) * 0.001,
        "ltp": 100, "spread_bps": 1, "microprice_bps": 0,
        "volume_increment": 10, "oi": 1000, "estimated_signed_volume": 0,
        "estimated_cvd": 0, "last_trade_age_seconds": 0})


def depth_frame(times):
    rows = []
    for stamp in times:
        rows.append({"timestamp": stamp, "date": "2026-08-20", "security_id": "1", "side_age_seconds": 0,
                     **book_features([{"price": 100, "quantity": 10}], [{"price": 101, "quantity": 10}])})
    return pd.DataFrame(rows)


def test_future_packet_changes_do_not_change_past_features():
    market = market_frame(); depth = depth_frame(market["timestamp"].iloc[::60] + pd.Timedelta(seconds=59))
    original = minute_features(market, depth, ResearchConfig())
    cut = pd.Timestamp("2026-08-20T03:55:00+00:00")
    changed = market.copy(); changed.loc[changed["timestamp"] >= cut, "mid"] = 999
    changed_depth = depth.copy(); changed_depth.loc[changed_depth["timestamp"] >= cut, "imbalance_200"] = 0.9
    altered = minute_features(changed, changed_depth, ResearchConfig())
    columns = [name for name in original if name not in {"target_bps", "label_at"}]
    pd.testing.assert_frame_equal(original.loc[original["decision_at"] <= cut, columns].reset_index(drop=True),
                                  altered.loc[altered["decision_at"] <= cut, columns].reset_index(drop=True))


def test_labels_do_not_cross_segments_and_exact_depth_is_excluded():
    market = market_frame(); market.loc[market.index >= 600, "segment"] = 1
    depth = depth_frame(pd.date_range("2026-08-20T03:46:00+00:00", periods=20, freq="min"))
    frame = minute_features(market, depth, ResearchConfig())
    assert frame.loc[frame["segment"] == 0, "target_bps"].isna().all()
    assert frame["imbalance_200"].isna().all()


def test_quote_lookup_never_uses_future_or_stale_quotes():
    frame = pd.DataFrame([{"timestamp": pd.Timestamp("2026-08-20T03:45:00Z"), "security_id": "1", "bid": 1},
                          {"timestamp": pd.Timestamp("2026-08-20T03:45:10Z"), "security_id": "1", "bid": 99}])
    book = QuoteBook(frame, 2)
    assert book.snapshot(pd.Timestamp("2026-08-20T03:45:01Z"))["1"]["bid"] == 1
    assert book.snapshot(pd.Timestamp("2026-08-20T03:45:03Z")) == {}
    assert book.snapshot(pd.Timestamp("2026-08-20T03:44:59Z")) == {}


def quotes(atm=24000):
    return {(kind, strike): {"bid": 100, "ask": 101, "security_id": f"{kind}-{strike}"}
            for kind in ("CE", "PE") for strike in range(atm - 100, atm + 101, 50)}


def test_strategy_payoffs_and_unlimited_risk():
    library = {s.name: s for s in strategy_library(quotes(), 24000, "2026-08-25")}
    assert len(library) == 11
    spread = library["bull_call_spread"]
    assert spread.terminal_pnl(np.array([23000, 25000]), 65).tolist() == [-65, 3185]
    assert spread.expiry_risk()["max_loss_before_costs"] == 65
    assert library["short_straddle"].expiry_risk()["unbounded_upper_loss"]
    assert not library["iron_condor"].expiry_risk()["unbounded_upper_loss"]
    assert library["no_trade"].terminal_pnl(np.array([0, 25000])).tolist() == [0, 0]


def test_mark_to_market_uses_correct_quote_sides():
    strategy = Strategy("spread", (Leg("CE", 24000, 1, 99, 100, "a", "2026-08-25"),
                                   Leg("CE", 24050, -1, 49, 50, "b", "2026-08-25")))
    exits = {"a": {"bid": 110, "ask": 111, "expiry": "2026-08-25", "strike": 24000, "option_type": "CE"},
             "b": {"bid": 54, "ask": 55, "expiry": "2026-08-25", "strike": 24050, "option_type": "CE"}}
    gross, transactions = mark_to_market(strategy, exits, ResearchConfig())
    assert gross == 260 and transactions == [(1, 100), (-1, 110), (-1, 49), (1, 55)]


def test_costs_include_sides_and_slippage():
    config = replace(ResearchConfig(), brokerage_per_order=0, option_exchange_rate=0, sebi_rate=0,
                     gst_rate=0, extra_slippage_per_leg=0, option_buy_stamp_rate=0)
    assert charge_estimate([(1, 100), (-1, 100)], config) == pytest.approx(9.75)
    assert charge_estimate([(1, 100), (-1, 100)], config, 0.5) == pytest.approx(74.75)
    with pytest.raises(ValueError): charge_estimate([(0, 100)], config)


def test_cost_configuration_rejects_nonfinite_and_negative_values():
    with pytest.raises(ValueError): ResearchConfig(extra_slippage_per_leg=-1)
    with pytest.raises(ValueError): ResearchConfig(option_quote_age_seconds=float("nan"))


def test_prepare_rejects_source_output_overlap(tmp_path):
    from nifty_lab.__main__ import prepare
    with pytest.raises(ValueError, match="overlap"):
        prepare([tmp_path], tmp_path / "derived", ResearchConfig(), False)


def test_unknown_future_label_remains_a_test_prediction():
    rows = []
    columns = {name for group in GROUPS.values() for name in group}
    for day in range(3, 6):
        for minute in range(10):
            at = pd.Timestamp(f"2026-08-{day:02}T04:{minute:02}:00Z")
            rows.append({**{name: float(minute) for name in columns}, "date": f"2026-08-{day:02}",
                         "decision_at": at, "label_at": at + pd.Timedelta(minutes=5),
                         "target_bps": float(minute) if day < 5 else np.nan, "feature_ready": True})
    predictions, summary = walk_forward(pd.DataFrame(rows), replace(ResearchConfig(), minimum_training_days=2, minimum_training_rows=10))
    assert len(predictions) == 10 and summary["scored_rows"] == 0


def test_option_identity_and_quote_validation(tmp_path):
    record = {"captured_at_utc": "2026-08-20T03:45:01Z", "security_id": "1", "option_type": "CE",
              "expiry_date": "2026-08-25", "strike_price": 24000, "best_bid": 1, "best_ask": 2}
    frame, audit = read_options(write_rows(tmp_path / "options.ndjson", [record, {**record, "best_ask": 0}]), "2026-08-20")
    assert len(frame) == 1 and audit["invalid_quote"] == 1


def test_walk_forward_training_uses_earlier_dates_only():
    rows = []
    columns = {name for group in GROUPS.values() for name in group}
    for day in range(3, 8):
        for minute in range(10):
            at = pd.Timestamp(f"2026-08-{day:02}T04:{minute:02}:00Z")
            rows.append({**{name: float(minute) for name in columns}, "date": f"2026-08-{day:02}",
                         "decision_at": at, "label_at": at + pd.Timedelta(minutes=5),
                         "target_bps": float(minute), "feature_ready": True})
    frame = pd.DataFrame(rows); config = replace(ResearchConfig(), minimum_training_days=2, minimum_training_rows=10)
    first, summary = walk_forward(frame, config)
    altered = frame.copy(); altered.loc[altered["date"] >= "2026-08-05", "target_bps"] = 999
    second, _ = walk_forward(altered, config)
    assert summary["folds"][0]["date"] == "2026-08-05"
    np.testing.assert_allclose(first.loc[first["date"] == "2026-08-05", "prediction_price"],
                               second.loc[second["date"] == "2026-08-05", "prediction_price"])


def test_unpriced_position_halts_remaining_day():
    at = pd.Timestamp("2026-08-20T04:00:00Z")
    options = pd.DataFrame([{"timestamp": at, "security_id": "1", "expiry": "2026-08-25",
                            "strike": 24000, "option_type": "CE", "bid": 99, "ask": 100}])
    predictions = pd.DataFrame([{"date": "2026-08-20", "decision_at": at, "close": 24000, "prediction_price": 3},
                                {"date": "2026-08-20", "decision_at": at + pd.Timedelta(minutes=6),
                                 "close": 24000, "prediction_price": 3}])
    ledger, counts = replay_policy(predictions, {"2026-08-20": QuoteBook(options, 2)}, ResearchConfig(), "price", "single")
    assert len(ledger) == 1 and counts["unpriced_exit"] == 1


def test_agent_evidence_excludes_future_outcomes_and_disables_execution():
    from nifty_lab.evidence import evidence_from_row
    at = pd.Timestamp("2026-08-20T04:00:00Z")
    columns = ["ret_1_bps", "ret_5_bps", "rv_5_bps", "range_5_bps", "spread_bps", "oi_change_bps",
               "imbalance_5", "imbalance_20", "imbalance_200", "imbalance_points_10", "imbalance_weighted"]
    row = {**{key: 0.0 for key in columns}, "decision_at": at, "date": "2026-08-20", "security_id": "1",
           "source_at": at - pd.Timedelta(seconds=1), "depth_at": at - pd.Timedelta(seconds=1),
           "close": 24000, "prediction_price": 2, "target_bps": 999, "label_at": at + pd.Timedelta(minutes=5)}
    frame = pd.DataFrame([{"timestamp": at, "security_id": "1", "bid": 99, "ask": 100,
                           "option_type": "CE", "strike": 24000, "expiry": "2026-08-25"}])
    bundle = evidence_from_row(row, QuoteBook(frame, 2), ResearchConfig())
    assert not bundle["execution_available"]
    assert "target_bps" not in json.dumps(bundle) and "label_at" not in json.dumps(bundle)
    assert "no_trade" in bundle["allowed_actions"]


def test_replay_blocks_entries_that_cannot_exit_before_market_close():
    at = pd.Timestamp("2026-08-20T09:57:00Z")
    predictions = pd.DataFrame([{"date": "2026-08-20", "decision_at": at, "close": 24000, "prediction_price": 3}])
    ledger, counts = replay_policy(predictions, {}, ResearchConfig(), "price", "single")
    assert not ledger and counts["blocked_by_session_close"] == 1
