from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class PipelineConfig:
    backend_dir: Path = Path(__file__).resolve().parent.parent
    root_dir: Path = backend_dir.parent

    bse_list_path: Path = backend_dir / "BSE_LIST.json"
    stage1_latest_path: Path = backend_dir / "stage1_universe_latest.json"
    stage2_latest_path: Path = backend_dir / "stage2_liquidity_latest.json"
    tick_stats_latest_path: Path = backend_dir / "stage2_tick_stats_latest.json"

    stage1_min_price: float = 100.0
    stage1_max_price: float = 3000.0
    stage1_min_adv_cr: float = 10.0
    stage1_min_atr_percent: float = 1.5

    stage2_max_spread_percent: float = 0.30
    stage2_min_ticks_per_hour: int = 500
    stage2_min_rvol: float = 1.0
    stage2_quote_batch_size: int = 1000

    historical_rate_limit_per_sec: int = 5
    stage1_workers: int = 20
    stage2_workers: int = 20
    stage2_loop_interval_seconds: int = 600
    tick_stats_save_interval_seconds: int = 30
    market_timezone: str = "Asia/Calcutta"
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 30

    def stage1_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"stage1-{market_date}.json"

    def stage2_daily_path(self, market_date: str) -> Path:
        return self.backend_dir / f"stage2-{market_date}.json"

    def tick_stats_daily_path(self, market_date: Optional[str] = None) -> Path:
        if market_date:
            return self.backend_dir / f"stage2-tick-stats-{market_date}.json"
        return self.tick_stats_latest_path
