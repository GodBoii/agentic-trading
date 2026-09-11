from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.stages.intra_finder import IntraFinder
from pipeline.stages.live_state import LiveStockState


NOW = datetime.fromisoformat("2026-09-09T10:00:00+05:30")


def test_candidate_refresh_updates_path_without_recomputing_within_second():
    state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    state.latest_price = 101
    state.price_samples.extend([(NOW.timestamp() - 10, 100), (NOW.timestamp(), 101)])
    state.refresh_derived(NOW)
    assert state.trend_efficiency == 1
    next_second = NOW + timedelta(seconds=1)
    state.latest_price = 100
    state._sample(next_second.timestamp(), 100)
    state.refresh_candidate_features(next_second)
    assert state.trend_efficiency == 0
    assert state.derived_as_of == next_second.isoformat()
    state.refresh_derived = Mock()
    state.refresh_candidate_features(next_second + timedelta(milliseconds=100))
    state.refresh_derived.assert_not_called()


@pytest.mark.parametrize("selected", [False, True])
def test_process_refreshes_selected_stock_before_recording_and_evaluation(selected):
    finder = object.__new__(IntraFinder)
    state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    state.session_live_started = True
    state.is_hot = True
    state.activity_rank = 1 if selected else 20
    state.refresh_derived(NOW - timedelta(seconds=4))
    finder.states = {state.key: state}
    finder.stocks = {state.key: {}}
    finder.packet_count = 0
    finder.received_keys = set()
    finder.full_packet_keys = set()
    finder.candidates_seen = 0
    finder.config = SimpleNamespace(intra_finder_setup_rank_limit=10)
    for name in ("_apply_recovery_results", "_log_coverage_milestones", "_rank_if_due",
                 "_flush_if_due", "_save_status_if_due"):
        setattr(finder, name, Mock())
    snapshots = []
    finder._record_observation = lambda stock, packet, now: snapshots.append(stock.feature_snapshot(now))
    finder.setup_engine = SimpleNamespace(evaluate=Mock(return_value=[]))
    finder.process_packet({"security_id": 1, "exchange_segment": 1, "LTP": 100, "volume": 10},
                          received_at=NOW)
    assert snapshots[0]["derived_as_of"] == (NOW if selected else NOW - timedelta(seconds=4)).isoformat()
    assert finder.setup_engine.evaluate.call_count == int(selected)


def test_minute_volume_keeps_boundary_delta_and_ignores_initial_cumulative_total():
    state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    assert not state._update_bar(NOW, 100, 1000, 100)
    state._update_bar(NOW + timedelta(seconds=59), 100, 1100, 100)
    first = state._update_bar(NOW + timedelta(minutes=1), 100, 1120, 100)[0]
    state._update_bar(NOW + timedelta(minutes=1, seconds=59), 100, 1200, 100)
    second = state._update_bar(NOW + timedelta(minutes=2), 100, 1250, 100)[0]
    assert first.volume == 100
    assert second.volume == 100
    assert first.volume + second.volume + state.minute_builder.close_bar().volume == 250


def test_restore_invalidates_derived_clock_and_reset_volume_cannot_be_negative():
    state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    state.refresh_derived(NOW)
    state.restore(state.checkpoint())
    assert state.derived_as_of is None
    assert state.rank_as_of is None
    assert state._derived_second is None
    state._update_bar(NOW, 100, 1000, 100)
    state._update_bar(NOW + timedelta(minutes=1), 100, 10, 100)
    assert state.minute_builder.close_bar().volume == 0
