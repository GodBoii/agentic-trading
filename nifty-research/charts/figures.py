"""Chart definitions and calculations. All times shown in India Standard Time."""
from __future__ import annotations

import numpy as np
import pandas as pd

COLORS = ["#4bd5ac", "#f28b82", "#79b8ff", "#efc46a", "#c4a7e7", "#aab8c5"]


def values(series) -> list:
    return [None if pd.isna(x) or not np.isfinite(x) else round(float(x), 6) for x in series]


def times(index) -> list[str]:
    return [x.strftime("%Y-%m-%d %H:%M:%S") for x in pd.DatetimeIndex(index)]


def line(x, y, name: str, color: str = COLORS[0], **extra) -> dict:
    return dict(type="scatter", mode="lines", x=list(x), y=values(y), name=name,
                connectgaps=False, line=dict(color=color, width=1.6), **extra)


def bar(x, y, name: str, color=COLORS[0], **extra) -> dict:
    return dict(type="bar", x=list(x), y=values(y), name=name, marker=dict(color=color), **extra)


def wilder(series: pd.Series, period: int) -> pd.Series:
    result = pd.Series(np.nan, index=series.index)
    valid = series.dropna()
    if len(valid) < period:
        return result
    average = valid.iloc[:period].mean()
    result.loc[valid.index[period - 1]] = average
    for index, value in valid.iloc[period:].items():
        average = (average * (period - 1) + value) / period
        result.loc[index] = average
    return result


def indicators(bars: pd.DataFrame) -> pd.DataFrame:
    result = bars.copy()
    for _, group in bars.groupby("run", sort=False):
        close = group["close"]
        delta = close.diff()
        gain, loss = wilder(delta.clip(lower=0), 14), wilder(-delta.clip(upper=0), 14)
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        rsi = rsi.mask((loss == 0) & (gain > 0), 100).mask((loss == 0) & (gain == 0), 50)
        ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
        ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
        macd = ema12 - ema26
        true_range = pd.concat([group["high"] - group["low"],
                                (group["high"] - close.shift()).abs(),
                                (group["low"] - close.shift()).abs()], axis=1).max(axis=1)
        low14, high14 = group["low"].rolling(14).min(), group["high"].rolling(14).max()
        stochastic = (close - low14) / (high14 - low14).replace(0, np.nan) * 100
        calculated = dict(sma20=close.rolling(20).mean(), ema20=close.ewm(span=20, adjust=False, min_periods=20).mean(),
                          std20=close.rolling(20).std(ddof=0), rsi=rsi, macd=macd,
                          signal=macd.ewm(span=9, adjust=False, min_periods=9).mean(),
                          atr=wilder(true_range, 14), stochastic=stochastic,
                          stochastic_d=stochastic.rolling(3).mean(),
                          ret=np.log(close / close.shift()) * 10000,
                          drawdown=(close / close.cummax() - 1) * 100,
                          cvd=group["signed"].cumsum(), cum_volume=group["volume"].cumsum())
        calculated["rv"] = calculated["ret"].rolling(20).std(ddof=1)
        for key, value in calculated.items():
            result.loc[group.index, key] = value
    return result


def heikin_ashi(bars: pd.DataFrame) -> pd.DataFrame:
    result = bars[["open", "high", "low", "close"]].copy() * np.nan
    for _, group in bars.groupby("run", sort=False):
        previous = None
        for stamp, row in group.dropna(subset=["close"]).iterrows():
            close = row[["open", "high", "low", "close"]].mean()
            opening = (row["open"] + row["close"]) / 2 if previous is None else sum(previous) / 2
            result.loc[stamp] = [opening, max(row["high"], opening, close), min(row["low"], opening, close), close]
            previous = opening, close
    return result


def candle(bars: pd.DataFrame, kind: str = "candlestick") -> dict:
    return dict(type=kind, x=times(bars.index), **{k: values(bars[k]) for k in ["open", "high", "low", "close"]},
                name="Nifty futures", increasing=dict(line=dict(color=COLORS[0])), decreasing=dict(line=dict(color=COLORS[1])))


def build_charts(ticks: pd.DataFrame, bars: pd.DataFrame, five: pd.DataFrame,
                 depth: list[dict], options: pd.DataFrame) -> list[dict]:
    charts = []
    b = indicators(bars)
    x = times(b.index)

    def add(key, title, category, question, method, traces, ylabel, **layout):
        charts.append(dict(id=key, title=title, category=category, question=question, method=method,
                           data=traces, layout=dict(yaxis=dict(title=ylabel), xaxis=dict(title="Time, IST"), **layout)))

    add("candles", "Candlestick", "Price", "Where did price open, trade and close each minute?",
        "One-minute OHLC of recorded futures LTP, not Nifty spot. Empty minutes stay blank. Partial candles remain visible; check recording coverage.", [candle(b)], "Futures points")
    add("candles5", "Five-minute candlestick", "Price", "What does the broader intraday structure look like?",
        "Five-minute aggregation of recorded LTP. Bars containing a feed restart are omitted.", [candle(five)], "Futures points")
    add("ohlc", "OHLC bars", "Price", "How do ranges and open-to-close moves compare?",
        "The same four prices as candlesticks, drawn as ticks and vertical ranges.", [candle(b, "ohlc")], "Futures points")
    add("line", "Close and intraminute range", "Price", "Where is the price path within its recorded range?",
        "Minute close with recorded high/low envelope. Lines break at missing candles.",
        [line(x,b["high"],"High",COLORS[5]), line(x,b["low"],"Low",COLORS[5],fill="tonexty",fillcolor="rgba(170,184,197,.1)"),line(x,b["close"],"Close")], "Futures points")
    add("ha", "Heikin-Ashi", "Price", "What trend remains after smoothing candle bodies?",
        "Synthetic candles: HA close is OHLC/4; HA open is the prior HA open/close average. Reset after gaps. These are not executable prices.", [candle(heikin_ashi(b))], "Synthetic points")
    rx, ry, rc = [], [], []
    for _, group in b.groupby("run"):
        close = group["close"].dropna()
        if close.empty: continue
        anchor = close.iloc[0]
        for price in close.iloc[1:]:
            while abs(price-anchor) >= 20:
                direction = 1 if price > anchor else -1
                anchor += direction*20
                rx.append(len(rx)+1); ry.append(anchor); rc.append(COLORS[0] if direction>0 else COLORS[1])
        rx.append(len(rx)+1); ry.append(np.nan); rc.append(COLORS[5])
    add("renko", "Close-based Renko", "Price", "How many fixed 20-point moves occurred?",
        "Simplified 20-point bricks from minute closes, restarting after gaps. Brick index replaces time. Intraminute paths and classic two-brick reversal rules are not reconstructed.",
        [dict(type="scatter",x=rx,y=values(ry),mode="lines+markers",line=dict(shape="hv",color=COLORS[5]),marker=dict(color=rc,size=7),name="20-point bricks")], "Synthetic points")
    charts[-1]["layout"]["xaxis"] = dict(title="Brick index, time is uneven")
    add("averages", "Moving averages", "Indicators", "Is short-term price above or below its recent trend?",
        "SMA 20 and EMA 20 on minute closes. Warm-up is blank; calculations restart after gaps or partial candles.",
        [line(x,b["close"],"Close",COLORS[5]),line(x,b["sma20"],"SMA 20",COLORS[3]),line(x,b["ema20"],"EMA 20")], "Futures points")
    add("bands", "Bollinger bands", "Indicators", "How far is price from its recent average?",
        "SMA 20 plus/minus two population standard deviations of minute closes. Band touches are descriptive, not trade signals.",
        [line(x,b["sma20"]+2*b["std20"],"Upper band",COLORS[2]),line(x,b["sma20"]-2*b["std20"],"Lower band",COLORS[2],fill="tonexty",fillcolor="rgba(121,184,255,.08)"),line(x,b["sma20"],"SMA 20",COLORS[3]),line(x,b["close"],"Close")], "Futures points")
    add("rsi", "RSI", "Indicators", "How persistent are recent gains relative to losses?",
        "14-period Wilder RSI. Initial average uses 14 changes. Flat windows are 50. Dashed lines mark 30 and 70.",
        [line(x,b["rsi"],"RSI 14")], "RSI, 0 to 100", shapes=[dict(type="line",xref="paper",x0=0,x1=1,y0=y,y1=y,line=dict(color=COLORS[5],dash="dot")) for y in [30,70]])
    add("macd", "MACD", "Indicators", "Is momentum accelerating or fading?",
        "EMA 12 minus EMA 26, EMA 9 signal, and their difference. EMA uses adjust=False and span-length warm-up.",
        [bar(x,b["macd"]-b["signal"],"Histogram",COLORS[5]),line(x,b["macd"],"MACD"),line(x,b["signal"],"Signal",COLORS[3])], "Futures points")
    add("stochastic", "Stochastic oscillator", "Indicators", "Where is the close within the last 14-minute range?",
        "%K = 100 × (close-low14)/(high14-low14); %D is a 3-period average. Zero-width ranges are missing.",
        [line(x,b["stochastic"],"%K"),line(x,b["stochastic_d"],"%D",COLORS[3])], "Range percentile")
    add("atr", "Average true range", "Volatility", "How wide is a typical recent price move?",
        "14-period Wilder average of max(high-low, abs(high-prior close), abs(low-prior close)). Gaps reset the calculation.",[line(x,b["atr"],"ATR 14",COLORS[3])], "Futures points")
    add("rv", "Rolling realised volatility", "Volatility", "When did minute returns become more variable?",
        "20-minute sample standard deviation of one-minute log returns, in basis points. Not annualised and not implied volatility.",[line(x,b["rv"],"20-minute realised volatility",COLORS[3])], "Return standard deviation, bps")
    add("returns", "Minute returns", "Volatility", "When did the largest recorded one-minute moves occur?",
        "10,000 × log(close/prior close). Changes across feed gaps are excluded.",[bar(x,b["ret"],"Log return",[COLORS[0] if r>=0 else COLORS[1] for r in b["ret"]])], "Return, bps")
    add("distribution", "Return distribution", "Volatility", "Are recorded minute moves clustered or spread out?",
        "Histogram of valid within-segment minute log returns. A single session cannot establish the market's tail distribution.",
        [dict(type="histogram",x=values(b["ret"].dropna()),nbinsx=35,marker=dict(color=COLORS[2]),name="Minute returns")], "Minute count")
    charts[-1]["layout"]["xaxis"] = dict(title="One-minute log return, bps")
    add("drawdown", "Decline from running high", "Volatility", "How far below the recorded running high did price fall?",
        "100 × (close/running maximum-1), restarted after gaps. This is a price decline, not strategy or account drawdown.",
        [line(x,b["drawdown"],"Decline",COLORS[1],fill="tozeroy",fillcolor="rgba(242,139,130,.12)")], "Change from running high, %")
    add("volume", "Interval volume", "Volume and flow", "When was reported trading activity highest?",
        "Differences of cumulative exchange volume, grouped by minute. The first packet after a reset contributes zero; activity during gaps is unknown.",
        [bar(x,b["volume"],"Reported interval volume",COLORS[2])], "Underlying units")
    add("cumvolume", "Cumulative recorded volume", "Volume and flow", "How much reported volume accumulated inside each continuous segment?",
        "Sum of accepted nonnegative volume increments. Restarted after feed gaps and counter resets; it excludes unobserved volume.",
        [line(x,b["cum_volume"],"Recorded cumulative volume",COLORS[2])], "Underlying units")
    weighted = ticks.assign(pv=ticks["price"]*ticks["volume"])
    weighted["vwap"] = weighted.groupby("segment")["pv"].cumsum()/weighted.groupby("segment")["volume"].cumsum().replace(0,np.nan)
    vwap = weighted["vwap"].resample("min").last().reindex(b.index)
    add("vwap", "Sampled VWAP proxy", "Volume and flow", "Where is price relative to the observed volume-weighted path?",
        "Each cumulative-volume increment is assigned to that packet's LTP. This is a sampled proxy, not exchange-exact VWAP. Resets after gaps.",
        [line(x,b["close"],"Close",COLORS[5]),line(x,vwap,"Sampled VWAP",COLORS[3])], "Futures points")
    profile = ticks.groupby((ticks["price"]/5).round()*5)["volume"].sum()
    add("profile", "Sampled volume profile", "Volume and flow", "At which observed price buckets did activity concentrate?",
        "Five-point buckets. Each interval's reported volume is assigned to its last sampled price. It cannot reconstruct exact volume traded at each price.",
        [dict(type="bar",x=values(profile),y=values(profile.index),orientation="h",marker=dict(color=COLORS[2]),name="Sampled volume")], "Futures price bucket")
    charts[-1]["layout"]["xaxis"] = dict(title="Underlying units, sampled allocation")
    add("delta", "Estimated signed volume", "Volume and flow", "Which minutes had more estimated buying or selling pressure?",
        "Quote rule, then tick rule, applied to interval volume. Unchanged interior trades remain unclassified. This feed does not identify aggressors for every trade.",
        [bar(x,b["signed"],"Estimated buy minus sell",[COLORS[0] if v>=0 else COLORS[1] for v in b["signed"]]),bar(x,b["unknown"],"Unclassified volume",COLORS[5])], "Estimated signed units")
    add("cvd", "Estimated cumulative delta", "Volume and flow", "Does estimated pressure persist over a continuous recording?",
        "Cumulative estimated signed interval volume. Resets after gaps. Aggregated packets and unknown trade direction limit interpretation.",
        [line(x,b["cvd"],"Estimated cumulative delta")], "Estimated signed units")
    add("volume_return", "Volume versus absolute return", "Volume and flow", "Did higher recorded activity coincide with larger minute moves?",
        "Same-minute association, not a forecast or causal test. Only within-segment returns are used.",
        [dict(type="scatter",mode="markers",x=values(b["volume"]),y=values(b["ret"].abs()),marker=dict(color=COLORS[2],size=5,opacity=.65),name="Minute")], "Absolute return, bps")
    charts[-1]["layout"]["xaxis"] = dict(title="Reported interval volume, units")
    add("oi", "Futures open interest", "Liquidity", "How did outstanding futures positions change?",
        "Last reported OI per minute. OI counts outstanding contracts in the feed's units; it does not reveal which side initiated a position.",
        [line(x,b["oi"],"Futures OI",COLORS[4])], "Reported OI units")
    oi_delta = b.groupby("run")["oi"].diff()
    add("oi_price", "Price change versus OI change", "Liquidity", "Which combinations of price and position changes appeared?",
        "Same-minute price return against OI difference. Quadrants do not prove long building, short covering, or trader identity.",
        [dict(type="scatter",mode="markers",x=values(oi_delta),y=values(b["ret"]),marker=dict(color=COLORS[4],size=5,opacity=.65),name="Minute")], "Price return, bps")
    charts[-1]["layout"]["xaxis"] = dict(title="OI change, reported units")
    add("spread", "Bid-ask spread", "Liquidity", "When was the observed top of book more expensive to cross?",
        "Median accepted ask minus bid per minute. No assumption of fills or capacity is made.",[line(x,b["spread"],"Median spread",COLORS[1])], "Futures points")
    add("micro", "Microprice deviation", "Liquidity", "Which side had more top-level displayed quantity?",
        "Quantity-weighted best bid/ask price minus midpoint, median per minute. Displayed size can change or cancel before execution.",
        [line(x,b["micro"],"Microprice minus midpoint",COLORS[3])], "Futures points")
    add("coverage", "Recording coverage", "Coverage", "Which minutes are complete, partial or missing?",
        "Complete requires a packet within 2 seconds of both minute boundaries. Gaps are never forward-filled. Warm-up indicators restart after partial or missing bars.",
        [bar(x,b["count"],"Accepted packets",[COLORS[0] if complete else COLORS[3] if count>0 else COLORS[1] for complete,count in zip(b["complete"],b["count"].fillna(0))])], "Packet count")
    if depth:
        add_depth_charts(depth, add, charts)
    if not options.empty:
        add_option_charts(options, add, charts)
    return charts


def add_depth_charts(depth: list[dict], add, charts: list[dict]) -> None:
    stamps = pd.DatetimeIndex([d["time"] for d in depth])
    # Reindex to all minutes so a missing snapshot creates a visible break.
    index = pd.date_range(stamps.min().floor("min"),stamps.max().floor("min"),freq="min")
    x = times(index)
    imbalances = {}
    for size in [5,20,200]:
        raw = []
        for d in depth:
            buy = sum(q for _,q in d["bid"][:size]); sell=sum(q for _,q in d["ask"][:size])
            raw.append((buy-sell)/(buy+sell) if buy+sell else np.nan)
        imbalances[size] = pd.Series(raw,index=stamps.floor("min")).reindex(index)
    add("imbalance", "Nearby versus deep-book imbalance", "Depth", "Does near-price liquidity agree with the wider book?",
        "(Bid quantity-ask quantity)/(bid+ask), for 5, 20 and up to 200 available levels. One fresh, uncrossed pair per minute; side ages at most 1 second.",
        [line(x,imbalances[n],f"{n} levels",COLORS[i]) for i,n in enumerate([5,20,200])], "Quantity imbalance, -1 to +1")
    distances = np.arange(-50,51,2)
    matrix = np.full((len(distances)-1,len(index)),np.nan)
    walls = {"bid":[],"ask":[]}
    for d in depth:
        j=index.get_loc(pd.Timestamp(d["time"]).floor("min"))
        mid=(d["bid"][0][0]+d["ask"][0][0])/2
        column=np.zeros(len(distances)-1)
        for side in ["bid","ask"]:
            for price,quantity in d[side]:
                offset=price-mid
                k=np.searchsorted(distances,offset,side="right")-1
                if 0<=k<len(column): column[k]+=quantity*(1 if side=="bid" else -1)
            walls[side].append(max((q for p,q in d[side] if abs(p-mid)<=25),default=0))
        matrix[:,j]=column
    add("depth_heatmap", "Liquidity distance heatmap", "Depth", "Where did displayed size persist relative to the moving midpoint?",
        "Two-point distance buckets within ±50 points. Green is bid size, red is ask size. One snapshot per minute, not summed messages. Blank columns mean no valid pair; zero means no displayed size in the bucket.",
        [dict(type="heatmap",x=x,y=values((distances[:-1]+distances[1:])/2),z=[values(row) for row in matrix],
              colorscale=[[0,COLORS[1]],[.5,"#111b26"],[1,COLORS[0]]],zmid=0,colorbar=dict(title="Signed size"))], "Distance from midpoint, points")
    add("walls", "Largest nearby displayed level", "Depth", "Did large displayed levels survive successive snapshots?",
        "Largest individual bid/ask level within 25 points of midpoint, sampled once per minute. Persistence of size does not establish trader identity or an executed order.",
        [line(x,pd.Series(walls[s],index=stamps.floor("min")).reindex(index),s.title(),COLORS[i]) for i,s in enumerate(["bid","ask"])], "Displayed units")
    final=depth[-1]
    label=pd.Timestamp(final["time"]).strftime("%H:%M:%S IST")
    add("ladder", "Depth ladder", "Depth", "How much displayed liquidity sits at each nearby price?",
        f"Final valid paired snapshot at {label}. Nearest 30 levels per side. Quantities are displayed orders, not executed trades.",
        [dict(type="bar",orientation="h",y=values([p for p,q in final[s][:30]]),x=values([q*(1 if s=="ask" else -1) for p,q in final[s][:30]]),marker=dict(color=COLORS[i]),name=s.title()) for i,s in enumerate(["bid","ask"])], "Futures price",barmode="overlay")
    charts[-1]["layout"]["xaxis"]=dict(title="Displayed units, bids left / asks right")
    add("cumulative_depth", "Cumulative depth curve", "Depth", "How quickly does displayed quantity accumulate away from the best price?",
        f"Final valid paired snapshot at {label}. Cumulative quantities over available levels. This is not a guaranteed executable market-impact curve.",
        [line([p for p,q in final[s]],np.cumsum([q for p,q in final[s]]),s.title(),COLORS[i]) for i,s in enumerate(["bid","ask"])], "Cumulative displayed units")
    charts[-1]["layout"]["xaxis"]=dict(title="Futures price")


def add_option_charts(options: pd.DataFrame, add, charts: list[dict]) -> None:
    expiry=options["expiry"].min()
    o=options.loc[options["expiry"]==expiry].copy()
    o["mid"]=(o["bid"]+o["ask"])/2
    o["spread"]=o["ask"]-o["bid"]
    # Preserve security IDs even if two contracts happen to share a display label.
    groups=list(o.groupby(["strike","kind","sid"]))
    grid=pd.date_range(o["cutoff"].min(),o["cutoff"].max(),freq="min")
    x=times(grid)
    prefix=f"Expiry {expiry}. Only captured strikes, not the full chain. Quotes sampled backward within 2 seconds of each minute cutoff. "
    for key,title,column,ylabel,question in [
        ("option_premiums","Option premium paths","mid","Premium points","Which captured contracts gained or lost premium?"),
        ("option_oi","Option OI paths","oi","Reported OI units","Where did outstanding option positions accumulate?"),
        ("option_spreads","Option bid-ask spreads","spread","Spread, premium points","Which recorded option quotes were wider?")]:
        traces=[line(x,g.set_index("cutoff")[column].reindex(grid),f"{strike:g} {kind}",COLORS[i%len(COLORS)]) for i,((strike,kind,sid),g) in enumerate(groups)]
        add(key,title,"Options",question,prefix+("Midpoint is indicative, not an execution price." if column=="mid" else "Missing or stale samples stay blank."),traces,ylabel)
    final=o.loc[o["cutoff"]==o["cutoff"].max()]
    stamp=final["cutoff"].iloc[0].strftime("%H:%M IST")
    add("oi_strike","Captured-strike OI","Options","How is recorded OI distributed across strikes?",
        prefix+f"Latest cutoff {stamp}. Only contracts with fresh quotes at that cutoff appear.",
        [bar(g["strike"].tolist(),g["oi"],kind,COLORS[i]) for i,(kind,g) in enumerate(final.groupby("kind"))],"Reported OI units",barmode="group")
    charts[-1]["layout"]["xaxis"]=dict(title="Captured strike")
    oi_change=[]
    for (strike,kind,sid),g in groups:
        oi_change.append(dict(strike=strike,kind=kind,change=g["oi"].iloc[-1]-g["oi"].iloc[0]))
    changes=pd.DataFrame(oi_change)
    add("oi_change","OI change by captured contract","Options","Which contracts changed OI over their observed interval?",
        prefix+"Last fresh OI minus first fresh OI for each fixed security ID. Observation start/end times can differ. This is not change from prior-day closing OI.",
        [bar(g["strike"].tolist(),g["change"],kind,COLORS[i]) for i,(kind,g) in enumerate(changes.groupby("kind"))],"OI change, reported units",barmode="group")
    charts[-1]["layout"]["xaxis"]=dict(title="Captured strike")
    contracts=o[["strike","kind","sid"]].drop_duplicates()
    count=o.groupby("cutoff").size()
    totals=o.groupby(["cutoff","kind"])["oi"].sum().unstack()
    if {"CE","PE"} <= set(totals):
        pcr=(totals["PE"]/totals["CE"].replace(0,np.nan)).where(count==len(contracts)).reindex(grid)
        add("pcr","Captured-basket put/call OI ratio","Options","How did put OI compare with call OI in the recorded basket?",
            prefix+"Sum put OI / sum call OI. Shown only when every contract in this session's captured basket is fresh at the same cutoff. Never a full-market PCR.",
            [line(x,pcr,"Captured-basket PCR",COLORS[4])],"Put OI / call OI")
    pairs=o.pivot_table(index="cutoff",columns=["strike","kind"],values="mid",aggfunc="last")
    paired=[s for s in sorted(o["strike"].unique()) if (s,"CE") in pairs and (s,"PE") in pairs]
    if paired:
        add("straddles","Fixed-strike straddle premium","Options","How did the combined call and put midpoint change?",
            prefix+"Call midpoint plus put midpoint at each fixed strike. Both legs must be fresh at the same cutoff. The selected strike never rolls with ATM.",
            [line(x,(pairs[(s,"CE")]+pairs[(s,"PE")]).reindex(grid),f"{s:g}",COLORS[i%len(COLORS)]) for i,s in enumerate(paired)],"Combined midpoint, points")
        add("synthetic","Synthetic forward proxy by strike","Options","Do call/put prices imply similar forward levels across captured strikes?",
            prefix+"Strike + call midpoint - put midpoint, with discount factor assumed 1. This is an approximate same-expiry synthetic forward, not spot, futures basis, or an arbitrage claim.",
            [line(x,(s+pairs[(s,"CE")]-pairs[(s,"PE")]).reindex(grid),f"{s:g}",COLORS[i%len(COLORS)]) for i,s in enumerate(paired)],"Synthetic forward proxy, points")
    heat=o.pivot_table(index=["strike","kind"],columns="cutoff",values="mid",aggfunc="last").reindex(columns=grid)
    add("premium_heatmap","Option premium heatmap","Options","Which strikes and option sides retained more premium through the session?",
        prefix+"Midpoint premium at fresh minute cutoffs. Missing observations are blank. Colour scales compare premiums, not IV.",
        [dict(type="heatmap",x=x,y=[f"{s:g} {k}" for s,k in heat.index],z=[values(r) for r in heat.to_numpy()],colorscale="Cividis",colorbar=dict(title="Premium"))],"Captured contract")
    add_payoff_chart(final,prefix,stamp,add,charts)


def add_payoff_chart(final: pd.DataFrame,prefix: str,stamp: str,add,charts: list[dict]) -> None:
    quotes={(r.strike,r.kind):(r.bid,r.ask) for r in final.itertuples()}
    strikes=sorted({s for s,k in quotes if (s,"CE") in quotes and (s,"PE") in quotes})
    if len(strikes)<3:
        return
    center=len(strikes)//2
    lo,atm,hi=strikes[center-1:center+2]
    definitions={"Long call":[(atm,"CE",1)],"Long put":[(atm,"PE",1)],
                 "Long straddle":[(atm,"CE",1),(atm,"PE",1)],"Short straddle":[(atm,"CE",-1),(atm,"PE",-1)],
                 "Long strangle":[(lo,"PE",1),(hi,"CE",1)],"Short strangle":[(lo,"PE",-1),(hi,"CE",-1)],
                 "Bull call spread":[(atm,"CE",1),(hi,"CE",-1)],"Bear put spread":[(atm,"PE",1),(lo,"PE",-1)],
                 "Iron butterfly":[(atm,"CE",-1),(atm,"PE",-1),(lo,"PE",1),(hi,"CE",1)]}
    if center>=2 and center+2<len(strikes):
        definitions["Iron condor"]=[(lo,"PE",-1),(hi,"CE",-1),(strikes[center-2],"PE",1),(strikes[center+2],"CE",1)]
    settlement=np.linspace(lo-250,hi+250,301)
    traces=[]
    for i,(name,legs) in enumerate(definitions.items()):
        pnl=np.zeros_like(settlement)
        for strike,kind,quantity in legs:
            bid,ask=quotes[strike,kind]
            intrinsic=np.maximum((settlement-strike) if kind=="CE" else (strike-settlement),0)
            pnl+=quantity*(intrinsic-(ask if quantity>0 else bid))
        traces.append(line(settlement.tolist(),pnl,name,COLORS[i%len(COLORS)]))
    legs_text="; ".join(f"{name}: "+", ".join(f"{'buy' if q>0 else 'sell'} {s:g} {k}" for s,k,q in legs) for name,legs in definitions.items())
    add("payoffs","Strategy expiry payoff comparison","Options","How do common structures respond to the eventual settlement index?",
        prefix+f"Hypothetical entries at {stamp}, buys at ask and sells at bid. P&L per option unit at expiry, before costs. No margin or intraday mark-to-market model; naked shorts have substantial tail risk. "+legs_text,
        traces,"Expiry P&L, points per option unit")
    charts[-1]["layout"]["xaxis"]=dict(title="Hypothetical Nifty settlement index, points")
