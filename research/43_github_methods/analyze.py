"""Verify saved evidence and describe trade outcomes without changing decisions."""

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from research.common.data import ROOT, load_manifest


def main() -> None:
    folder = Path(__file__).parent
    run = folder / "runs/initial-v1"
    plan = json.loads((run / "plan.json").read_text())
    aggregate = json.loads((run / "aggregate.json").read_text())
    snapshot_digest = sha256()
    for path in sorted((run / "source").rglob("*.py")):
        relative = path.relative_to(run / "source")
        snapshot_digest.update(relative.as_posix().encode())
        snapshot_digest.update(path.read_bytes())
        if path.read_bytes() != (ROOT / relative).read_bytes():
            raise ValueError(f"source changed since replay: {relative}")
    if snapshot_digest.hexdigest() != plan["source_sha256"]:
        raise ValueError("source snapshot digest disagrees with plan")
    for day, expected in plan["input_hashes"].items():
        if load_manifest(day)["cache_sha256"] != expected:
            raise ValueError(f"input changed for {day}")
    for variant in plan["variants"]:
        params = variant["parameters"]
        for filename, key in (("hypotheses.md", "hypotheses_sha256"),
                              ("upstream/manifest.json", "source_manifest_sha256")):
            if sha256((folder / filename).read_bytes()).hexdigest() != params[key]:
                raise ValueError(f"frozen evidence changed: {filename}")
    upstream = json.loads((folder / "upstream/manifest.json").read_text())
    for source in upstream["sources"]:
        if sha256((folder / "upstream" / source["saved_file"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"upstream evidence changed: {source['saved_file']}")
    summaries = [json.loads(path.read_text()) for path in sorted(run.glob("summary-*.json"))]
    expected = len(plan["dates"]) * len(plan["variants"])
    if len(summaries) != expected or aggregate["policy_session_replays"] != expected:
        raise ValueError("replay summary count differs from frozen plan")
    trade_rows: list[dict] = []
    checks = []
    for summary in summaries:
        stem = f"{summary['date']}-{summary['variant']}-{summary['mode']}"
        path = run / f"trades-{stem}.csv"
        trades = [] if not path.read_text().strip() else pd.read_csv(path).to_dict("records")
        if len(trades) != summary["trades"]:
            raise ValueError(f"trade count differs: {stem}")
        for key in ("gross_pnl", "fees", "net_pnl"):
            if abs(sum(trade[key] for trade in trades) - summary[key]) > .02:
                raise ValueError(f"trade ledger {key} differs: {stem}")
        for trade in trades:
            if not trade["signal_us"] < trade["entry_us"] <= trade["exit_us"]:
                raise ValueError(f"noncausal fill chronology: {stem}")
            if abs(trade["gross_pnl"] - trade["fees"] - trade["net_pnl"]) > .01:
                raise ValueError(f"trade accounting differs: {stem}")
            trade_rows.append({**trade, "variant": summary["variant"], "mode": summary["mode"],
                               "phase": summary["phase"], "date": summary["date"]})
        checks.append({"session": stem, "trades": len(trades), "verified": True})
    metrics = []
    for variant in sorted({item["variant"] for item in summaries}):
        for mode in ("recent_trade", "receipt_proxy"):
            for period in ("all", "after_development"):
                rows = [item for item in trade_rows if item["variant"] == variant and item["mode"] == mode
                        and (period == "all" or item["phase"] != "development")]
                sessions = [item for item in summaries if item["variant"] == variant and item["mode"] == mode
                            and (period == "all" or item["phase"] != "development")]
                net = sum(item["net_pnl"] for item in rows)
                wins = sum(item["net_pnl"] > 0 for item in rows)
                counts = Counter()
                for session in sessions:
                    counts.update(session["counts"])
                metrics.append({"variant": variant, "mode": mode, "period": period,
                                "sessions": len(sessions), "trades": len(rows),
                                "net_wins": wins, "net_win_rate": wins / len(rows) if rows else None,
                                "gross_pnl": round(sum(item["gross_pnl"] for item in rows), 2),
                                "fees": round(sum(item["fees"] for item in rows), 2),
                                "net_pnl": round(net, 2), "expectancy": round(net / len(rows), 2) if rows else None,
                                "incomplete_sessions": sum(not item["complete"] for item in sessions),
                                "daily_loss_halts": counts["daily_loss_halt"]})
    report = {"verified": True, "replays": len(summaries), "upstream_files": len(upstream["sources"]),
              "source_sha256": plan["source_sha256"], "session_ledger_checks": checks, "metrics": metrics,
              "metric_semantics": "net trade win rate, not calibrated prediction accuracy"}
    (folder / "evidence-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    pd.DataFrame(metrics).to_csv(folder / "trade-metrics.csv", index=False)
    def modified(path: Path) -> str:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    summary_paths = list(run.glob("summary-*.json"))
    chronology = {"source_retrieved_utc": upstream["retrieved_utc"],
                  "plan_written_utc": modified(run / "plan.json"),
                  "first_session_summary_utc": modified(min(summary_paths, key=lambda p: p.stat().st_mtime)),
                  "last_session_summary_utc": modified(max(summary_paths, key=lambda p: p.stat().st_mtime)),
                  "aggregate_written_utc": modified(run / "aggregate.json"),
                  "verified_utc": datetime.now(timezone.utc).isoformat(),
                  "frozen_hypotheses_sha256": sha256((folder / "hypotheses.md").read_bytes()).hexdigest(),
                  "frozen_source_sha256": plan["source_sha256"],
                  "limitations": "filesystem timestamps are descriptive, not tamper-proof; analyze.py was added after initial replay started"}
    (folder / "chronology.json").write_text(json.dumps(chronology, indent=2), encoding="utf-8")
    print(json.dumps({"verified": True, "replays": len(summaries), "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
