from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PipelineConfig:
    backend_dir: Path = Path(__file__).resolve().parent.parent
    root_dir: Path = backend_dir.parent
    results_dir: Path = backend_dir / "results"
    runtime_dir: Path = backend_dir / "runtime-data"
    runtime_secrets_dir: Path = runtime_dir / "secrets"
    dhan_credentials_path: Path = runtime_secrets_dir / "dhan-scanner-credentials.json"
    dhan_auth_health_path: Path = results_dir / "auth" / "sanitized-health" / "latest.json"

    bse_list_path: Path = backend_dir / "BSE_LIST.json"
    security_master_path: Path = root_dir / "security_id_list.csv"
    security_master_reference_dir: Path = results_dir / "reference" / "security-master"
    stage1_results_dir: Path = results_dir / "stage1"
    stage2_results_dir: Path = results_dir / "stage2"
    nifty_results_dir: Path = results_dir / "nifty-50-market-depth"
    regime_results_dir: Path = results_dir / "regime"
    agents_results_dir: Path = results_dir / "agents"
    stage1_latest_path: Path = results_dir / "stage1" / "latest.json"
    stage2_latest_path: Path = results_dir / "stage2" / "latest-state.json"
    monitor_latest_path: Path = backend_dir / "monitor_liquidity_latest.json"
    regime_latest_path: Path = results_dir / "regime" / "latest.json"
    market_calendar_cache_path: Path = results_dir / "reference" / "market-calendar" / "cache.json"
    market_holidays_path: Path = results_dir / "reference" / "market-calendar" / "holidays.json"
    session_supervisor_state_path: Path = backend_dir / "session_supervisor_state.json"
    session_supervisor_status_path: Path = backend_dir / "session_supervisor_status.json"
    ai_trading_state_path: Path = backend_dir / "ai_trading_state.json"
    order_placement_state_path: Path = backend_dir / "order_placement_state.json"
    ai_trading_request_path: Path = results_dir / "agents" / "request.json"
    ai_trading_run_status_path: Path = results_dir / "agents" / "run-status.json"
    ai_trading_sessions_dir: Path = results_dir / "agents" / "sessions"
    stock_analyzer_latest_path: Path = results_dir / "agents" / "stock-analyzer-latest.json"
    stock_agent_latest_path: Path = results_dir / "agents" / "stock-agent-latest.json"
    risk_analyzer_latest_path: Path = results_dir / "agents" / "risk-analyzer-latest.json"
    executioner_latest_path: Path = results_dir / "agents" / "executioner-latest.json"
    stock_analyzer_artifacts_dir: Path = results_dir / "agents" / "artifacts"
    regime_source_catalog_path: Path = backend_dir / "pipeline" / "regime" / "market_sources.json"
    regime_inputs_dir: Path = backend_dir / "regime_inputs"
    regime_market_news_path: Path = backend_dir / "regime_inputs" / "market_news.json"
    tick_stats_latest_path: Path = backend_dir / "stage2_tick_stats_latest.json"
    tick_stats_history_latest_path: Path = backend_dir / "stage2_tick_stats_history_latest.json"
    dhan_rate_limit_state_path: Path = backend_dir / "dhan_rate_limit_state.json"
    dhan_quote_rate_limit_state_path: Path = backend_dir / "dhan_quote_rate_limit_state.json"
    nifty_depth_latest_path: Path = results_dir / "nifty-50-market-depth" / "latest.json"
    nifty_depth_data_dir: Path = results_dir / "nifty-50-market-depth"
    nifty_depth_charts_latest_path: Path = results_dir / "nifty-50-market-depth" / "charts-latest.json"
    nifty_depth_charts_dir: Path = results_dir / "nifty-50-market-depth" / "charts"

    stage1_min_price: float = 100.0
    stage1_max_price: float = 3000.0
    stage1_min_adv_cr: float = 10.0
    stage1_min_atr_percent: float = 1.5
    stage1_min_valid_sessions: int = 21
    stage1_history_days: int = 60
    stage1_min_active_session_ratio: float = 0.90
    stage1_venue_switch_ratio: float = 1.20
    stage1_master_max_age_hours: int = 30

    stage2_history_days: int = 15
    stage2_min_rvol: float = 1.3
    stage2_min_price_vs_vwap_percent: float = 0.0
    stage2_min_volume_acceleration_ratio: float = 1.1
    stage2_opening_range_minutes: int = 15
    stage2_min_breakout_percent: float = 0.0
    stage2_volume_acceleration_window_minutes: int = 5
    stage2_volume_acceleration_denominator_floor_fraction: float = 0.35
    stage2_volume_acceleration_max_ratio: float = 8.0
    stage2_near_miss_limit: int = 10
    stage2_quote_batch_size: int = 1000
    stage2_live_quote_enrichment_enabled: bool = True
    stage2_good_spread_percent: float = 0.08
    stage2_acceptable_spread_percent: float = 0.20
    stage2_min_intraday_value_cr: float = 1.0
    intra_finder_trigger_score: float = 75.0
    intra_finder_max_spread_percent: float = 0.20
    intra_finder_min_rvol: float = 1.30
    intra_finder_min_volume_acceleration: float = 1.10
    intra_finder_data_stale_seconds: int = 30
    intra_finder_global_idle_seconds: int = 60
    intra_finder_preopen_idle_seconds: int = 180
    intra_finder_start_time: str = "09:10"
    intra_finder_confirmation_bucket_seconds: int = 5
    intra_finder_confirmation_buckets: int = 2
    intra_finder_min_confirmation_seconds: int = 8
    intra_finder_reconnect_warmup_seconds: int = 30
    intra_finder_subscription_verify_seconds: int = 30
    intra_finder_volume_warmup_seconds: int = 180
    intra_finder_volume_acceleration_cap: float = 8.0
    intra_finder_orb_break_buffer_percent: float = 0.05
    intra_finder_min_rvol_floor: float = 0.80
    intra_finder_vwap_extension_percent: float = 0.15
    intra_finder_vwap_pullback_tolerance_percent: float = 0.08
    intra_finder_vwap_continuation_percent: float = 0.08
    intra_finder_vwap_pullback_hold_seconds: int = 5
    intra_finder_vwap_max_sequence_seconds: int = 600
    intra_finder_setup_cooldown_seconds: int = 1200
    intra_finder_detector_mode: str = "indicator_events"
    intra_finder_indicator_aggregation_seconds: int = 60
    intra_finder_indicator_event_cooldown_seconds: int = 600
    intra_finder_stock_agent_cooldown_seconds: int = 1200
    intra_finder_indicator_max_evidence: int = 20
    intra_finder_indicator_volume_surge_ratio: float = 1.80
    intra_finder_indicator_max_event_lag_seconds: int = 60
    intra_finder_readiness_score_threshold: float = 75.0
    intra_finder_readiness_direction_margin: float = 10.0
    intra_finder_readiness_min_completed_bars: int = 45
    intra_finder_readiness_min_room_atr: float = 0.55
    intra_finder_readiness_max_last_trade_age_seconds: int = 90
    intra_finder_readiness_observation_seconds: int = 600
    intra_finder_readiness_reevaluation_seconds: int = 60
    intra_finder_readiness_min_confirmation_seconds: int = 300
    intra_finder_readiness_max_entry_drift_atr: float = 0.80
    intra_finder_max_slippage_percent: float = 0.20
    intra_finder_raw_retention_days: int = 7
    intra_finder_derived_retention_days: int = 90
    intra_finder_flush_seconds: int = 30
    intra_finder_status_seconds: int = 30
    intra_finder_shadow_mode: bool = True
    regime_history_days: int = 5
    regime_opening_range_minutes: int = 15
    regime_min_minutes_after_open: int = 30
    regime_sector_limit: int = 12

    monitor_max_spread_percent: float = 0.30
    monitor_min_ticks_last_10min: int = 50
    monitor_min_rvol: float = 1.0
    stage2_min_tick_stats_coverage_ratio: float = 0.90
    stage2_max_tick_stats_staleness_seconds: int = 120
    stage2_min_tick_collector_warmup_seconds: int = 120
    tick_collector_refresh_check_interval_seconds: int = 30

    historical_rate_limit_per_sec: int = 4
    quote_request_gap_seconds: float = 1.1
    quote_request_retries: int = 3
    historical_circuit_breaker_threshold: int = 12
    historical_circuit_breaker_cooldown_seconds: int = 300
    stage1_max_missing_ohlc_ratio: float = 0.20
    stage1_max_fetch_failure_ratio: float = 0.10
    stage2_max_fetch_failure_ratio: float = 0.10
    stage1_workers: int = 8
    stage2_workers: int = 8
    regime_workers: int = 8
    multimodal_model_id: str = "xiaomi/mimo-v2.5"
    regime_model_id: str = "xiaomi/mimo-v2.5-pro"
    alpha_vantage_api_key_env: str = "ALPHA_VANTAGE_API_KEY"
    regime_global_context_enabled: bool = True
    regime_alpha_vantage_news_limit: int = 25
    regime_source_max_staleness_seconds: int = 900
    stage2_loop_interval_seconds: int = 1800
    stage1_degraded_retry_interval_seconds: int = 900
    monitor_loop_interval_seconds: int = 600
    regime_loop_interval_seconds: int = 900
    regime_schedule_times: tuple[str, ...] = ("09:15", "09:45", "12:30")
    stage1_schedule_time: str = "08:40"
    stage2_first_run_time: str = "09:32"
    new_entry_cutoff_time: str = "15:00"
    protect_positions_time: str = "15:20"
    agent_min_run_interval_seconds: int = 1800
    agent_security_cooldown_seconds: int = 2700
    agent_periodic_refresh_seconds: int = 5400
    agent_stage2_score_delta_threshold: float = 25.0
    agent_stage2_score_delta_ratio: float = 0.20
    agent_trigger_top_n: int = 10
    stock_analyzer_loop_interval_seconds: int = 30
    stock_analyzer_report_refresh_seconds: int = 300
    stock_analyzer_top_n: int = 3
    stock_agent_manual_scan_limit: int = 30
    stock_agent_max_workers: int = 4
    risk_analyzer_loop_interval_seconds: int = 30
    risk_analyzer_report_refresh_seconds: int = 300
    executioner_loop_interval_seconds: int = 30
    executioner_report_refresh_seconds: int = 120
    executioner_fresh_snapshot_enabled: bool = True
    executioner_max_market_snapshot_staleness_seconds: int = 120
    tick_stats_save_interval_seconds: int = 30
    tick_stats_history_save_interval_seconds: int = 600
    rate_limit_backoff_base_seconds: float = 0.5
    rate_limit_backoff_max_seconds: float = 8.0
    rate_limit_backoff_jitter_seconds: float = 0.35
    rate_limit_cooldown_trigger: int = 6
    rate_limit_cooldown_window_seconds: int = 15
    rate_limit_cooldown_seconds: float = 6.0
    shared_rate_limit_window_seconds: float = 1.0
    shared_rate_limit_poll_seconds: float = 0.05
    market_data_gateway_host: str = "0.0.0.0"
    market_data_gateway_port: int = 8010
    market_data_gateway_timeout_seconds: float = 30.0
    ai_trading_gateway_host: str = "0.0.0.0"
    ai_trading_gateway_port: int = 8020
    market_timezone: str = "Asia/Calcutta"
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 30

    def stage1_daily_path(self, market_date: str) -> Path:
        return self.stage1_results_dir / market_date / "universe.json"

    def stage1_degraded_path(self, market_date: str) -> Path:
        return self.stage1_results_dir / market_date / "degraded-universe.json"

    def stage2_daily_path(self, market_date: str) -> Path:
        return self.stage2_results_dir / market_date / "latest-state.json"

    def stage2_degraded_path(self, market_date: str) -> Path:
        return self.stage2_results_dir / market_date / "degraded-state.json"

    def monitor_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"monitor-{market_date}.json"

    def regime_daily_path(self, market_date: str) -> Path:
        return self.regime_results_dir / market_date / "regime.json"

    def stage1_exclusions_path(self, market_date: str) -> Path:
        return self.stage1_results_dir / market_date / "exclusions.json"

    def stage1_run_report_path(self, market_date: str) -> Path:
        return self.stage1_results_dir / market_date / "run-report.json"

    def stage1_universe_parquet_path(self, market_date: str) -> Path:
        return self.stage1_results_dir / market_date / "universe.parquet"

    def stage1_venue_comparison_path(self, market_date: str) -> Path:
        return self.stage1_results_dir / market_date / "venue-comparison.parquet"

    def stage2_events_path(self, market_date: str) -> Path:
        return self.stage2_results_dir / market_date / "setup-events.jsonl"

    def stage2_event_state_path(self, market_date: str) -> Path:
        return self.stage2_results_dir / market_date / "event-state.json"

    def stage2_runtime_state_path(self, market_date: str) -> Path:
        return self.stage2_results_dir / market_date / "runtime-state.json"

    def stock_analyzer_daily_path(self, market_date: str) -> Path:
        return self.agents_results_dir / market_date / "stock-analyzer.json"

    def stock_agent_daily_path(self, market_date: str) -> Path:
        return self.agents_results_dir / market_date / "stock-agent.json"

    def risk_analyzer_daily_path(self, market_date: str) -> Path:
        return self.agents_results_dir / market_date / "risk-analyzer.json"

    def executioner_daily_path(self, market_date: str) -> Path:
        return self.agents_results_dir / market_date / "executioner.json"

    def tick_stats_daily_path(self, market_date: Optional[str] = None) -> Path:
        if market_date:
            return self.backend_dir / f"stage2-tick-stats-{market_date}.json"
        return self.tick_stats_latest_path

    def tick_stats_history_daily_path(self, market_date: Optional[str] = None) -> Path:
        if market_date:
            return self.backend_dir / f"stage2-tick-history-{market_date}.json"
        return self.tick_stats_history_latest_path

    def market_data_gateway_url(self) -> Optional[str]:
        explicit = os.getenv("MARKET_DATA_GATEWAY_URL")
        if explicit:
            return explicit.rstrip("/")
        return None
