"""Offline September 9 chart coverage and causal feature audit. No broker calls."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "progress/ranking-research-2026-09-10/chart-review"


def features(bars: list[dict], timestamp: float) -> dict:
    prior = [b for b in bars if b["t"] + 60 <= timestamp and b["t"] >= timestamp - 16 * 60]
    result = {"prior_minutes": len(prior)}
    for minutes in (5, 15):
        window = [b for b in prior if b["t"] >= timestamp - (minutes + 1) * 60]
        if len(window) < minutes:
            continue
        closes = np.array([window[0]["o"]] + [b["c"] for b in window])
        path = np.abs(np.diff(closes)).sum()
        result[f"pre_return_{minutes}"] = 100 * (closes[-1] / closes[0] - 1)
        result[f"pre_efficiency_{minutes}"] = abs(closes[-1] - closes[0]) / path if path else 0
        result[f"pre_range_{minutes}"] = 100 * (max(b["h"] for b in window) - min(b["l"] for b in window)) / closes[-1]
    if len(prior) >= 15:
        recent = sum(b["volume"] for b in prior[-3:]) / 3
        earlier = sum(b["volume"] for b in prior[-15:-3]) / 12
        result["volume_ratio_3_to_12"] = recent / earlier if earlier > 0 else None
    return result


def outcome(bars: list[dict], timestamp: float, direction: str) -> dict:
    # Enter at the first later minute open, never the signal minute's already-seen high/low.
    future = [b for b in bars if b["t"] > timestamp]
    if not future or future[0]["t"] - timestamp > 90:
        return {}
    entry = future[0]["o"]
    result = {"proxy_entry_time": future[0]["t"], "proxy_entry": entry}
    sign = 1 if direction == "LONG" else -1
    for minutes in (5, 15, 30):
        window = [b for b in future if b["t"] < future[0]["t"] + minutes * 60]
        if len(window) < minutes * 0.8:
            continue
        ret = 100 * (window[-1]["c"] / entry - 1)
        up = 100 * (max(b["h"] for b in window) / entry - 1)
        down = 100 * (1 - min(b["l"] for b in window) / entry)
        result.update({f"return_{minutes}": ret, f"abs_return_{minutes}": abs(ret),
                       f"direction_return_{minutes}": sign * ret,
                       f"max_excursion_{minutes}": max(up, down),
                       f"range_{minutes}": up + down})
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / "september-09-session-review/data.json").read_text())
    evidence = json.loads((ROOT / "python-backend/results/research/session-audit-2026-09-09/evidence.json").read_text())
    raw = {s["event_id"]: s for s in evidence["signals"]}
    events = []
    stocks = []
    plt.rcParams.update({"font.size": 8})
    for i, stock in enumerate(data["stocks"]):
        bars = stock["bars"]
        for signal in stock["signals"]:
            run = signal.get("run") or {}
            source = raw[signal["id"]]
            row = {"key": stock["key"], "name": stock["name"], "id": signal["id"],
                   "time": signal["time"], "time_ist": pd.to_datetime(signal["time"], unit="s", utc=True).tz_convert("Asia/Kolkata").strftime("%H:%M:%S"),
                   "family": signal["family"], "rank": signal["rank"], "direction": signal["direction"],
                   "ai_ran": bool(run.get("agent_start")), "order_attempted": bool(run.get("attempts")),
                   "order_submitted": any(t["event_id"] == signal["id"] for t in data["trades"]), "reason": run.get("reason"),
                   "spread": source.get("spread"), "rvol": source.get("relative_volume"),
                   **{f"activity_{k}": v for k, v in source["activity"].items()},
                   **features(bars, signal["time"]), **outcome(bars, signal["time"], signal["direction"])}
            events.append(row)
        subset = events[-len(stock["signals"]):]
        stocks.append({"key": stock["key"], "name": stock["name"], "signals": len(subset),
                       "ai_runs": sum(r["ai_ran"] for r in subset), "orders": len(stock["trades"]),
                       "bars": len(bars), "first_signal": subset[0]["time_ist"],
                       "median_signal_abs_return_15": pd.Series([r.get("abs_return_15") for r in subset], dtype=float).median(),
                       "best_signal_abs_return_15": max((r.get("abs_return_15", 0) for r in subset), default=0),
                       "sheet": f"charts-{i // 12 + 1:02}.png", "panel": i % 12 + 1})
    frame = pd.DataFrame(events)
    frame["half_hour"] = (frame.time // 1800).astype(int)
    frame.to_csv(OUT / "signal-audit.csv", index=False)
    coverage = pd.DataFrame(stocks)
    notes_path = OUT / "visual-notes.txt"
    if notes_path.exists():
        notes = dict(line.split(": ", 1) for line in notes_path.read_text().splitlines()[2:] if ": " in line)
        coverage["visual_observation"] = coverage["name"].map(notes)
    coverage.to_csv(OUT / "stock-coverage.csv", index=False)
    metrics = ["abs_return_15", "max_excursion_15", "direction_return_15", "pre_range_5", "pre_efficiency_5", "volume_ratio_3_to_12", "activity_traded_value_5m", "spread"]
    summary = {"signals": len(frame), "stocks": len(stocks), "by_ai": frame.groupby("ai_ran")[metrics].agg(["count", "median"]).to_string(),
               "by_order": frame.groupby("order_submitted")[metrics].agg(["count", "median"]).to_string(),
               "reasons": frame.reason.value_counts().to_dict(),
               "half_hour_control": frame.groupby(["half_hour", "ai_ran"])[metrics].median().to_string(),
               "family": frame.groupby("family")[metrics].agg(["count", "median"]).to_string()}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    for offset in range(0, len(data["stocks"]), 12):
        fig, axes = plt.subplots(4, 3, figsize=(19, 13))
        for ax, stock in zip(axes.flat, data["stocks"][offset:offset + 12]):
            bars = stock["bars"]
            t = np.array([b["t"] for b in bars])
            minute = (t + 19800) % 86400 / 60
            close = np.array([b["c"] for b in bars])
            ax.plot(minute, close, color="#283d50", lw=.9)
            ax.fill_between(minute, [b["l"] for b in bars], [b["h"] for b in bars], color="#627f90", alpha=.2)
            ax.plot(minute, [b["vwap"] for b in bars], color="#dd9d20", lw=.7, alpha=.7)
            for s in stock["signals"]:
                x = (s["time"] + 19800) % 86400 / 60
                ax.scatter(x, s["price"], s=15, marker="^" if s["direction"] == "LONG" else "v", color="#3c99ad", zorder=3)
                if (s.get("run") or {}).get("agent_start"):
                    ax.axvline((s["run"]["agent_start"] + 19800) % 86400 / 60, color="#a12ac0", alpha=.6, lw=.8)
            for trade in data["trades"]:
                if trade["key"] == stock["key"] and trade.get("entry_time"):
                    ax.scatter((trade["entry_time"] + 19800) % 86400 / 60, trade["entry_price"], color="#e53c39", marker="*", s=85, zorder=4)
            ax.set_title(f"{stock['name']} | signals {len(stock['signals'])}, AI {sum(bool((s.get('run') or {}).get('agent_start')) for s in stock['signals'])}, orders {len(stock['trades'])}", fontsize=9)
            ax.set_xticks([555, 630, 705, 780, 855, 930], ["09:15", "10:30", "11:45", "13:00", "14:15", "15:30"])
            ax.grid(alpha=.2)
        for ax in list(axes.flat)[len(data["stocks"][offset:offset + 12]):]:
            ax.set_visible(False)
        fig.suptitle("September 9 | teal: signal direction | purple: AI start | red star: filled entry | gold: VWAP | sampled minute bars", fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, .97))
        fig.savefig(OUT / f"charts-{offset // 12 + 1:02}.png", dpi=130)
        plt.close(fig)
    print(OUT)


if __name__ == "__main__":
    main()
