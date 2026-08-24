from __future__ import annotations

from typing import Any, Dict


class StockDecisionContextBuilder:
    """Merge stock-agent inputs into one compact, non-duplicative snapshot."""

    _LIVE_CIRCUIT_KEYS = {
        "upper_circuit",
        "lower_circuit",
        "upper_circuit_limit",
        "lower_circuit_limit",
        "upper_circuit_buffer_percent",
        "lower_circuit_buffer_percent",
    }

    @classmethod
    def build(
        cls,
        *,
        selected_stock: Dict[str, Any],
        timing_context: Dict[str, Any],
        security_overview: Dict[str, Any],
        current_state: Dict[str, Any],
        technical_data: Dict[str, Any],
        account_overview: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Choose one canonical source for every fact sent to the LLM."""
        session = dict(timing_context.get("market_session") or {})
        quote = dict(current_state.get("quote") or {})
        quote_fetched_at = quote.pop("as_of_ist", None)

        tradability = dict(security_overview.get("tradability") or {})
        if quote.get("upper_circuit") is not None or quote.get("lower_circuit") is not None:
            for key in cls._LIVE_CIRCUIT_KEYS:
                tradability.pop(key, None)

        market_evidence = dict(security_overview.get("market_evidence") or {})

        technical = dict(technical_data.get("readings") or {})
        chart_close = cls._number(technical.pop("latest_price", None))
        chart_vwap = cls._number(technical.get("vwap"))
        technical.pop("price_vs_vwap", None)
        if chart_close is not None and chart_vwap not in (None, 0):
            technical["price_vs_vwap_percent"] = round(
                ((chart_close - chart_vwap) / chart_vwap) * 100,
                4,
            )

        account = dict(account_overview)
        account.pop("assigned_security_id", None)
        account.pop("intraday_margin_budget", None)
        account_errors = account.pop("errors", None)
        account.pop("status", None)

        component_errors = []
        for payload in (security_overview, technical_data):
            errors = payload.get("errors")
            if isinstance(errors, list):
                component_errors.extend(errors)
        if isinstance(account_errors, list):
            component_errors.extend(account_errors)
        current_errors = current_state.get("errors")
        if isinstance(current_errors, list):
            component_errors.extend(current_errors)

        market_state = {
            "source": current_state.get("source"),
            "quote": quote,
            "one_minute": current_state.get("one_minute"),
            "five_minute": current_state.get("five_minute"),
        }

        payload = {
            "timestamps_and_session": {
                "context_generated_at_ist": timing_context.get("current_market_time_ist"),
                "quote_fetched_at_ist": quote_fetched_at or current_state.get("as_of_ist"),
                "candle_data_as_of_ist": current_state.get("candle_data_as_of_ist"),
                "candle_data_age_seconds": current_state.get("candle_data_age_seconds"),
                "technical_data_as_of_ist": technical_data.get("data_as_of_ist"),
                "technical_data_age_seconds": technical_data.get("data_age_seconds"),
                "charts_built_at_ist": technical_data.get("charts_built_at_ist"),
                "regular_session": session.get("regular_session") or "09:15-15:30 IST",
                "market_open_now": session.get("is_open_now"),
                "minutes_to_close": session.get("minutes_to_close"),
            },
            "instrument": {
                "security_id": security_overview.get("security_id")
                or selected_stock.get("security_id"),
                "symbol": security_overview.get("symbol") or selected_stock.get("symbol"),
                "display_name": security_overview.get("display_name")
                or selected_stock.get("display_name"),
                "exchange_segment": security_overview.get("exchange_segment"),
                "tradability": tradability,
                "historical_liquidity_and_volatility": {
                    "average_daily_value_crore": security_overview.get(
                        "average_daily_value_crore"
                    ),
                    "average_volume_20_sessions": security_overview.get(
                        "average_volume_20_sessions"
                    ),
                    "historical_atr_percent": security_overview.get(
                        "historical_atr_percent"
                    ),
                },
            },
            "risk_budget": {
                "margin_allocation_rupees": selected_stock.get("trade_amount"),
                "trade_mode": selected_stock.get("trade_mode"),
                "amount_source": selected_stock.get("amount_source"),
                "requested_whole_share_quantity": selected_stock.get("requested_quantity"),
                "estimated_notional_rupees": selected_stock.get("estimated_notional"),
                "estimated_depth_slippage_percent": selected_stock.get(
                    "estimated_slippage_percent"
                ),
            },
            "market_evidence": market_evidence,
            "live_market": market_state,
            "technical": {
                "basis": technical_data.get("basis"),
                "candles_used": technical_data.get("candles_used"),
                "last_candle_start_ist": technical_data.get("last_candle_start_ist"),
                "last_candle_complete": technical_data.get("last_candle_complete"),
                "readings": technical,
            },
            "account": account,
            "evidence_availability": {
                "missing_fields": current_state.get("missing_fields"),
                "errors": component_errors,
            },
        }
        return cls._without_empty(payload)

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value)
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
