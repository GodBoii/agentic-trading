"""Shared venue-aware contracts between Universe Scanner, Intra-Finder and agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class VenueIdentity:
    exchange: str
    exchange_segment: str
    security_id: int
    series: str
    trading_symbol: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UniverseRecord:
    isin: str
    symbol: str
    display_name: str
    instrument: str
    instrument_type: str
    selected_venue: VenueIdentity
    selected_venue_reason: str
    alternate_venues: List[Dict[str, Any]] = field(default_factory=list)
    historical: Dict[str, Any] = field(default_factory=dict)
    intraday_baselines: Dict[str, Any] = field(default_factory=dict)
    corporate_action: Optional[Dict[str, Any]] = None
    surveillance: Dict[str, Any] = field(default_factory=dict)
    tradability: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        selected = payload.pop("selected_venue")
        payload.update(selected)
        return payload


@dataclass(frozen=True)
class SetupEvent:
    event_id: str
    market_date: str
    universe_version: str
    isin: str
    exchange_segment: str
    security_id: int
    symbol: str
    direction: str
    setup_type: str
    setup_state: str
    setup_score: float
    payload: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        merged = asdict(self)
        detail = merged.pop("payload")
        merged.update(detail)
        return merged
