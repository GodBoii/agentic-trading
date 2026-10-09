"""Shared cost/risk comparison with per-track immutable hypotheses and evidence."""

from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import platform
import shutil
import time
from typing import Callable, Protocol

import pandas as pd

from research.intraday_lab.domain import ExecutionConfig, PolicyConfig, Signal, Tick
from research.intraday_lab.replay import ReplayEngine
from .data import CACHE, DATES, ROOT, load_manifest, load_ticks, phase


class Policy(Protocol):
    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]: ...


@dataclass(frozen=True)
class Variant:
    name: str
    factory: Callable[[PolicyConfig], Policy]
    parameters: dict
    policy_overrides: dict = field(default_factory=dict)
    execution_overrides: dict = field(default_factory=dict)


class CheckedPolicy:
    def __init__(self, policy: Policy):
        self.policy = policy

    def on_tick(self, tick: Tick) -> tuple[Signal | None, str]:
        signal, reason = self.policy.on_tick(tick)
        if not isinstance(reason, str):
            raise ValueError("policy reason must be text")
        if signal is not None:
            if (signal.at_us != tick.at_us or signal.security_id != tick.security_id
                    or not isfinite(signal.reference_midpoint) or signal.reference_midpoint <= 0
                    or not isfinite(signal.move_bps) or not isfinite(signal.confirmation_bps)):
                raise ValueError("policy emitted invalid identity, timestamp, or numeric evidence")
        return signal, reason


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def _snapshot(track_dir: Path, output: Path) -> str:
    paths = list(Path(__file__).parent.glob("*.py"))
    paths += list((ROOT / "research/intraday_lab").glob("*.py"))
    paths += [p for p in track_dir.rglob("*.py") if "runs" not in p.relative_to(track_dir).parts]
    digest = sha256()
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        digest.update(relative.as_posix().encode())
        content = path.read_bytes()
        digest.update(content)
        target = output / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return digest.hexdigest()


def run_track(track_dir: Path, variants: list[Variant], run_name: str = "initial-v1",
              dates: list[str] | tuple[str, ...] | None = None,
              modes: tuple[str, ...] = ("recent_trade", "receipt_proxy"),
              cache: Path = CACHE) -> Path:
    track_dir = track_dir.resolve()
    if not track_dir.is_relative_to(ROOT / "research") or not track_dir.is_dir():
        raise ValueError("track must be an existing directory inside research")
    if not variants or len({v.name for v in variants}) != len(variants):
        raise ValueError("provide nonempty variants with unique names")
    if any(not v.name.replace("_", "").replace("-", "").isalnum() for v in variants):
        raise ValueError("variant names must be simple filename-safe identifiers")
    if not modes or any(mode not in {"recent_trade", "receipt_proxy"} for mode in modes):
        raise ValueError("invalid freshness modes")
    days = list(DATES if dates is None else dates)
    if not days or len(set(days)) != len(days) or any(day not in DATES for day in days):
        raise ValueError("provide unique preregistered session dates")
    output = (track_dir / "runs" / run_name).resolve()
    if not output.is_relative_to(track_dir / "runs") or output.exists():
        raise ValueError("run must use a new directory inside track/runs")
    specs = []
    for variant in variants:
        for mode in modes:
            config = replace(PolicyConfig(), **{**variant.policy_overrides,
                                              "name": variant.name, "freshness_mode": mode})
            execution = replace(ExecutionConfig(), **variant.execution_overrides)
            specs.append((variant, mode, config, execution))
    manifests = {day: load_manifest(day, cache) for day in days}
    output.mkdir(parents=True)
    source_hash = _snapshot(track_dir, output)
    plan = {"track": track_dir.name, "source_sha256": source_hash, "dates": days,
            "runtime": {"python": platform.python_version(), "pandas": pd.__version__},
            "universe": json.loads((cache / "universe.json").read_text()),
            "variants": [{"name": v.name, "parameters": v.parameters,
                          "mode": mode, "policy": asdict(cfg), "execution": asdict(ex)}
                         for v, mode, cfg, ex in specs],
            "input_hashes": {day: manifest["cache_sha256"] for day, manifest in manifests.items()},
            "phases": {day: phase(day) for day in days}, "promotion_eligible": False,
            "limitations": ["previously inspected historical data; no pristine holdout",
                            "downsampled observations; source quote age unverified",
                            "all-or-none aggressive fill proxy; no queue or calibrated impact",
                            "many hypotheses tested; selected maximum is biased",
                            "pending orders and account loss limits apply to all tracks"]}
    _write(output / "plan.json", plan)
    rows = []
    for day in days:
        ticks = load_ticks(day, cache)
        _write(output / f"input-{day}.json", manifests[day])
        for variant, mode, cfg, execution in specs:
            started = time.perf_counter()
            engine = ReplayEngine(cfg, execution)
            engine.policy = CheckedPolicy(variant.factory(cfg))
            summary = engine.run(ticks)
            summary.update({"track": track_dir.name, "variant": variant.name, "mode": mode,
                            "date": day, "phase": phase(day),
                            "replay_seconds": round(time.perf_counter() - started, 3)})
            rows.append(summary)
            stem = f"{day}-{variant.name}-{mode}"
            _write(output / f"summary-{stem}.json", summary)
            pd.DataFrame([asdict(t) for t in engine.trades]).to_csv(output / f"trades-{stem}.csv", index=False)
            print(json.dumps({"track": track_dir.name, "date": day, "variant": variant.name,
                              "mode": mode, "trades": summary["trades"],
                              "net_pnl": summary["net_pnl"], "complete": summary["complete"]}), flush=True)
    groups = []
    for variant in variants:
        for mode in modes:
            for phase_name in ("all", "development", "validation_diagnostic", "historical_audit"):
                selected = [r for r in rows if r["variant"] == variant.name and r["mode"] == mode
                            and (phase_name == "all" or r["phase"] == phase_name)]
                if not selected:
                    continue
                trades = sum(r["trades"] for r in selected)
                counts = Counter()
                for row in selected:
                    counts.update(row["counts"])
                groups.append({"track": track_dir.name, "variant": variant.name, "mode": mode,
                               "phase": phase_name, "sessions": len(selected), "trades": trades,
                               "gross_pnl": round(sum(r["gross_pnl"] for r in selected), 2),
                               "fees": round(sum(r["fees"] for r in selected), 2),
                               "net_pnl": round(sum(r["net_pnl"] for r in selected), 2),
                               "incomplete_sessions": sum(not r["complete"] for r in selected),
                               "positive_sessions": sum(r["net_pnl"] > 0 for r in selected),
                               "promotion_eligible": False, "counts": dict(counts)})
    _write(output / "aggregate.json", {"results": groups, "policy_session_replays": len(rows)})
    pd.DataFrame([{k: v for k, v in row.items() if k != "counts"} for row in groups]).to_csv(
        output / "comparison.csv", index=False)
    return output
