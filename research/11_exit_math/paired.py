"""Exit-only counterfactuals on frozen baseline fills, without portfolio feedback."""

from bisect import bisect_left
import csv
from dataclasses import asdict, dataclass
from importlib import import_module
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path

from research.common.data import DATES, load_ticks, phase
from research.intraday_lab.costs import round_trip_fees
from research.intraday_lab.domain import ExecutionConfig, PolicyConfig, Side, Tick, session_second

ExitSpec = import_module("research.11_exit_math.strategy").ExitSpec


@dataclass(frozen=True)
class FrozenEntry:
    security_id: int
    side: Side
    entered_us: int
    entry_price: float
    quantity: int

    def __post_init__(self) -> None:
        if (self.security_id <= 0 or self.entered_us <= 0 or self.quantity <= 0
                or not isfinite(self.entry_price) or self.entry_price <= 0):
            raise ValueError("valid positive entry identity, quantity, price and time required")


def replay_exit(entry: FrozenEntry, ticks: list[Tick], spec: ExitSpec,
                policy: PolicyConfig, execution: ExecutionConfig) -> dict:
    """No portfolio loss actions. Callers pass one stock's timestamp-ordered tape."""
    if any(t.security_id != entry.security_id for t in ticks):
        raise ValueError("paired exit requires a single matching instrument")
    if any(a.at_us >= b.at_us for a, b in zip(ticks, ticks[1:])):
        raise ValueError("paired tape timestamps must increase")
    start = bisect_left([t.at_us for t in ticks], entry.entered_us)
    pending_us = None
    reason = None
    for tick in ticks[start:]:
        if not tick.usable(policy.maximum_trade_age_seconds,
                           receipt_proxy=policy.freshness_mode == "receipt_proxy"):
            continue
        if pending_us is not None:
            if (tick.at_us <= pending_us
                    or tick.at_us < pending_us + execution.latency_ms*1000):
                continue
            rate = execution.extra_slippage_bps/10000
            price = tick.bid*(1-rate) if entry.side is Side.LONG else tick.ask*(1+rate)
            gross = entry.side.sign*(price-entry.entry_price)*entry.quantity
            fees = round_trip_fees(entry.entry_price,price,entry.quantity,long=entry.side is Side.LONG)
            return {**asdict(entry), "side":entry.side.value,"complete":True,
                    "exit_us":tick.at_us,"exit_price":price,"exit_reason":reason,
                    "gross_pnl":gross,"fees":fees,"net_pnl":gross-fees}
        quote = tick.bid if entry.side is Side.LONG else tick.ask
        move = entry.side.sign*(quote/entry.entry_price-1)*10000
        if session_second(tick.at_us) >= execution.flatten_second:
            reason = "session_flatten"
        elif move <= -spec.stop_bps:
            reason = "stop"
        elif move >= spec.target_bps:
            reason = "target"
        elif tick.at_us-entry.entered_us >= spec.horizon_seconds*1_000_000:
            reason = "time"
        if reason:
            pending_us = tick.at_us
    return {**asdict(entry), "side":entry.side.value,"complete":False,
            "exit_us":None,"exit_price":None,"exit_reason":reason,
            "gross_pnl":None,"fees":None,"net_pnl":None}


def main() -> None:
    root = Path(__file__).resolve().parent
    original = root / "runs/initial-v1"
    output = root / "runs/paired-exits-v1"
    if not (original/"aggregate.json").exists():
        raise ValueError("complete the baseline account experiment first")
    if output.exists():
        raise ValueError("paired experiment must use a new output directory")
    specs = {"fixed_30_15_300":ExitSpec(30,15,300),
             "double_distances_60_30_300":ExitSpec(60,30,300),
             "short_time_30_15_60":ExitSpec(30,15,60)}
    plan = json.loads((original/"plan.json").read_text())
    output.mkdir()
    paired_plan = {"frozen_baseline":"fixed_30_15_300 receipt_proxy fills",
                   "input_hashes":plan["input_hashes"],"specs":{k:asdict(v) for k,v in specs.items()},
                   "baseline_trade_hashes":{day:sha256((original/f"trades-{day}-fixed_30_15_300-receipt_proxy.csv").read_bytes()).hexdigest()
                                            for day in DATES},
                   "promotion_eligible":False,"portfolio_loss_actions":False,
                   "limitations":["overlapping counterfactual positions may exceed account capacity",
                                  "same coarse receipt-proxy quote and execution assumptions",
                                  "excludes original portfolio loss-action exits"]}
    source_dir = output/"source"
    source_dir.mkdir()
    source_hashes = {}
    for path in root.glob("*.py"):
        content = path.read_bytes()
        (source_dir/path.name).write_bytes(content)
        source_hashes[path.name] = sha256(content).hexdigest()
    paired_plan["track_source_hashes"] = source_hashes
    (output/"plan.json").write_text(json.dumps(paired_plan,indent=2),encoding="utf-8")
    all_rows = []
    policy = PolicyConfig(freshness_mode="receipt_proxy")
    execution = ExecutionConfig()
    for day in DATES:
        path = original/f"trades-{day}-fixed_30_15_300-receipt_proxy.csv"
        with path.open(newline="",encoding="utf-8") as stream:
            entries = [FrozenEntry(int(r["security_id"]),Side(r["side"]),int(r["entry_us"]),
                                   float(r["entry_price"]),int(r["quantity"])) for r in csv.DictReader(stream)]
        by_stock: dict[int,list[Tick]] = {}
        for tick in load_ticks(day):
            by_stock.setdefault(tick.security_id,[]).append(tick)
        for name,spec in specs.items():
            outcomes = [replay_exit(entry,by_stock[entry.security_id],spec,policy,execution)
                        for entry in entries]
            payload = {"date":day,"phase":phase(day),"variant":name,"entries":len(entries),
                       "complete":sum(r["complete"] for r in outcomes),"outcomes":outcomes}
            (output/f"{day}-{name}.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
            all_rows.append({"date":day,"phase":phase(day),"variant":name,"entries":len(entries),
                             "incomplete":sum(not r["complete"] for r in outcomes),
                             "gross_pnl":sum(r["gross_pnl"] or 0 for r in outcomes),
                             "fees":sum(r["fees"] or 0 for r in outcomes),
                             "net_pnl":sum(r["net_pnl"] or 0 for r in outcomes)})
    with (output/"comparison.csv").open("w",newline="",encoding="utf-8") as stream:
        writer = csv.DictWriter(stream,fieldnames=list(all_rows[0]))
        writer.writeheader(); writer.writerows(all_rows)
    print(json.dumps({"paired_entries_per_variant":sum(r["entries"] for r in all_rows
                                                      if r["variant"]=="fixed_30_15_300"),
                      "output":str(output)},indent=2))


if __name__ == "__main__":
    main()
