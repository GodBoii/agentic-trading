import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import matplotlib.style as style

def load_ndjson(filepath):
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return data

def extract_levels(depth_list, side):
    levels = []
    if not isinstance(depth_list, list): return levels
    for level in depth_list:
        if not isinstance(level, dict): continue
        price = level.get('price') or level.get(f'{side}_price') or level.get(f'{side}Price')
        qty = level.get('quantity') or level.get('qty') or level.get(f'{side}_quantity') or level.get(f'{side}Quantity')
        if price is not None and qty is not None:
            levels.append({'price': float(price), 'quantity': float(qty)})
    return levels

def extract_packet_value(packet, keys):
    for k in keys:
        if k in packet and packet[k] is not None:
            return float(packet[k])
    return None

def main():
    print("Loading data for Bookmap-style chart...")
    data_dir = Path("/app/python-backend/nifty_market_depth/2026-06-23")
    if not data_dir.exists():
        data_dir = Path("python-backend/nifty_market_depth/2026-06-23")
        
    depth_file = data_dir / "depth_200.ndjson"
    full_file = data_dir / "full_market.ndjson"
    
    if not depth_file.exists() or not full_file.exists():
        print("Data files not found.")
        return
        
    depth_data = load_ndjson(depth_file)
    full_data = load_ndjson(full_file)
    print(f"Loaded {len(depth_data)} depth packets and {len(full_data)} full market packets.")

    # Parse Depth Data
    depth_records = []
    best_bids = {}
    best_asks = {}
    
    for packet in depth_data:
        ts_str = packet.get('captured_at_utc')
        side = packet.get('side')
        levels = extract_levels(packet.get('depth'), side)
        if not ts_str or not levels: continue
        
        dt = pd.to_datetime(ts_str)
        # Store for heatmap
        for lvl in levels:
            depth_records.append({
                'timestamp': dt,
                'price': lvl['price'],
                'quantity': lvl['quantity']
            })
            
        # Store best bid/ask
        if side == 'bid':
            best_price = max([l['price'] for l in levels])
            best_bids[dt] = best_price
        else:
            best_price = min([l['price'] for l in levels])
            best_asks[dt] = best_price

    df_depth = pd.DataFrame(depth_records)
    
    bb_df = pd.Series(best_bids).sort_index().to_frame('best_bid')
    ba_df = pd.Series(best_asks).sort_index().to_frame('best_ask')
    best_quotes = bb_df.join(ba_df, how='outer').ffill().bfill()
    
    # Parse Trades Data
    trade_records = []
    last_vol = None
    
    for packet in full_data:
        ts_str = packet.get('captured_at_utc')
        p = packet.get('packet', {})
        if not ts_str or not p: continue
        
        dt = pd.to_datetime(ts_str)
        ltp = extract_packet_value(p, ['LTP', 'last_price', 'lastPrice', 'latest_traded_price'])
        vol = extract_packet_value(p, ['volume', 'Volume', 'total_volume'])
        ltq = extract_packet_value(p, ['LTQ', 'last_traded_quantity', 'lastTradedQuantity'])
        
        if ltp is not None:
            # Estimate trade size if LTQ is missing but volume changed
            trade_qty = 0
            if vol is not None:
                if last_vol is not None and vol > last_vol:
                    trade_qty = vol - last_vol
                last_vol = vol
            
            if trade_qty == 0 and ltq is not None:
                trade_qty = ltq
                
            if trade_qty > 0:
                trade_records.append({
                    'timestamp': dt,
                    'price': ltp,
                    'quantity': trade_qty
                })
                
    df_trades = pd.DataFrame(trade_records)

    # Plotting
    style.use('dark_background')
    fig, ax = plt.subplots(figsize=(18, 10))
    
    # 1. Heatmap Background (Limit Order Book Density)
    # Bookmap uses a colormap where high volume is warm (red/white) and low is cool (blue/black)
    if not df_depth.empty:
        sc = ax.scatter(
            df_depth['timestamp'], df_depth['price'], 
            c=df_depth['quantity'], cmap='ocean', 
            s=40, marker='s', alpha=0.8, edgecolors='none'
        )
        cbar = plt.colorbar(sc, ax=ax, pad=0.01)
        cbar.set_label('Resting Liquidity (Contracts)')

    # 2. Trades (Bubbles)
    if not df_trades.empty:
        # Determine aggressor (Green = buy at ask, Red = sell at bid)
        # We need to map each trade to the closest known best bid/ask
        colors = []
        sizes = []
        for _, trade in df_trades.iterrows():
            t = trade['timestamp']
            p = trade['price']
            q = trade['quantity']
            
            # Find closest quote
            idx = best_quotes.index.get_indexer([t], method='pad')[0]
            if idx >= 0:
                quote = best_quotes.iloc[idx]
                bb = quote['best_bid']
                ba = quote['best_ask']
                
                if p >= ba:
                    colors.append('lime') # Aggressive Buy
                elif p <= bb:
                    colors.append('red') # Aggressive Sell
                else:
                    colors.append('yellow') # Inside spread
            else:
                colors.append('yellow')
            
            # Scale bubble size
            sizes.append(q * 2) # Adjust scale factor as needed
            
        ax.scatter(
            df_trades['timestamp'], df_trades['price'],
            s=sizes, c=colors, alpha=0.9, edgecolors='white', linewidth=0.5, zorder=5
        )

    # 3. Best Bid / Ask Lines
    if not best_quotes.empty:
        ax.plot(best_quotes.index, best_quotes['best_bid'], color='green', linewidth=1, label='Best Bid', zorder=4)
        ax.plot(best_quotes.index, best_quotes['best_ask'], color='red', linewidth=1, label='Best Ask', zorder=4)

    ax.set_title('NIFTY Order Book Heatmap & Trade Bubbles (Bookmap Style)', fontsize=16)
    ax.set_xlabel('Time (UTC)')
    ax.set_ylabel('Price')
    
    # Focus Y Axis
    if not df_depth.empty:
        min_p = df_depth['price'].quantile(0.01)
        max_p = df_depth['price'].quantile(0.99)
        ax.set_ylim(min_p, max_p)

    ax.grid(True, linestyle=':', alpha=0.2, color='white')
    
    output_path = '/app/artifacts/bookmap_style_chart.png' if Path('/app').exists() else 'bookmap_style_chart.png'
    if Path('/app').exists() and not Path('/app/artifacts').exists():
        Path('/app/artifacts').mkdir(exist_ok=True)
        
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"Bookmap style chart saved to: {output_path}")

if __name__ == "__main__":
    main()
