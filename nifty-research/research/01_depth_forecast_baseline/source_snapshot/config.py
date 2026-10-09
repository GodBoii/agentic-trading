from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path


@dataclass(frozen=True)
class ResearchConfig:
    horizon_minutes: int = 5
    packet_gap_seconds: float = 10.0
    depth_side_age_seconds: float = 1.0
    depth_feature_age_seconds: float = 2.0
    depth_emit_seconds: float = 1.0
    option_quote_age_seconds: float = 2.0
    minimum_training_days: int = 5
    minimum_training_rows: int = 200
    ridge_alpha: float = 100.0
    lot_size: int = 65
    brokerage_per_order: float = 20.0
    option_sell_stt_rate: float = 0.0015
    # Combined NSE transaction and IPFT rate effective 1 March 2026.
    option_exchange_rate: float = 0.0003553
    sebi_rate: float = 0.000001
    option_buy_stamp_rate: float = 0.00003
    gst_rate: float = 0.18
    extra_slippage_per_leg: float = 0.10
    entry_threshold_bps: float = 2.0

    def __post_init__(self) -> None:
        if self.horizon_minutes < 1 or self.minimum_training_days < 1:
            raise ValueError("Horizon and training days must be positive")
        if self.minimum_training_rows < 1 or self.lot_size < 1:
            raise ValueError("Training rows and lot size must be positive")
        for field in ("packet_gap_seconds", "depth_side_age_seconds", "depth_feature_age_seconds",
                      "depth_emit_seconds", "option_quote_age_seconds", "ridge_alpha"):
            if not math.isfinite(getattr(self, field)) or getattr(self, field) <= 0:
                raise ValueError(f"{field} must be positive")
        for field in ("brokerage_per_order", "option_sell_stt_rate", "option_exchange_rate", "sebi_rate",
                      "option_buy_stamp_rate", "gst_rate", "extra_slippage_per_leg", "entry_threshold_bps"):
            if not math.isfinite(getattr(self, field)) or getattr(self, field) < 0:
                raise ValueError(f"{field} must be finite and non-negative")

    def to_dict(self) -> dict:
        return asdict(self)


def default_sources(workspace: Path) -> list[Path]:
    return [workspace / "python-backend/nifty_market_depth",
            workspace / "python-backend/results/nifty-50-market-depth"]
