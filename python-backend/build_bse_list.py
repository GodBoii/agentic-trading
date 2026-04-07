import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from dotenv import dotenv_values
from dhanhq import DhanContext, dhanhq


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BACKEND_DIR / "BSE_LIST.json"
MASTER_CACHE_PATH = ROOT_DIR / "security_id_list.csv"


def load_env() -> Dict[str, str]:
    root_env = dotenv_values(ROOT_DIR / ".env")
    backend_env = dotenv_values(BACKEND_DIR / ".env")

    merged: Dict[str, str] = {}
    merged.update({k: v for k, v in root_env.items() if v is not None})
    merged.update({k: v for k, v in backend_env.items() if v is not None})
    return merged


def get_dhan_client() -> dhanhq:
    cfg = load_env()
    client_id = cfg.get("DHAN_DATA_CLIENT_ID") or cfg.get("DHAN_CLIENT_ID")
    access_token = cfg.get("DHAN_DATA_ACCESS_TOKEN") or cfg.get("DHAN_ACCESS_TOKEN")

    if not client_id or not access_token:
        raise ValueError("Missing Dhan credentials in .env. Expected DHAN_DATA_CLIENT_ID and DHAN_DATA_ACCESS_TOKEN.")

    dhan_context = DhanContext(client_id, access_token)
    return dhanhq(dhan_context)


def load_master_df() -> pd.DataFrame:
    dhan = get_dhan_client()
    print("Fetching latest Dhan detailed security master...")
    df = dhan.fetch_security_list("detailed", filename=str(MASTER_CACHE_PATH))
    if df is None or df.empty:
        raise RuntimeError("Could not fetch Dhan security master.")
    return df


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def normalize_value(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return float(value)
    return value


def build_record(row: pd.Series) -> Dict[str, Any]:
    instrument_type = normalize_value(row.get("INSTRUMENT_TYPE"))
    series = normalize_value(row.get("SERIES"))

    return {
        "security_id": normalize_value(row.get("SECURITY_ID")),
        "symbol": normalize_value(row.get("SYMBOL_NAME")),
        "display_name": normalize_value(row.get("DISPLAY_NAME")),
        "isin": normalize_value(row.get("ISIN")),
        "exchange": normalize_value(row.get("EXCH_ID")),
        "segment": normalize_value(row.get("SEGMENT")),
        "instrument": normalize_value(row.get("INSTRUMENT")),
        "instrument_type": instrument_type,
        "series": series,
        "lot_size": normalize_value(row.get("LOT_SIZE")),
        "tick_size": normalize_value(row.get("TICK_SIZE")),
        "asm_gsm_flag": normalize_value(row.get("ASM_GSM_FLAG")),
        "asm_gsm_category": normalize_value(row.get("ASM_GSM_CATEGORY")),
        "buy_sell_indicator": normalize_value(row.get("BUY_SELL_INDICATOR")),
        "mtf_leverage": normalize_value(row.get("MTF_LEVERAGE")),
        "upper_circuit": normalize_value(row.get("SM_UPPER_LIMIT")),
        "lower_circuit": normalize_value(row.get("SM_LOWER_LIMIT")),
        "is_common_equity_candidate": instrument_type == "ES",
    }


def build_bse_list(df: pd.DataFrame) -> List[Dict[str, Any]]:
    filtered = df[
        (df["EXCH_ID"] == "BSE")
        & (df["SEGMENT"] == "E")
        & (df["INSTRUMENT"] == "EQUITY")
    ].copy()

    filtered = filtered.sort_values(["SYMBOL_NAME", "SECURITY_ID"], na_position="last")
    return [build_record(row) for _, row in filtered.iterrows()]


def save_json(records: List[Dict[str, Any]]) -> None:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Dhan detailed security master",
        "filter": {
            "exchange": "BSE",
            "segment": "E",
            "instrument": "EQUITY",
        },
        "total_count": len(records),
        "stocks": records,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    df = load_master_df()
    records = build_bse_list(df)
    save_json(records)

    print(f"Saved {len(records)} BSE equity instruments to {OUTPUT_PATH}")
    print("This file is reusable in other scripts.")
    print("You only need to rebuild it when Dhan updates the master or when you want a fresh universe snapshot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
