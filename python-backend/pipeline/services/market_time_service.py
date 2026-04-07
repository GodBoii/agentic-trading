from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pipeline.config import PipelineConfig


class MarketTimeService:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.tz = self._resolve_timezone(config.market_timezone)

    @staticmethod
    def _resolve_timezone(timezone_name: str):
        aliases = [timezone_name]
        if timezone_name == "Asia/Calcutta":
            aliases.append("Asia/Kolkata")

        for alias in aliases:
            try:
                return ZoneInfo(alias)
            except ZoneInfoNotFoundError:
                continue

        # Docker/dev fallback: IST has no DST, so a fixed offset is safe here.
        return timezone(timedelta(hours=5, minutes=30), name="IST")

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def market_date_str(self) -> str:
        return self.now().date().isoformat()

    def is_market_hours(self) -> bool:
        current_time = self.now().time()
        market_open = dt_time(self.config.market_open_hour, self.config.market_open_minute)
        market_close = dt_time(self.config.market_close_hour, self.config.market_close_minute)
        return market_open <= current_time <= market_close

    def market_status_text(self) -> str:
        now = self.now()
        return f"{now.strftime('%Y-%m-%d %H:%M:%S')} {self.config.market_timezone}"
