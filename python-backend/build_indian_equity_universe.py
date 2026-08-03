"""Build one deduplicated Indian common-equity universe from Dhan's master.

The same company can be listed on both NSE and BSE with different security
IDs. ISIN is used as the company/security identity. NSE's normal EQ series is
preferred; BSE A/B/X series are used when no supported NSE EQ row exists.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
MASTER_PATH = ROOT_DIR / "security_id_list.csv"
OUTPUT_PATH = BACKEND_DIR / "INDIAN_EQUITY_UNIVERSE.json"

NSE_SUPPORTED_SERIES = {"EQ"}
BSE_SUPPORTED_SERIES = {"A", "B", "X"}


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _number(value: Any) -> Any:
    text = _text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _exchange_segment(exchange: str, segment: str) -> str:
    if segment == "E":
        return f"{exchange}_EQ"
    return f"{exchange}_{segment}"


def _record(row: pd.Series) -> Dict[str, Any]:
    exchange = _text(row.get("EXCH_ID")).upper()
    segment = _text(row.get("SEGMENT")).upper()
    return {
        "security_id": int(float(row["SECURITY_ID"])),
        "isin": _text(row.get("ISIN")).upper(),
        "symbol": _text(row.get("SYMBOL_NAME")),
        "display_name": _text(row.get("DISPLAY_NAME")),
        "exchange": exchange,
        "segment": segment,
        "exchange_segment": _exchange_segment(exchange, segment),
        "instrument": _text(row.get("INSTRUMENT")).upper(),
        "instrument_type": _text(row.get("INSTRUMENT_TYPE")).upper(),
        "series": _text(row.get("SERIES")).upper(),
        "lot_size": _number(row.get("LOT_SIZE")),
        "tick_size": _number(row.get("TICK_SIZE")),
        "asm_gsm_flag": _text(row.get("ASM_GSM_FLAG")).upper(),
        "asm_gsm_category": _text(row.get("ASM_GSM_CATEGORY")),
        "buy_sell_indicator": _text(row.get("BUY_SELL_INDICATOR")).upper(),
        "mtf_leverage": _number(row.get("MTF_LEVERAGE")),
        "upper_circuit": _number(row.get("SM_UPPER_LIMIT")),
        "lower_circuit": _number(row.get("SM_LOWER_LIMIT")),
    }


def _eligible_rows(frame: pd.DataFrame) -> pd.DataFrame:
    common = frame[
        (frame["SEGMENT"] == "E")
        & (frame["INSTRUMENT"] == "EQUITY")
        & (frame["INSTRUMENT_TYPE"] == "ES")
        & frame["ISIN"].notna()
        & (frame["ISIN"].astype(str).str.strip() != "")
    ].copy()
    return common[
        (
            (common["EXCH_ID"] == "NSE")
            & common["SERIES"].isin(NSE_SUPPORTED_SERIES)
        )
        | (
            (common["EXCH_ID"] == "BSE")
            & common["SERIES"].isin(BSE_SUPPORTED_SERIES)
        )
    ].copy()


def build_universe(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    eligible = _eligible_rows(frame)
    records: List[Dict[str, Any]] = []
    for _, group in eligible.groupby("ISIN", sort=True):
        nse = group[(group["EXCH_ID"] == "NSE") & (group["SERIES"] == "EQ")]
        selected = nse.iloc[0] if not nse.empty else group.iloc[0]
        record = _record(selected)
        record["available_venues"] = [
            {
                "exchange": _text(row.get("EXCH_ID")).upper(),
                "exchange_segment": _exchange_segment(
                    _text(row.get("EXCH_ID")).upper(),
                    _text(row.get("SEGMENT")).upper(),
                ),
                "security_id": int(float(row["SECURITY_ID"])),
                "series": _text(row.get("SERIES")).upper(),
            }
            for _, row in group.sort_values(["EXCH_ID", "SECURITY_ID"]).iterrows()
        ]
        record["venue_selection_reason"] = (
            "preferred_nse_normal_equity"
            if record["exchange"] == "NSE"
            else "bse_fallback_no_supported_nse_eq"
        )
        records.append(record)
    return records


def save_universe(records: Iterable[Dict[str, Any]]) -> None:
    rows = list(records)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Dhan detailed security master",
        "identity_key": "ISIN",
        "venue_policy": {
            "preferred": "NSE_EQ series EQ",
            "fallback": "BSE_EQ series A/B/X",
            "excluded_examples": "SME, trade-to-trade, Z/non-compliant, and unsupported NS/NT series",
        },
        "total_count": len(rows),
        "stocks": rows,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    frame = pd.read_csv(MASTER_PATH, low_memory=False)
    records = build_universe(frame)
    save_universe(records)
    nse_count = sum(row["exchange"] == "NSE" for row in records)
    print(
        f"Saved {len(records)} unique ISINs: "
        f"{nse_count} NSE-preferred and {len(records) - nse_count} BSE fallbacks."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
