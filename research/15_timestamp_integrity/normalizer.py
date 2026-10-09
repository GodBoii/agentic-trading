"""Offline Dhan full-packet contracts with explicit time and depth provenance."""

from dataclasses import dataclass
from datetime import datetime, time, timezone
from hashlib import sha256
import json
from math import isfinite
import re
import struct
from typing import Literal


class NormalizationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class DepthLevel:
    bid_price: float
    ask_price: float
    bid_quantity: int
    ask_quantity: int
    bid_orders: int
    ask_orders: int


@dataclass(frozen=True, slots=True)
class NormalizedPacket:
    version: int
    received_at_raw: str
    received_utc_us: int
    security_id: int
    exchange_segment: Literal["NSE_EQ"]
    packet_type: Literal["Full Data"]
    capture_scope: Literal["all", "hot_only", "unknown"]
    last_price: float
    trade_time_raw: str | int | None
    trade_time_of_day: str | None
    trade_utc_us: int | None
    trade_time_semantics: str
    signed_receipt_minus_trade_seconds: float | None
    quote_event_utc_us: None
    quote_source_age_seconds: None
    source_sequence: None
    decoder_provenance: str
    original_wire_available: bool
    best_bid: float
    best_ask: float
    best_bid_quantity: int
    best_ask_quantity: int
    bid_quantity_5: int
    ask_quantity_5: int
    levels: tuple[DepthLevel, ...]
    packet_sha256: str


def _integer(value, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise NormalizationError("invalid_integer")
    if isinstance(value, str) and not re.fullmatch(r"[0-9]+", value):
        raise NormalizationError("invalid_integer")
    result = int(value)
    if result < 0 or positive and result == 0:
        raise NormalizationError("invalid_integer")
    return result


def _price(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int,float,str)):
        raise NormalizationError("invalid_price")
    try:
        result = float(value)
    except ValueError as exc:
        raise NormalizationError("invalid_price") from exc
    if not isfinite(result) or result <= 0:
        raise NormalizationError("invalid_price")
    return result


def _receipt(raw: str) -> datetime:
    if not isinstance(raw, str):
        raise NormalizationError("invalid_receipt")
    try:
        result = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise NormalizationError("invalid_receipt") from exc
    if result.tzinfo is None or result.utcoffset() is None or result.timestamp() <= 0:
        raise NormalizationError("receipt_timezone_or_epoch_unknown")
    return result


def _trade(raw) -> tuple[str | None,int | None,str]:
    if raw is None:
        return None,None,"missing"
    if isinstance(raw,int) and not isinstance(raw,bool):
        if raw <= 0:
            raise NormalizationError("invalid_trade_epoch")
        try:
            datetime.fromtimestamp(raw,timezone.utc)
        except (ValueError,OverflowError,OSError) as exc:
            raise NormalizationError("invalid_trade_epoch") from exc
        return None,raw*1_000_000,"wire_or_explicit_epoch_seconds_utc"
    if isinstance(raw,str) and re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}",raw):
        try:
            time.fromisoformat(raw)
        except ValueError as exc:
            raise NormalizationError("invalid_trade_time") from exc
        return raw,None,"time_of_day_date_and_timezone_unknown"
    if isinstance(raw,str):
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise NormalizationError("invalid_trade_time") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.timestamp() <= 0:
            raise NormalizationError("trade_timezone_or_epoch_unknown")
        return None,int(parsed.timestamp()*1_000_000),"explicit_aware_datetime"
    raise NormalizationError("invalid_trade_time")


def normalize_decoded_row(row: dict, *, decoder_provenance: str = "archived_sdk_version_unknown") -> NormalizedPacket:
    """Validate recorded decoded full packets. Bare times never acquire a date implicitly."""
    required = {"received_at","security_id","exchange_segment","packet_json"}
    if not required.issubset(row):
        raise NormalizationError("missing_capture_identity")
    receipt = _receipt(row["received_at"])
    sid = _integer(row["security_id"],positive=True)
    if row["exchange_segment"] != "NSE_EQ":
        raise NormalizationError("unsupported_capture_venue")
    if not isinstance(row["packet_json"],str):
        raise NormalizationError("invalid_packet_json")
    try:
        packet = json.loads(row["packet_json"])
    except json.JSONDecodeError as exc:
        raise NormalizationError("invalid_packet_json") from exc
    if not isinstance(packet,dict):
        raise NormalizationError("packet_must_be_object")
    if packet.get("type") != "Full Data":
        raise NormalizationError("not_full_packet")
    if _integer(packet.get("security_id"),positive=True) != sid:
        raise NormalizationError("packet_capture_id_mismatch")
    if packet.get("exchange_segment") not in (1,"1","NSE_EQ") or isinstance(packet.get("exchange_segment"),bool):
        raise NormalizationError("packet_capture_venue_mismatch")
    depth = packet.get("depth")
    if not isinstance(depth,list) or len(depth) != 5:
        raise NormalizationError("requires_five_depth_levels")
    levels = []
    keys = {"bid_price","ask_price","bid_quantity","ask_quantity","bid_orders","ask_orders"}
    for level in depth:
        if not isinstance(level,dict) or not keys.issubset(level):
            raise NormalizationError("incomplete_depth_level")
        levels.append(DepthLevel(_price(level["bid_price"]),_price(level["ask_price"]),
                                 _integer(level["bid_quantity"]),_integer(level["ask_quantity"]),
                                 _integer(level["bid_orders"]),_integer(level["ask_orders"])))
    if any(a.bid_price <= b.bid_price or a.ask_price >= b.ask_price for a,b in zip(levels,levels[1:])):
        raise NormalizationError("unsorted_or_duplicate_depth_prices")
    top = levels[0]
    if top.bid_price > top.ask_price:
        raise NormalizationError("crossed_book")
    if top.bid_quantity == 0 or top.ask_quantity == 0:
        raise NormalizationError("empty_top_depth")
    scope = row.get("capture_scope") or "unknown"
    if scope not in {"all","hot_only","unknown"}:
        raise NormalizationError("unknown_capture_scope_value")
    raw = packet.get("LTT")
    tod,trade_us,semantics = _trade(raw)
    received_us = int(receipt.timestamp()*1_000_000)
    signed = (received_us-trade_us)/1_000_000 if trade_us is not None else None
    return NormalizedPacket(1,row["received_at"],received_us,sid,"NSE_EQ","Full Data",scope,
                            _price(packet.get("LTP")),raw,tod,trade_us,semantics,signed,
                            None,None,None,decoder_provenance,False,
                            top.bid_price,top.ask_price,top.bid_quantity,top.ask_quantity,
                            sum(p.bid_quantity for p in levels),sum(p.ask_quantity for p in levels),
                            tuple(levels),sha256(row["packet_json"].encode()).hexdigest())


def normalize_binary_full(wire: bytes, *, received_at: str, capture_scope: str = "unknown") -> NormalizedPacket:
    """NSE Full response code8, exactly162 bytes. No live feed or credentials."""
    from dataclasses import replace

    if not isinstance(wire,bytes) or len(wire) != 162:
        raise NormalizationError("invalid_wire_length")
    fields = struct.unpack("<BHBIfHIfIIIIIIffff100s",wire)
    if fields[0] != 8 or fields[1] != 162 or fields[2] != 1:
        raise NormalizationError("invalid_full_wire_header")
    depth = []
    for offset in range(0,100,20):
        bidq,askq,bido,asko,bid,ask = struct.unpack("<IIHHff",fields[18][offset:offset+20])
        depth.append({"bid_quantity":bidq,"ask_quantity":askq,"bid_orders":bido,
                      "ask_orders":asko,"bid_price":bid,"ask_price":ask})
    packet = {"type":"Full Data","security_id":fields[3],"exchange_segment":fields[2],
              "LTP":fields[4],"LTT":fields[6],"depth":depth}
    row = {"received_at":received_at,"security_id":fields[3],"exchange_segment":"NSE_EQ",
           "capture_scope":capture_scope,"packet_json":json.dumps(packet)}
    result = normalize_decoded_row(row,decoder_provenance="offline_dhan_full_le_v1")
    return replace(result,original_wire_available=True,packet_sha256=sha256(wire).hexdigest())


def assumed_same_date_offset(packet: NormalizedPacket, *, basis: Literal["UTC","Asia/Kolkata"]) -> float | None:
    """Sensitivity arithmetic only. Not normalized source time or measured latency."""
    if basis not in {"UTC","Asia/Kolkata"}:
        raise ValueError("explicit sensitivity basis required")
    if packet.trade_time_of_day is None:
        return None
    from datetime import timedelta

    zone = timezone.utc if basis == "UTC" else timezone(timedelta(hours=5,minutes=30))
    receipt = datetime.fromtimestamp(packet.received_utc_us/1_000_000,zone)
    clock = time.fromisoformat(packet.trade_time_of_day)
    candidate = datetime.combine(receipt.date(),clock,tzinfo=zone)
    return receipt.timestamp()-candidate.timestamp()
