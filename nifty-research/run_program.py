"""Run owned research scripts and retain per-study failures without hiding them."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def run_one(folder: str, runner: str) -> dict:
    directory = (ROOT / "research" / folder).resolve()
    if not directory.is_relative_to((ROOT / "research").resolve()): raise ValueError("Study path outside workspace")
    script = (directory / runner).resolve()
    if not script.is_relative_to(directory) or not script.is_file(): raise ValueError(f"Missing or unsafe runner: {script}")
    output = directory / "artifacts"; output.mkdir(exist_ok=True)
    start = time.monotonic()
    with (output / "run.log").open("w", encoding="utf-8") as handle:
        result = subprocess.run([sys.executable, str(script)], cwd=ROOT, stdout=handle,
                                stderr=subprocess.STDOUT, timeout=1800, check=False)
    return {"folder": folder, "runner": runner, "exit_code": result.returncode,
            "elapsed_seconds": round(time.monotonic() - start, 2),
            "runner_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "log": str(output / "run.log"), "report_exists": (directory / "report.md").exists() or (output / "report.md").exists()}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--studies", nargs="*")
    parser.add_argument("--workers", type=int, default=3); args = parser.parse_args()
    if args.workers < 1 or args.workers > 3: parser.error("Choose 1-3 study workers")
    registry = json.loads((ROOT / "research/program.json").read_text(encoding="utf-8"))
    selected = [s for s in registry["studies"] if s.get("runner") and s["runner"] != "baseline"
                and (not args.studies or s["id"] in args.studies)]
    if args.studies and set(args.studies) - {s["id"] for s in selected}:
        parser.error("Requested study has no registered runnable script")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks = {pool.submit(run_one, study["folder"], study["runner"]): study for study in selected}
        for future in as_completed(tasks):
            study = tasks[future]
            try: result = future.result()
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                result = {"folder": study["folder"], "exit_code": None, "error": str(exc)}
            results.append(result); print(json.dumps(result), flush=True)
    destination = ROOT / "research" / "program_runs"; destination.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (destination / f"{stamp}.json").write_text(json.dumps({"created_at_utc": stamp, "results": results}, indent=2) + "\n", encoding="utf-8")
    if any(r["exit_code"] != 0 for r in results): raise SystemExit(1)


if __name__ == "__main__": main()
