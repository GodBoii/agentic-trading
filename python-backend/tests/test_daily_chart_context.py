from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
import numpy as np
import pandas as pd
import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from pipeline.services.charting_service import CandlestickChartService
from pipeline.stock.decision_context import StockDecisionContextBuilder
from pipeline.stock.toolkits.technical_toolkit import StockTechnicalToolkit
from pipeline.runtime.run_stock_analyzer import MultiStockAnalyzerRunner
from pipeline.runtime.run_risk_analyzer import RiskAnalyzerRunner


def ohlcv(timestamps):
    count = len(timestamps)
    prices = 100 + np.arange(count) * 0.01
    return pd.DataFrame({
        "timestamp": timestamps, "open": prices, "high": prices + 0.2,
        "low": prices - 0.2, "close": prices + 0.1, "volume": np.full(count, 1000),
    })


def intraday():
    times = pd.date_range("2026-08-27 09:15", periods=375, freq="min", tz="Asia/Kolkata")
    times = times.append(pd.date_range("2026-08-28 09:15", periods=143, freq="min", tz="Asia/Kolkata"))
    return ohlcv(times)


def test_daily_history_excludes_current_future_dates_and_caps_actual_daily_bars():
    service = CandlestickChartService("Asia/Kolkata")
    frame = ohlcv(pd.date_range("2025-01-01", "2026-09-01", freq="B", tz="Asia/Kolkata"))
    result = service.prepare_daily_frame(frame, "2026-08-28")
    assert len(result) == 250
    assert result.index[-1].date().isoformat() == "2026-08-27"
    assert result.index.is_unique
    assert result["close"].iloc[-1] == frame.loc[frame.timestamp.dt.strftime("%Y-%m-%d") == "2026-08-27", "close"].iloc[0]


def test_short_daily_history_is_honest_and_invalid_history_fails():
    service = CandlestickChartService("Asia/Kolkata")
    frame = ohlcv(pd.date_range("2026-08-20", periods=3, tz="Asia/Kolkata"))
    assert len(service.prepare_daily_frame(frame, "2026-08-28")) == 3
    frame.loc[0, "high"] = 1
    with pytest.raises(ValueError, match="invalid OHLCV"):
        service.prepare_daily_frame(frame, "2026-08-28")
    with pytest.raises(ValueError, match="No completed"):
        service.prepare_daily_frame(frame, "2026-08-19")


def test_nine_real_images_no_signal_lines_and_snapshot_contains_daily_context():
    service = CandlestickChartService("Asia/Kolkata")
    daily = ohlcv(pd.date_range("2025-06-01", "2026-08-31", freq="B", tz="Asia/Kolkata"))
    with TemporaryDirectory() as directory, patch.object(Axes, "axvline", side_effect=AssertionError("Signal line drawn")):
        bundle = service.build_intraday_chart_set(
            intraday(), "Test Stock", "2026-08-28", Path(directory),
            signal_time_ist="2026-08-28T11:36:00+05:30", daily_frame=daily,
        )
        assert list(bundle["charts"]) == list(service.REQUIRED_AGENT_CHARTS)
        assert bundle["chart_count"] == 9
        assert all(Path(path).stat().st_size > 1000 for path in bundle["chart_paths_ordered"])
        assert bundle["charts"]["daily_1d"]["candles"] == 250
        # The saved chart ends at 11:37. Wall-clock date must not complete 11:35-11:40.
        assert bundle["charts"]["current_5m"]["last_candle_complete"] is False
        metadata = bundle["technical_metadata"]
        momentum = bundle["charts"]["momentum_volatility"]["metadata"]["latest"]["5"]
        assert metadata["atr"] == round(momentum["atr"], 2)
        assert metadata["rsi"] == round(momentum["rsi"], 1)
        technical = StockTechnicalToolkit(bundle).technical_data_payload()
        context = StockDecisionContextBuilder.build(
            selected_stock={}, timing_context={}, security_overview={}, current_state={},
            technical_data=technical, account_overview={},
        )
        readings = context["technical"]["readings"]
        assert len(readings["chart_manifest"]) == 9
        assert readings["chart_evidence"]["daily_1d"]["last_session"] == "2026-08-27"
        assert readings["chart_evidence"]["tpo_profile"]["shared_price_axis"] is True


def test_tpo_brackets_start_at_session_open():
    service = CandlestickChartService("Asia/Kolkata")
    frame = ohlcv(pd.date_range("2026-08-28 09:15", periods=60, freq="min", tz="Asia/Kolkata"))
    profile = service._build_tpo_profile(frame.set_index("timestamp"))
    assert profile["brackets"] == 2


def test_rsi_handles_monotonic_and_flat_price_history():
    service = CandlestickChartService("Asia/Kolkata")
    frame = ohlcv(pd.date_range("2026-08-28 09:15", periods=50, freq="min", tz="Asia/Kolkata"))
    assert service._compute_warm_indicators(frame)["rsi"].iloc[-1] == 100
    frame["close"] = 100
    assert service._compute_warm_indicators(frame)["rsi"].iloc[-1] == 50


def test_daily_fetch_uses_candidate_exchange_and_full_history_request():
    runner = MultiStockAnalyzerRunner.__new__(MultiStockAnalyzerRunner)
    frame = ohlcv(pd.date_range("2026-08-01", periods=10, tz="Asia/Kolkata"))
    runner.dhan = SimpleNamespace(
        fetch_daily_history=Mock(return_value={"status": "success", "data": {}}),
        daily_response_to_df=Mock(return_value=frame),
        is_auth_invalid=Mock(return_value=False),
    )
    packet = {"security_id": 123, "exchange_segment": "BSE_EQ", "instrument": "EQUITY"}
    assert runner._fetch_daily_chart_history(packet) is frame
    runner.dhan.fetch_daily_history.assert_called_once_with(
        123, days=400, exchange_segment="BSE_EQ", instrument_candidates=["EQUITY", "EQUITY"],
    )
    runner.dhan.fetch_daily_history.return_value = {"status": "failure"}
    with pytest.raises(RuntimeError, match="stock_daily_history_failed"):
        runner._fetch_daily_chart_history(packet)


def test_legacy_risk_receives_daily_after_intraday_and_accepts_old_bundles():
    runner = RiskAnalyzerRunner.__new__(RiskAnalyzerRunner)
    charts = {key: {"path": key + ".png"} for key in ("current_1m", "current_5m", "current_15m", "daily_1d")}
    report = {"candidate": {"chart_artifacts": {"charts": charts}}}
    assert runner._collect_chart_paths([report])[-1] == "daily_1d.png"
    del charts["daily_1d"]
    assert len(runner._collect_chart_paths([report])) == 3
