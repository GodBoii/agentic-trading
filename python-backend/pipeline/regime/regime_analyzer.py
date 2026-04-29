from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dt_time, timedelta, timezone
import json
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.regime.regime_analyzer_agent import RegimeNewsAnalyzerAgent
from pipeline.services.dhan_service import DhanService
from pipeline.services.market_reference_service import MarketReferenceService
from pipeline.services.regime_news_service import RegimeNewsService
from pipeline.services.market_time_service import MarketTimeService
from pipeline.services.storage_service import StorageService


class MarketRegimeAnalyzer:
    """
    Market-context regime analyzer.
    This lane reads market-wide sources only: indices, sector indices, index futures,
    and optional externally provided market-summary JSON files for movers/news/attention.
    It does not consume Stage 1 or any stock-selection output.
    """

    EXTERNAL_INPUT_FILES = {
        "market_breadth": "market_breadth.json",
        "market_movers": "market_movers.json",
        "market_news": "market_news.json",
        "market_attention": "market_attention.json",
        "market_derivatives": "market_derivatives.json",
    }

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.dhan = DhanService(self.config)
        self.market_time = MarketTimeService(self.config)
        self.news_service = RegimeNewsService(self.config, self.market_time)
        self.news_agent = RegimeNewsAnalyzerAgent()
        self.references = MarketReferenceService(self.config)
        self.catalog = self._load_source_catalog()

    def _load_source_catalog(self) -> Dict[str, Any]:
        return json.loads(self.config.regime_source_catalog_path.read_text(encoding="utf-8"))

    def _print_group_preview(self, title: str, items: List[Dict[str, Any]], extra_keys: Optional[List[str]] = None) -> None:
        print(f"{title}: {len(items)}")
        if not items:
            return
        preview_parts: List[str] = []
        for item in items[:5]:
            label = item.get("name") or item.get("symbol") or "unknown"
            details: List[str] = []
            for key in extra_keys or []:
                value = item.get(key)
                if value is not None:
                    details.append(f"{key}={value}")
            preview_parts.append(f"{label}" + (f" ({', '.join(details)})" if details else ""))
        print(f"  Preview: {', '.join(preview_parts)}")

    def _print_failure_summary(self, failures: Dict[str, str]) -> None:
        print(f"Source failures: {len(failures)}")
        if not failures:
            print("  None")
            return
        for key in sorted(failures):
            print(f"  {key} -> {failures[key]}")

    def _print_external_input_summary(self, external_inputs: Dict[str, Any], external_missing: Dict[str, str]) -> None:
        print("External inputs:")
        provided = sorted(external_inputs.keys())
        missing = sorted(external_missing.keys())
        print(f"  Provided: {', '.join(provided) if provided else 'none'}")
        print(f"  Missing: {', '.join(missing) if missing else 'none'}")

    def _print_option_chain_summary(self, option_chains: List[Dict[str, Any]]) -> None:
        print(f"Option chain snapshots: {len(option_chains)}")
        if not option_chains:
            print("  None")
            return
        for chain in option_chains:
            print(
                "  "
                f"{chain['name']} | expiry={chain.get('selected_expiry')} "
                f"underlying={chain.get('underlying_price')} "
                f"strikes={chain.get('strike_count')} "
                f"atm={chain.get('atm_strike')} "
                f"pcr_oi={chain.get('put_call_oi_ratio')} "
                f"atm_iv_spread={chain.get('atm_iv_spread')}"
            )
            debug_meta = chain.get("debug_meta") or {}
            if debug_meta:
                print(f"    debug_meta={json.dumps(debug_meta, ensure_ascii=True)}")

    def _print_debug_payload_summary(self, debug_payloads: Dict[str, Any]) -> None:
        print(f"Debug payloads captured: {len(debug_payloads)}")
        if not debug_payloads:
            print("  None")
            return
        for key in sorted(debug_payloads):
            print(f"  {key}: {json.dumps(debug_payloads[key], ensure_ascii=True)[:1200]}")

    def _print_regime_diagnostics(self, regime: Dict[str, Any]) -> None:
        diagnostics = regime.get("diagnostics") or {}
        if not diagnostics:
            return
        print("Regime diagnostics:")
        for key in sorted(diagnostics):
            print(f"  {key}={diagnostics[key]}")

    def _session_state(self) -> Dict[str, Any]:
        now = self.market_time.now()
        market_open = now.replace(
            hour=self.config.market_open_hour,
            minute=self.config.market_open_minute,
            second=0,
            microsecond=0,
        )
        market_close = now.replace(
            hour=self.config.market_close_hour,
            minute=self.config.market_close_minute,
            second=0,
            microsecond=0,
        )
        minutes_since_open = max(0, int((now - market_open).total_seconds() // 60))
        minutes_to_close = max(0, int((market_close - now).total_seconds() // 60))

        if now < market_open:
            session = "pre_open"
        elif now <= market_close:
            session = "live_market"
        else:
            session = "post_market"

        return {
            "market_session": session,
            "minutes_since_open": minutes_since_open,
            "minutes_to_close": minutes_to_close,
            "is_market_hours": session == "live_market",
            "is_discovery_phase": session == "live_market"
            and minutes_since_open < self.config.regime_min_minutes_after_open,
        }

    def _resolve_index_source(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.references.find_index(source["symbol"], source["exchange"])

    def _resolve_future_source(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.references.find_front_month_future(source["exchange"], source["underlying_symbol"])

    def _resolve_option_chain_source(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self.references.find_index(source["symbol"], source["exchange"])

    def _today_market_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        local_ts = frame["timestamp"].dt.tz_localize("UTC").dt.tz_convert(self.market_time.tz)
        local_frame = frame.copy()
        local_frame["market_timestamp"] = local_ts
        local_frame["market_date"] = local_ts.dt.date
        today = self.market_time.now().date()
        return local_frame[local_frame["market_date"] == today].sort_values("market_timestamp")

    def _compute_intraday_vwap(self, today_frame: pd.DataFrame) -> Optional[float]:
        if today_frame.empty:
            return None
        volume = pd.to_numeric(today_frame["volume"], errors="coerce").fillna(0.0)
        total_volume = float(volume.sum())
        if math.isclose(total_volume, 0.0):
            return None
        typical_price = (
            pd.to_numeric(today_frame["high"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["low"], errors="coerce").fillna(0.0)
            + pd.to_numeric(today_frame["close"], errors="coerce").fillna(0.0)
        ) / 3.0
        vwap = (typical_price * volume).sum() / total_volume
        return float(vwap) if pd.notna(vwap) else None

    def _compute_opening_range_break(self, today_frame: pd.DataFrame, latest_price: float) -> Dict[str, Optional[float]]:
        if today_frame.empty or "market_timestamp" not in today_frame.columns:
            return {
                "opening_range_high": None,
                "opening_range_low": None,
                "opening_range_breakout_percent": None,
                "opening_range_breakdown_percent": None,
                "opening_range_complete": False,
            }

        open_dt = datetime.combine(
            self.market_time.now().date(),
            dt_time(self.config.market_open_hour, self.config.market_open_minute),
            tzinfo=self.market_time.tz,
        )
        range_end = open_dt + timedelta(minutes=self.config.regime_opening_range_minutes)
        opening_slice = today_frame[
            (today_frame["market_timestamp"] >= open_dt)
            & (today_frame["market_timestamp"] < range_end)
        ]
        expected_bars = self.config.regime_opening_range_minutes
        opening_range_complete = len(opening_slice) >= max(3, expected_bars // 2)
        if opening_slice.empty:
            return {
                "opening_range_high": None,
                "opening_range_low": None,
                "opening_range_breakout_percent": None,
                "opening_range_breakdown_percent": None,
                "opening_range_complete": False,
            }

        opening_high = float(pd.to_numeric(opening_slice["high"], errors="coerce").max())
        opening_low = float(pd.to_numeric(opening_slice["low"], errors="coerce").min())
        breakout = ((latest_price - opening_high) / opening_high) * 100.0 if opening_high > 0 else None
        breakdown = ((opening_low - latest_price) / opening_low) * 100.0 if opening_low > 0 else None
        return {
            "opening_range_high": round(opening_high, 4),
            "opening_range_low": round(opening_low, 4),
            "opening_range_breakout_percent": round(breakout, 4) if breakout is not None else None,
            "opening_range_breakdown_percent": round(breakdown, 4) if breakdown is not None else None,
            "opening_range_complete": opening_range_complete,
        }

    def _fetch_source_snapshot(
        self,
        source_key: str,
        source_meta: Dict[str, Any],
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str], Optional[Dict[str, Any]]]:
        exchange_segment = source_meta["exchange_segment"]
        instrument = source_meta["instrument"]
        security_id = int(source_meta["security_id"])
        try:
            resp = self.dhan.fetch_intraday_history(
                security_id,
                days=self.config.regime_history_days,
                interval=1,
                exchange_segment=exchange_segment,
                instrument_candidates=[instrument],
            )
        except Exception as exc:
            return source_key, None, f"intraday_history_exception::{type(exc).__name__}::{exc}", None
        if not resp or str(resp.get("status", "")).lower() != "success":
            remarks = str(resp.get("remarks", "") or resp.get("message", "") or "").strip()
            data_blob = str(resp.get("data", "")).strip()
            detail = "intraday_history_failed"
            if remarks:
                detail += f"::remarks={remarks[:160]}"
            elif data_blob:
                detail += f"::data={data_blob[:160]}"
            return source_key, None, detail, None

        frame = self.dhan.intraday_response_to_df(resp)
        if frame.empty:
            return source_key, None, "intraday_history_empty", None

        today_frame = self._today_market_frame(frame)
        if today_frame.empty:
            return source_key, None, "intraday_today_empty", None

        latest_price = float(pd.to_numeric(today_frame["close"], errors="coerce").iloc[-1])
        open_price = float(pd.to_numeric(today_frame["open"], errors="coerce").iloc[0])
        vwap = self._compute_intraday_vwap(today_frame)
        rvol = self.dhan.compute_time_of_day_rvol(frame)
        day_change_percent = ((latest_price - open_price) / open_price) * 100.0 if open_price > 0 else None
        price_vs_vwap_percent = ((latest_price - vwap) / vwap) * 100.0 if vwap and vwap > 0 else None
        opening_range = self._compute_opening_range_break(today_frame, latest_price)

        snapshot = {
            "name": source_meta["name"],
            "exchange": source_meta["exchange"],
            "exchange_segment": exchange_segment,
            "instrument": instrument,
            "security_id": security_id,
            "symbol": source_meta["symbol"],
            "display_name": source_meta["display_name"],
            "underlying_symbol": source_meta.get("underlying_symbol"),
            "expiry_date": source_meta.get("expiry_date"),
            "latest_price": round(latest_price, 4),
            "open_price": round(open_price, 4),
            "intraday_vwap": round(vwap, 4) if vwap is not None else None,
            "day_change_percent": round(day_change_percent, 4) if day_change_percent is not None else None,
            "price_vs_vwap_percent": round(price_vs_vwap_percent, 4) if price_vs_vwap_percent is not None else None,
            "time_of_day_rvol": round(rvol, 4) if rvol is not None else None,
            "latest_bar_time": today_frame["market_timestamp"].iloc[-1].isoformat(),
            "is_above_open": bool(day_change_percent is not None and day_change_percent > 0),
            "is_above_vwap": bool(price_vs_vwap_percent is not None and price_vs_vwap_percent > 0),
        }
        snapshot.update(opening_range)
        return source_key, snapshot, None, None

    def _load_external_market_inputs(self) -> Tuple[Dict[str, Any], Dict[str, str]]:
        payloads: Dict[str, Any] = {}
        missing: Dict[str, str] = {}
        self.config.regime_inputs_dir.mkdir(parents=True, exist_ok=True)

        for key, file_name in self.EXTERNAL_INPUT_FILES.items():
            path = self.config.regime_inputs_dir / file_name
            if not path.exists():
                missing[key] = "not_provided"
                continue
            try:
                payloads[key] = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                missing[key] = f"invalid_json::{type(exc).__name__}"
        return payloads, missing

    def _refresh_market_news_input(self) -> Optional[Dict[str, Any]]:
        self.config.regime_inputs_dir.mkdir(parents=True, exist_ok=True)
        try:
            collected = self.news_service.collect_market_news_payload()
            headlines = collected.get("headlines") or []
            agno_error: Optional[str] = None
            analysis_engine = "heuristic"

            if headlines:
                agent_analysis, agno_error = self.news_agent.analyze(headlines)
                if agent_analysis is not None and not agno_error:
                    analysis = agent_analysis
                    analysis_engine = "agno"
                else:
                    analysis = self.news_service.analyze_with_heuristics(headlines)
            else:
                analysis = self.news_service.analyze_with_heuristics([])

            payload = self.news_service.finalize_market_news_payload(
                collected=collected,
                analysis=analysis,
                analysis_engine=analysis_engine,
                agno_error=agno_error,
            )
            StorageService.save_snapshot(self.config.regime_market_news_path, payload)
            return payload
        except Exception as exc:
            print(f"Market news refresh failed: {type(exc).__name__}: {exc}")
            return None

    def _derive_operational_controls(
        self,
        session_state: Dict[str, Any],
        regime: Dict[str, Any],
        external_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        market_regime = str(regime.get("market_regime") or "data_unavailable")
        confidence = float(regime.get("confidence") or 0.0)
        news_input = external_inputs.get("market_news") or {}
        news_severity = float(news_input.get("event_severity_score") or 0.0)
        news_caution = str(news_input.get("trade_caution_level") or "medium").lower()

        control_map: Dict[str, Dict[str, Any]] = {
            "trend_up": {
                "trade_permission": "allowed",
                "preferred_style": "trend_following",
                "long_bias": 0.70,
                "short_bias": 0.30,
                "position_size_multiplier": 1.0,
                "max_concurrent_positions": 3,
            },
            "trend_down": {
                "trade_permission": "allowed",
                "preferred_style": "trend_following",
                "long_bias": 0.30,
                "short_bias": 0.70,
                "position_size_multiplier": 1.0,
                "max_concurrent_positions": 3,
            },
            "risk_on": {
                "trade_permission": "allowed",
                "preferred_style": "trend_following",
                "long_bias": 0.65,
                "short_bias": 0.35,
                "position_size_multiplier": 0.85,
                "max_concurrent_positions": 3,
            },
            "risk_off": {
                "trade_permission": "reduced",
                "preferred_style": "defensive_selective",
                "long_bias": 0.35,
                "short_bias": 0.65,
                "position_size_multiplier": 0.55,
                "max_concurrent_positions": 2,
            },
            "mean_reversion": {
                "trade_permission": "reduced",
                "preferred_style": "mean_reversion",
                "long_bias": 0.50,
                "short_bias": 0.50,
                "position_size_multiplier": 0.70,
                "max_concurrent_positions": 2,
            },
            "choppy": {
                "trade_permission": "reduced",
                "preferred_style": "observer_only",
                "long_bias": 0.50,
                "short_bias": 0.50,
                "position_size_multiplier": 0.35,
                "max_concurrent_positions": 1,
            },
            "event_driven": {
                "trade_permission": "reduced",
                "preferred_style": "observer_only",
                "long_bias": 0.50,
                "short_bias": 0.50,
                "position_size_multiplier": 0.25,
                "max_concurrent_positions": 1,
            },
            "open_discovery": {
                "trade_permission": "blocked",
                "preferred_style": "observer_only",
                "long_bias": 0.50,
                "short_bias": 0.50,
                "position_size_multiplier": 0.0,
                "max_concurrent_positions": 0,
            },
            "pre_open": {
                "trade_permission": "blocked",
                "preferred_style": "observer_only",
                "long_bias": 0.50,
                "short_bias": 0.50,
                "position_size_multiplier": 0.0,
                "max_concurrent_positions": 0,
            },
            "post_market": {
                "trade_permission": "blocked",
                "preferred_style": "observer_only",
                "long_bias": 0.50,
                "short_bias": 0.50,
                "position_size_multiplier": 0.0,
                "max_concurrent_positions": 0,
            },
            "data_unavailable": {
                "trade_permission": "blocked",
                "preferred_style": "observer_only",
                "long_bias": 0.50,
                "short_bias": 0.50,
                "position_size_multiplier": 0.0,
                "max_concurrent_positions": 0,
            },
        }
        controls = dict(control_map.get(market_regime, control_map["data_unavailable"]))
        notes: List[str] = [f"base_policy={market_regime}"]

        if confidence < 55.0 and controls["trade_permission"] != "blocked":
            controls["trade_permission"] = "reduced"
            controls["position_size_multiplier"] = round(
                min(float(controls["position_size_multiplier"]), 0.5),
                2,
            )
            controls["max_concurrent_positions"] = min(int(controls["max_concurrent_positions"]), 2)
            notes.append("regime_confidence_low")

        if (news_severity >= 0.75 or news_caution == "high") and controls["trade_permission"] != "blocked":
            controls["trade_permission"] = "reduced"
            controls["preferred_style"] = "observer_only"
            controls["position_size_multiplier"] = 0.25
            controls["max_concurrent_positions"] = min(int(controls["max_concurrent_positions"]), 1)
            notes.append("news_risk_escalation")
        elif (news_severity >= 0.45 or news_caution == "medium") and controls["trade_permission"] == "allowed":
            controls["trade_permission"] = "reduced"
            controls["position_size_multiplier"] = round(
                min(float(controls["position_size_multiplier"]), 0.6),
                2,
            )
            controls["max_concurrent_positions"] = min(int(controls["max_concurrent_positions"]), 2)
            notes.append("news_caution_moderate")

        if session_state.get("is_discovery_phase", False):
            controls["trade_permission"] = "blocked"
            controls["preferred_style"] = "observer_only"
            controls["position_size_multiplier"] = 0.0
            controls["max_concurrent_positions"] = 0
            notes.append("opening_discovery_gate")

        controls["notes"] = notes
        return controls

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            normalized = str(value).replace(",", "").strip()
            if not normalized:
                return None
            return float(normalized)
        except Exception:
            return None

    def _coerce_int(self, value: Any) -> Optional[int]:
        numeric = self._coerce_float(value)
        if numeric is None:
            return None
        try:
            return int(round(numeric))
        except Exception:
            return None

    def _parse_iso_date(self, value: Any) -> Optional[date]:
        if value in (None, ""):
            return None
        try:
            return date.fromisoformat(str(value).strip())
        except Exception:
            return None

    def _extract_expiry_list(self, response: Dict[str, Any]) -> List[str]:
        data = response.get("data")
        candidates: List[Any] = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            for key in ("expiryList", "expiries", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    candidates = value
                    break

        expiries: List[str] = []
        for item in candidates:
            if isinstance(item, dict):
                raw = item.get("expiry") or item.get("date") or item.get("value")
            else:
                raw = item
            parsed = self._parse_iso_date(raw)
            if parsed:
                expiries.append(parsed.isoformat())
        return sorted(set(expiries))

    def _extract_option_leg(self, payload: Any, option_type: str) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None

        greeks = payload.get("greeks") if isinstance(payload.get("greeks"), dict) else {}
        leg = {
            "option_type": option_type,
            "last_price": self._coerce_float(
                payload.get("last_price")
                or payload.get("ltp")
                or payload.get("lastTradedPrice")
                or payload.get("last_price_traded")
                or payload.get("price")
            ),
            "volume": self._coerce_int(payload.get("volume") or payload.get("tradedVolume")),
            "open_interest": self._coerce_int(
                payload.get("open_interest")
                or payload.get("oi")
                or payload.get("openInterest")
            ),
            "change_in_open_interest": self._coerce_int(
                payload.get("change_in_open_interest")
                or payload.get("changeInOpenInterest")
                or payload.get("oi_change")
                or payload.get("changeOi")
            ),
            "implied_volatility": self._coerce_float(
                payload.get("implied_volatility")
                or payload.get("iv")
                or payload.get("impliedVolatility")
            ),
            "delta": self._coerce_float(payload.get("delta") or greeks.get("delta")),
            "gamma": self._coerce_float(payload.get("gamma") or greeks.get("gamma")),
            "theta": self._coerce_float(payload.get("theta") or greeks.get("theta")),
            "vega": self._coerce_float(payload.get("vega") or greeks.get("vega")),
            "bid_price": self._coerce_float(
                payload.get("bid_price")
                or payload.get("top_bid_price")
                or payload.get("bestBidPrice")
                or payload.get("bidPrice")
            ),
            "ask_price": self._coerce_float(
                payload.get("ask_price")
                or payload.get("top_ask_price")
                or payload.get("bestAskPrice")
                or payload.get("askPrice")
            ),
            "bid_quantity": self._coerce_int(
                payload.get("bid_quantity")
                or payload.get("top_bid_quantity")
                or payload.get("bestBidQty")
                or payload.get("bidQty")
            ),
            "ask_quantity": self._coerce_int(
                payload.get("ask_quantity")
                or payload.get("top_ask_quantity")
                or payload.get("bestAskQty")
                or payload.get("askQty")
            ),
            "security_id": self._coerce_int(payload.get("security_id")),
            "average_price": self._coerce_float(payload.get("average_price")),
            "previous_open_interest": self._coerce_int(
                payload.get("previous_oi") or payload.get("previousOpenInterest")
            ),
            "previous_volume": self._coerce_int(payload.get("previous_volume")),
        }
        if all(value is None or value == option_type for value in leg.values()):
            return None
        return leg

    def _flatten_option_chain_rows(
        self,
        payload: Any,
        rows: Optional[List[Dict[str, Any]]] = None,
        parent_strike: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        if rows is None:
            rows = []
        if isinstance(payload, list):
            for item in payload:
                self._flatten_option_chain_rows(item, rows, parent_strike)
            return rows

        if not isinstance(payload, dict):
            return rows

        nested_data = payload.get("data")
        if isinstance(nested_data, (dict, list)):
            nested_keys = set(str(key) for key in payload.keys())
            if nested_keys.issubset({"data", "status", "remarks", "message"}):
                return self._flatten_option_chain_rows(nested_data, rows, parent_strike)

        if "oc" in payload and isinstance(payload.get("oc"), dict):
            return self._flatten_option_chain_rows(payload.get("oc"), rows, parent_strike)
        if "optionChain" in payload and isinstance(payload.get("optionChain"), dict):
            return self._flatten_option_chain_rows(payload.get("optionChain"), rows, parent_strike)
        if "records" in payload and isinstance(payload.get("records"), (dict, list)):
            return self._flatten_option_chain_rows(payload.get("records"), rows, parent_strike)

        strike = self._coerce_float(
            payload.get("strike_price")
            or payload.get("strikePrice")
            or payload.get("strike")
            or parent_strike
        )
        call_payload = (
            payload.get("call")
            or payload.get("CALL")
            or payload.get("ce")
            or payload.get("CE")
            or payload.get("callData")
        )
        put_payload = (
            payload.get("put")
            or payload.get("PUT")
            or payload.get("pe")
            or payload.get("PE")
            or payload.get("putData")
        )
        if strike is not None and (isinstance(call_payload, dict) or isinstance(put_payload, dict)):
            rows.append(
                {
                    "strike_price": strike,
                    "call": self._extract_option_leg(call_payload, "CALL"),
                    "put": self._extract_option_leg(put_payload, "PUT"),
                }
            )
            return rows

        for key, value in payload.items():
            inferred_strike = strike
            if inferred_strike is None:
                inferred_strike = self._coerce_float(key)
            self._flatten_option_chain_rows(value, rows, inferred_strike)
        return rows

    def _pick_nearest_expiry(self, expiries: List[str]) -> Optional[str]:
        if not expiries:
            return None
        today = self.market_time.now().date()
        dated = [(self._parse_iso_date(item), item) for item in expiries]
        valid = [(parsed, raw) for parsed, raw in dated if parsed is not None and parsed >= today]
        if not valid:
            return expiries[0]
        valid.sort(key=lambda item: item[0])
        return valid[0][1]

    def _option_chain_underlying_price(self, response: Dict[str, Any]) -> Optional[float]:
        data = response.get("data")
        if isinstance(data, dict):
            nested_data = data.get("data")
            if isinstance(nested_data, dict):
                data = nested_data
            for key in (
                "underlyingPrice",
                "underlying_price",
                "underlyingValue",
                "spotPrice",
                "last_price",
            ):
                numeric = self._coerce_float(data.get(key))
                if numeric is not None:
                    return numeric
        return None

    def _option_chain_debug_meta(self, response: Dict[str, Any]) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "response_status": response.get("status"),
        }
        data = response.get("data")
        if isinstance(data, dict):
            meta["data_keys"] = sorted(str(key) for key in data.keys())
            nested_data = data.get("data")
            if isinstance(nested_data, dict):
                meta["nested_data_keys"] = sorted(str(key) for key in nested_data.keys())
            oc = data.get("oc")
            if not isinstance(oc, dict) and isinstance(nested_data, dict):
                oc = nested_data.get("oc")
            if isinstance(oc, dict):
                strike_keys = list(oc.keys())
                meta["oc_strike_count"] = len(strike_keys)
                meta["oc_sample_keys"] = strike_keys[:5]
                if strike_keys:
                    first_value = oc.get(strike_keys[0])
                    if isinstance(first_value, dict):
                        meta["sample_strike_keys"] = sorted(str(key) for key in first_value.keys())
                        ce_payload = (
                            first_value.get("ce")
                            or first_value.get("CE")
                            or first_value.get("call")
                            or first_value.get("CALL")
                        )
                        pe_payload = (
                            first_value.get("pe")
                            or first_value.get("PE")
                            or first_value.get("put")
                            or first_value.get("PUT")
                        )
                        if isinstance(ce_payload, dict):
                            meta["sample_ce_keys"] = sorted(str(key) for key in ce_payload.keys())[:20]
                        if isinstance(pe_payload, dict):
                            meta["sample_pe_keys"] = sorted(str(key) for key in pe_payload.keys())[:20]
        return meta

    def _option_chain_debug_payload(self, response: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "debug_meta": self._option_chain_debug_meta(response),
        }
        data = response.get("data")
        nested_data = data.get("data") if isinstance(data, dict) else None
        oc = None
        if isinstance(data, dict) and isinstance(data.get("oc"), dict):
            oc = data.get("oc")
        elif isinstance(nested_data, dict) and isinstance(nested_data.get("oc"), dict):
            oc = nested_data.get("oc")

        if isinstance(oc, dict) and oc:
            first_key = next(iter(oc.keys()))
            first_value = oc.get(first_key)
            payload["sample_strike_key"] = first_key
            if isinstance(first_value, dict):
                sample_payload: Dict[str, Any] = {}
                for key in list(first_value.keys())[:12]:
                    value = first_value.get(key)
                    if isinstance(value, dict):
                        sample_payload[key] = {sub_key: value.get(sub_key) for sub_key in list(value.keys())[:20]}
                    else:
                        sample_payload[key] = value
                payload["sample_strike_payload"] = sample_payload
        return payload

    def _fetch_option_chain_snapshot(
        self,
        source_key: str,
        source_meta: Dict[str, Any],
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str], Optional[Dict[str, Any]]]:
        expiry_response = self.dhan.fetch_option_chain_expiry_list(
            under_security_id=int(source_meta["security_id"]),
            under_exchange_segment=str(source_meta["exchange_segment"]),
        )
        if str(expiry_response.get("status", "")).lower() != "success":
            return source_key, None, "option_expiry_list_failed", {"expiry_response": expiry_response}

        expiries = self._extract_expiry_list(expiry_response)
        selected_expiry = self._pick_nearest_expiry(expiries)
        if not selected_expiry:
            return source_key, None, "option_expiry_unavailable", {"expiry_response": expiry_response}

        chain_response = self.dhan.fetch_option_chain(
            under_security_id=int(source_meta["security_id"]),
            under_exchange_segment=str(source_meta["exchange_segment"]),
            expiry=selected_expiry,
        )
        if str(chain_response.get("status", "")).lower() != "success":
            return source_key, None, "option_chain_failed", self._option_chain_debug_payload(chain_response)

        rows = self._flatten_option_chain_rows(chain_response.get("data"))
        if not rows:
            debug_meta = self._option_chain_debug_meta(chain_response)
            failure_bits = ["option_chain_empty"]
            if debug_meta.get("data_keys"):
                failure_bits.append(f"keys={','.join(debug_meta['data_keys'])}")
            if debug_meta.get("nested_data_keys"):
                failure_bits.append(f"nested_keys={','.join(debug_meta['nested_data_keys'])}")
            if debug_meta.get("oc_strike_count") is not None:
                failure_bits.append(f"oc_strikes={debug_meta['oc_strike_count']}")
            return source_key, None, "::".join(failure_bits), self._option_chain_debug_payload(chain_response)

        rows = [row for row in rows if row.get("strike_price") is not None]
        rows.sort(key=lambda row: float(row["strike_price"]))
        underlying_price = self._option_chain_underlying_price(chain_response)
        if underlying_price is None:
            directional_spot = next(
                (
                    item
                    for item in (
                        self.catalog.get("primary_indices", [])
                        + self.catalog.get("sector_indices", [])
                    )
                    if self._normalized_symbol(item.get("symbol"))
                    == self._normalized_symbol(source_meta.get("symbol"))
                ),
                None,
            )
            if directional_spot:
                resolved_spot = self._resolve_index_source(directional_spot)
                if resolved_spot:
                    resp = self.dhan.fetch_intraday_history(
                        int(resolved_spot["security_id"]),
                        days=self.config.regime_history_days,
                        interval=1,
                        exchange_segment="IDX_I",
                        instrument_candidates=["INDEX"],
                    )
                    frame = self.dhan.intraday_response_to_df(resp) if resp else pd.DataFrame()
                    today_frame = self._today_market_frame(frame) if not frame.empty else pd.DataFrame()
                    if not today_frame.empty:
                        underlying_price = self._coerce_float(today_frame["close"].iloc[-1])

        atm_row = None
        if underlying_price is not None and rows:
            atm_row = min(
                rows,
                key=lambda row: abs(float(row["strike_price"]) - float(underlying_price)),
            )

        total_call_oi = sum((row.get("call") or {}).get("open_interest") or 0 for row in rows)
        total_put_oi = sum((row.get("put") or {}).get("open_interest") or 0 for row in rows)
        total_call_volume = sum((row.get("call") or {}).get("volume") or 0 for row in rows)
        total_put_volume = sum((row.get("put") or {}).get("volume") or 0 for row in rows)
        max_call_row = max(rows, key=lambda row: (row.get("call") or {}).get("open_interest") or 0)
        max_put_row = max(rows, key=lambda row: (row.get("put") or {}).get("open_interest") or 0)
        atm_call = (atm_row or {}).get("call") or {}
        atm_put = (atm_row or {}).get("put") or {}
        atm_call_iv = self._coerce_float(atm_call.get("implied_volatility"))
        atm_put_iv = self._coerce_float(atm_put.get("implied_volatility"))
        atm_iv_spread = (
            round(atm_put_iv - atm_call_iv, 4)
            if atm_call_iv is not None and atm_put_iv is not None
            else None
        )
        put_call_oi_ratio = round(total_put_oi / total_call_oi, 4) if total_call_oi > 0 else None
        put_call_volume_ratio = round(total_put_volume / total_call_volume, 4) if total_call_volume > 0 else None

        snapshot = {
            "name": source_meta["name"],
            "exchange": source_meta["exchange"],
            "exchange_segment": source_meta["exchange_segment"],
            "instrument": "OPTIDX",
            "security_id": int(source_meta["security_id"]),
            "symbol": source_meta["symbol"],
            "display_name": source_meta["display_name"],
            "selected_expiry": selected_expiry,
            "available_expiries": expiries[:6],
            "underlying_price": round(underlying_price, 4) if underlying_price is not None else None,
            "strike_count": len(rows),
            "atm_strike": round(float(atm_row["strike_price"]), 4) if atm_row else None,
            "put_call_oi_ratio": put_call_oi_ratio,
            "put_call_volume_ratio": put_call_volume_ratio,
            "total_call_open_interest": int(total_call_oi),
            "total_put_open_interest": int(total_put_oi),
            "total_call_volume": int(total_call_volume),
            "total_put_volume": int(total_put_volume),
            "max_call_oi_strike": round(float(max_call_row["strike_price"]), 4) if max_call_row else None,
            "max_put_oi_strike": round(float(max_put_row["strike_price"]), 4) if max_put_row else None,
            "atm_call": atm_call,
            "atm_put": atm_put,
            "atm_iv_spread": atm_iv_spread,
            "chain_sample": rows[max(0, (len(rows) // 2) - 1): min(len(rows), (len(rows) // 2) + 2)],
            "debug_meta": self._option_chain_debug_meta(chain_response),
        }
        return source_key, snapshot, None, None

    def _resolve_market_sources(self) -> Dict[str, List[Dict[str, Any]]]:
        resolved: Dict[str, List[Dict[str, Any]]] = {
            "primary_indices": [],
            "sector_indices": [],
            "index_futures": [],
            "option_chain_underlyings": [],
        }

        for item in self.catalog.get("primary_indices", []):
            resolved_item = self._resolve_index_source(item)
            if not resolved_item:
                continue
            resolved["primary_indices"].append({
                "name": item["name"],
                "exchange": item["exchange"],
                "symbol": item["symbol"],
                "display_name": resolved_item["display_name"],
                "exchange_segment": "IDX_I",
                "instrument": "INDEX",
                "security_id": resolved_item["security_id"],
            })

        sector_items = self.catalog.get("sector_indices", [])[: self.config.regime_sector_limit]
        for item in sector_items:
            resolved_item = self._resolve_index_source(item)
            if not resolved_item:
                continue
            resolved["sector_indices"].append({
                "name": item["name"],
                "exchange": item["exchange"],
                "symbol": item["symbol"],
                "display_name": resolved_item["display_name"],
                "exchange_segment": "IDX_I",
                "instrument": "INDEX",
                "security_id": resolved_item["security_id"],
            })

        for item in self.catalog.get("index_futures", []):
            resolved_item = self._resolve_future_source(item)
            if not resolved_item:
                continue
            resolved["index_futures"].append({
                "name": item["name"],
                "exchange": item["exchange"],
                "symbol": resolved_item["symbol"],
                "display_name": resolved_item["display_name"],
                "exchange_segment": f"{item['exchange']}_FNO" if item["exchange"] in {"NSE", "BSE"} else resolved_item["exchange_segment"],
                "instrument": "FUTIDX",
                "security_id": resolved_item["security_id"],
                "underlying_symbol": item["underlying_symbol"],
                "expiry_date": resolved_item["expiry_date"].isoformat() if resolved_item.get("expiry_date") else None,
            })

        for item in self.catalog.get("option_chain_underlyings", []):
            resolved_item = self._resolve_option_chain_source(item)
            if not resolved_item:
                continue
            resolved["option_chain_underlyings"].append({
                "name": item["name"],
                "exchange": item["exchange"],
                "symbol": item["symbol"],
                "display_name": resolved_item["display_name"],
                "exchange_segment": "IDX_I",
                "instrument": "INDEX",
                "security_id": resolved_item["security_id"],
            })
        return resolved

    def _fetch_resolved_sources(
        self,
        resolved: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
        snapshots: Dict[str, Dict[str, Any]] = {}
        failures: Dict[str, str] = {}
        debug_payloads: Dict[str, Any] = {}
        work_items: List[Tuple[str, Dict[str, Any]]] = []
        option_chain_items: List[Tuple[str, Dict[str, Any]]] = []
        for group_name, items in resolved.items():
            for item in items:
                if group_name == "option_chain_underlyings":
                    option_chain_items.append((f"{group_name}.{item['name']}", item))
                else:
                    work_items.append((f"{group_name}.{item['name']}", item))

        with ThreadPoolExecutor(max_workers=self.config.regime_workers) as executor:
            futures = [
                executor.submit(self._fetch_source_snapshot, key, item)
                for key, item in work_items
            ]
            for future in as_completed(futures):
                key, snapshot, failure, debug_payload = future.result()
                if snapshot:
                    snapshots[key] = snapshot
                elif failure:
                    failures[key] = failure
                if debug_payload is not None:
                    debug_payloads[key] = debug_payload

        for key, item in option_chain_items:
            snapshot, failure = None, None
            debug_payload = None
            try:
                _, snapshot, failure, debug_payload = self._fetch_option_chain_snapshot(key, item)
            except Exception:
                failure = "option_chain_exception"
            if snapshot:
                snapshots[key] = snapshot
            elif failure:
                failures[key] = failure
            if debug_payload is not None:
                debug_payloads[key] = debug_payload
        return snapshots, failures, debug_payloads

    def _average(self, rows: List[Dict[str, Any]], key: str) -> Optional[float]:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        if not values:
            return None
        return sum(values) / len(values)

    def _ratio(self, rows: List[Dict[str, Any]], key: str) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if row.get(key)) / len(rows)

    def _summarize_news_input(self, news_input: Dict[str, Any]) -> Dict[str, Any]:
        overlay = news_input.get("llm_regime_overlay")
        if not isinstance(overlay, dict):
            overlay = {}
        return {
            "analysis_scope": news_input.get("analysis_scope"),
            "analysis_engine": news_input.get("analysis_engine"),
            "headline_count": news_input.get("headline_count"),
            "market_sentiment": news_input.get("market_sentiment"),
            "confidence_score": news_input.get("confidence_score"),
            "event_severity_score": news_input.get("event_severity_score"),
            "trade_caution_level": news_input.get("trade_caution_level"),
            "risk_of_abnormal_volatility": news_input.get("risk_of_abnormal_volatility"),
            "affected_sectors": news_input.get("affected_sectors"),
            "event_clusters": news_input.get("event_clusters"),
            "headline_summary": news_input.get("headline_summary"),
            "structured_reasoning": news_input.get("structured_reasoning"),
            "llm_regime_overlay": overlay,
            "market_signal_distribution": news_input.get("market_signal_distribution"),
            "agno_error": news_input.get("agno_error"),
        }

    def _normalized_symbol(self, value: Optional[str]) -> str:
        return str(value or "").strip().upper().replace(" ", "")

    def _classify_regime(
        self,
        session_state: Dict[str, Any],
        primary_indices: List[Dict[str, Any]],
        sector_indices: List[Dict[str, Any]],
        futures: List[Dict[str, Any]],
        option_chains: List[Dict[str, Any]],
        external_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        if session_state["market_session"] == "pre_open":
            return {
                "market_regime": "pre_open",
                "confidence": 100.0,
                "reasoning_summary": "Market has not opened yet; regime is informationally unavailable until live price discovery starts.",
            }
        if session_state["market_session"] == "post_market":
            return {
                "market_regime": "post_market",
                "confidence": 100.0,
                "reasoning_summary": "Market session is closed; this snapshot is end-of-day context rather than a live trading regime.",
            }
        if session_state["is_discovery_phase"]:
            return {
                "market_regime": "open_discovery",
                "confidence": 60.0,
                "reasoning_summary": "The market is still in the opening discovery window, so structural labels remain provisional.",
            }

        if not primary_indices and not sector_indices and not futures:
            return {
                "market_regime": "data_unavailable",
                "confidence": 0.0,
                "reasoning_summary": "Core market context sources were unavailable for this cycle, so regime classification is suspended.",
                "diagnostics": {
                    "avg_primary_change_percent": None,
                    "avg_primary_vwap_percent": None,
                    "primary_above_open_ratio": None,
                    "primary_above_vwap_ratio": None,
                    "sector_breadth_ratio": None,
                    "avg_sector_change_percent": None,
                    "avg_sector_vwap_percent": None,
                    "breakout_ratio": None,
                    "futures_alignment_ratio": None,
                    "futures_alignment_count": 0,
                    "futures_compared_count": 0,
                    "vix_change_percent": None,
                    "news_severity_score": 0.0,
                    "option_chain_count": len(option_chains),
                    "avg_option_put_call_oi_ratio": None,
                    "avg_option_atm_iv_spread": None,
                },
            }

        vix_snapshot = next((row for row in primary_indices if row["name"] == "india_vix"), None)
        directional_indices = [row for row in primary_indices if row["name"] != "india_vix"]

        avg_primary_change = self._average(directional_indices, "day_change_percent") or 0.0
        avg_primary_vwap = self._average(directional_indices, "price_vs_vwap_percent") or 0.0
        primary_above_open = self._ratio(directional_indices, "is_above_open")
        primary_above_vwap = self._ratio(directional_indices, "is_above_vwap")
        sector_breadth = self._ratio(sector_indices, "is_above_open")
        avg_sector_change = self._average(sector_indices, "day_change_percent") or 0.0
        avg_sector_vwap = self._average(sector_indices, "price_vs_vwap_percent") or 0.0
        breakout_ratio = self._ratio(
            [row for row in directional_indices + sector_indices if row.get("opening_range_complete")],
            "is_above_vwap",
        )

        futures_alignment_score = 0.0
        futures_compared = 0
        futures_aligned = 0
        if futures:
            primary_map = {
                self._normalized_symbol(row.get("symbol")): row
                for row in directional_indices + sector_indices
            }
            for future_row in futures:
                underlying = self._normalized_symbol(future_row.get("underlying_symbol"))
                spot_row = primary_map.get(underlying)
                if not spot_row:
                    continue
                future_move = float(future_row.get("day_change_percent") or 0.0)
                spot_move = float(spot_row.get("day_change_percent") or 0.0)
                if math.isclose(future_move, 0.0) or math.isclose(spot_move, 0.0):
                    continue
                futures_compared += 1
                if (future_move > 0 and spot_move > 0) or (future_move < 0 and spot_move < 0):
                    futures_aligned += 1
            futures_alignment_score = (
                futures_aligned / futures_compared if futures_compared else 0.0
            )

        vix_change = float(vix_snapshot.get("day_change_percent") or 0.0) if vix_snapshot else 0.0
        event_input = external_inputs.get("market_news", {})
        news_severity = float(event_input.get("event_severity_score", 0.0) or 0.0)
        news_overlay = event_input.get("llm_regime_overlay") or {}
        news_bias = str(news_overlay.get("regime_bias") or "neutral")
        news_horizon = str(news_overlay.get("impact_horizon") or "unclear")
        option_pcr_values = [
            float(item["put_call_oi_ratio"])
            for item in option_chains
            if item.get("put_call_oi_ratio") is not None
        ]
        avg_option_pcr = sum(option_pcr_values) / len(option_pcr_values) if option_pcr_values else None
        option_iv_spreads = [
            float(item["atm_iv_spread"])
            for item in option_chains
            if item.get("atm_iv_spread") is not None
        ]
        avg_option_iv_spread = (
            sum(option_iv_spreads) / len(option_iv_spreads) if option_iv_spreads else None
        )

        if abs(avg_primary_change) >= 0.9 or abs(vix_change) >= 8.0 or news_severity >= 0.7:
            label = "event_driven"
        elif (
            avg_primary_change >= 0.35
            and avg_primary_vwap >= 0.15
            and primary_above_open >= 0.66
            and sector_breadth >= 0.58
            and futures_alignment_score >= 0.5
        ):
            label = "trend_up"
        elif (
            avg_primary_change <= -0.35
            and avg_primary_vwap <= -0.15
            and primary_above_open <= 0.34
            and sector_breadth <= 0.42
            and futures_alignment_score >= 0.5
        ):
            label = "trend_down"
        elif avg_primary_change > 0 and sector_breadth >= 0.58 and vix_change <= 2.0:
            label = "risk_on"
        elif avg_primary_change < 0 and sector_breadth <= 0.42 and vix_change >= 2.0:
            label = "risk_off"
        elif abs(avg_primary_vwap) <= 0.12 and 0.40 <= sector_breadth <= 0.60:
            label = "mean_reversion"
        else:
            label = "choppy"

        confidence = min(
            100.0,
            45.0
            + min(abs(avg_primary_change) * 22.0, 22.0)
            + min(abs(avg_primary_vwap) * 18.0, 18.0)
            + min(abs(sector_breadth - 0.5) * 40.0, 10.0)
            + min(futures_alignment_score * 10.0, 10.0),
        )
        summary = (
            f"avg_primary_change={round(avg_primary_change, 4)}%, "
            f"avg_primary_vwap={round(avg_primary_vwap, 4)}%, "
            f"sector_breadth={round(sector_breadth, 4)}, "
            f"avg_sector_change={round(avg_sector_change, 4)}%, "
            f"avg_sector_vwap={round(avg_sector_vwap, 4)}%, "
            f"futures_alignment={round(futures_alignment_score, 4)} ({futures_aligned}/{futures_compared}), "
            f"vix_change={round(vix_change, 4)}%, "
            f"breakout_ratio={round(breakout_ratio, 4)}, "
            f"avg_option_pcr={round(avg_option_pcr, 4) if avg_option_pcr is not None else 'na'}, "
            f"avg_option_iv_spread={round(avg_option_iv_spread, 4) if avg_option_iv_spread is not None else 'na'}, "
            f"news_bias={news_bias}, "
            f"news_horizon={news_horizon}"
        )
        return {
            "market_regime": label,
            "confidence": round(confidence, 2),
            "reasoning_summary": summary,
            "diagnostics": {
                "avg_primary_change_percent": round(avg_primary_change, 4),
                "avg_primary_vwap_percent": round(avg_primary_vwap, 4),
                "primary_above_open_ratio": round(primary_above_open, 4),
                "primary_above_vwap_ratio": round(primary_above_vwap, 4),
                "sector_breadth_ratio": round(sector_breadth, 4),
                "avg_sector_change_percent": round(avg_sector_change, 4),
                "avg_sector_vwap_percent": round(avg_sector_vwap, 4),
                "breakout_ratio": round(breakout_ratio, 4),
                "futures_alignment_ratio": round(futures_alignment_score, 4),
                "futures_alignment_count": futures_aligned,
                "futures_compared_count": futures_compared,
                "vix_change_percent": round(vix_change, 4),
                "news_severity_score": round(news_severity, 4),
                "option_chain_count": len(option_chains),
                "avg_option_put_call_oi_ratio": round(avg_option_pcr, 4) if avg_option_pcr is not None else None,
                "avg_option_atm_iv_spread": round(avg_option_iv_spread, 4) if avg_option_iv_spread is not None else None,
            },
        }

    def _save_payload(self, payload: Dict[str, Any]) -> None:
        StorageService.save_snapshot(self.config.regime_latest_path, payload)
        StorageService.save_snapshot(self.config.regime_daily_path(self.market_time.market_date_str()), payload)

    def run(self) -> Dict[str, Any]:
        print("=" * 60)
        print("REGIME - MARKET CONTEXT ANALYZER")
        print("=" * 60)
        print(f"Current market time: {self.market_time.market_status_text()}")

        session_state = self._session_state()
        resolved = self._resolve_market_sources()
        print("Resolved source groups:")
        self._print_group_preview("  Primary indices", resolved["primary_indices"], ["symbol", "security_id"])
        self._print_group_preview("  Sector indices", resolved["sector_indices"], ["symbol", "security_id"])
        self._print_group_preview("  Index futures", resolved["index_futures"], ["underlying_symbol", "security_id"])
        self._print_group_preview("  Option chain underlyings", resolved["option_chain_underlyings"], ["symbol", "security_id"])

        with ThreadPoolExecutor(max_workers=2) as executor:
            source_future = executor.submit(self._fetch_resolved_sources, resolved)
            news_future = executor.submit(self._refresh_market_news_input)
            source_snapshots, source_failures, debug_payloads = source_future.result()
            refreshed_market_news = news_future.result()
        external_inputs, external_missing = self._load_external_market_inputs()

        primary_indices = [
            source_snapshots[key]
            for key in sorted(source_snapshots)
            if key.startswith("primary_indices.")
        ]
        sector_indices = [
            source_snapshots[key]
            for key in sorted(source_snapshots)
            if key.startswith("sector_indices.")
        ]
        futures = [
            source_snapshots[key]
            for key in sorted(source_snapshots)
            if key.startswith("index_futures.")
        ]
        option_chains = [
            source_snapshots[key]
            for key in sorted(source_snapshots)
            if key.startswith("option_chain_underlyings.")
        ]

        regime = self._classify_regime(
            session_state=session_state,
            primary_indices=primary_indices,
            sector_indices=sector_indices,
            futures=futures,
            option_chains=option_chains,
            external_inputs=external_inputs,
        )
        controls = self._derive_operational_controls(
            session_state=session_state,
            regime=regime,
            external_inputs=external_inputs,
        )

        print("Fetched source groups:")
        print(f"  Primary indices: {len(primary_indices)}")
        print(f"  Sector indices: {len(sector_indices)}")
        print(f"  Index futures: {len(futures)}")
        print(f"  Option chains: {len(option_chains)}")
        self._print_failure_summary(source_failures)
        self._print_external_input_summary(external_inputs, external_missing)
        if refreshed_market_news:
            print(
                "Market news refresh: "
                f"engine={refreshed_market_news.get('analysis_engine')} "
                f"headlines={refreshed_market_news.get('headline_count')} "
                f"severity={refreshed_market_news.get('event_severity_score')}"
            )
        self._print_option_chain_summary(option_chains)
        self._print_debug_payload_summary(debug_payloads)
        self._print_regime_diagnostics(regime)

        payload = {
            "stage": "market_regime",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "market_date": self.market_time.market_date_str(),
                "market_session": session_state["market_session"],
                "resolved_source_groups": {
                    "primary_indices": len(resolved["primary_indices"]),
                    "sector_indices": len(resolved["sector_indices"]),
                    "index_futures": len(resolved["index_futures"]),
                    "option_chain_underlyings": len(resolved["option_chain_underlyings"]),
                },
                "fetched_source_groups": {
                    "primary_indices": len(primary_indices),
                    "sector_indices": len(sector_indices),
                    "index_futures": len(futures),
                    "option_chain_underlyings": len(option_chains),
                },
                "source_failures": source_failures,
                "debug_payloads": debug_payloads,
                "external_inputs_missing": external_missing,
                "market_news_refresh": {
                    "performed": refreshed_market_news is not None,
                    "analysis_engine": (refreshed_market_news or {}).get("analysis_engine"),
                    "headline_count": (refreshed_market_news or {}).get("headline_count"),
                    "event_severity_score": (refreshed_market_news or {}).get("event_severity_score"),
                },
                "review_interval_seconds": self.config.regime_loop_interval_seconds,
                "next_review_at": (
                    self.market_time.now() + timedelta(seconds=self.config.regime_loop_interval_seconds)
                ).isoformat(),
            },
            "regime": {
                "status": session_state["market_session"],
                "market_regime": regime["market_regime"],
                "confidence": regime["confidence"],
                "minutes_since_open": session_state["minutes_since_open"],
                "is_actionable": session_state["market_session"] == "live_market"
                and not session_state["is_discovery_phase"],
                "reasoning_summary": regime["reasoning_summary"],
                "diagnostics": regime.get("diagnostics", {}),
                "trade_permission": controls["trade_permission"],
                "preferred_style": controls["preferred_style"],
                "long_bias": controls["long_bias"],
                "short_bias": controls["short_bias"],
                "position_size_multiplier": controls["position_size_multiplier"],
                "max_concurrent_positions": controls["max_concurrent_positions"],
                "control_notes": controls["notes"],
                "news_analysis": self._summarize_news_input(external_inputs.get("market_news") or {}),
            },
            "market_context": {
                "session_state": session_state,
                "primary_indices": primary_indices,
                "sector_indices": sector_indices,
                "index_futures": futures,
                "option_chains": option_chains,
                "external_inputs": external_inputs,
            },
        }
        self._save_payload(payload)

        print("\nRegime analysis complete")
        print(f"Market session: {session_state['market_session']}")
        print(f"Market regime: {regime['market_regime']}")
        print(f"Confidence: {regime['confidence']}")
        print(f"Primary indices fetched: {len(primary_indices)}")
        print(f"Sector indices fetched: {len(sector_indices)}")
        print(f"Index futures fetched: {len(futures)}")
        print(f"Option chains fetched: {len(option_chains)}")
        print(f"Saved latest snapshot: {self.config.regime_latest_path.name}")
        print(f"Saved daily snapshot: {self.config.regime_daily_path(self.market_time.market_date_str()).name}")
        return payload
