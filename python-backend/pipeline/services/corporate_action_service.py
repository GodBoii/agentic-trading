"""Deterministic corporate-action calendar used by historical and gap features."""

from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

from pipeline.config import PipelineConfig
from pipeline.services.storage_service import StorageService


PRICE_RESET_TERMS = (
    "BONUS",
    "SPLIT",
    "SUB-DIVISION",
    "SUB DIVISION",
    "CONSOLIDATION",
    "RIGHTS",
    "DEMERGER",
    "DE-MERGER",
    "MERGER",
    "AMALGAMATION",
)


class CorporateActionService:
    NSE_URL = "https://www.nseindia.com/api/corporates-corporateActions"
    BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w"

    def __init__(self, config: PipelineConfig, session: Optional[requests.Session] = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; Trader/1.0)",
                "Accept": "application/json,text/csv,*/*",
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
            }
        )

    def actions_for_date(self, market_date: str) -> Dict[str, Any]:
        path = self.config.corporate_actions_dir / f"{market_date}.json"
        cached = StorageService.load_snapshot(path)
        if (
            cached
            and cached.get("market_date") == market_date
            and cached.get("status") == "ready"
        ):
            return cached

        rows: List[Dict[str, Any]] = []
        source_errors: List[str] = []
        source_successes: List[str] = []
        try:
            rows.extend(self._fetch_nse(market_date))
            source_successes.append("NSE")
        except (requests.RequestException, ValueError, TypeError) as exc:
            source_errors.append(f"NSE:{type(exc).__name__}")
        try:
            rows.extend(self._fetch_bse(market_date))
            rows.extend(self._load_bse_csv(market_date))
            source_successes.append("BSE")
        except (requests.RequestException, OSError, ValueError, TypeError) as exc:
            source_errors.append(f"BSE:{type(exc).__name__}")

        payload = {
            "market_date": market_date,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "ready" if source_successes else "unavailable",
            "source_successes": source_successes,
            "source_errors": source_errors,
            "actions": _deduplicate(rows),
        }
        # Preserve a prior cache if every source failed. A missing action calendar
        # is visible to Stage 1, but cannot prevent the tradable universe publish.
        StorageService.save_snapshot(path, payload)
        StorageService.save_snapshot(self.config.corporate_actions_latest_path, payload)
        return payload

    def _fetch_nse(self, market_date: str) -> List[Dict[str, Any]]:
        parsed = date.fromisoformat(market_date)
        formatted = parsed.strftime("%d-%m-%Y")
        response = self.session.get(
            self.NSE_URL,
            params={"index": "equities", "from_date": formatted, "to_date": formatted},
            timeout=15,
        )
        if response.status_code in {401, 403}:
            self.session.get("https://www.nseindia.com", timeout=10)
            response = self.session.get(
                self.NSE_URL,
                params={"index": "equities", "from_date": formatted, "to_date": formatted},
                timeout=15,
            )
        response.raise_for_status()
        payload = response.json()
        raw_rows = payload if isinstance(payload, list) else payload.get("data") or []
        return [
            normalized
            for row in raw_rows
            if isinstance(row, dict)
            for normalized in [self._normalize(row, "NSE")]
            if normalized is not None and normalized["ex_date"] == market_date
        ]

    def _load_bse_csv(self, market_date: str) -> List[Dict[str, Any]]:
        configured = os.getenv("BSE_CORPORATE_ACTION_CSV", "").strip()
        if not configured:
            return []
        if configured.lower().startswith(("http://", "https://")):
            response = self.session.get(configured, timeout=20)
            response.raise_for_status()
            text = response.text
        else:
            text = Path(configured).read_text(encoding="utf-8-sig")
        rows = csv.DictReader(io.StringIO(text))
        result = []
        for row in rows:
            normalized = self._normalize(dict(row), "BSE")
            if normalized is not None and normalized["ex_date"] == market_date:
                result.append(normalized)
        return result

    def _fetch_bse(self, market_date: str) -> List[Dict[str, Any]]:
        parsed = date.fromisoformat(market_date)
        formatted = parsed.strftime("%Y%m%d")
        response = self.session.get(
            self.BSE_URL,
            params={
                "ddlcategorys": "E",
                "ddlindustrys": "",
                "segment": "0",
                "strSearch": "D",
                "Fdate": formatted,
                "TDate": formatted,
            },
            headers={"Origin": "https://www.bseindia.com", "Referer": "https://www.bseindia.com/"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        raw_rows = payload if isinstance(payload, list) else payload.get("Table") or payload.get("data") or []
        return [
            normalized
            for row in raw_rows
            if isinstance(row, dict)
            for normalized in [self._normalize(row, "BSE")]
            if normalized is not None and normalized["ex_date"] == market_date
        ]

    @staticmethod
    def _normalize(row: Dict[str, Any], exchange: str) -> Optional[Dict[str, Any]]:
        symbol = _first(row, "symbol", "SYMBOL", "scrip_code", "Security Code")
        purpose = _first(row, "subject", "purpose", "PURPOSE", "Purpose")
        ex_date = _parse_date(_first(row, "exDate", "ex_date", "Ex_date", "EX-DATE", "Ex Date"))
        if not symbol or not purpose or ex_date is None:
            return None
        upper = purpose.upper()
        return {
            "exchange": exchange,
            "symbol": symbol.upper(),
            "security_id": _first(row, "scrip_code", "SCRIP_CODE", "Security Code"),
            "isin": _first(row, "isin", "ISIN").upper(),
            "ex_date": ex_date.isoformat(),
            "record_date": (
                _parse_date(_first(row, "recDate", "record_date", "RECORD DATE", "Record Date"))
                or ex_date
            ).isoformat(),
            "purpose": purpose,
            "price_reference_unsafe": any(term in upper for term in PRICE_RESET_TERMS),
            "gap_setup_disabled": True,
        }


def action_index(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for action in payload.get("actions") or []:
        if not isinstance(action, dict):
            continue
        isin = str(action.get("isin") or "").upper()
        symbol = str(action.get("symbol") or "").upper()
        exchange = str(action.get("exchange") or "").upper()
        security_id = str(action.get("security_id") or "").strip()
        if isin:
            result[f"ISIN:{isin}"] = action
        if symbol:
            result[f"{exchange}:{symbol}"] = action
            result.setdefault(f"SYMBOL:{symbol}", action)
        if exchange == "BSE" and security_id:
            result[f"BSE_SECURITY:{security_id}"] = action
    return result


def action_for_stock(index: Dict[str, Dict[str, Any]], stock: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    isin = str(stock.get("isin") or "").upper()
    exchange = str(stock.get("exchange") or "").upper()
    security_id = str(stock.get("security_id") or "").strip()
    symbols = {
        str(stock.get("symbol") or "").upper(),
        str(stock.get("trading_symbol") or "").upper(),
    }
    if isin and f"ISIN:{isin}" in index:
        return index[f"ISIN:{isin}"]
    if exchange == "BSE" and security_id and f"BSE_SECURITY:{security_id}" in index:
        return index[f"BSE_SECURITY:{security_id}"]
    for symbol in symbols:
        if not symbol:
            continue
        if f"{exchange}:{symbol}" in index:
            return index[f"{exchange}:{symbol}"]
        if f"SYMBOL:{symbol}" in index:
            return index[f"SYMBOL:{symbol}"]
    return None


def _first(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    for pattern in (
        "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S", "%d %b %Y",
    ):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            continue
    return None


def _deduplicate(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        key = (row.get("exchange"), row.get("symbol"), row.get("ex_date"), row.get("purpose"))
        unique[key] = row
    return sorted(unique.values(), key=lambda row: (row["exchange"], row["symbol"], row["purpose"]))
