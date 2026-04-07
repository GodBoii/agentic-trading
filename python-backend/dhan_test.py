import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import dotenv_values
from dhanhq import dhanhq


def load_combined_env() -> dict:
    """
    Load both env files with python-backend values taking priority.
    """
    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent

    root_env_path = root_dir / ".env"
    backend_env_path = backend_dir / ".env"

    root_env = dotenv_values(root_env_path) if root_env_path.exists() else {}
    backend_env = dotenv_values(backend_env_path) if backend_env_path.exists() else {}

    combined = {}
    combined.update(root_env)
    combined.update(backend_env)
    return {k: v for k, v in combined.items() if v is not None}


def require_env(cfg: dict, key: str) -> str:
    value = cfg.get(key) or os.getenv(key)
    if not value:
        raise ValueError(f"Missing required env var: {key}")
    return value


def safe_print_json(title: str, payload) -> None:
    print(f"\n=== {title} ===")
    try:
        print(json.dumps(payload, indent=2, default=str)[:5000])
    except Exception:
        print(str(payload)[:5000])


def main() -> int:
    cfg = load_combined_env()

    # Prefer dedicated data credentials, fallback to generic names if needed.
    client_id = cfg.get("DHAN_DATA_CLIENT_ID") or cfg.get("DHAN_CLIENT_ID")
    access_token = cfg.get("DHAN_DATA_ACCESS_TOKEN") or cfg.get("DHAN_ACCESS_TOKEN")

    if not client_id or not access_token:
        print("Could not find Dhan data credentials in .env files.")
        print("Expected: DHAN_DATA_CLIENT_ID and DHAN_DATA_ACCESS_TOKEN")
        return 1

    # App creds are optional for this file; useful for token-flow debugging.
    app_id = cfg.get("DHAN_APP_ID")
    app_secret = cfg.get("DHAN_APP_SECRET")
    if app_id and app_secret:
        print("Found DHAN_APP_ID and DHAN_APP_SECRET in root .env")
    else:
        print("App credentials not found (optional for direct data fetch).")

    dhan = dhanhq(client_id, access_token)

    # Use docs sample defaults; override with env if needed.
    security_id = cfg.get("DHAN_TEST_SECURITY_ID", "1333")
    exchange_segment = cfg.get("DHAN_TEST_EXCHANGE_SEGMENT", dhan.NSE)
    instrument_type = cfg.get("DHAN_TEST_INSTRUMENT_TYPE", "EQUITY")

    today = date.today()
    from_date = (today - timedelta(days=4)).isoformat()
    to_date = today.isoformat()

    print("Running Dhan data checks...")
    masked_client = f"{client_id[:2]}***{client_id[-2:]}" if len(client_id) >= 4 else "***"
    print(f"Client ID: {masked_client}")
    print(
        f"Test Instrument: security_id={security_id}, "
        f"exchange_segment={exchange_segment}, instrument_type={instrument_type}"
    )
    print(f"Date range: {from_date} -> {to_date}")

    try:
        fund_limits = dhan.get_fund_limits()
        safe_print_json("Fund Limits", fund_limits)
    except Exception as exc:
        print(f"\nFund limits call failed: {exc}")

    try:
        holdings = dhan.get_holdings()
        safe_print_json("Holdings", holdings)
    except Exception as exc:
        print(f"\nHoldings call failed: {exc}")

    try:
        ohlc = dhan.ohlc_data({"NSE_EQ": [int(security_id)]})
        safe_print_json("OHLC Quote", ohlc)
    except Exception as exc:
        print(f"\nOHLC quote call failed: {exc}")

    try:
        intraday = dhan.intraday_minute_data(
            security_id=security_id,
            exchange_segment=exchange_segment,
            instrument_type=instrument_type,
            from_date=from_date,
            to_date=to_date,
            interval=1,
        )
        safe_print_json("Intraday Minute Data", intraday)
    except Exception as exc:
        print(f"\nIntraday data call failed: {exc}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as exc:
        print(str(exc))
        sys.exit(1)
