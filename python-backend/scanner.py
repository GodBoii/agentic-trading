import pandas as pd
import numpy as np
import random
from datetime import datetime
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

# --- Configuration ---
NIFTY_TICKER = "^NSEI"
HISTORY_PERIOD = "1y"

NIFTY_STOCKS_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "HINDUNILVR.NS", 
    "ITC.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "LT.NS", "SBIN.NS",
    "ASIANPAINT.NS", "BAJFINANCE.NS", "HINDALCO.NS", "AXISBANK.NS", "SUNPHARMA.NS",
    "MARUTI.NS", "TATAMOTORS.NS", "TITAN.NS", "POWERGRID.NS", "ONGC.NS",
    "NESTLEIND.NS", "ADANIPORTS.NS", "ULTRACEMCO.NS", "BHARTIARTL.NS", "DRREDDY.NS",
    "HCLTECH.NS", "GRASIM.NS", "INDUSINDBK.NS", "NTPC.NS", "JSWSTEEL.NS",
    "SHREECEM.NS", "TECHM.NS", "HEROMOTOCO.NS", "EICHERMOT.NS", "WIPRO.NS",
    "M&M.NS", "BRITANNIA.NS", "DIVISLAB.NS", "TATASTEEL.NS", "UPL.NS",
    "APOLLOHOSP.NS", "CIPLA.NS", "TATACONSUM.NS", "BPCL.NS", "IOC.NS",
    "GAIL.NS", "INDIGO.NS", "DLF.NS"
]

# --- Optimized Technical Indicators ---
def calculate_ema(data, period):
    return data.ewm(span=period, adjust=False).mean()

def calculate_atr(df, period=14):
    high, low, close = df['High'].values, df['Low'].values, df['Close'].values
    tr = np.maximum.reduce([
        high - low,
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1))
    ])
    tr[0] = high[0] - low[0]
    return pd.Series(tr, index=df.index).ewm(span=period, adjust=False).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain, index=series.index).ewm(span=period, adjust=False).mean()
    avg_loss = pd.Series(loss, index=series.index).ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_bb_width(series, window=20, num_std=2):
    ma = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    return ((std * num_std * 2) / ma).fillna(0)

def calculate_beta(stock_returns, index_returns):
    combined = pd.concat([stock_returns, index_returns], axis=1).dropna()
    if len(combined) < 30:
        return 0.0
    cov_matrix = np.cov(combined.iloc[:, 0], combined.iloc[:, 1])
    return cov_matrix[0, 1] / cov_matrix[1, 1] if cov_matrix[1, 1] != 0 else 0.0

# --- Data Loading ---
def load_data_optimized(tickers, index_ticker, period):
    print(f"Fetching data for {len(tickers)} stocks...")
    
    all_tickers = tickers + [index_ticker]
    data = yf.download(all_tickers, period=period, progress=False, 
                       auto_adjust=True, threads=True, group_by='ticker')
    
    if data.empty:
        return {}, pd.DataFrame()
    
    nifty_returns = data[index_ticker]['Close'].pct_change().dropna()
    sectors = ['Banking', 'IT', 'FMCG', 'Auto', 'Pharma', 'Oil & Gas', 'Metal', 'Cement', 'Energy']
    
    historical_data = {}
    records = []
    
    print("Processing stocks...", end='', flush=True)
    
    for ticker in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                stock_df = data[ticker].copy()
            else:
                stock_df = data.copy()
            
            if len(stock_df) < 200:
                continue
            
            stock_df['Returns'] = stock_df['Close'].pct_change()
            beta = calculate_beta(stock_df['Returns'], nifty_returns)
            
            latest = stock_df.iloc[-1]
            avg_vol = stock_df['Volume'].iloc[:-1].mean()
            avg_turnover = (stock_df['Close'] * stock_df['Volume']).iloc[:-1].mean()
            
            historical_data[ticker] = stock_df
            records.append({
                'Symbol': ticker,
                'Sector': random.choice(sectors),
                'Beta': beta,
                'Price': latest['Close'],
                'AvgDailyVolume': avg_vol,
                'AvgDailyTurnover': avg_turnover,
                'CurrentVolume': latest['Volume'],
            })
            
            print('.', end='', flush=True)
            
        except Exception:
            continue
    
    print(" Done!")
    return historical_data, pd.DataFrame(records)

# --- Agent Class ---
class StockSortingAgent:
    def __init__(self, historical_data, universe_df, config, strategy_name):
        self.hist_data = historical_data
        self.universe_df = universe_df
        self.config = config
        self.strategy_name = strategy_name
        self.filter_stats = {}
    
    def calculate_all_indicators(self):
        indicators_list = []
        
        for symbol in self.universe_df['Symbol']:
            if symbol not in self.hist_data:
                continue
            
            df = self.hist_data[symbol]
            close = df['Close']
            
            ema20 = calculate_ema(close, 20).iloc[-1]
            ema50 = calculate_ema(close, 50).iloc[-1]
            atr = calculate_atr(df, 14).iloc[-1]
            rsi = calculate_rsi(close, 14).iloc[-2]
            bb_width = calculate_bb_width(close, 20, 2).iloc[-1]
            avg_vol_10d = df['Volume'].iloc[-11:-1].mean()
            
            indicators_list.append({
                'Symbol': symbol,
                'Close': close.iloc[-1],
                'EMA20': ema20,
                'EMA50': ema50,
                'ATR_Pct': atr / close.iloc[-1],
                'RSI': rsi,
                'BB_Width': bb_width,
                'AvgVol10d': avg_vol_10d
            })
        
        return pd.DataFrame(indicators_list)
    
    def apply_filters(self):
        df = self.universe_df.copy()
        cfg = self.config
        self.filter_stats['initial'] = len(df)
        
        # Liquidity
        df = df[(df['AvgDailyVolume'] > cfg['MIN_VOL']) & 
                (df['AvgDailyTurnover'] > cfg['MIN_TURNOVER'])].copy()
        self.filter_stats['liquidity'] = len(df)
        
        if df.empty:
            return pd.DataFrame()
        
        # Calculate indicators
        indicators = self.calculate_all_indicators()
        df = df.merge(indicators, on='Symbol', how='inner')
        
        if df.empty:
            return pd.DataFrame()
        
        # Volatility
        df = df[(df['ATR_Pct'] >= cfg['ATR_MIN']) & 
                (df['ATR_Pct'] <= cfg['ATR_MAX']) &
                (df['BB_Width'] > 0.05)].copy()
        self.filter_stats['volatility'] = len(df)
        
        if df.empty:
            return pd.DataFrame()
        
        # Trend & Momentum - FIXED LOGIC
        trend_mask = (df['Close'] > df['EMA20']) & (df['EMA20'] > df['EMA50'])
        rsi_mask = (df['RSI'] >= cfg['RSI_MIN']) & (df['RSI'] <= cfg['RSI_MAX'])
        volume_mask = df['CurrentVolume'] > (df['AvgVol10d'] * cfg['VOL_MULT'])
        
        # Must have trend AND either good RSI or volume surge
        df = df[trend_mask & (rsi_mask | volume_mask)].copy()
        self.filter_stats['trend_momentum'] = len(df)
        
        if df.empty:
            return pd.DataFrame()
        
        # Beta - STRICT ENFORCEMENT
        df = df[df['Beta'] >= cfg['MIN_BETA']].copy()
        self.filter_stats['beta'] = len(df)
        
        return df
    
    def rank_stocks(self, df):
        if df.empty:
            return pd.DataFrame()
        
        # Scoring logic
        atr_diff = np.abs(df['ATR_Pct'] - cfg['OPTIMAL_ATR'])
        df['VolScore'] = np.maximum(0, 30 - (atr_diff / 0.001))
        
        df['MomScore'] = 20
        df.loc[df['CurrentVolume'] > 2 * df['AvgVol10d'], 'MomScore'] += 10
        
        # RSI bonus (favor 50-60 range)
        rsi_optimal = np.abs(df['RSI'] - 55)
        df['RSIScore'] = np.maximum(0, 15 - rsi_optimal)
        
        df['Score'] = df['VolScore'] + df['MomScore'] + df['RSIScore']
        
        return df.nlargest(5, 'Score')
    
    def run(self):
        filtered = self.apply_filters()
        return self.rank_stocks(filtered)

# --- Main Execution ---
if __name__ == '__main__':
    start_time = datetime.now()
    
    historical_data, universe_df = load_data_optimized(
        NIFTY_STOCKS_UNIVERSE, NIFTY_TICKER, HISTORY_PERIOD
    )
    
    if universe_df.empty:
        print("Error: No data available")
        exit()
    
    # OPTIMIZED PARAMETERS FOR BEST RESULTS
    scenarios = {
        "CONSERVATIVE (Safe & Steady)": {
            'MIN_VOL': 100000, 'MIN_TURNOVER': 50000000,
            'ATR_MIN': 0.012, 'ATR_MAX': 0.020, 'OPTIMAL_ATR': 0.016,
            'RSI_MIN': 40, 'RSI_MAX': 65, 
            'VOL_MULT': 1.0, 'MIN_BETA': 0.8
        },
        "BALANCED (Recommended)": {
            'MIN_VOL': 500000, 'MIN_TURNOVER': 100000000,
            'ATR_MIN': 0.018, 'ATR_MAX': 0.028, 'OPTIMAL_ATR': 0.023,
            'RSI_MIN': 45, 'RSI_MAX': 65,
            'VOL_MULT': 1.2, 'MIN_BETA': 0.85
        },
        "AGGRESSIVE (High Risk-Reward)": {
            'MIN_VOL': 800000, 'MIN_TURNOVER': 150000000,
            'ATR_MIN': 0.022, 'ATR_MAX': 0.040, 'OPTIMAL_ATR': 0.030,
            'RSI_MIN': 48, 'RSI_MAX': 68,
            'VOL_MULT': 1.3, 'MIN_BETA': 0.9
        }
    }
    
    print(f"\n{'='*85}")
    print(f"{'🎯 INTRADAY STOCK SCANNER - OPTIMIZED RESULTS':^85}")
    print(f"{'='*85}\n")
    
    all_results = {}
    
    for strategy_name, config in scenarios.items():
        # Save config in global scope for scoring function
        cfg = config
        
        agent = StockSortingAgent(historical_data, universe_df, config, strategy_name)
        results = agent.run()
        all_results[strategy_name] = results
        
        print(f">>> {strategy_name}")
        print(f"    Filters: {agent.filter_stats.get('initial', 0)} → "
              f"{agent.filter_stats.get('liquidity', 0)} → "
              f"{agent.filter_stats.get('volatility', 0)} → "
              f"{agent.filter_stats.get('trend_momentum', 0)} → "
              f"{agent.filter_stats.get('beta', 0)} stocks")
        
        if results.empty:
            print("    ⚠️  No candidates match criteria\n")
        else:
            output = results[['Symbol', 'Price', 'ATR_Pct', 'RSI', 'Beta', 'Score']].copy()
            output['ATR%'] = (output['ATR_Pct'] * 100).round(2)
            output['Price'] = output['Price'].round(2)
            output['RSI'] = output['RSI'].round(1)
            output['Beta'] = output['Beta'].round(2)
            output['Score'] = output['Score'].round(1)
            
            display = output[['Symbol', 'Price', 'ATR%', 'RSI', 'Beta', 'Score']]
            print(display.to_string(index=False))
            
            # Highlight best pick
            best = display.iloc[0]
            print(f"    ⭐ BEST PICK: {best['Symbol']} (Score: {best['Score']})")
            print()
    
    