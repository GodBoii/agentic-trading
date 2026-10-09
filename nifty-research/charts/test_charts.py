from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(f"chart_{name}", HERE / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


data = module("data")
figures = module("figures")


def write_rows(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def market_row(second, price, volume, seq=1):
    return {
        "captured_at_utc": f"2026-08-21T03:45:{second:02d}+00:00",
        "event_sequence": seq,
        "packet": {
            "type": "Full Data",
            "security_id": 1,
            "LTP": price,
            "volume": volume,
            "OI": 500,
            "depth": [
                {
                    "bid_price": price - 1,
                    "ask_price": price + 1,
                    "bid_quantity": 10,
                    "ask_quantity": 20,
                }
            ],
        },
    }


def test_volume_resets_and_unknown_direction(tmp_path):
    path = tmp_path / "market.ndjson"
    write_rows(
        path,
        [
            market_row(0, 100, 50, 1),
            market_row(1, 100, 60, 2),
            market_row(2, 101, 70, 3),
            market_row(20, 102, 150, 4),
            market_row(21, 102, 2, 5),
        ],
    )
    frame, audit = data.load_market(path, "2026-08-21")
    assert frame["volume"].tolist() == [0, 10, 10, 0, 0]
    assert frame["unknown"].iloc[1] == 10
    assert frame["signed"].iloc[2] == 10
    assert audit["resets"] == 2
    assert len(audit["sha256"]) == 64


def synthetic_ticks():
    index = pd.date_range("2026-08-21 09:15:00", periods=180, freq="s", tz=data.IST)
    return pd.DataFrame(
        {
            "price": np.arange(180) + 100,
            "volume": 1,
            "oi": 500,
            "sid": "1",
            "segment": 0,
            "spread": 2,
            "signed": 1,
            "unknown": 0,
            "micro": 0,
        },
        index=index,
    )


def test_candles_are_true_sampled_ohlc_and_missing_stays_blank():
    ticks = synthetic_ticks()
    bars = data.make_bars(ticks, "2026-08-21")
    assert bars.iloc[0][["open", "high", "low", "close"]].tolist() == [
        100,
        159,
        100,
        159,
    ]
    assert bars.iloc[0]["volume"] == 60
    assert bars["complete"].sum() == 3
    assert bars["close"].isna().sum() == 372


def test_restart_within_candle_drops_ambiguous_candle():
    ticks = synthetic_ticks()
    ticks.loc[ticks.index[30:], "segment"] = 1
    bars = data.make_bars(ticks, "2026-08-21")
    assert pd.isna(bars.iloc[0]["close"])
    assert bars.iloc[1]["open"] == 160


def test_indicators_warm_up_again_after_gap():
    ticks = pd.concat([synthetic_ticks().iloc[:60], synthetic_ticks().iloc[120:]])
    bars = figures.indicators(data.make_bars(ticks, "2026-08-21"))
    assert pd.isna(bars.iloc[2]["ret"])
    assert pd.isna(bars.iloc[2]["sma20"])
    assert bars.iloc[2]["drawdown"] == 0


def test_wilder_seed_and_flat_rsi():
    result = figures.wilder(pd.Series([1.0, 2.0, 3.0, 4.0]), 3)
    assert pd.isna(result.iloc[1])
    assert result.iloc[2] == 2
    assert result.iloc[3] == pytest.approx(8 / 3)
    ticks = synthetic_ticks()
    ticks["price"] = 100
    bars = data.make_bars(ticks, "2026-08-21")
    # A long complete flat recording reaches neutral RSI instead of NaN or 100.
    complete = pd.concat([bars.iloc[:1]] * 20, ignore_index=True)
    complete.index = pd.date_range(
        "2026-08-21 09:15", periods=20, freq="min", tz=data.IST
    )
    complete["run"] = 1
    assert figures.indicators(complete)["rsi"].iloc[-1] == 50


def test_depth_requires_fresh_uncrossed_pair(tmp_path):
    path = tmp_path / "depth.ndjson"

    def row(second, side, price):
        return {
            "captured_at_utc": f"2026-08-21T03:45:{second:02d}+00:00",
            "side": side,
            "security_id": 1,
            "depth": [{"price": price, "quantity": 10}],
        }

    write_rows(
        path,
        [row(0, "bid", 100), row(2, "ask", 102), row(3, "bid", 100), row(4, "ask", 99)],
    )
    snapshots, audit = data.load_depth(path, "2026-08-21")
    assert len(snapshots) == 1
    assert snapshots[0]["time"].endswith("09:15:03+05:30")
    assert audit["stale_or_crossed"] == 2


def test_options_do_not_carry_stale_quote_forward(tmp_path):
    path = tmp_path / "options.ndjson"
    row = {
        "captured_at_utc": "2026-08-21T03:45:59+00:00",
        "security_id": 10,
        "best_bid": 10,
        "best_ask": 12,
        "strike_price": 24000,
        "open_interest": 100,
        "expiry_date": "2026-08-25",
        "option_type": "CE",
    }
    write_rows(path, [row])
    samples, audit = data.load_options(path, "2026-08-21")
    assert len(samples) == 1
    assert samples.iloc[0]["cutoff"].strftime("%H:%M") == "09:16"
    assert audit["fresh_minute_quotes"] == 1


def test_strategy_payoff_uses_ask_for_buy_bid_for_sell():
    rows = [
        {"strike": s, "kind": k, "bid": 8, "ask": 10}
        for s in [23950.0, 24000.0, 24050.0]
        for k in ["CE", "PE"]
    ]
    captured = []

    def add(*args, **kwargs):
        captured.append({"data": args[5], "layout": {}})

    figures.add_payoff_chart(
        pd.DataFrame(rows), "Expiry test. ", "15:30", add, captured
    )
    traces = {t["name"]: t for t in captured[0]["data"]}
    long = traces["Long straddle"]
    short = traces["Short straddle"]
    index = long["x"].index(24000.0)
    assert long["y"][index] == -20
    assert short["y"][index] == 16


def test_weekend_packets_are_excluded(tmp_path):
    path = tmp_path / "weekend.ndjson"
    row = market_row(0, 100, 50)
    row["captured_at_utc"] = "2026-08-22T03:45:00+00:00"
    write_rows(path, [row])
    with pytest.raises(ValueError, match="No valid market packets"):
        data.load_market(path, "2026-08-22")


def test_offline_build_and_cache_from_real_packet_files(tmp_path):
    archive = tmp_path / "source" / "2026-08-21"
    archive.mkdir(parents=True)
    write_rows(
        archive / "full_market.ndjson",
        [market_row(i, 100 + i, i, i) for i in range(60)],
    )
    output = tmp_path / "gallery"
    command = [
        sys.executable,
        str(HERE / "build.py"),
        "--source-root",
        str(archive.parent),
        "--dates",
        archive.name,
        "--output",
        str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    html = (output / "index.html").read_text(encoding="utf-8")
    assert html.find("/*__DATA__*/") == -1
    assert html.find("/*__PLOTLY__*/") == -1

    class Scripts(HTMLParser):
        external: list[str]

        def __init__(self):
            super().__init__()
            self.external = []

        def handle_starttag(self, tag, attrs):
            if tag == "script":
                self.external.extend(value for key, value in attrs if key == "src")

    parsed = Scripts()
    parsed.feed(html)
    assert parsed.external == []
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["chart_count"][archive.name] == 28
    cached = subprocess.run(command, check=True, capture_output=True, text=True)
    assert "using verified chart cache" in cached.stdout
    refused = subprocess.run(
        command[:-1] + [str(archive / "output")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert refused.returncode != 0
    assert "Output must not be inside a raw archive root" in refused.stderr
