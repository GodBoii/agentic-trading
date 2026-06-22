from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any, Dict, List, Optional

import requests

from pipeline.config import PipelineConfig


class AlphaVantageService:
    """Best-effort Alpha Vantage collector for regime context.

    The regime pipeline must remain operational without Alpha Vantage, so every
    fetch returns structured status instead of raising.
    """

    BASE_URL = "https://www.alphavantage.co/query"
    NEWS_TOPICS = (
        "financial_markets",
        "economy_macro",
        "economy_monetary",
        "economy_fiscal",
        "energy_transportation",
        "finance",
        "manufacturing",
        "technology",
    )
    GLOBAL_QUOTE_SYMBOLS = {
        "nikkei_225": "^N225",
        "hang_seng": "^HSI",
        "shanghai_composite": "000001.SS",
        "sp500_proxy": "SPY",
        "nasdaq_proxy": "QQQ",
        "gift_nifty": "GIFTNIFTY",
    }

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.api_key = os.getenv(config.alpha_vantage_api_key_env, "").strip()
        self.session = requests.Session()
        self.timeout_seconds = float(os.getenv("ALPHA_VANTAGE_TIMEOUT_SECONDS", "8"))
        self.request_gap_seconds = float(os.getenv("ALPHA_VANTAGE_REQUEST_GAP_SECONDS", "0.8"))
        self.max_quote_symbols = int(os.getenv("ALPHA_VANTAGE_MAX_GLOBAL_QUOTES", "4"))
        self._last_request_ts = 0.0

    def collect_context(self) -> Dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        if not self.api_key:
            return {
                "enabled": False,
                "generated_at_utc": generated_at,
                "source_status": {
                    "alpha_vantage": {
                        "ok": False,
                        "error": f"{self.config.alpha_vantage_api_key_env}_not_set",
                    }
                },
                "news_sentiment": {},
                "market_status": {},
                "global_quotes": {},
                "fx": {},
                "commodities": {},
            }

        return {
            "enabled": True,
            "generated_at_utc": generated_at,
            "source_status": {},
            "news_sentiment": self.fetch_news_sentiment(),
            "market_status": self.fetch_market_status(),
            "global_quotes": self.fetch_global_quotes(),
            "fx": {
                "usd_inr": self.fetch_currency_exchange_rate("USD", "INR"),
                "usd_jpy": self.fetch_currency_exchange_rate("USD", "JPY"),
                "usd_cny": self.fetch_currency_exchange_rate("USD", "CNY"),
            },
            "commodities": {
                "brent": self.fetch_commodity("BRENT"),
                "wti": self.fetch_commodity("WTI"),
                "gold": self.fetch_gold_silver_spot("GOLD"),
                "silver": self.fetch_gold_silver_spot("SILVER"),
            },
        }

    def fetch_news_sentiment(self) -> Dict[str, Any]:
        return self._request(
            {
                "function": "NEWS_SENTIMENT",
                "topics": ",".join(self.NEWS_TOPICS),
                "sort": "LATEST",
                "limit": str(max(1, int(self.config.regime_alpha_vantage_news_limit))),
            }
        )

    def fetch_market_status(self) -> Dict[str, Any]:
        return self._request({"function": "MARKET_STATUS"})

    def fetch_global_quotes(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for name, symbol in list(self.GLOBAL_QUOTE_SYMBOLS.items())[: max(0, self.max_quote_symbols)]:
            payload[name] = self._request({"function": "GLOBAL_QUOTE", "symbol": symbol})
        return payload

    def fetch_currency_exchange_rate(self, from_currency: str, to_currency: str) -> Dict[str, Any]:
        return self._request(
            {
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_currency,
                "to_currency": to_currency,
            }
        )

    def fetch_commodity(self, function: str) -> Dict[str, Any]:
        return self._request({"function": function, "interval": "daily"})

    def fetch_gold_silver_spot(self, symbol: str) -> Dict[str, Any]:
        return self._request({"function": "GOLD_SILVER_SPOT", "symbol": symbol})

    def compact_for_agent(self, context: Dict[str, Any]) -> Dict[str, Any]:
        news = context.get("news_sentiment") or {}
        feed = news.get("feed") if isinstance(news.get("feed"), list) else []
        compact_news = []
        for item in feed[: max(1, int(self.config.regime_alpha_vantage_news_limit))]:
            compact_news.append(
                {
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "time_published": item.get("time_published"),
                    "summary": item.get("summary"),
                    "overall_sentiment_score": item.get("overall_sentiment_score"),
                    "overall_sentiment_label": item.get("overall_sentiment_label"),
                    "topics": item.get("topics"),
                    "ticker_sentiment": item.get("ticker_sentiment"),
                    "url": item.get("url"),
                }
            )

        return {
            "enabled": context.get("enabled"),
            "generated_at_utc": context.get("generated_at_utc"),
            "news_sentiment": {
                "status": news.get("status"),
                "items": compact_news,
                "information": news.get("Information") or news.get("Note") or news.get("Error Message"),
            },
            "market_status": self._compact_status_payload(context.get("market_status") or {}),
            "global_quotes": self._compact_quotes(context.get("global_quotes") or {}),
            "fx": context.get("fx") or {},
            "commodities": context.get("commodities") or {},
            "source_quality": self._source_quality(context),
        }

    def _request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            return {"status": "unavailable", "error": f"{self.config.alpha_vantage_api_key_env}_not_set"}
        self._enforce_gap()
        request_params = dict(params)
        request_params["apikey"] = self.api_key
        try:
            response = self.session.get(self.BASE_URL, params=request_params, timeout=self.timeout_seconds)
            response.raise_for_status()
            body = response.json()
            if "Note" in body or "Information" in body:
                body.setdefault("status", "limited")
            elif "Error Message" in body:
                body.setdefault("status", "failure")
            else:
                body.setdefault("status", "success")
            body.setdefault("fetched_at_utc", datetime.now(timezone.utc).isoformat())
            return body
        except Exception as exc:
            return {
                "status": "failure",
                "error": f"{type(exc).__name__}: {exc}",
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            }

    def _enforce_gap(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.request_gap_seconds:
            time.sleep(self.request_gap_seconds - elapsed)
        self._last_request_ts = time.time()

    def _compact_status_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        markets = payload.get("markets") if isinstance(payload.get("markets"), list) else []
        return {
            "status": payload.get("status"),
            "fetched_at_utc": payload.get("fetched_at_utc"),
            "markets": [
                {
                    "market_type": item.get("market_type"),
                    "region": item.get("region"),
                    "primary_exchanges": item.get("primary_exchanges"),
                    "current_status": item.get("current_status"),
                    "local_open": item.get("local_open"),
                    "local_close": item.get("local_close"),
                }
                for item in markets
            ],
            "information": payload.get("Information") or payload.get("Note") or payload.get("Error Message"),
        }

    def _compact_quotes(self, quotes: Dict[str, Any]) -> Dict[str, Any]:
        compact: Dict[str, Any] = {}
        for name, payload in quotes.items():
            quote = payload.get("Global Quote") if isinstance(payload, dict) else None
            compact[name] = {
                "status": payload.get("status") if isinstance(payload, dict) else "failure",
                "symbol": (quote or {}).get("01. symbol"),
                "price": (quote or {}).get("05. price"),
                "change_percent": (quote or {}).get("10. change percent"),
                "volume": (quote or {}).get("06. volume"),
                "latest_trading_day": (quote or {}).get("07. latest trading day"),
                "information": (
                    payload.get("Information") or payload.get("Note") or payload.get("Error Message")
                    if isinstance(payload, dict)
                    else "invalid_payload"
                ),
            }
        return compact

    def _source_quality(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for key in ("news_sentiment", "market_status"):
            payload = context.get(key) or {}
            rows.append(
                {
                    "source": f"alpha_vantage.{key}",
                    "status": payload.get("status"),
                    "fetched_at_utc": payload.get("fetched_at_utc"),
                    "is_fallback": False,
                    "error": payload.get("error") or payload.get("Information") or payload.get("Note"),
                }
            )
        for name, payload in (context.get("global_quotes") or {}).items():
            rows.append(
                {
                    "source": f"alpha_vantage.global_quote.{name}",
                    "status": payload.get("status") if isinstance(payload, dict) else "failure",
                    "fetched_at_utc": payload.get("fetched_at_utc") if isinstance(payload, dict) else None,
                    "is_fallback": False,
                    "error": (
                        payload.get("error") or payload.get("Information") or payload.get("Note")
                        if isinstance(payload, dict)
                        else "invalid_payload"
                    ),
                }
            )
        return rows
