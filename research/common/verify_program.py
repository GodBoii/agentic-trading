"""Verify saved evidence across tracks without ranking incomplete account P&L."""

import argparse
import csv
from hashlib import sha256
import importlib.util
import json
from math import isclose, isfinite
from pathlib import Path
import unittest

from .data import CACHE, ROOT, load_manifest


def close(actual: float, expected: float, context: str, tolerance: float = .00011) -> None:
    if not isfinite(actual) or not isfinite(expected) or not isclose(actual, expected, abs_tol=tolerance, rel_tol=1e-10):
        raise ValueError(f"Accounting mismatch {context}: {actual} versus {expected}")


def verify_run(run: Path) -> dict:
    plan = json.loads((run / "plan.json").read_text(encoding="utf-8"))
    aggregate = json.loads((run / "aggregate.json").read_text(encoding="utf-8"))
    sources = sorted((run / "source").rglob("*.py"), key=lambda path: path.relative_to(run / "source").as_posix())
    digest = sha256()
    for path in sources:
        digest.update(path.relative_to(run / "source").as_posix().encode())
        digest.update(path.read_bytes())
    if digest.hexdigest() != plan["source_sha256"]:
        raise ValueError(f"Source snapshot fingerprint mismatch in {run}")
    expected = {(day, spec["name"], spec["mode"]) for day in plan["dates"] for spec in plan["variants"]}
    seen = set()
    unresolved = []
    closed_trades = 0
    for path in sorted(run.glob("summary-*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        key = (row["date"], row["variant"], row["mode"])
        if key not in expected or key in seen:
            raise ValueError(f"Unexpected or duplicated session identity in {path}")
        seen.add(key)
        manifest = load_manifest(row["date"], CACHE)
        if plan["input_hashes"][row["date"]] != manifest["cache_sha256"]:
            raise ValueError(f"Input hash mismatch in {path}")
        if row["promotion_eligible"] or row["maximum_slots_used"] > row["execution"]["maximum_positions"]:
            raise ValueError(f"Promotion or slot limit violated in {path}")
        complete = not row["unresolved_positions"] and row["pending_entries"] == 0
        if complete != row["complete"]:
            raise ValueError(f"Unresolved exposure flag mismatch in {path}")
        if not complete:
            unresolved.append({"date": row["date"], "variant": row["variant"], "mode": row["mode"],
                               "positions": row["unresolved_positions"], "pending_entries": row["pending_entries"]})
        trade_path = run / path.name.replace("summary-", "trades-").replace(".json", ".csv")
        with trade_path.open(encoding="utf-8", newline="") as stream:
            trades = list(csv.DictReader(stream)) if trade_path.stat().st_size > 2 else []
        if len(trades) != row["trades"]:
            raise ValueError(f"Trade count mismatch in {path}")
        for trade in trades:
            sign = 1 if trade["side"] == "LONG" else -1 if trade["side"] == "SHORT" else 0
            if not sign or int(trade["quantity"]) <= 0:
                raise ValueError(f"Invalid trade side or quantity in {trade_path}")
            if not int(trade["signal_us"]) < int(trade["entry_us"]) < int(trade["exit_us"]):
                raise ValueError(f"Trade uses same or earlier observation in {trade_path}")
            gross = sign * (float(trade["exit_price"]) - float(trade["entry_price"])) * int(trade["quantity"])
            close(float(trade["gross_pnl"]), gross, str(trade_path), 1e-7)
            close(float(trade["net_pnl"]), gross - float(trade["fees"]), str(trade_path), 1e-7)
        closed_trades += len(trades)
        for column in ("gross_pnl", "fees", "net_pnl"):
            close(float(row[column]), sum(float(t[column]) for t in trades), f"{path.name}/{column}")
    if seen != expected or aggregate["policy_session_replays"] != len(seen):
        raise ValueError(f"Experiment coverage incomplete in {run}")
    summaries = [json.loads(path.read_text()) for path in run.glob("summary-*.json")]
    for group in aggregate["results"]:
        subset = [r for r in summaries if r["variant"] == group["variant"] and r["mode"] == group["mode"]
                  and (group["phase"] == "all" or r["phase"] == group["phase"])]
        if len(subset) != group["sessions"] or sum(r["trades"] for r in subset) != group["trades"]:
            raise ValueError(f"Aggregate counts mismatch in {run}")
        for column in ("gross_pnl", "fees", "net_pnl"):
            close(float(group[column]), sum(r[column] for r in subset), f"aggregate/{column}", .0051)
        if group["incomplete_sessions"] != sum(not r["complete"] for r in subset):
            raise ValueError(f"Aggregate incomplete exposure mismatch in {run}")
    return {"track": plan["track"], "run": run.name, "policy_session_replays": len(seen),
            "closed_trades": closed_trades, "unresolved_sessions": unresolved,
            "source_and_input_fingerprints": "pass", "accounting": "pass", "promotion_eligible": False}


def run_tests() -> dict:
    suite = unittest.TestSuite()
    paths = sorted((ROOT / "research").glob("*/tests/test*.py"))
    for index, path in enumerate(paths):
        spec = importlib.util.spec_from_file_location(f"research_program_tests_{index}", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load tests in {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    outcome = unittest.TextTestRunner(verbosity=1).run(suite)
    return {"files": len(paths), "tests": outcome.testsRun, "failures": len(outcome.failures),
            "errors": len(outcome.errors), "success": outcome.wasSuccessful()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tests", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "research/program/runs") or output.exists():
        parser.error("output must be a new directory under research/program/runs")
    output.mkdir(parents=True)
    reports = []
    skipped = []
    for track in sorted((ROOT / "research").glob("[0-9][0-9]_*")):
        for run in sorted((track / "runs").glob("*")):
            if not run.is_dir():
                continue
            invalid = list(run.glob("invalid*.md")) + list(track.glob(f"invalid-{run.name}.md"))
            if invalid or not (run / "aggregate.json").exists() or not (run / "plan.json").exists():
                skipped.append({"track": track.name, "run": run.name,
                                "reason": "marked invalid" if invalid else "separate diagnostic or unfinished run"})
                continue
            plan = json.loads((run / "plan.json").read_text(encoding="utf-8"))
            aggregate = json.loads((run / "aggregate.json").read_text(encoding="utf-8"))
            if ("variants" not in plan or "source_sha256" not in plan
                    or not isinstance(aggregate, dict) or "policy_session_replays" not in aggregate):
                skipped.append({"track": track.name, "run": run.name,
                                "reason": "separate diagnostic; not a common account replay"})
                continue
            reports.append(verify_run(run))
    test_report = run_tests() if args.tests else None
    report = {"verified_runs": reports, "skipped": skipped, "tests": test_report,
              "verified_policy_session_replays": sum(row["policy_session_replays"] for row in reports),
              "promotion_eligible": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"verified_runs": len(reports), "replays": report["verified_policy_session_replays"],
                      "tests": test_report}), flush=True)
    if test_report and not test_report["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
