from datetime import datetime, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch
from statistics import median
from concurrent.futures import Future

import pandas as pd
import pytest

from pipeline.config import PipelineConfig
from pipeline.services.storage_service import StorageService
from pipeline.stages.activity_ranker import RankingResult
from pipeline.stages.intra_finder import IntraFinder
from pipeline.stages.live_state import LiveStockState
from pipeline.stages.setups.base import arm_or_trigger


OPEN = datetime.fromisoformat("2026-09-08T09:15:00+05:30")


def observe(tracker, seconds):
    return arm_or_trigger(tracker, now=OPEN + timedelta(seconds=seconds), family="TEST",
                          direction="LONG", level=100, invalidation=99, reason="test",
                          diagnostics={"price": 101}, hold_seconds=5, expiry_seconds=30)


def finder(root):
    config = PipelineConfig(stage2_results_dir=root, stage2_latest_path=root / "latest.json")
    with patch("pipeline.stages.intra_finder.DhanService"):
        service = IntraFinder(config)
    service.market_time = SimpleNamespace(now=lambda: OPEN + timedelta(hours=1),
                                          market_date_str=lambda: OPEN.date().isoformat(), tz=OPEN.tzinfo)
    service._log = Mock()
    return service


def shutdown(service):
    service.io_executor.shutdown(wait=True)
    service.recovery_executor.shutdown(wait=True)


def test_hold_restarts_after_observation_gap_and_clock_reversal():
    tracker = {}
    assert observe(tracker, 0) is None
    assert observe(tracker, 3840) is None
    assert tracker["armed_at"] == (OPEN + timedelta(seconds=3840)).isoformat()
    assert observe(tracker, 3843) is None
    signal = observe(tracker, 3845)
    assert signal is not None
    assert (signal.triggered_at - signal.armed_at).total_seconds() == 5
    tracker = {}
    observe(tracker, 10)
    assert observe(tracker, 9) is None
    assert tracker["armed_at"] == (OPEN + timedelta(seconds=9)).isoformat()


def test_rank_exit_resets_pending_hold_without_waiting_for_another_packet():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        try:
            state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
            state.activity_rank = 1
            state.setup_state["TEST"] = {}
            observe(state.setup_state["TEST"], 0)
            service.last_ranking = RankingResult([state], [state], 1)

            def rank(_states, _now):
                state.activity_rank = 11
                return RankingResult([state], [state], 1)

            service.ranker = SimpleNamespace(rank=rank)
            service._rank_if_due(OPEN + timedelta(seconds=1))
            assert state.setup_state["TEST"]["phase"] == "IDLE"
        finally:
            shutdown(service)


@pytest.mark.parametrize("minutes,complete", [(range(15), True), (range(1, 15), False), ([0, 14], False)])
def test_opening_range_requires_the_whole_window(minutes, complete):
    state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    for minute in minutes:
        state._update_opening_range(100 + minute, OPEN + timedelta(minutes=minute))
    state._update_opening_range(120, OPEN + timedelta(minutes=15))
    assert state.opening_range_complete is complete


def test_restore_preserves_verified_range_but_never_pending_hold():
    state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    for minute in range(15):
        state._update_opening_range(100, OPEN + timedelta(minutes=minute))
    state._update_opening_range(100, OPEN + timedelta(minutes=15))
    state.setup_state["TEST"] = {}
    observe(state.setup_state["TEST"], 0)
    restored = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    restored.restore(state.checkpoint())
    assert restored.opening_range_complete
    assert restored.setup_state["TEST"]["phase"] == "IDLE"
    legacy = state.checkpoint()
    del legacy["opening_range_minute_mask"]
    restored.restore(legacy)
    assert not restored.opening_range_complete


def test_recovery_rejects_partial_window_and_accepts_all_fifteen_minutes():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        try:
            frame = pd.DataFrame({"timestamp": [OPEN + timedelta(minutes=i) for i in range(15)],
                                  "high": [102.0] * 15, "low": [99.0] * 15})
            service.historical_dhan = Mock()
            service.historical_dhan.fetch_intraday_history.return_value = {"status": "success"}
            service.historical_dhan.intraday_response_to_df.return_value = frame.iloc[1:]
            stock = {"exchange_segment": "NSE_EQ", "security_id": 1}
            assert service._fetch_opening_range(stock)[3] == "opening_range_incomplete"
            service.historical_dhan.intraday_response_to_df.return_value = frame
            assert service._fetch_opening_range(stock)[1:] == (102.0, 99.0, None)
        finally:
            shutdown(service)


def test_daily_count_comes_from_unique_dated_archive_and_survives_restart():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        service = finder(root)
        day = OPEN.date().isoformat()
        try:
            service.universe_version = "v1"
            service.event_state = {"events": {}}
            event = {"event_id": "a", "market_date": day, "created_at": OPEN.isoformat()}
            path = service.config.stage2_events_path(day)
            StorageService.append_json_line(path, event)
            StorageService.append_json_line(path, event)
            StorageService.append_json_line(path, {**event, "event_id": "old", "market_date": "2026-09-07"})
            with path.open("a") as handle:
                handle.write('{"interrupted":')
            service._load_event_state(day)
            assert service.events_formed == 1
            assert service.persisted_event_counts[day] == 1
            assert "a" in service.event_state["events"]
            service.packet_count = 20
            service._begin_session("2026-09-09")
            assert service.packet_count == 0
            assert service.events_formed == 0
        finally:
            shutdown(service)


def test_after_close_empty_process_does_not_replace_daily_report():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        try:
            service._mark_session_ended = Mock()
            service._finalize_and_release_session(OPEN.date().isoformat())
            service._mark_session_ended.assert_not_called()
        finally:
            shutdown(service)


def test_empty_process_shutdown_preserves_completed_checkpoint_and_status():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        day = OPEN.date().isoformat()
        checkpoint = service.config.stage2_runtime_state_path(day)
        status = service.config.stage2_daily_path(day)
        StorageService.save_snapshot(checkpoint, {"states": {"saved": True}})
        StorageService.save_snapshot(status, {"summary": {"events_formed": 750}})
        before = checkpoint.read_bytes(), status.read_bytes()
        service.close()
        assert (checkpoint.read_bytes(), status.read_bytes()) == before


@pytest.mark.parametrize("cutoff", [999, 1000, 1150, 1179, 1180])
def test_depth_window_matches_reference_at_boundaries_and_after_restore(cutoff):
    state = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    state.depth_samples.extend((1000 + i, (i % 11 - 5) / 5, .03) for i in range(180))
    values = [v for t, v, _ in state.depth_samples if t >= cutoff]
    assert state.depth_median(30, cutoff + 30) == (median(values) if values else None)
    saved = state.checkpoint()
    saved["depth_samples"] = list(reversed(saved["depth_samples"]))
    restored = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
    restored.restore(saved)
    values = [v for t, v, _ in restored.depth_samples if t >= cutoff]
    assert restored.depth_median(30, cutoff + 30) == (median(values) if values else None)


def test_opening_recovery_retries_are_bounded_and_skip_unobserved_stocks():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        try:
            service.recovery_executor.shutdown(wait=True)
            service.recovery_executor = Mock()
            service.recovery_executor.submit.side_effect = lambda *_args: Future()
            now = OPEN + timedelta(minutes=30)
            service.market_time.now = lambda: now
            for sid in range(12):
                state = LiveStockState("NSE_EQ", sid, str(sid), str(sid))
                service.states[state.key] = state
                service.stocks[state.key] = {"security_id": sid, "exchange_segment": "NSE_EQ"}
                if sid < 10:
                    service.full_packet_keys.add(state.key)
            service._start_opening_range_recovery()
            assert service.recovery_executor.submit.call_count == 8
            key = ("NSE_EQ", 0)
            for _ in range(3):
                response = Future()
                response.set_result((key, None, None, "opening_range_incomplete"))
                service._apply_opening_range_recovery(response)
            assert service.opening_recovery_errors["opening_range_incomplete"] == 3
            assert service.opening_recovery_retry_at[key] == now.timestamp() + 300
            service.recovery_futures.clear()
            service.opening_recovery_attempts[key] = 3
            now += timedelta(minutes=6)
            service._start_opening_range_recovery()
            assert key not in service.opening_recovery_requested
            assert ("NSE_EQ", 11) not in service.opening_recovery_requested
        finally:
            shutdown(service)


def test_midnight_finalization_uses_the_session_date():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        try:
            service.session_market_date = "2026-09-08"
            service.states = {("NSE_EQ", 1): object()}
            service._mark_session_ended = Mock()
            service._wait_for_pending_io = Mock(return_value=True)
            service._release_session_memory = Mock(return_value=1)
            service._finalize_and_release_session("2026-09-09")
            service._mark_session_ended.assert_called_once_with("2026-09-08")
        finally:
            shutdown(service)


def test_superseded_recovery_does_not_clear_current_pending_request():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        try:
            key = ("NSE_EQ", 1)
            service.universe_version = "new"
            service.opening_recovery_requested.add(key)
            response = Future()
            response.set_result((key, 100, 99, None))
            service.recovery_results.put((("old", OPEN.date().isoformat()), "opening_range", response))
            service._apply_recovery_results()
            assert key in service.opening_recovery_requested
        finally:
            shutdown(service)


def test_recovery_completion_refills_the_bounded_pool():
    with TemporaryDirectory() as temporary:
        service = finder(Path(temporary))
        try:
            key = ("NSE_EQ", 1)
            service.states[key] = LiveStockState(*key, "TEST", "INE1")
            service._start_opening_range_recovery = Mock()
            response = Future()
            response.set_result((key, 100, 99, None))
            service.recovery_results.put(((service.universe_version, OPEN.date().isoformat()), "opening_range", response))
            service._apply_recovery_results()
            assert service.states[key].opening_range_complete
            service._start_opening_range_recovery.assert_called_once_with()
        finally:
            shutdown(service)
