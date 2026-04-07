from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

from pipeline.config import PipelineConfig


class MarketTimeService:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.tz = ZoneInfo(config.market_timezone)

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
