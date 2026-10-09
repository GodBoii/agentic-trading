"""Build a self-contained, offline Nifty archive chart explorer."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from data import load_depth, load_market, load_options, make_bars
from figures import build_charts
from plotly.offline import get_plotlyjs

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
DEFAULT_ROOTS = [
    WORKSPACE / "python-backend/nifty_market_depth",
    WORKSPACE / "python-backend/results/nifty-50-market-depth",
]


def discover(roots: list[Path]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for directory in root.iterdir():
            try:
                day = date.fromisoformat(directory.name)
            except ValueError:
                continue
            market = directory / "full_market.ndjson"
            if not market.is_file() or day.weekday() >= 5:
                continue
            # Choose one complete recording directory; never splice overlapping runs.
            previous = found.get(directory.name)
            if (
                previous is None
                or market.stat().st_size > (previous / market.name).stat().st_size
            ):
                found[directory.name] = directory
    return dict(sorted(found.items()))


def signature(directory: Path) -> dict:
    return {
        "code": hashlib.sha256(
            (HERE / "data.py").read_bytes()
            + (HERE / "figures.py").read_bytes()
            + (HERE / "build.py").read_bytes()
        ).hexdigest(),
        "files": {
            str(p.resolve()): [p.stat().st_size, p.stat().st_mtime_ns]
            for p in sorted(directory.glob("*.ndjson"))
            if p.name
            in {"full_market.ndjson", "depth_200.ndjson", "options_feed.ndjson"}
        },
    }


def build_session(directory: Path) -> dict:
    day = directory.name
    print(f"{day}: reading market packets", flush=True)
    ticks, market_audit = load_market(directory / "full_market.ndjson", day)
    bars = make_bars(ticks, day)
    five = make_bars(ticks, day, 5)
    depth, depth_audit = [], {}
    if (directory / "depth_200.ndjson").is_file():
        print(f"{day}: reading depth snapshots", flush=True)
        depth, depth_audit = load_depth(directory / "depth_200.ndjson", day)
        # Enforce instrument identity against nearby market packets.
        valid = []
        for d in depth:
            stamp = pd.Timestamp(d["time"])
            loc = ticks.index.get_indexer(
                [stamp], method="pad", tolerance=pd.Timedelta(seconds=2)
            )[0]
            if loc >= 0 and ticks.iloc[loc]["sid"] == d["sid"]:
                valid.append(d)
        depth_audit["market_matched_snapshots"] = len(valid)
        depth = valid
    options, option_audit = pd.DataFrame(), {}
    if (directory / "options_feed.ndjson").is_file():
        print(f"{day}: reading fixed option contracts", flush=True)
        options, option_audit = load_options(directory / "options_feed.ndjson", day)
    charts = build_charts(ticks, bars, five, depth, options)
    # Plotly's schema validation catches invalid traces before shipping the HTML.
    for chart in charts:
        go.Figure(data=chart["data"], layout=chart["layout"])
    valid_bars = bars.dropna(subset=["close"])
    return {
        "date": day,
        "source": str(directory.resolve()),
        "charts": charts,
        "stats": {
            "packets": len(ticks),
            "minutes": len(valid_bars),
            "complete": int(bars["complete"].sum()),
            "missing": int(bars["close"].isna().sum()),
            "partial": int((bars["close"].notna() & ~bars["complete"]).sum()),
            "resets": market_audit["resets"],
            "instruments": sorted(ticks["sid"].unique().tolist()),
            "first": ticks.index.min().strftime("%H:%M:%S"),
            "last": ticks.index.max().strftime("%H:%M:%S"),
            "depth": len(depth),
            "options": option_audit.get("fresh_minute_quotes", 0),
            "expiry": None if options.empty else options["expiry"].min(),
        },
        "audit": {
            "market": market_audit,
            "depth": depth_audit,
            "options": option_audit,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dates", nargs="+", default=["2026-07-28", "2026-08-20", "2026-08-21"]
    )
    parser.add_argument(
        "--all", action="store_true", help="Build every available weekday recording"
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        action="append",
        help="Repeat for additional archive roots",
    )
    parser.add_argument("--output", type=Path, default=HERE / "artifacts")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    found = discover(args.source_root or DEFAULT_ROOTS)
    dates = list(found) if args.all else args.dates
    missing = set(dates) - set(found)
    if missing:
        parser.error(f"No weekday archive found for {', '.join(sorted(missing))}")
    output = args.output.resolve()
    # Prevent accidental writes into any source directory.
    for root in args.source_root or DEFAULT_ROOTS:
        if output == root.resolve() or root.resolve() in output.parents:
            parser.error("Output must not be inside a raw archive root")
    output.mkdir(parents=True, exist_ok=True)
    sessions = []
    for day in dates:
        key = signature(found[day])
        cache = output / f"{day}.json"
        cached = (
            json.loads(cache.read_text(encoding="utf-8"))
            if cache.is_file() and not args.rebuild
            else None
        )
        if cached and cached.get("signature") == key:
            print(f"{day}: using verified chart cache", flush=True)
            result = cached["session"]
        else:
            result = build_session(found[day])
            if signature(found[day]) != key:
                raise RuntimeError(f"Sources changed during build: {day}")
            cache.write_text(
                json.dumps({"signature": key, "session": result}, allow_nan=False),
                encoding="utf-8",
            )
        sessions.append(result)
    if not sessions:
        parser.error("No sessions selected")
    payload = json.dumps(
        {"sessions": sessions, "default": dates[-1]}, allow_nan=False
    ).replace("<", "\\u003c")
    template = (HERE / "explorer.html").read_text(encoding="utf-8")
    html = template.replace("/*__PLOTLY__*/", get_plotlyjs()).replace(
        "/*__DATA__*/", payload
    )
    (output / "index.html").write_text(html, encoding="utf-8")
    manifest = {
        "sessions": [{k: v for k, v in s.items() if k != "charts"} for s in sessions],
        "chart_count": {s["date"]: len(s["charts"]) for s in sessions},
        "available_recordings": list(found),
        "not_built": sorted(set(found) - set(dates)),
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        f"Built {output / 'index.html'}: {len(sessions)} sessions, {[len(s['charts']) for s in sessions]} charts",
        flush=True,
    )


if __name__ == "__main__":
    main()
