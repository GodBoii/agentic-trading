from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PipelineConfig:
    backend_dir: Path = Path(__file__).resolve().parent.parent
    root_dir: Path = backend_dir.parent

    bse_list_path: Path = backend_dir / "BSE_LIST.json"
    security_master_path: Path = root_dir / "security_id_list.csv"
    stage1_latest_path: Path = backend_dir / "stage1_universe_latest.json"
    stage2_latest_path: Path = backend_dir / "stage2_momentum_latest.json"
    monitor_latest_path: Path = backend_dir / "monitor_liquidity_latest.json"
    regime_latest_path: Path = backend_dir / "regime_latest.json"
    ai_trading_state_path: Path = backend_dir / "ai_trading_state.json"
    stock_analyzer_latest_path: Path = backend_dir / "stock_analyzer_latest.json"
    risk_analyzer_latest_path: Path = backend_dir / "risk_analyzer_latest.json"
    executioner_latest_path: Path = backend_dir / "executioner_latest.json"
    stock_analyzer_artifacts_dir: Path = backend_dir / "stock_analyzer_artifacts"
    regime_source_catalog_path: Path = backend_dir / "pipeline" / "regime" / "market_sources.json"
    regime_inputs_dir: Path = backend_dir / "regime_inputs"
    regime_market_news_path: Path = backend_dir / "regime_inputs" / "market_news.json"
    tick_stats_latest_path: Path = backend_dir / "stage2_tick_stats_latest.json"
    tick_stats_history_latest_path: Path = backend_dir / "stage2_tick_stats_history_latest.json"
    dhan_rate_limit_state_path: Path = backend_dir / "dhan_rate_limit_state.json"

    stage1_min_price: float = 100.0
    stage1_max_price: float = 3000.0
    stage1_min_adv_cr: float = 10.0
    stage1_min_atr_percent: float = 1.5

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
    stage1_workers: int = 8
    stage2_workers: int = 8
    regime_workers: int = 8
    stage2_loop_interval_seconds: int = 600
    monitor_loop_interval_seconds: int = 600
    regime_loop_interval_seconds: int = 900
    stock_analyzer_loop_interval_seconds: int = 30
    stock_analyzer_report_refresh_seconds: int = 300
    stock_analyzer_top_n: int = 3
    risk_analyzer_loop_interval_seconds: int = 30
    risk_analyzer_report_refresh_seconds: int = 300
    executioner_loop_interval_seconds: int = 30
    executioner_report_refresh_seconds: int = 120
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
    market_timezone: str = "Asia/Calcutta"
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 30

    def stage1_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"stage1-{market_date}.json"

    def stage2_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"stage2-{market_date}.json"

    def monitor_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"monitor-{market_date}.json"

    def regime_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"regime-{market_date}.json"

    def stock_analyzer_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"stock-analyzer-{market_date}.json"

    def risk_analyzer_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"risk-analyzer-{market_date}.json"

    def executioner_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"executioner-{market_date}.json"

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
