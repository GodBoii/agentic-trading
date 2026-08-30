"""Causal replay for the production activity ranker and setup engine."""

from __future__ import annotations

import json
import time
from datetime import datetime, time as dt_time
from typing import Any, Dict, Iterable, List

from pipeline.config import PipelineConfig
from pipeline.stages.activity_ranker import ActivityRanker
from pipeline.stages.intra_finder import FEED_SEGMENTS, IntraFinder
from pipeline.stages.live_state import InstrumentKey, LiveStockState
from pipeline.stages.setups import SetupEngine


def replay_opportunities(
    *,
    stocks: Iterable[Dict[str, Any]],
    rows: Iterable[Dict[str, Any]],
    config: PipelineConfig | None = None,
) -> Dict[str, Any]:
    settings = config or PipelineConfig()
    states = {
        (str(stock["exchange_segment"]).upper(), int(stock["security_id"])): LiveStockState.from_stock(stock)
        for stock in stocks
    }
    ranker = ActivityRanker(
        hot_size=settings.intra_finder_hot_set_size,
        reserve_size=settings.intra_finder_hot_reserve_size,
        hysteresis_seconds=settings.intra_finder_hot_hysteresis_seconds,
        max_packet_age_seconds=max(5, settings.intra_finder_data_stale_seconds),
        max_trade_age_seconds=settings.intra_finder_readiness_max_last_trade_age_seconds,
        max_spread_percent=settings.intra_finder_max_spread_percent,
    )
    engine = SetupEngine()
    events: List[Dict[str, Any]] = []
    packet_count = 0
    rank_count = 0
    last_rank_at = 0.0
    started = time.perf_counter()
    for row in rows:
        try:
            received_at = datetime.fromisoformat(str(row["received_at"]))
            packet = row.get("packet") or json.loads(str(row["packet_json"]))
            security_id = int(packet["security_id"])
            raw_segment = packet.get("exchange_segment")
            segment = (
                raw_segment.upper()
                if isinstance(raw_segment, str) and raw_segment.upper() in {"NSE_EQ", "BSE_EQ"}
                else FEED_SEGMENTS.get(int(raw_segment))
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        state = states.get((str(segment), security_id))
        if state is None:
            continue
        price = IntraFinder._number(packet, "LTP", "ltp", "last_price")
        if price is None or price <= 0:
            continue
        depth = IntraFinder._depth(packet)
        state.apply_packet(
            received_at=received_at,
            price=price,
            cumulative_volume=IntraFinder._number(packet, "volume", "total_volume") or state.cumulative_volume,
            vwap=IntraFinder._number(packet, "avg_price", "average_price", "ATP"),
            last_trade_at=IntraFinder._packet_last_trade_at(packet, received_at),
            last_trade_quantity=IntraFinder._number(packet, "LTQ", "last_trade_quantity"),
            depth=depth,
            depth_features=IntraFinder._depth_features(depth, price),
        )
        previous_close = IntraFinder._number(packet, "close", "previous_close", "prev_close")
        if previous_close and received_at.time() < dt_time(15, 30):
            state.previous_close = previous_close
        official_open = IntraFinder._number(packet, "open", "day_open")
        official_high = IntraFinder._number(packet, "high", "day_high")
        official_low = IntraFinder._number(packet, "low", "day_low")
        if official_open and official_open > 0:
            state.session_open = official_open
        if official_high and official_high > 0:
            state.session_high = max(state.session_high or official_high, official_high)
        if official_low and official_low > 0:
            state.session_low = min(state.session_low or official_low, official_low)
        packet_count += 1
        interval = (
            settings.intra_finder_open_rank_interval_seconds
            if dt_time(9, 15) <= received_at.time() < dt_time(9, 30)
            else settings.intra_finder_rank_interval_seconds
        )
        if received_at.timestamp() - last_rank_at >= interval:
            ranker.rank(states, received_at)
            last_rank_at = received_at.timestamp()
            rank_count += 1
        if state.activity_rank is None or state.activity_rank > settings.intra_finder_setup_rank_limit:
            continue
        for signal in engine.evaluate(state, received_at):
            events.append(
                {
                    "exchange_segment": state.exchange_segment,
                    "security_id": state.security_id,
                    "symbol": state.symbol,
                    "setup_type": signal.family,
                    "direction": signal.direction,
                    "armed_at": signal.armed_at.isoformat(),
                    "triggered_at": signal.triggered_at.isoformat(),
                    "expires_at": signal.expires_at.isoformat(),
                    "trigger_price": signal.trigger_price,
                    "activity_rank": state.activity_rank,
                    "hotness": state.hotness,
                    "diagnostics": signal.diagnostics,
                }
            )
    return {
        "schema_version": 1,
        "packets": packet_count,
        "rank_evaluations": rank_count,
        "events": events,
        "event_count": len(events),
        "elapsed_seconds": round(time.perf_counter() - started, 4),
    }
