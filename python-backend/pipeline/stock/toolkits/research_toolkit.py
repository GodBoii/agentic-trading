from __future__ import annotations

from datetime import datetime, timezone
import json

from agno.tools.websearch import WebSearchTools


class StockResearchToolkit(WebSearchTools):
    """Agno WebSearchTools configured for one assigned Indian stock."""

    def __init__(self, display_name: str, symbol: str = "", market_time=None) -> None:
        self.stock_identity = " ".join(
            part for part in (str(display_name or ""), str(symbol or "")) if part
        ).strip()
        self.market_time = market_time
        super().__init__(
            backend="auto",
            modifier=f"{self.stock_identity} India stock",
            fixed_max_results=3,
            timelimit="m",
            region="in-en",
        )

    def web_search(self, query: str, max_results: int = 3) -> str:
        """Search the web only when current company information may explain today's price action."""
        return super().web_search(query, max_results=max_results)

    def search_news(self, query: str, max_results: int = 3) -> str:
        """Get recent news only when a company event may explain today's price action."""
        scoped_query = f"{self.stock_identity} India stock {str(query or '').strip()}".strip()
        raw = super().search_news(scoped_query, max_results=max_results)
        try:
            results = json.loads(raw)
        except Exception:
            return raw
        if not isinstance(results, list):
            return raw
        today = (
            self.market_time.now().date()
            if self.market_time is not None
            else datetime.now(timezone.utc).date()
        )
        filtered = []
        for result in results:
            if not isinstance(result, dict):
                continue
            published = self._parse_result_date(result.get("date"))
            if published is not None and published > today:
                continue
            filtered.append(result)
        return json.dumps(filtered, indent=2, ensure_ascii=True)

    @staticmethod
    def _parse_result_date(value):
        if value in (None, ""):
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None
