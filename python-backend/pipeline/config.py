from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PipelineConfig:
    backend_dir: Path = Path(__file__).resolve().parent.parent
    root_dir: Path = backend_dir.parent

    bse_list_path: Path = backend_dir / "BSE_LIST.json"
    stage1_latest_path: Path = backend_dir / "stage1_universe_latest.json"
    stage2_latest_path: Path = backend_dir / "stage2_momentum_latest.json"
    monitor_latest_path: Path = backend_dir / "monitor_liquidity_latest.json"
    tick_stats_latest_path: Path = backend_dir / "stage2_tick_stats_latest.json"
    tick_stats_history_latest_path: Path = backend_dir / "stage2_tick_stats_history_latest.json"

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
    stage2_quote_batch_size: int = 1000

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
    stage2_loop_interval_seconds: int = 600
    monitor_loop_interval_seconds: int = 600
    tick_stats_save_interval_seconds: int = 30
    tick_stats_history_save_interval_seconds: int = 600
    rate_limit_backoff_base_seconds: float = 0.5
    rate_limit_backoff_max_seconds: float = 8.0
    rate_limit_backoff_jitter_seconds: float = 0.35
    rate_limit_cooldown_trigger: int = 6
    rate_limit_cooldown_window_seconds: int = 15
    rate_limit_cooldown_seconds: float = 6.0
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

    def tick_stats_daily_path(self, market_date: Optional[str] = None) -> Path:
        if market_date:
            return self.backend_dir / f"stage2-tick-stats-{market_date}.json"
        return self.tick_stats_latest_path

    def tick_stats_history_daily_path(self, market_date: Optional[str] = None) -> Path:
        if market_date:
            return self.backend_dir / f"stage2-tick-history-{market_date}.json"
        return self.tick_stats_history_latest_path
