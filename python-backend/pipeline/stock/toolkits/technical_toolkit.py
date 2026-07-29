from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from agno.tools import Toolkit


class StockTechnicalToolkit(Toolkit):
    """Read-only technical context derived from the attached chart data."""

    def __init__(self, chart_bundle: Dict[str, Any], market_time: Any = None) -> None:
        self.chart_bundle = chart_bundle if isinstance(chart_bundle, dict) else {}
        self.market_time = market_time
        super().__init__(
            name="stock_technical_tools",
            tools=[self.get_technical_data],
        )

    def get_technical_data(self) -> str:
        """Get current technical readings, price levels, and detected zones.

        Only computed values are returned. Indicators that do not have enough
        candles are omitted instead of being represented as neutral values.
        """
        metadata = dict(self.chart_bundle.get("technical_metadata") or {})
        charts = self.chart_bundle.get("charts") or {}
        primary = charts.get("current_5m") if isinstance(charts, dict) else {}
        candle_count = int((primary or {}).get("candles") or 0)
        data_as_of = metadata.pop("data_as_of_ist", None) or self.chart_bundle.get("data_as_of_ist")
        last_candle_start = metadata.pop("last_candle_start_ist", None)
        last_candle_complete = metadata.pop("last_candle_complete", None)
        data_age_seconds = self._age_seconds(data_as_of)

        if candle_count < 15:
            metadata.pop("rsi", None)
        if candle_count < 20:
            metadata.pop("bb_upper", None)
            metadata.pop("bb_lower", None)

        payload = {
            "as_of_market_date": self.chart_bundle.get("market_date"),
            "data_as_of_ist": data_as_of,
            "data_age_seconds": round(data_age_seconds, 3) if data_age_seconds is not None else None,
            "charts_built_at_ist": self.chart_bundle.get("charts_built_at_ist"),
            "basis": "current 5-minute chart",
            "candles_used": candle_count,
            "last_candle_start_ist": last_candle_start,
            "last_candle_complete": last_candle_complete,
            "readings": metadata,
        }
        return json.dumps(self._without_empty(payload), ensure_ascii=True)

    def _age_seconds(self, value: Any) -> Any:
        if value in (None, ""):
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            now = self.market_time.now() if self.market_time is not None else datetime.now(timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=now.tzinfo or timezone.utc)
            return max(0.0, (now - parsed.astimezone(now.tzinfo or timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None

    @classmethod
    def _without_empty(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                cleaned = cls._without_empty(item)
                if cleaned not in (None, "", [], {}):
                    result[key] = cleaned
            return result
        if isinstance(value, list):
            return [cls._without_empty(item) for item in value if item not in (None, "", [], {})]
        return value
