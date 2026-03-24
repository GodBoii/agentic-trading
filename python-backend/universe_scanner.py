import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import requests
from io import StringIO

class UniverseScanner:
    def __init__(self):
        self.min_price = 50
        self.max_price = 5000
        self.min_liquidity_cr = 10  # in Crores
        self.min_atr_percent = 1.5
        self.lock = Lock()  # For thread-safe printing
        self.progress_count = 0
        self.gsm_stocks = set()  # Set of GSM stocks to exclude
        self.asm_stocks = set()  # Set of ASM stocks to exclude
        
    def download_asm_csv(self, asm_type="long"):
        """Download latest ASM CSV from BSE website
        asm_type: 'long' for Long Term ASM, 'short' for Short Term ASM
        """
        today = datetime.now()
        
        # Try today and last 7 days
        for days_back in range(8):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%d%m%Y")
            
            # BSE URL pattern for ASM
            if asm_type == "long":
                url = f"https://www.bseindia.com/downloads1/List_of_Long_Term_ASM_Securities_{date_str}.CSV"
                file_prefix = "Long_Term"
            else:
                url = f"https://www.bseindia.com/downloads1/List_of_Short_Term_ASM_Securities_{date_str}.CSV"
                file_prefix = "Short_Term"
            
            try:
                print(f"Attempting to download {file_prefix} ASM for {check_date.strftime('%d-%m-%Y')}...", end=" ")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    # Save to file
                    filename = f"List_of_{file_prefix}_ASM_Securities_{date_str}.CSV"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    
                    print(f"✓ Downloaded")
                    return filename
                else:
                    print(f"✗ Not found (HTTP {response.status_code})")
                    
            except Exception as e:
                print(f"✗ Error: {str(e)[:50]}")
        
        print(f"⚠ Could not download {file_prefix} ASM file from BSE")
        return None
    
    def load_asm_list(self):
        """Load ASM (Additional Surveillance Measure) stocks from CSV"""
        print("Loading ASM lists...")
        
        # Try to download first (with short timeout)
        try:
            long_term_file = self.download_asm_csv("long")
            short_term_file = self.download_asm_csv("short")
        except:
            long_term_file = None
            short_term_file = None
        
        asm_files = []
        
        # Add downloaded files
        if long_term_file:
            asm_files.append(long_term_file)
        if short_term_file:
            asm_files.append(short_term_file)
        
        # If download failed, try local files
        if not asm_files:
            local_files = [
                'List_of_Long_Term_ASM_Securities_23032026.CSV',
                '../List_of_Long_Term_ASM_Securities_23032026.CSV',
                'List_of_Short_Term_ASM_Securities_23032026.CSV',
                '../List_of_Short_Term_ASM_Securities_23032026.CSV'
            ]
            
            for file_path in local_files:
                if os.path.exists(file_path):
                    asm_files.append(file_path)
                    print(f"✓ Found local ASM file: {os.path.basename(file_path)}")
        
        if not asm_files:
            print("⚠ No ASM files found. Proceeding without ASM filter.")
            return False
        
        # Load all ASM files
        for asm_file in asm_files:
            try:
                with open(asm_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Skip header line
                for line in lines[1:]:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        scrip_code = parts[1].strip()
                        if scrip_code.isdigit():
                            # Add .BO suffix to match yfinance format
                            self.asm_stocks.add(f"{scrip_code}.BO")
                
            except Exception as e:
                print(f"Error loading ASM file {asm_file}: {e}")
        
        if self.asm_stocks:
            print(f"✓ Loaded {len(self.asm_stocks)} ASM stocks")
            return True
        else:
            print("⚠ No ASM stocks loaded")
            return False
    
    def download_gsm_csv(self):
        """Download latest GSM CSV from BSE website"""
        # BSE GSM download URL - this changes daily with date
        today = datetime.now()
        
        # Try today and last 7 days (BSE might not update daily)
        for days_back in range(8):
            check_date = today - timedelta(days=days_back)
            date_str = check_date.strftime("%d%m%Y")
            
            # BSE URL pattern
            url = f"https://www.bseindia.com/downloads1/List_of_GSM_Securities_{date_str}.CSV"
            
            try:
                print(f"Attempting to download GSM list for {check_date.strftime('%d-%m-%Y')}...", end=" ")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    # Save to file
                    filename = f"List_of_GSM_Securities_{date_str}.CSV"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    
                    print(f"✓ Downloaded")
                    return filename
                else:
                    print(f"✗ Not found (HTTP {response.status_code})")
                    
            except Exception as e:
                print(f"✗ Error: {str(e)[:50]}")
        
        print("⚠ Could not download GSM file from BSE")
        return None
    
    def load_gsm_list(self):
        """Load GSM (Graded Surveillance Measure) stocks from CSV"""
        # Try to download latest from BSE (with fallback to local)
        try:
            gsm_file = self.download_gsm_csv()
        except:
            gsm_file = None
        
        # If download failed, try local files
        if not gsm_file:
            local_files = [
                'List_of_GSM_Securities_23032026.CSV',
                '../List_of_GSM_Securities_23032026.CSV'
            ]
            
            for file_path in local_files:
                if os.path.exists(file_path):
                    gsm_file = file_path
                    print(f"✓ Found local GSM file: {os.path.basename(gsm_file)}")
                    break
        
        if not gsm_file:
            print("⚠ No GSM file found. Proceeding without GSM filter.")
            return False
        
        try:
            with open(gsm_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Skip header line
            for line in lines[1:]:
                parts = line.strip().split(',')
                if len(parts) >= 2:
                    scrip_code = parts[1].strip()
                    if scrip_code.isdigit():
                        # Add .BO suffix to match yfinance format
                        self.gsm_stocks.add(f"{scrip_code}.BO")
            
            print(f"✓ Loaded {len(self.gsm_stocks)} GSM stocks")
            return True
            
        except Exception as e:
            print(f"Error loading GSM file: {e}")
            return False
        
    def get_bse_symbols(self):
        """
        Parse BSE stock list from bse-list.txt file
        Returns list of symbols in yfinance format (SYMBOL.BO)
        """
        symbols = []
        
        # Try multiple paths
        possible_paths = [
            'bse-list.txt',           # Same directory
            '../bse-list.txt',        # Parent directory
            'C:/Users/prajw/Downloads/Trader/bse-list.txt'  # Absolute path
        ]
        
        file_path = None
        for path in possible_paths:
            if os.path.exists(path):
                file_path = path
                break
        
        if not file_path:
            raise FileNotFoundError("bse-list.txt not found in any expected location")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Skip header line
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                
                # Split by whitespace and extract Security Code (first column)
                parts = line.split()
                if len(parts) >= 1:
                    security_code = parts[0]
                    # BSE security codes are numeric
                    if security_code.isdigit():
                        # yfinance uses Security Code for BSE stocks
                        symbols.append(f"{security_code}.BO")
            
            print(f"✓ Loaded {len(symbols)} BSE stocks from {file_path}")
            return symbols
            
        except Exception as e:
            print(f"ERROR reading bse-list.txt: {e}")
            raise
    
    def calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        # True Range calculation
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1] if len(atr) > 0 else 0
    
    def fetch_stock_data(self, symbol, idx=None, total=None):
        """Fetch and calculate metrics for a single stock"""
        try:
            ticker = yf.Ticker(symbol)
            
            # Fetch last 20 days data (buffer for calculations)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            df = ticker.history(start=start_date, end=end_date)
            
            if df.empty or len(df) < 14:
                return None
            
            # Current price (latest close)
            current_price = df['Close'].iloc[-1]
            
            # Last 10 days for volume and price average
            last_10_days = df.tail(10)
            avg_volume = last_10_days['Volume'].mean()
            avg_price = last_10_days['Close'].mean()
            
            # Liquidity in Crores (Volume × Price / 1 Crore)
            liquidity_cr = (avg_volume * avg_price) / 10000000
            
            # ATR calculation (14 days)
            atr = self.calculate_atr(df, period=14)
            atr_percent = (atr / current_price) * 100 if current_price > 0 else 0
            
            return {
                "symbol": symbol,
                "price": round(current_price, 2),
                "avg_volume_10d": int(avg_volume),
                "avg_price_10d": round(avg_price, 2),
                "liquidity_cr": round(liquidity_cr, 2),
                "atr_14": round(atr, 2),
                "atr_percent": round(atr_percent, 2),
                "last_updated": datetime.now().isoformat()
            }
            
        except Exception as e:
            # Suppress common errors for cleaner output
            if "possibly delisted" not in str(e):
                with self.lock:
                    if idx and total:
                        print(f"[{idx}/{total}] {symbol} Error: {str(e)[:50]}")
            return None
    
    def apply_filters(self, stock_data):
        """Apply sanitation filters"""
        if not stock_data:
            return False
        
        # Filter 0a: GSM stocks (surveillance)
        if stock_data['symbol'] in self.gsm_stocks:
            return False
        
        # Filter 0b: ASM stocks (surveillance)
        if stock_data['symbol'] in self.asm_stocks:
            return False
        
        # Filter 1: Price range
        if stock_data['price'] < self.min_price or stock_data['price'] > self.max_price:
            return False
        
        # Filter 2: Liquidity
        if stock_data['liquidity_cr'] < self.min_liquidity_cr:
            return False
        
        # Filter 3: Volatility (ATR%)
        if stock_data['atr_percent'] < self.min_atr_percent:
            return False
        
        return True
    
    def process_single_stock(self, symbol, idx, total):
        """Process a single stock and return result"""
        stock_data = self.fetch_stock_data(symbol, idx, total)
        
        if stock_data:
            passed = self.apply_filters(stock_data)
            
            with self.lock:
                self.progress_count += 1
                status = "✓ PASS" if passed else "✗ FILTERED"
                details = f"(₹{stock_data['price']}, {stock_data['liquidity_cr']}Cr, {stock_data['atr_percent']}%)" if passed else ""
                print(f"[{self.progress_count}/{total}] {symbol} {status} {details}")
                
                # Progress milestone
                if self.progress_count % 100 == 0:
                    print(f"\n--- Progress: {self.progress_count}/{total} ({self.progress_count/total*100:.1f}%) ---\n")
            
            return stock_data, passed
        else:
            with self.lock:
                self.progress_count += 1
                print(f"[{self.progress_count}/{total}] {symbol} ✗ NO DATA")
            return None, False
    
    def scan_universe(self, max_stocks=None, workers=20):
        """Main scanning function with parallel processing"""
        print("=" * 60)
        print("BSE UNIVERSE SCANNER - Step 1.1: Universe Sanitation")
        print("=" * 60)
        
        # Load GSM and ASM lists first
        self.load_gsm_list()
        self.load_asm_list()
        
        total_surveillance = len(self.gsm_stocks) + len(self.asm_stocks)
        
        print(f"\nFilters Applied:")
        print(f"  - GSM Stocks: Excluded ({len(self.gsm_stocks)} stocks)")
        print(f"  - ASM Stocks: Excluded ({len(self.asm_stocks)} stocks)")
        print(f"  - Total Surveillance: {total_surveillance} stocks")
        print(f"  - Price Range: ₹{self.min_price} to ₹{self.max_price}")
        print(f"  - Min Liquidity: ₹{self.min_liquidity_cr} Crores")
        print(f"  - Min ATR%: {self.min_atr_percent}%")
        print(f"\nParallel Workers: {workers}")
        print("=" * 60)
        
        symbols = self.get_bse_symbols()
        
        # Limit for testing
        if max_stocks:
            symbols = symbols[:max_stocks]
            print(f"\n⚠ TEST MODE: Scanning only first {max_stocks} stocks")
        
        total_stocks = len(symbols)
        
        print(f"\nScanning {total_stocks} BSE stocks in parallel...")
        print("-" * 60)
        
        all_stocks = []
        filtered_stocks = []
        failed_count = 0
        gsm_filtered_count = 0
        asm_filtered_count = 0
        
        start_time = time.time()
        
        # Parallel processing with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            futures = {
                executor.submit(self.process_single_stock, symbol, idx, total_stocks): symbol 
                for idx, symbol in enumerate(symbols, 1)
            }
            
            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    stock_data, passed = future.result()
                    
                    if stock_data:
                        all_stocks.append(stock_data)
                        if passed:
                            filtered_stocks.append(stock_data)
                        else:
                            # Track which surveillance list filtered it
                            if stock_data['symbol'] in self.gsm_stocks:
                                gsm_filtered_count += 1
                            elif stock_data['symbol'] in self.asm_stocks:
                                asm_filtered_count += 1
                    else:
                        failed_count += 1
                        
                except Exception as e:
                    failed_count += 1
                    print(f"Task error: {e}")
        
        elapsed_time = time.time() - start_time
        
        # Sort by liquidity (highest first)
        filtered_stocks.sort(key=lambda x: x['liquidity_cr'], reverse=True)
        
        # Save results
        self.save_results(all_stocks, filtered_stocks)
        
        # Print summary
        self.print_summary(total_stocks, len(all_stocks), len(filtered_stocks), 
                          failed_count, elapsed_time, gsm_filtered_count, asm_filtered_count)
        
        return filtered_stocks
    
    def save_results(self, all_stocks, filtered_stocks):
        """Save results to JSON files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save all fetched stocks
        with open(f'all_stocks_{timestamp}.json', 'w') as f:
            json.dump(all_stocks, f, indent=2)
        
        # Save filtered tradeable universe
        with open(f'tradeable_universe_{timestamp}.json', 'w') as f:
            json.dump(filtered_stocks, f, indent=2)
        
        # Save latest as well (overwrite)
        with open('tradeable_universe_latest.json', 'w') as f:
            json.dump(filtered_stocks, f, indent=2)
        
        print(f"\n✓ Results saved to:")
        print(f"  - tradeable_universe_{timestamp}.json")
        print(f"  - tradeable_universe_latest.json")
    
    def print_summary(self, total, fetched, filtered, failed, elapsed_time, gsm_filtered=0, asm_filtered=0):
        """Print scan summary"""
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
        print(f"Time Taken: {elapsed_time:.1f} seconds ({elapsed_time/60:.1f} minutes)")
        print(f"Speed: {total/elapsed_time:.1f} stocks/second")
        print("=" * 60)


if __name__ == "__main__":
    scanner = UniverseScanner()
    
    # For testing, scan first 200 stocks with 20 parallel workers
    # For full scan: max_stocks=None, workers=50 (will take ~5-10 minutes instead of 20)
    tradeable_stocks = scanner.scan_universe(max_stocks=200, workers=20)
    
    # Display top 10 by liquidity
    if tradeable_stocks:
        print("\nTop 10 Most Liquid Stocks:")
        print("-" * 60)
        for i, stock in enumerate(tradeable_stocks[:10], 1):
            print(f"{i}. {stock['symbol']:20} ₹{stock['price']:8.2f}  "
                  f"{stock['liquidity_cr']:8.2f}Cr  ATR: {stock['atr_percent']:.2f}%")
    else:
        print("\n⚠ No stocks passed the filters!")
