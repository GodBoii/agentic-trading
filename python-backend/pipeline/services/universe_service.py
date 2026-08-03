from typing import Any, Dict, List

from pipeline.config import PipelineConfig
from pipeline.services.storage_service import StorageService


class UniverseService:
    def __init__(self, config: PipelineConfig):
        self.config = config

    def load_bse_common_equities(self) -> List[Dict[str, Any]]:
        """Legacy compatibility method. New code must load the venue-aware universe."""
        payload = StorageService.load_snapshot(self.config.bse_list_path)
        if not payload:
            raise FileNotFoundError(f"BSE list not found: {self.config.bse_list_path}")

        stocks = payload.get("stocks", [])
        return [
            stock for stock in stocks
            if stock.get("exchange") == "BSE"
            and stock.get("segment") == "E"
            and stock.get("instrument") == "EQUITY"
            and stock.get("instrument_type") == "ES"
            and stock.get("security_id") is not None
        ]

    def load_current_indian_equities(self) -> List[Dict[str, Any]]:
        payload = StorageService.load_snapshot(self.config.stage1_latest_path)
        if not payload or payload.get("stage") != "universe_scanner":
            raise FileNotFoundError(
                f"Venue-aware Universe Scanner output not found: {self.config.stage1_latest_path}"
            )
        return [
            stock
            for stock in payload.get("stocks", [])
            if stock.get("exchange_segment") in {"NSE_EQ", "BSE_EQ"}
            and stock.get("security_id") is not None
            and stock.get("isin")
        ]
