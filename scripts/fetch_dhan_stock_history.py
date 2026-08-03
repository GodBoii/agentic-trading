#!/usr/bin/env python3
"""Refresh NSE/BSE stock universes and download Dhan historical candles.

The downloader is intentionally resumable. Each completed unit is recorded in
context/stocks-data/download_state.sqlite3, and Parquet files are written
atomically so an interrupted run can be restarted safely.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "context" / "stocks-data"
MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
MASTER_PATH = DATA_ROOT / "_master" / "api-scrip-master-detailed.csv"
LEGACY_MASTER_PATH = ROOT / "security_id_list.csv"
STATE_PATH = DATA_ROOT / "download_state.sqlite3"
HISTORICAL_URL = "https://api.dhan.co/v2/charts/historical"
INTRADAY_URL = "https://api.dhan.co/v2/charts/intraday"
EXCHANGE_SEGMENTS = {"NSE": "NSE_EQ", "BSE": "BSE_EQ"}
UNIVERSE_COLUMNS = [
    "EXCH_ID",
    "SEGMENT",
    "SECURITY_ID",
    "ISIN",
    "INSTRUMENT",
    "SYMBOL_NAME",
    "DISPLAY_NAME",
    "INSTRUMENT_TYPE",
    "SERIES",
    "LOT_SIZE",
    "TICK_SIZE",
    "ASM_GSM_FLAG",
    "ASM_GSM_CATEGORY",
    "BUY_SELL_INDICATOR",
]


class AuthenticationError(RuntimeError):
    pass


class ApiError(RuntimeError):
    pass


class RateLimitExhaustedError(ApiError):
    pass


@dataclass(frozen=True)
class Stock:
    exchange: str
    security_id: str
    isin: str
    symbol: str
    display_name: str
    series: str

    @property
    def directory(self) -> Path:
        return DATA_ROOT / self.exchange / self.security_id


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self.interval = 1.0 / requests_per_second
        self.last_request = 0.0

    def wait(self) -> None:
        delay = self.interval - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def load_credentials() -> tuple[str, str]:
    merged: dict[str, Any] = {}
    for env_path in (ROOT / ".env", ROOT / ".env.local", ROOT / "python-backend" / ".env"):
        if env_path.exists():
            merged.update({key: value for key, value in dotenv_values(env_path).items() if value})
    client_id = str(
        merged.get("DHAN_DATA_CLIENT_ID")
        or merged.get("DHAN_CLIENT_ID")
        or os.environ.get("DHAN_DATA_CLIENT_ID")
        or ""
    )
    token = str(
        merged.get("DHAN_DATA_ACCESS_TOKEN")
        or merged.get("DHAN_ACCESS_TOKEN")
        or os.environ.get("DHAN_DATA_ACCESS_TOKEN")
        or ""
    )
    if not client_id or not token:
        raise AuthenticationError(
            "Missing DHAN_DATA_CLIENT_ID or DHAN_DATA_ACCESS_TOKEN. "
            "Add both to python-backend/.env."
        )
    return client_id, token


def refresh_master(session: requests.Session) -> pd.DataFrame:
    print(f"Refreshing Dhan security master from {MASTER_URL}")
    response = session.get(MASTER_URL, timeout=120)
    response.raise_for_status()
    atomic_write_bytes(MASTER_PATH, response.content)
    # Runtime reference services read the legacy root path directly. Keep it
    # synchronized so derivatives do not disappear when that copy goes stale.
    atomic_write_bytes(LEGACY_MASTER_PATH, response.content)
    return pd.read_csv(MASTER_PATH, dtype=str, low_memory=False)


def load_master(session: requests.Session, refresh: bool) -> pd.DataFrame:
    if refresh or not MASTER_PATH.exists():
        return refresh_master(session)
    return pd.read_csv(MASTER_PATH, dtype=str, low_memory=False)


def common_equities(master: pd.DataFrame, exchange: str) -> pd.DataFrame:
    missing = set(UNIVERSE_COLUMNS) - set(master.columns)
    if missing:
        raise ValueError(f"Dhan security master is missing columns: {sorted(missing)}")
    frame = master[
        (master["EXCH_ID"] == exchange)
        & (master["SEGMENT"] == "E")
        & (master["INSTRUMENT"] == "EQUITY")
        & (master["INSTRUMENT_TYPE"] == "ES")
    ][UNIVERSE_COLUMNS].copy()
    frame = frame.dropna(subset=["SECURITY_ID"]).drop_duplicates("SECURITY_ID", keep="last")
    frame["SECURITY_ID"] = frame["SECURITY_ID"].astype(str).str.replace(r"\.0$", "", regex=True)
    return frame.sort_values(["SYMBOL_NAME", "SECURITY_ID"], na_position="last").reset_index(drop=True)


def normalize_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def build_change_report(previous: pd.DataFrame | None, current: pd.DataFrame) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": MASTER_URL,
        "exchanges": {},
    }
    for exchange in ("NSE", "BSE"):
        new = common_equities(current, exchange)
        section: dict[str, Any] = {"current_count": len(new)}
        if previous is not None:
            old = common_equities(previous, exchange)
            old_isins = set(old["ISIN"].dropna()) - {"", "NA"}
            new_isins = set(new["ISIN"].dropna()) - {"", "NA"}
            joined = old[["ISIN", "SECURITY_ID", "SYMBOL_NAME", "DISPLAY_NAME"]].merge(
                new[["ISIN", "SECURITY_ID", "SYMBOL_NAME", "DISPLAY_NAME"]],
                on="ISIN",
                suffixes=("_old", "_new"),
            )
            symbol_changes = joined[joined["SYMBOL_NAME_old"] != joined["SYMBOL_NAME_new"]]
            id_changes = joined[joined["SECURITY_ID_old"] != joined["SECURITY_ID_new"]]
            section.update(
                {
                    "previous_count": len(old),
                    "added_isins": len(new_isins - old_isins),
                    "removed_isins": len(old_isins - new_isins),
                    "symbol_name_changes": len(symbol_changes),
                    "security_id_changes": len(id_changes),
                    "symbol_change_details": symbol_changes.head(500).fillna("").to_dict("records"),
                    "security_id_change_details": id_changes.head(1000).fillna("").to_dict("records"),
                }
            )
        report["exchanges"][exchange] = section
    return report


def save_universes(master: pd.DataFrame, report: dict[str, Any]) -> dict[str, pd.DataFrame]:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    universes: dict[str, pd.DataFrame] = {}
    for exchange in ("NSE", "BSE"):
        frame = common_equities(master, exchange)
        exchange_dir = DATA_ROOT / exchange
        exchange_dir.mkdir(parents=True, exist_ok=True)
        frame.to_csv(exchange_dir / "universe.csv", index=False)
        atomic_write_parquet(exchange_dir / "universe.parquet", frame)
        universes[exchange] = frame
    atomic_write_json(DATA_ROOT / "universe_changes.json", report)
    atomic_write_json(
        DATA_ROOT / "manifest.json",
        {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": MASTER_URL,
            "filter": {
                "SEGMENT": "E",
                "INSTRUMENT": "EQUITY",
                "INSTRUMENT_TYPE": "ES",
            },
            "counts": {exchange: len(frame) for exchange, frame in universes.items()},
            "storage": {
                "daily": "<EXCHANGE>/<SECURITY_ID>/daily.parquet",
                "intraday_1m": "<EXCHANGE>/<SECURITY_ID>/intraday_1m/<YEAR>.parquet",
            },
        },
    )
    return universes


def connect_state() -> sqlite3.Connection:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(STATE_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS downloads (
            exchange TEXT NOT NULL,
            security_id TEXT NOT NULL,
            data_kind TEXT NOT NULL,
            range_key TEXT NOT NULL,
            status TEXT NOT NULL,
            rows_written INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            updated_at_utc TEXT NOT NULL,
            PRIMARY KEY (exchange, security_id, data_kind, range_key)
        )
        """
    )
    connection.commit()
    return connection


def state_is_complete(
    connection: sqlite3.Connection, stock: Stock, data_kind: str, range_key: str
) -> bool:
    row = connection.execute(
        """
        SELECT status FROM downloads
        WHERE exchange=? AND security_id=? AND data_kind=? AND range_key=?
        """,
        (stock.exchange, stock.security_id, data_kind, range_key),
    ).fetchone()
    return bool(row and row[0] in {"complete", "complete_empty"})


def update_state(
    connection: sqlite3.Connection,
    stock: Stock,
    data_kind: str,
    range_key: str,
    status: str,
    rows_written: int = 0,
    error: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO downloads (
            exchange, security_id, data_kind, range_key, status,
            rows_written, attempts, error, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(exchange, security_id, data_kind, range_key) DO UPDATE SET
            status=excluded.status,
            rows_written=excluded.rows_written,
            attempts=downloads.attempts + 1,
            error=excluded.error,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            stock.exchange,
            stock.security_id,
            data_kind,
            range_key,
            status,
            rows_written,
            (error or "")[:2000],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    connection.commit()


def error_message(response: requests.Response, payload: Any) -> str:
    if isinstance(payload, dict):
        fields = [
            payload.get("errorCode"),
            payload.get("errorType"),
            payload.get("errorMessage"),
            payload.get("remarks"),
        ]
        message = " | ".join(str(field) for field in fields if field)
        if message:
            return message
    return f"HTTP {response.status_code}: {response.text[:500]}"


def post_dhan(
    session: requests.Session,
    limiter: RateLimiter,
    url: str,
    body: dict[str, Any],
    retries: int = 5,
) -> dict[str, Any]:
    for attempt in range(retries):
        limiter.wait()
        response = session.post(url, json=body, timeout=90)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        message = error_message(response, payload)
        if response.status_code in {401, 403} or "DH-901" in message:
            raise AuthenticationError(f"Dhan rejected the access token: {message}")
        if response.ok and isinstance(payload, dict) and not payload.get("errorCode"):
            return payload
        retryable = response.status_code in {429, 500, 502, 503, 504} or "DH-904" in message
        if not retryable or attempt == retries - 1:
            if response.status_code == 429 or "DH-904" in message:
                raise RateLimitExhaustedError(
                    f"Dhan rate limit remained active after {retries} retries: {message}"
                )
            raise ApiError(message)
        time.sleep(min(30.0, (2**attempt) + 0.25))
    raise ApiError("Dhan request failed after retries")


def candles_to_frame(payload: dict[str, Any]) -> pd.DataFrame:
    if isinstance(payload.get("data"), dict):
        payload = payload["data"]
    timestamp = payload.get("timestamp") or []
    if not timestamp:
        return pd.DataFrame(
            columns=["timestamp", "datetime_ist", "open", "high", "low", "close", "volume"]
        )
    length = len(timestamp)
    data: dict[str, Any] = {"timestamp": timestamp}
    for name in ("open", "high", "low", "close", "volume", "open_interest"):
        values = payload.get(name)
        if isinstance(values, list) and len(values) == length:
            data[name] = values
    frame = pd.DataFrame(data)
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce").astype("Int64")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["timestamp"] = frame["timestamp"].astype("int64")
    frame["datetime_ist"] = (
        pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        .dt.tz_convert("Asia/Kolkata")
        .astype(str)
    )
    for column in ("open", "high", "low", "close", "volume", "open_interest"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")


def save_stock_metadata(stock: Stock) -> None:
    stock.directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        stock.directory / "metadata.json",
        {
            "exchange": stock.exchange,
            "exchange_segment": EXCHANGE_SEGMENTS[stock.exchange],
            "security_id": stock.security_id,
            "isin": stock.isin,
            "symbol": stock.symbol,
            "display_name": stock.display_name,
            "series": stock.series,
            "instrument": "EQUITY",
        },
    )


def download_daily(
    session: requests.Session,
    limiter: RateLimiter,
    connection: sqlite3.Connection,
    stock: Stock,
    end_date: date,
) -> None:
    range_key = f"1900-01-01_{end_date.isoformat()}"
    output = stock.directory / "daily.parquet"
    if output.exists() and state_is_complete(connection, stock, "daily", range_key):
        return
    body = {
        "securityId": stock.security_id,
        "exchangeSegment": EXCHANGE_SEGMENTS[stock.exchange],
        "instrument": "EQUITY",
        "expiryCode": 0,
        "oi": False,
        "fromDate": "1900-01-01",
        "toDate": end_date.isoformat(),
    }
    payload = post_dhan(session, limiter, HISTORICAL_URL, body)
    frame = candles_to_frame(payload)
    if frame.empty:
        update_state(connection, stock, "daily", range_key, "complete_empty")
        return
    atomic_write_parquet(output, frame)
    update_state(connection, stock, "daily", range_key, "complete", len(frame))


def date_windows(start: date, end: date, days: int = 89) -> Iterable[tuple[date, date]]:
    cursor = start
    while cursor <= end:
        window_end = min(end, cursor + timedelta(days=days))
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def merge_year_file(path: Path, incoming: pd.DataFrame) -> int:
    if path.exists():
        existing = pd.read_parquet(path)
        incoming = pd.concat([existing, incoming], ignore_index=True)
    incoming = incoming.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    atomic_write_parquet(path, incoming)
    return len(incoming)


def download_intraday_1m(
    session: requests.Session,
    limiter: RateLimiter,
    connection: sqlite3.Connection,
    stock: Stock,
    end_date: date,
) -> None:
    start_date = end_date - timedelta(days=365 * 5 + 2)
    for window_start, window_end in date_windows(start_date, end_date):
        range_key = f"{window_start.isoformat()}_{window_end.isoformat()}"
        if state_is_complete(connection, stock, "intraday_1m", range_key):
            continue
        body = {
            "securityId": stock.security_id,
            "exchangeSegment": EXCHANGE_SEGMENTS[stock.exchange],
            "instrument": "EQUITY",
            "interval": "1",
            "oi": False,
            "fromDate": f"{window_start.isoformat()} 09:00:00",
            "toDate": f"{window_end.isoformat()} 16:00:00",
        }
        payload = post_dhan(session, limiter, INTRADAY_URL, body)
        frame = candles_to_frame(payload)
        if frame.empty:
            update_state(connection, stock, "intraday_1m", range_key, "complete_empty")
            continue
        datetimes = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert(
            "Asia/Kolkata"
        )
        frame["_year"] = datetimes.dt.year
        rows_written = 0
        for year, year_frame in frame.groupby("_year"):
            year_frame = year_frame.drop(columns=["_year"])
            output = stock.directory / "intraday_1m" / f"{int(year)}.parquet"
            merge_year_file(output, year_frame)
            rows_written += len(year_frame)
        update_state(
            connection, stock, "intraday_1m", range_key, "complete", rows_written
        )


def rows_to_stocks(exchange: str, frame: pd.DataFrame) -> list[Stock]:
    return [
        Stock(
            exchange=exchange,
            security_id=normalize_text(row.SECURITY_ID),
            isin=normalize_text(row.ISIN),
            symbol=normalize_text(row.SYMBOL_NAME),
            display_name=normalize_text(row.DISPLAY_NAME),
            series=normalize_text(row.SERIES),
        )
        for row in frame.itertuples(index=False)
    ]


def validate_token(session: requests.Session, limiter: RateLimiter, stock: Stock) -> None:
    body = {
        "securityId": stock.security_id,
        "exchangeSegment": EXCHANGE_SEGMENTS[stock.exchange],
        "instrument": "EQUITY",
        "expiryCode": 0,
        "oi": False,
        "fromDate": (date.today() - timedelta(days=14)).isoformat(),
        "toDate": date.today().isoformat(),
    }
    post_dhan(session, limiter, HISTORICAL_URL, body, retries=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("universe", "daily", "intraday", "all"),
        default="all",
        help="all stores inception-to-date daily plus five years of 1-minute bars",
    )
    parser.add_argument(
        "--exchange",
        choices=("NSE", "BSE", "both"),
        default="both",
    )
    parser.add_argument("--refresh-master", action="store_true")
    parser.add_argument("--limit", type=int, help="Process only the first N stocks per exchange")
    parser.add_argument("--requests-per-second", type=float, default=4.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.requests_per_second <= 0 or args.requests_per_second > 5:
        raise ValueError("--requests-per-second must be greater than 0 and no more than 5")

    session = requests.Session()
    session.headers.update({"User-Agent": "Trader-Dhan-History/1.0"})
    previous = None
    if LEGACY_MASTER_PATH.exists():
        previous = pd.read_csv(LEGACY_MASTER_PATH, dtype=str, low_memory=False)
    master = load_master(session, refresh=args.refresh_master)
    report = build_change_report(previous, master)
    universes = save_universes(master, report)
    print(
        "Current ordinary-share universe: "
        + ", ".join(f"{exchange}={len(frame)}" for exchange, frame in universes.items())
    )
    if args.mode == "universe":
        return 0

    client_id, token = load_credentials()
    session.headers.update(
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": token,
            "client-id": client_id,
        }
    )
    limiter = RateLimiter(args.requests_per_second)
    selected_exchanges = ("NSE", "BSE") if args.exchange == "both" else (args.exchange,)
    all_stocks: list[Stock] = []
    for exchange in selected_exchanges:
        stocks = rows_to_stocks(exchange, universes[exchange])
        all_stocks.extend(stocks[: args.limit] if args.limit else stocks)
    if not all_stocks:
        print("No stocks selected.")
        return 0

    print("Validating Dhan historical-data access...")
    validate_token(session, limiter, all_stocks[0])
    print(f"Token accepted. Processing {len(all_stocks)} stock(s).")
    connection = connect_state()
    end_date = date.today()
    completed = 0
    failed = 0
    try:
        for index, stock in enumerate(all_stocks, start=1):
            save_stock_metadata(stock)
            try:
                if args.mode in {"daily", "all"}:
                    download_daily(session, limiter, connection, stock, end_date)
                if args.mode in {"intraday", "all"}:
                    download_intraday_1m(session, limiter, connection, stock, end_date)
                completed += 1
            except (AuthenticationError, RateLimitExhaustedError):
                raise
            except Exception as exc:
                failed += 1
                update_state(
                    connection,
                    stock,
                    args.mode,
                    "stock",
                    "failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
                print(
                    f"[{index}/{len(all_stocks)}] FAILED "
                    f"{stock.exchange} {stock.security_id} {stock.display_name}: {exc}",
                    file=sys.stderr,
                )
            if index == 1 or index % 25 == 0 or index == len(all_stocks):
                print(
                    f"[{index}/{len(all_stocks)}] completed={completed} failed={failed} "
                    f"latest={stock.exchange}:{stock.security_id}"
                )
    finally:
        connection.close()
    print(f"Finished: completed={completed}, failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuthenticationError as exc:
        print(f"AUTHENTICATION ERROR: {exc}", file=sys.stderr)
        raise SystemExit(3)
    except RateLimitExhaustedError as exc:
        print(f"RATE LIMIT STOP: {exc}", file=sys.stderr)
        print("Re-run the same command later; completed ranges are checkpointed.", file=sys.stderr)
        raise SystemExit(4)
