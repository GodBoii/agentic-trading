import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from threading import Condition, Lock
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from dhanhq import DhanContext, HistoricalData, dhanhq
from dotenv import dotenv_values


class UniverseScanner:
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.root_dir = self.base_dir.parent
        self.bse_list_path = self.base_dir / "BSE_LIST.json"

        self.min_price = 50
        self.max_price = 5000
        self.min_liquidity_cr = 10
        self.min_atr_percent = 1.5

        self.lock = Lock()
        self.progress_count = 0
        self.quote_request_gap = 1.1
        self.historical_rate_limit_per_sec = 5
        self.request_times = deque()
        self.rate_condition = Condition()

        self.gsm_stocks = set()
        self.asm_stocks = set()

        self.dhan_client, self.historical_api = self._build_dhan_clients()

    def _load_env(self) -> Dict[str, str]:
        root_env = dotenv_values(self.root_dir / ".env")
        backend_env = dotenv_values(self.base_dir / ".env")

        merged: Dict[str, str] = {}
        merged.update({k: v for k, v in root_env.items() if v is not None})
        merged.update({k: v for k, v in backend_env.items() if v is not None})
        return merged

    def _build_dhan_clients(self) -> Tuple[dhanhq, HistoricalData]:
        cfg = self._load_env()
        client_id = cfg.get("DHAN_DATA_CLIENT_ID") or cfg.get("DHAN_CLIENT_ID")
        access_token = cfg.get("DHAN_DATA_ACCESS_TOKEN") or cfg.get("DHAN_ACCESS_TOKEN")

        if not client_id or not access_token:
            raise ValueError("Missing Dhan credentials. Expected DHAN_DATA_CLIENT_ID and DHAN_DATA_ACCESS_TOKEN.")

        dhan_context = DhanContext(client_id, access_token)
        return dhanhq(dhan_context), HistoricalData(dhan_context)

    def acquire_historical_slot(self) -> None:
        """
        Allow multiple workers to run, but keep the total historical request rate
        within Dhan's documented 5 requests/second data API limit.
        """
        with self.rate_condition:
            while True:
                now = time.time()
                while self.request_times and now - self.request_times[0] >= 1.0:
                    self.request_times.popleft()

                if len(self.request_times) < self.historical_rate_limit_per_sec:
                    self.request_times.append(now)
                    self.rate_condition.notify_all()
                    return

                wait_time = max(0.01, 1.0 - (now - self.request_times[0]))
                self.rate_condition.wait(timeout=wait_time)

    def download_asm_csv(self, asm_type: str = "long") -> Optional[Path]:
        today = datetime.now()

        for days_back in range(8):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%d%m%Y")

            if asm_type == "long":
                url = f"https://www.bseindia.com/downloads1/List_of_Long_Term_ASM_Securities_{date_str}.CSV"
                file_prefix = "Long_Term"
            else:
                url = f"https://www.bseindia.com/downloads1/List_of_Short_Term_ASM_Securities_{date_str}.CSV"
                file_prefix = "Short_Term"

            try:
                print(f"Attempting to download {file_prefix} ASM for {check_date.strftime('%d-%m-%Y')}...", end=" ")
                response = requests.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                if response.status_code == 200:
                    filename = self.root_dir / f"List_of_{file_prefix}_ASM_Securities_{date_str}.CSV"
                    filename.write_text(response.text, encoding="utf-8")
                    print("Downloaded")
                    return filename
                print(f"Not found (HTTP {response.status_code})")
            except Exception as exc:
                print(f"Error: {str(exc)[:50]}")

        print(f"Could not download {file_prefix} ASM file from BSE")
        return None

    def load_asm_list(self) -> bool:
        print("Loading ASM lists...")

        asm_files: List[Path] = []
        try:
            long_term_file = self.download_asm_csv("long")
            short_term_file = self.download_asm_csv("short")
            if long_term_file:
                asm_files.append(long_term_file)
            if short_term_file:
                asm_files.append(short_term_file)
        except Exception:
            pass

        if not asm_files:
            fallback_names = [
                "List_of_Long_Term_ASM_Securities_06042026.CSV",
                "List_of_Long_Term_ASM_Securities_23032026.CSV",
                "List_of_Short_Term_ASM_Securities_06042026.CSV",
                "List_of_Short_Term_ASM_Securities_23032026.CSV",
            ]
            for name in fallback_names:
                path = self.root_dir / name
                if path.exists():
                    asm_files.append(path)
                    print(f"Found local ASM file: {path.name}")

        if not asm_files:
            print("No ASM files found. Proceeding without ASM filter.")
            return False

        for asm_file in asm_files:
            try:
                lines = asm_file.read_text(encoding="utf-8").splitlines()
                for line in lines[1:]:
                    parts = line.strip().split(",")
                    if len(parts) >= 2 and parts[1].strip().isdigit():
                        self.asm_stocks.add(int(parts[1].strip()))
            except Exception as exc:
                print(f"Error loading ASM file {asm_file.name}: {exc}")

        print(f"Loaded {len(self.asm_stocks)} ASM security ids")
        return bool(self.asm_stocks)

    def download_gsm_csv(self) -> Optional[Path]:
        today = datetime.now()

        for days_back in range(8):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%d%m%Y")
            url = f"https://www.bseindia.com/downloads1/List_of_GSM_Securities_{date_str}.CSV"

            try:
                print(f"Attempting to download GSM list for {check_date.strftime('%d-%m-%Y')}...", end=" ")
                response = requests.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                if response.status_code == 200:
                    filename = self.root_dir / f"List_of_GSM_Securities_{date_str}.CSV"
                    filename.write_text(response.text, encoding="utf-8")
                    print("Downloaded")
                    return filename
                print(f"Not found (HTTP {response.status_code})")
            except Exception as exc:
                print(f"Error: {str(exc)[:50]}")

        print("Could not download GSM file from BSE")
        return None

    def load_gsm_list(self) -> bool:
        gsm_file = None
        try:
            gsm_file = self.download_gsm_csv()
        except Exception:
            gsm_file = None

        if not gsm_file:
            for name in ["List_of_GSM_Securities_06042026.CSV", "List_of_GSM_Securities_23032026.CSV"]:
                path = self.root_dir / name
                if path.exists():
                    gsm_file = path
                    print(f"Found local GSM file: {path.name}")
                    break

        if not gsm_file:
            print("No GSM file found. Proceeding without GSM filter.")
            return False

        try:
            lines = gsm_file.read_text(encoding="utf-8").splitlines()
            for line in lines[1:]:
                parts = line.strip().split(",")
                if len(parts) >= 2 and parts[1].strip().isdigit():
                    self.gsm_stocks.add(int(parts[1].strip()))
            print(f"Loaded {len(self.gsm_stocks)} GSM security ids")
            return True
        except Exception as exc:
            print(f"Error loading GSM file: {exc}")
            return False

    def load_bse_universe(self) -> List[Dict[str, Any]]:
        if not self.bse_list_path.exists():
            raise FileNotFoundError(f"BSE list not found: {self.bse_list_path}")

        payload = json.loads(self.bse_list_path.read_text(encoding="utf-8"))
        stocks = payload.get("stocks", [])

        # Keep the scanner focused on ordinary equity-style stocks.
        filtered = [
            stock for stock in stocks
            if stock.get("exchange") == "BSE"
            and stock.get("segment") == "E"
            and stock.get("instrument") == "EQUITY"
            and stock.get("instrument_type") == "ES"
            and stock.get("security_id") is not None
        ]

        print(f"Loaded {len(filtered)} common BSE equity stocks from {self.bse_list_path.name}")
        return filtered

    def chunked(self, items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
        return [items[i:i + size] for i in range(0, len(items), size)]

    def fetch_price_snapshots(self, stocks: List[Dict[str, Any]], batch_size: int = 1000) -> Dict[int, Dict[str, Any]]:
        """
        Fetch current price in bulk using Dhan OHLC quote endpoint.
        This is much faster than making a historical request for every stock up front.
        """
        snapshots: Dict[int, Dict[str, Any]] = {}
        batches = self.chunked(stocks, batch_size)

        print(f"\nStage 1: Bulk price snapshot for {len(stocks)} stocks in {len(batches)} Dhan batches...")

        for batch_index, batch in enumerate(batches, 1):
            security_ids = [int(stock["security_id"]) for stock in batch]
            time.sleep(self.quote_request_gap)
            resp = self.dhan_client.ohlc_data({"BSE_EQ": security_ids})

            if str(resp.get("status", "")).lower() != "success":
                print(f"  Batch {batch_index}/{len(batches)} failed: {resp.get('remarks')}")
                continue

            batch_data = resp.get("data", {}).get("data", {}).get("BSE_EQ", {})
            for raw_security_id, value in batch_data.items():
                try:
                    security_id = int(raw_security_id)
                except Exception:
                    continue

                last_price = value.get("last_price")
                ohlc = value.get("ohlc", {})
                snapshots[security_id] = {
                    "price": float(last_price) if last_price is not None else None,
                    "open": ohlc.get("open"),
                    "close": ohlc.get("close"),
                    "high": ohlc.get("high"),
                    "low": ohlc.get("low"),
                }

            print(f"  Batch {batch_index}/{len(batches)} complete")

        print(f"Price snapshots fetched for {len(snapshots)} stocks")
        return snapshots

    def prefilter_candidates(self, stocks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Fast prefilter using surveillance lists and batched current-price snapshots.
        This removes obvious rejects before we spend time on historical API calls.
        """
        snapshot_map = self.fetch_price_snapshots(stocks)
        candidates: List[Dict[str, Any]] = []
        stats = {
            "initial": len(stocks),
            "gsm_filtered": 0,
            "asm_filtered": 0,
            "missing_price": 0,
            "price_filtered": 0,
        }

        for stock in stocks:
            security_id = int(stock["security_id"])

            if security_id in self.gsm_stocks:
                stats["gsm_filtered"] += 1
                continue
            if security_id in self.asm_stocks:
                stats["asm_filtered"] += 1
                continue

            snapshot = snapshot_map.get(security_id)
            price = snapshot.get("price") if snapshot else None
            if price is None:
                stats["missing_price"] += 1
                continue
            if price < self.min_price or price > self.max_price:
                stats["price_filtered"] += 1
                continue

            enriched = dict(stock)
            enriched["snapshot_price"] = round(price, 2)
            candidates.append(enriched)

        stats["remaining"] = len(candidates)
        return candidates, stats

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return float(atr.iloc[-1]) if len(atr) > 0 and pd.notna(atr.iloc[-1]) else 0.0

    def response_to_df(self, resp: Dict[str, Any]) -> pd.DataFrame:
        data = resp.get("data", {}) if isinstance(resp, dict) else {}
        timestamps = data.get("timestamp", [])

        df = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": data.get("open", []),
                "high": data.get("high", []),
                "low": data.get("low", []),
                "close": data.get("close", []),
                "volume": data.get("volume", []),
            }
        )

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

        return df

    def fetch_history_with_retry(self, security_id: int, retries: int = 3) -> Optional[Dict[str, Any]]:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=25)

        last_response = None
        for attempt in range(retries):
            self.acquire_historical_slot()
            resp = self.historical_api.historical_daily_data(
                security_id=str(security_id),
                exchange_segment="BSE_EQ",
                instrument_type="EQUITY",
                from_date=start_date.isoformat(),
                to_date=end_date.isoformat(),
            )
            last_response = resp

            if isinstance(resp, dict) and str(resp.get("status", "")).lower() == "success":
                return resp

            remarks = str(resp.get("remarks", "")) if isinstance(resp, dict) else ""
            data_blob = str(resp.get("data", "")) if isinstance(resp, dict) else ""
            error_text = f"{remarks} {data_blob}".lower()
            if "too many requests" in error_text or "805" in error_text:
                time.sleep(min(2.0, 0.4 * (attempt + 1)))
                continue
            return resp

        return last_response

    def fetch_stock_data(self, stock: Dict[str, Any], idx: Optional[int] = None, total: Optional[int] = None) -> Optional[Dict[str, Any]]:
        security_id = int(stock["security_id"])

        try:
            resp = self.fetch_history_with_retry(security_id)
            if not resp or str(resp.get("status", "")).lower() != "success":
                return None

            df = self.response_to_df(resp)
            if df.empty or len(df) < 14:
                return None

            current_price = float(df["close"].iloc[-1])
            last_10_days = df.tail(10)
            avg_volume = float(last_10_days["volume"].mean())
            avg_price = float(last_10_days["close"].mean())
            liquidity_cr = (avg_volume * avg_price) / 10000000
            atr = self.calculate_atr(df, period=14)
            atr_percent = (atr / current_price) * 100 if current_price > 0 else 0

            return {
                "security_id": security_id,
                "symbol": stock.get("symbol"),
                "display_name": stock.get("display_name"),
                "isin": stock.get("isin"),
                "series": stock.get("series"),
                "price": round(float(stock.get("snapshot_price", current_price)), 2),
                "avg_volume_10d": int(avg_volume),
                "avg_price_10d": round(avg_price, 2),
                "liquidity_cr": round(liquidity_cr, 2),
                "atr_14": round(atr, 2),
                "atr_percent": round(atr_percent, 2),
                "asm_gsm_flag": stock.get("asm_gsm_flag"),
                "upper_circuit": stock.get("upper_circuit"),
                "lower_circuit": stock.get("lower_circuit"),
                "history_points": len(df),
                "last_candle_date": df["timestamp"].iloc[-1].date().isoformat(),
                "last_updated": datetime.now().isoformat(),
            }
        except Exception as exc:
            with self.lock:
                if idx and total:
                    print(f"[{idx}/{total}] {stock.get('symbol')} ({security_id}) Error: {str(exc)[:80]}")
            return None

    def apply_filters(self, stock_data: Dict[str, Any]) -> bool:
        if not stock_data:
            return False

        security_id = stock_data["security_id"]

        if security_id in self.gsm_stocks:
            return False
        if security_id in self.asm_stocks:
            return False
        if stock_data["price"] < self.min_price or stock_data["price"] > self.max_price:
            return False
        if stock_data["liquidity_cr"] < self.min_liquidity_cr:
            return False
        if stock_data["atr_percent"] < self.min_atr_percent:
            return False

        return True

    def process_single_stock(self, stock: Dict[str, Any], idx: int, total: int) -> Tuple[Optional[Dict[str, Any]], bool]:
        stock_data = self.fetch_stock_data(stock, idx, total)

        if stock_data:
            passed = self.apply_filters(stock_data)
            with self.lock:
                self.progress_count += 1
                status = "PASS" if passed else "FILTERED"
                details = (
                    f"(Rs{stock_data['price']}, {stock_data['liquidity_cr']}Cr, {stock_data['atr_percent']}%)"
                    if passed else ""
                )
                print(f"[{self.progress_count}/{total}] {stock_data['symbol']} ({stock_data['security_id']}) {status} {details}")
                if self.progress_count % 100 == 0:
                    pct = self.progress_count / total * 100
                    print(f"\n--- Progress: {self.progress_count}/{total} ({pct:.1f}%) ---\n")
            return stock_data, passed

        with self.lock:
            self.progress_count += 1
            print(f"[{self.progress_count}/{total}] {stock.get('symbol')} ({stock.get('security_id')}) NO DATA")
        return None, False

    def scan_universe(self, max_stocks: Optional[int] = None, workers: int = 4) -> List[Dict[str, Any]]:
        print("=" * 60)
        print("BSE UNIVERSE SCANNER - Step 1.1: Universe Sanitation")
        print("=" * 60)

        self.load_gsm_list()
        self.load_asm_list()

        print("\nFilters Applied:")
        print(f"  - GSM Stocks: Excluded ({len(self.gsm_stocks)} stocks)")
        print(f"  - ASM Stocks: Excluded ({len(self.asm_stocks)} stocks)")
        print(f"  - Price Range: Rs{self.min_price} to Rs{self.max_price}")
        print(f"  - Min Liquidity: Rs{self.min_liquidity_cr} Crores")
        print(f"  - Min ATR%: {self.min_atr_percent}%")
        print(f"  - Dhan historical rate control: {self.historical_rate_limit_per_sec} req/sec shared across workers")
        print(f"  - Dhan bulk quote prefilter: enabled")
        print(f"  - Parallel Workers: {workers}")
        print("=" * 60)

        stocks = self.load_bse_universe()
        if max_stocks:
            stocks = stocks[:max_stocks]
            print(f"\nTEST MODE: Scanning only first {max_stocks} stocks")

        total_stocks = len(stocks)
        candidates, prefilter_stats = self.prefilter_candidates(stocks)

        print("\nStage 1 Summary:")
        print(f"  - Initial universe: {prefilter_stats['initial']}")
        print(f"  - GSM filtered: {prefilter_stats['gsm_filtered']}")
        print(f"  - ASM filtered: {prefilter_stats['asm_filtered']}")
        print(f"  - Missing live price: {prefilter_stats['missing_price']}")
        print(f"  - Price filtered: {prefilter_stats['price_filtered']}")
        print(f"  - Remaining for historical scan: {prefilter_stats['remaining']}")

        total_candidates = len(candidates)
        print(f"\nStage 2: Scanning {total_candidates} BSE stocks using Dhan historical daily data...")
        print("-" * 60)

        all_stocks: List[Dict[str, Any]] = []
        filtered_stocks: List[Dict[str, Any]] = []
        failed_count = 0
        gsm_filtered_count = 0
        asm_filtered_count = 0

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.process_single_stock, stock, idx, total_candidates): stock
                for idx, stock in enumerate(candidates, 1)
            }

            for future in as_completed(futures):
                try:
                    stock_data, passed = future.result()
                    if stock_data:
                        all_stocks.append(stock_data)
                        if passed:
                            filtered_stocks.append(stock_data)
                        else:
                            if stock_data["security_id"] in self.gsm_stocks:
                                gsm_filtered_count += 1
                            elif stock_data["security_id"] in self.asm_stocks:
                                asm_filtered_count += 1
                    else:
                        failed_count += 1
                except Exception as exc:
                    failed_count += 1
                    print(f"Task error: {exc}")

        elapsed_time = time.time() - start_time
        filtered_stocks.sort(key=lambda x: x["liquidity_cr"], reverse=True)

        self.save_results(all_stocks, filtered_stocks)
        self.print_summary(
            total_candidates,
            len(all_stocks),
            len(filtered_stocks),
            failed_count,
            elapsed_time,
            gsm_filtered_count,
            asm_filtered_count,
        )
        return filtered_stocks

    def save_results(self, all_stocks: List[Dict[str, Any]], filtered_stocks: List[Dict[str, Any]]) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        all_path = self.base_dir / f"all_stocks_{timestamp}.json"
        filtered_path = self.base_dir / f"tradeable_universe_{timestamp}.json"
        latest_path = self.base_dir / "tradeable_universe_latest.json"

        all_path.write_text(json.dumps(all_stocks, indent=2), encoding="utf-8")
        filtered_path.write_text(json.dumps(filtered_stocks, indent=2), encoding="utf-8")
        latest_path.write_text(json.dumps(filtered_stocks, indent=2), encoding="utf-8")

        print("\nResults saved to:")
        print(f"  - {all_path.name}")
        print(f"  - {filtered_path.name}")
        print(f"  - {latest_path.name}")

    def print_summary(
        self,
        total: int,
        fetched: int,
        filtered: int,
        failed: int,
        elapsed_time: float,
        gsm_filtered: int = 0,
        asm_filtered: int = 0,
    ) -> None:
        print("\n" + "=" * 60)
        print("SCAN COMPLETE")
        print("=" * 60)
        print(f"Total Stocks Scanned: {total}")
        print(f"Data Retrieved: {fetched}")
        print(f"Failed to Fetch: {failed}")
        print(f"GSM Filtered Out: {gsm_filtered}")
        print(f"ASM Filtered Out: {asm_filtered}")
        print(f"Passed All Filters: {filtered}")
        if fetched > 0:
            print(f"Pass Rate: {(filtered / fetched * 100):.1f}%")
        print(f"Time Taken: {elapsed_time:.1f} seconds ({elapsed_time / 60:.1f} minutes)")
        if elapsed_time > 0:
            print(f"Speed: {total / elapsed_time:.2f} stocks/second")
        print("=" * 60)


if __name__ == "__main__":
    scanner = UniverseScanner()
    tradeable_stocks = scanner.scan_universe(max_stocks=None, workers=20)

    if tradeable_stocks:
        print("\nTop 10 Most Liquid Stocks:")
        print("-" * 60)
        for i, stock in enumerate(tradeable_stocks[:10], 1):
            print(
                f"{i}. {stock['symbol']:20} Rs{stock['price']:8.2f}  "
                f"{stock['liquidity_cr']:8.2f}Cr  ATR: {stock['atr_percent']:.2f}%"
            )
    else:
        print("\nNo stocks passed the filters.")
