import json
import pandas as pd
import matplotlib.pyplot as plt
import os
from pathlib import Path

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
    """Normalize the keys from Dhan's raw API format"""
    levels = []
    if not isinstance(depth_list, list):
        return levels
        
    for level in depth_list:
        if not isinstance(level, dict):
            continue
            
        # Handle various key names depending on the packet type
        price = level.get('price') or level.get(f'{side}_price') or level.get(f'{side}Price')
        qty = level.get('quantity') or level.get('qty') or level.get(f'{side}_quantity') or level.get(f'{side}Quantity')
        
        if price is not None and qty is not None:
            levels.append({
                'price': float(price),
                'quantity': float(qty)
            })
    return levels

def main():
    print("Loading depth_200.ndjson data...")
    # Target the specific path where your script saves the NDJSON file
    data_dir = Path("/app/python-backend/nifty_market_depth/2026-06-23")
    if not data_dir.exists():
        data_dir = Path("python-backend/nifty_market_depth/2026-06-23")
        
    file_path = data_dir / "depth_200.ndjson"
    
    if not file_path.exists():
        print(f"Error: Could not find data file at {file_path}")
        return
        
    raw_data = load_ndjson(file_path)
    print(f"Loaded {len(raw_data)} WebSocket packets.")
    
    if not raw_data:
        print("No data available to plot.")
        return
        
    records = []
    
    for packet in raw_data:
        timestamp_str = packet.get('captured_at_utc')
        side = packet.get('side')
        depth_array = packet.get('depth')
        
        if not timestamp_str or not side or not depth_array:
            continue
            
        dt = pd.to_datetime(timestamp_str)
        levels = extract_levels(depth_array, side)
        
        for level in levels:
            records.append({
                'timestamp': dt,
                'side': side,
                'price': level['price'],
                'quantity': level['quantity']
            })
            
    df = pd.DataFrame(records)
    print(f"Extracted {len(df)} individual price level data points.")
    
    if df.empty:
        print("No valid price levels parsed.")
        return
        
    # Generate Heatmap Scatter Plot
    print("Generating market depth heatmap chart...")
    plt.figure(figsize=(16, 9))
    
    bids = df[df['side'] == 'bid']
    asks = df[df['side'] == 'ask']
    
    # Plot Bids (Buy orders stacked below current price)
    if not bids.empty:
        scatter_bids = plt.scatter(
            bids['timestamp'], bids['price'], 
            c=bids['quantity'], cmap='Greens', 
            s=5, alpha=0.5, label='Bid Liquidity'
        )
        
    # Plot Asks (Sell orders stacked above current price)
    if not asks.empty:
        scatter_asks = plt.scatter(
            asks['timestamp'], asks['price'], 
            c=asks['quantity'], cmap='Reds', 
            s=5, alpha=0.5, label='Ask Liquidity'
        )

    plt.title('NIFTY Market Depth Heatmap (200-Level WebSocket Stream)', fontsize=16)
    plt.xlabel('Time (UTC)', fontsize=12)
    plt.ylabel('Price', fontsize=12)
    
    # Focus the Y-axis to avoid outliers expanding the chart too much
    min_price = df['price'].quantile(0.01)
    max_price = df['price'].quantile(0.99)
    plt.ylim(min_price, max_price)
    
    plt.grid(True, linestyle='--', alpha=0.3)
    
    # Format the colorbar to show quantity intensity
    cbar_ax = plt.gcf().add_axes([0.92, 0.15, 0.02, 0.7])
    plt.colorbar(scatter_asks, cax=cbar_ax, label='Resting Quantity (Contracts)')
    
    output_path = '/app/artifacts/market_depth_heatmap.png' if Path('/app').exists() else 'market_depth_heatmap.png'
    
    # Ensure artifacts dir exists if inside container
    if Path('/app').exists() and not Path('/app/artifacts').exists():
        Path('/app/artifacts').mkdir(exist_ok=True)
        
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"Chart successfully saved to: {output_path}")

if __name__ == "__main__":
    main()
