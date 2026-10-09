"""Audit complete phase comparisons across finished research tracks."""

from collections import defaultdict
import argparse
import json
from pathlib import Path

import pandas as pd

from .statistics import benjamini_hochberg, sign_flip_tail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default="initial-v1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    rows = []
    included = []
    for track in sorted(root.glob("[0-9][0-9]_*")):
        completed = [p for p in (track / "runs").glob("*/aggregate.json")
                     if p.parent.name.startswith("initial-") and (p.parent / "plan.json").exists()
                     and not list(p.parent.glob("invalid*.md"))
                     and not list(track.glob(f"invalid-{p.parent.name}.md"))]
        if not completed:
            continue
        # Versions remain separate; selecting a profitable version is prohibited.
        for aggregate_path in sorted(completed):
            run = aggregate_path.parent
            plan = json.loads((run / "plan.json").read_text())
            if "validation_diagnostic" not in plan.get("phases", {}).values():
                continue
            included.append(str(run.relative_to(root)))
            groups = defaultdict(list)
            for summary in run.glob("summary-*.json"):
                result = json.loads(summary.read_text())
                if result["phase"] == "validation_diagnostic":
                    groups[(result["variant"], result["mode"])].append(result)
            for (variant, mode), results in sorted(groups.items()):
                if len(results) != 2 or not all(result["complete"] for result in results):
                    rows.append({"track": track.name, "run": run.name, "variant": variant,
                                 "mode": mode, "eligible_for_diagnostic": False,
                                 "reason": "missing or unresolved validation sessions"})
                    continue
                values = [result["net_pnl"] for result in sorted(results, key=lambda item: item["date"])]
                rows.append({"track": track.name, "run": run.name, "variant": variant, "mode": mode,
                             "eligible_for_diagnostic": True, "reason": "assumptions unverified",
                             "sessions": 2, "net_pnl": sum(values),
                             "trades": sum(result["trades"] for result in results),
                             "raw_tail_diagnostic": sign_flip_tail(values)})
    eligible = [row for row in rows if row["eligible_for_diagnostic"]]
    adjusted = benjamini_hochberg([row["raw_tail_diagnostic"] for row in eligible])
    for row, value in zip(eligible, adjusted, strict=True):
        row["bh_adjusted_diagnostic"] = value
        row["promotion_eligible"] = False
    run_root = Path(__file__).parent / "runs"
    output = (run_root / args.run_name).resolve()
    if not output.is_relative_to(run_root.resolve()) or output.exists():
        raise ValueError("statistics evidence cannot be overwritten; choose a new version")
    output.mkdir(parents=True)
    report = {"source_runs": included, "comparisons": rows,
              "assumptions": ["exact tail assumes independent symmetric session errors",
                              "BH FDR guarantee needs valid pvalues and suitable dependence",
                              "neither assumption is established by these recordings",
                              "two validation sessions provide at most four sign permutations",
                              "all dates previously inspected; no pristine final holdout"],
              "promotion_eligible": False}
    (output / "diagnostics.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    pd.DataFrame(rows).to_csv(output / "comparisons.csv", index=False)
    print(json.dumps({"comparisons": len(rows), "complete_for_diagnostic": len(eligible),
                      "adjusted_below_005": sum(value < .05 for value in adjusted)}))


if __name__ == "__main__":
    main()
