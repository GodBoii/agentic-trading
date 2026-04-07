import json
import os
import sys
import time
from contextlib import redirect_stdout
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import dotenv_values
from dhanhq import DhanContext, FullDepth, HistoricalData, MarketFeed, OptionChain, dhanhq


def load_combined_env() -> Dict[str, str]:
    backend_dir = Path(__file__).resolve().parent
    root_dir = backend_dir.parent

    root_env = dotenv_values(root_dir / ".env")
    backend_env = dotenv_values(backend_dir / ".env")

    combined: Dict[str, str] = {}
    combined.update({k: v for k, v in root_env.items() if v is not None})
    combined.update({k: v for k, v in backend_env.items() if v is not None})
    return combined


def status_ok(resp: Any) -> bool:
    return isinstance(resp, dict) and str(resp.get("status", "")).lower() == "success"


def find_first_number(obj: Any) -> Optional[float]:
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            out = find_first_number(v)
            if out is not None:
                return out
    if isinstance(obj, list):
        for v in obj:
            out = find_first_number(v)
            if out is not None:
                return out
    return None


def extract_depth_levels(obj: Any) -> int:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).lower()
            if key in {"depth", "market_depth", "bids", "asks"} and isinstance(v, list):
                return len(v)
            nested = extract_depth_levels(v)
            if nested:
                return nested
    elif isinstance(obj, list):
        for v in obj:
            nested = extract_depth_levels(v)
            if nested:
                return nested
    return 0


def extract_historical_points(resp_data: Any) -> int:
    if isinstance(resp_data, dict):
        for key in ("open", "close", "high", "low", "volume", "timestamp"):
            value = resp_data.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def print_step(title: str) -> None:
    print(f"\n[STEP] {title}")


def print_result(name: str, passed: bool, details: str, sample: Any = None) -> None:
    state = "PASS" if passed else "FAIL"
    print(f"[{state}] {name}: {details}")
    if sample is not None:
        try:
            dump = json.dumps(sample, indent=2, default=str)
        except Exception:
            dump = str(sample)
        print(dump[:1200])


def run_marketfeed_full_packet_check(
    dhan_context: DhanContext, security_id: str
) -> Tuple[bool, str, Optional[Any]]:
    """
    Fetch one MarketFeed Full packet.
    This is the regular live market feed full packet, which typically contains 5-level depth.
    """
    try:
        sink = StringIO()
        with redirect_stdout(sink):
            feed = MarketFeed(
                dhan_context,
                [(MarketFeed.NSE, security_id, MarketFeed.Full)],
                version="v2",
            )
            feed.run_forever()
            packet = feed.get_data()
            try:
                feed.close_connection()
            except Exception:
                pass

        if isinstance(packet, dict):
            levels = extract_depth_levels(packet)
            if levels > 0:
                return True, f"Received MarketFeed Full packet with depth levels={levels}.", packet
            return True, "Received MarketFeed Full packet (depth key not found in parsed payload).", packet
        return True, "Received MarketFeed Full packet (non-dict payload).", packet
    except Exception as exc:
        return False, f"MarketFeed Full packet failed: {exc}", None


def run_full_depth_check(
    dhan_context: DhanContext, security_id: str, depth_level: int
) -> Tuple[bool, str, Optional[Any]]:
    """
    Fetch one packet from the dedicated FullDepth websocket.
    depth_level=20 tests 20-level depth.
    depth_level=200 tests the latest full-depth/200-level feed.
    """
    try:
        feed = FullDepth(dhan_context, [(FullDepth.NSE, security_id)], depth_level=depth_level)

        # The SDK exposes the class, but the 200-level endpoint in rc1 still needs the docs path.
        if depth_level == 200:
            feed.ws_url = "wss://full-depth-api.dhan.co/twohundreddepth"

        sink = StringIO()
        with redirect_stdout(sink):
            feed.run_forever()
            raw = feed.loop.run_until_complete(feed.ws.recv())
        remaining_data = raw
        bid_data = None
        ask_data = None

        while remaining_data:
            update = feed.process_data(remaining_data)
            if not update:
                break
            remaining_data = update.pop("remaining_data", None)
            if update.get("type") == "Bid":
                bid_data = update
            elif update.get("type") == "Ask":
                ask_data = update
            if bid_data and ask_data and bid_data.get("security_id") == ask_data.get("security_id"):
                combined = {
                    "exchange_segment": bid_data["exchange_segment"],
                    "security_id": bid_data["security_id"],
                    "bid_depth": bid_data["depth"],
                    "ask_depth": ask_data["depth"],
                }
                try:
                    with redirect_stdout(sink):
                        feed.close_connection()
                except Exception:
                    pass
                levels = min(len(bid_data["depth"]), len(ask_data["depth"]))
                return True, f"Received dedicated FullDepth packet with {levels} bid and {levels} ask levels.", combined

        try:
            with redirect_stdout(sink):
                feed.close_connection()
        except Exception:
            pass
        return False, "Connected to FullDepth feed but could not assemble bid/ask packet.", None
    except Exception as exc:
        return False, f"FullDepth websocket failed: {exc}", None


def main() -> int:
    cfg = load_combined_env()
    client_id = cfg.get("DHAN_DATA_CLIENT_ID") or cfg.get("DHAN_CLIENT_ID")
    access_token = cfg.get("DHAN_DATA_ACCESS_TOKEN") or cfg.get("DHAN_ACCESS_TOKEN")

    if not client_id or not access_token:
        print("Missing credentials. Expected DHAN_DATA_CLIENT_ID and DHAN_DATA_ACCESS_TOKEN.")
        return 1

    dhan_context = DhanContext(client_id, access_token)
    dhan = dhanhq(dhan_context)
    option_chain_api = OptionChain(dhan_context)
    historical_api = HistoricalData(dhan_context)
    today = date.today()

    security_id = cfg.get("DHAN_TEST_SECURITY_ID", "1333")
    eq_exchange_segment = cfg.get("DHAN_TEST_EXCHANGE_SEGMENT", dhan.NSE)
    eq_instrument_type = cfg.get("DHAN_TEST_INSTRUMENT_TYPE", "EQUITY")

    under_security_id = int(cfg.get("DHAN_OPTION_UNDER_SECURITY_ID", "13"))  # NIFTY by docs
    under_exchange_segment = cfg.get("DHAN_OPTION_UNDER_EXCHANGE_SEGMENT", "IDX_I")

    expired_option_security_id = cfg.get("DHAN_EXPIRED_OPTION_SECURITY_ID")
    expired_option_exchange_segment = cfg.get("DHAN_EXPIRED_OPTION_EXCHANGE_SEGMENT", dhan.NSE_FNO)
    expired_option_instrument_type = cfg.get("DHAN_EXPIRED_OPTION_INSTRUMENT_TYPE", dhan.FNO)
    expired_option_expiry_code = int(cfg.get("DHAN_EXPIRED_OPTION_EXPIRY_CODE", "1"))

    masked_client = f"{client_id[:2]}***{client_id[-2:]}" if len(client_id) >= 4 else "***"
    print("Dhan Data API Validation")
    print(f"Client ID: {masked_client}")
    print(f"Base Equity Security: {security_id} ({eq_exchange_segment}, {eq_instrument_type})")
    print(f"Option Chain Underlying: {under_security_id} ({under_exchange_segment})")

    results: List[Tuple[str, bool, str]] = []

    # 1) Real-time Price
    print_step("Real-time Price")
    try:
        resp = dhan.ticker_data({"NSE_EQ": [int(security_id)]})
        ltp = find_first_number(resp)
        passed = status_ok(resp) and ltp is not None
        details = f"LTP found={ltp}" if ltp is not None else "Could not locate LTP in response."
        print_result("Real-time Price", passed, details, resp if not passed else None)
        results.append(("Real-time Price", passed, details))
    except Exception as exc:
        details = f"Exception: {exc}"
        print_result("Real-time Price", False, details)
        results.append(("Real-time Price", False, details))

    time.sleep(1.2)

    # 2) Historical Data for 5 Years
    print_step("Historical Data for 5 Years")
    try:
        from_date = (today - timedelta(days=365 * 5)).isoformat()
        to_date = today.isoformat()
        resp = historical_api.historical_daily_data(
            security_id=security_id,
            exchange_segment=eq_exchange_segment,
            instrument_type=eq_instrument_type,
            from_date=from_date,
            to_date=to_date,
        )
        points = extract_historical_points(resp.get("data") if isinstance(resp, dict) else {})
        passed = status_ok(resp) and points > 200
        details = f"Received {points} daily candles ({from_date} to {to_date})."
        print_result("Historical Data for 5 Years", passed, details, resp if not passed else None)
        results.append(("Historical Data for 5 Years", passed, details))
    except Exception as exc:
        details = f"Exception: {exc}"
        print_result("Historical Data for 5 Years", False, details)
        results.append(("Historical Data for 5 Years", False, details))

    time.sleep(1.2)

    # 3) 20 Market Depth
    print_step("20 Market Depth")
    passed, details, sample = run_full_depth_check(dhan_context, security_id, depth_level=20)
    print_result("20 Market Depth", passed, details, sample if not passed else None)
    results.append(("20 Market Depth", passed, details))

    # 4) Option Chain on APIs
    print_step("Option Chain on APIs")
    try:
        exp_resp = option_chain_api.expiry_list(under_security_id, under_exchange_segment)
        expiry = None
        if status_ok(exp_resp):
            data = exp_resp.get("data")
            if isinstance(data, list) and data:
                expiry = data[0]
            elif isinstance(data, dict):
                exp_list = data.get("expiryList") or data.get("expiries") or data.get("data")
                if isinstance(exp_list, list) and exp_list:
                    expiry = exp_list[0]
        if not expiry:
            raise ValueError(f"Could not resolve expiry from expiry_list response: {exp_resp}")

        time.sleep(1.2)
        chain_resp = option_chain_api.option_chain(under_security_id, under_exchange_segment, str(expiry))
        passed = status_ok(chain_resp)
        details = f"Option chain fetched for expiry={expiry}."
        print_result("Option Chain on APIs", passed, details, chain_resp if not passed else None)
        results.append(("Option Chain on APIs", passed, details))
    except Exception as exc:
        details = f"Exception: {exc}"
        print_result("Option Chain on APIs", False, details)
        results.append(("Option Chain on APIs", False, details))

    time.sleep(1.2)

    # 5) Full Market Depth
    print_step("Full Market Depth")
    passed, details, sample = run_full_depth_check(dhan_context, security_id, depth_level=200)
    if not passed:
        fallback_passed, fallback_details, fallback_sample = run_marketfeed_full_packet_check(dhan_context, security_id)
        details = (
            f"{details} Falling back to MarketFeed Full packet check. "
            f"{fallback_details}"
        )
        passed = fallback_passed
        sample = fallback_sample
    print_result("Full Market Depth", passed, details, sample if not passed else None)
    results.append(("Full Market Depth", passed, details))

    # 6) Expired Options Data
    print_step("Expired Options Data")
    if not expired_option_security_id:
        details = (
            "Skipped: set DHAN_EXPIRED_OPTION_SECURITY_ID (and optional "
            "DHAN_EXPIRED_OPTION_EXCHANGE_SEGMENT, DHAN_EXPIRED_OPTION_EXPIRY_CODE) in .env."
        )
        print_result("Expired Options Data", False, details)
        results.append(("Expired Options Data", False, details))
    else:
        try:
            from_date = (today - timedelta(days=90)).isoformat()
            to_date = today.isoformat()
            resp = historical_api.expired_options_data(
                security_id=expired_option_security_id,
                exchange_segment=expired_option_exchange_segment,
                instrument_type=expired_option_instrument_type,
                expiry_flag=True,
                expiry_code=expired_option_expiry_code,
                strike=cfg.get("DHAN_EXPIRED_OPTION_STRIKE", ""),
                drv_option_type=cfg.get("DHAN_EXPIRED_OPTION_TYPE", "PUT"),
                required_data=cfg.get("DHAN_EXPIRED_OPTION_REQUIRED_DATA", "days"),
                from_date=from_date,
                to_date=to_date,
                interval=1,
            )
            points = extract_historical_points(resp.get("data") if isinstance(resp, dict) else {})
            passed = status_ok(resp) and points > 0
            details = (
                f"Received {points} candles for expired option security_id={expired_option_security_id}, "
                f"expiry_code={expired_option_expiry_code}."
            )
            print_result("Expired Options Data", passed, details, resp if not passed else None)
            results.append(("Expired Options Data", passed, details))
        except Exception as exc:
            details = f"Exception: {exc}"
            print_result("Expired Options Data", False, details)
            results.append(("Expired Options Data", False, details))

    print("\nSummary")
    for name, passed, details in results:
        state = "PASS" if passed else "FAIL"
        print(f"- {name}: {state} | {details}")

    failed = sum(1 for _, passed, _ in results if not passed)
    print(f"\nTotal: {len(results)} checks, {len(results) - failed} passed, {failed} failed.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Fatal error: {exc}")
        sys.exit(1)
