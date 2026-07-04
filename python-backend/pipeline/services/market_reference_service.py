import csv
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pipeline.config import PipelineConfig


class MarketReferenceService:
    def __init__(self, config: PipelineConfig):
        self.config = config

    @lru_cache(maxsize=1)
    def _load_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with self.config.security_master_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(row)
        return rows

    def _parse_expiry_date(self, raw_value: Optional[str]) -> Optional[date]:
        if not raw_value:
            return None
        raw_value = str(raw_value).strip()
        if not raw_value or raw_value == "0001-01-01":
            return None
        try:
            return datetime.strptime(raw_value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row)
        normalized["security_id"] = int(row["SECURITY_ID"])
        normalized["exchange_segment"] = "IDX_I" if row["SEGMENT"] == "I" else f"{row['EXCH_ID']}_{row['SEGMENT']}"
        normalized["instrument"] = row.get("INSTRUMENT")
        normalized["symbol"] = row.get("SYMBOL_NAME")
        normalized["display_name"] = row.get("DISPLAY_NAME")
        normalized["underlying_symbol"] = row.get("UNDERLYING_SYMBOL")
        normalized["expiry_date"] = self._parse_expiry_date(row.get("SM_EXPIRY_DATE"))
        return normalized

    def find_index(self, symbol_name: str, exch_id: str) -> Optional[Dict[str, Any]]:
        target_symbol = symbol_name.strip().upper()
        for row in self._load_rows():
            if (
                row.get("EXCH_ID") == exch_id
                and row.get("SEGMENT") == "I"
                and (row.get("SYMBOL_NAME") or "").strip().upper() == target_symbol
            ):
                return self._normalize_row(row)
        return None

    def find_sector_indices(self, exch_id: str, symbol_names: List[str]) -> List[Dict[str, Any]]:
        wanted = {name.strip().upper() for name in symbol_names}
        results: List[Dict[str, Any]] = []
        for row in self._load_rows():
            if row.get("EXCH_ID") != exch_id or row.get("SEGMENT") != "I":
                continue
            symbol_name = (row.get("SYMBOL_NAME") or "").strip().upper()
            if symbol_name in wanted:
                results.append(self._normalize_row(row))
        return results

    def find_front_month_future(self, exch_id: str, underlying_symbol: str) -> Optional[Dict[str, Any]]:
        target_underlying = underlying_symbol.strip().upper()
        today = date.today()
        candidates: List[Dict[str, Any]] = []
        for row in self._load_rows():
            if row.get("EXCH_ID") != exch_id or row.get("SEGMENT") != "D":
                continue
            if (row.get("INSTRUMENT") or "").strip().upper() != "FUTIDX":
                continue
            if (row.get("UNDERLYING_SYMBOL") or "").strip().upper() != target_underlying:
                continue
            normalized = self._normalize_row(row)
            expiry_date = normalized.get("expiry_date")
            if expiry_date is None or expiry_date < today:
                continue
            candidates.append(normalized)

        candidates.sort(key=lambda row: row["expiry_date"])
        return candidates[0] if candidates else None

    def find_nearest_index_options(
        self,
        exch_id: str,
        underlying_symbol: str,
        reference_price: float,
        strikes_each_side: int = 2,
    ) -> List[Dict[str, Any]]:
        target_underlying = underlying_symbol.strip().upper()
        today = date.today()
        candidates: List[Dict[str, Any]] = []
        for row in self._load_rows():
            if row.get("EXCH_ID") != exch_id or row.get("SEGMENT") != "D":
                continue
            if (row.get("INSTRUMENT") or "").strip().upper() != "OPTIDX":
                continue
            if (row.get("UNDERLYING_SYMBOL") or "").strip().upper() != target_underlying:
                continue
            expiry_date = self._parse_expiry_date(row.get("SM_EXPIRY_DATE"))
            if expiry_date is None or expiry_date < today:
                continue
            option_type = (row.get("OPTION_TYPE") or "").strip().upper()
            if option_type not in {"CE", "PE"}:
                continue
            try:
                float(row.get("STRIKE_PRICE") or 0)
            except ValueError:
                continue
            candidates.append(self._normalize_row(row))

        if not candidates:
            return []

        nearest_expiry = min(row["expiry_date"] for row in candidates if row.get("expiry_date"))
        expiry_rows = [row for row in candidates if row.get("expiry_date") == nearest_expiry]
        strikes = sorted({float(row.get("STRIKE_PRICE") or 0.0) for row in expiry_rows})
        if not strikes:
            return []

        atm_strike = min(strikes, key=lambda strike: abs(strike - reference_price))
        atm_index = strikes.index(atm_strike)
        start = max(0, atm_index - max(strikes_each_side, 0))
        end = min(len(strikes), atm_index + max(strikes_each_side, 0) + 1)
        wanted_strikes = set(strikes[start:end])

        results = [
            row
            for row in expiry_rows
            if float(row.get("STRIKE_PRICE") or 0.0) in wanted_strikes
        ]
        results.sort(
            key=lambda row: (
                float(row.get("STRIKE_PRICE") or 0.0),
                0 if (row.get("OPTION_TYPE") or "").strip().upper() == "CE" else 1,
            )
        )
        return results
