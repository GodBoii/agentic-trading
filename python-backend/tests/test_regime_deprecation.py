from pipeline.runtime.run_stock_agent import MultiStockAgentRunner
from pipeline.runtime.run_stock_analyzer import MultiStockAnalyzerRunner


def test_regime_gate_stays_disabled_for_legacy_requests() -> None:
    runner = MultiStockAnalyzerRunner.__new__(MultiStockAnalyzerRunner)

    assert runner._resolve_regime_gate(None, None) is False
    assert runner._resolve_regime_gate({"regime_analysis_enabled": True}, None) is False
    assert runner._resolve_regime_gate(None, True) is False


def test_stock_agent_strips_cached_regime_context() -> None:
    runner = MultiStockAgentRunner.__new__(MultiStockAgentRunner)
    packet = {
        "regime_analysis_enabled": True,
        "regime_report": "legacy report",
        "latest_regime_context": {"regime": {"market_regime": "trend_down"}},
        "monitor": {"passed": True},
        "source_snapshots": {
            "regime_analysis_enabled": True,
            "regime_generated_at_utc": "2026-08-12T07:34:17+00:00",
            "regime_generated_at_ist": "2026-08-12T13:04:17+05:30",
            "monitor_generated_at_utc": "2026-08-12T07:34:17+00:00",
        },
        "timing_context": {
            "source_snapshot_times": {
                "regime_generated_at_utc": "2026-08-12T07:34:17+00:00",
                "monitor_generated_at_utc": "2026-08-12T07:34:17+00:00",
            },
            "source_snapshot_ages_seconds": {"regime": 10.0, "monitor": 5.0},
        },
    }

    runner._strip_monitor_context(packet)

    assert packet["regime_analysis_enabled"] is False
    assert "regime_report" not in packet
    assert "latest_regime_context" not in packet
    assert packet["source_snapshots"]["regime_analysis_enabled"] is False
    assert "regime_generated_at_utc" not in packet["source_snapshots"]
    assert "regime_generated_at_utc" not in packet["timing_context"]["source_snapshot_times"]
    assert "regime" not in packet["timing_context"]["source_snapshot_ages_seconds"]
