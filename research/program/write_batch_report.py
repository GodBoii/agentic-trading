"""Produce a phase-aware cross-track report without selecting best returns."""

import json
from pathlib import Path

from .build_index import TOPICS, evidence


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    lines = ["# Research batch results", "",
             "Results are offline historical diagnostics. The table lists every completed account-replay variant by track, with no sorting by profitability. Different strategy/account policies can change exposure and loss-halt timing, so totals alone do not measure forecast quality.", "",
             "Receipt-proxy rows assume quote usability from recorded receipts. Source event age, exact queues, actual fills and decoder provenance are not established. Strict rows can be too sparse to estimate performance. No pristine final holdout exists in these dates.", "",
             "Incomplete exposure is reported separately. Closed-trade P&L excludes remaining positions and is not the account's final outcome. The seven dates are development Aug19/20/21, validation Aug24/25, and historical audit Aug31/Sep1. Models that train on development evaluate only later dates.", "",
             "## Account simulations", "",
             "| Track | Variant | Mode | Sessions | Closed trades | Gross Rs | Fees Rs | Closed net Rs | Incomplete sessions |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    total_replays = 0
    total_variants = 0
    for _, title, name, _ in TOPICS:
        item = evidence(ROOT / name)
        total_replays += item["account_replays"]
        total_variants += item["variants"]
        for run in item["runs"]:
            results = json.loads((ROOT / name / "runs" / run["run"] / "aggregate.json").read_text())["results"]
            for row in results:
                if row["phase"] != "all":
                    continue
                lines.append(f"|{name}|{row['variant']}|{row['mode']}|{row['sessions']}|{row['trades']}|"
                             f"{row['gross_pnl']:,.2f}|{row['fees']:,.2f}|{row['net_pnl']:,.2f}|{row['incomplete_sessions']}|")
    lines += ["", f"Current initial batches total {total_variants} frozen variant specifications and {total_replays} policy/session account replays. This excludes original baseline runs, exact repeats and non-account diagnostics.", "",
              "## What the evidence says", "",
              "The early momentum, indicator, snapshot-imbalance and peer-residual proxy experiments generally lose before fees. Fees add a substantial hurdle. A smaller monetary loss under a reduced order size or tighter opportunity gate is not proof of improved alpha.", "",
              "The numerical ridge/logistic model abstains because predicted net opportunity does not pass its frozen entry rules. Strict training was insufficient. Abstention is a valid outcome and must not be relabeled a profitable model.", "",
              "The unanimous same-time-of-day rule has only three filled trades, all SBI shorts, and one later audit loss. Its small positive total does not establish repeatability across instruments or market conditions. Pair diagnostics have insufficient strict coverage and a negative fitted hedge coefficient. No pair trades qualified.", "",
              "The paired exit experiment holds baseline entries fixed and diagnoses exits independently of account feedback. Its results are counterfactual outcomes, not a feasible simultaneous portfolio. Different holding times can overlap positions and need a real account controller before implementation.", "",
              "Track 15 treats bare archived last-trade times as ambiguous without original wire/decoder provenance. Attaching a receipt date and timezone without evidence can produce misleading apparent freshness. Last-trade time is also not a source quote-event timestamp.", "",
              "The raw-packet audit also shows that an aggregate-depth footprint can exceed displayed best-level size. Current aggressive fills remain a price/size proxy, not a depth-sweep or queue simulator. The new normalizer preserves actual level quantities for the next execution-model study.", "",
              "Relative-volume continuation and climax-reversal lose before fees and after them. Their three-day seasonal baseline is weak and strict data cannot fit it. Gaussian-mixture continuation loses; the low-efficiency fade abstains. Density responsibilities are not profit probabilities.", "",
              "The separate volatility-forecast study compares three fixed methods on 12,004 identical next-minute outcomes per method. Small pooled metric differences change ordering across periods. A squared-return forecast ranking does not establish directional alpha or a tradeable volatility opportunity.", "",
              "## Where to inspect evidence", "",
              "[Research index](C:/Users/prajw/Downloads/Trader/research/README.md) links each track's method. Each track stores its findings and versioned runs. The machine registry is [registry.json](C:/Users/prajw/Downloads/Trader/research/program/registry.json).", "",
              "The verification tool checks archived source/data fingerprints and accounting on completed common runs. Its test report and verified-run list are saved below `program/runs`. Successful verification establishes consistency of the experiment evidence, not correctness of market-access assumptions.", "",
              "## Next gates", "",
              "Preserve an independently selected cohort with full packets and timestamp/decoder provenance. Add actual top-level quantities, corporate-action and trading-status references, and disconnect/queue-quality events. Calibrate order timelines and fills under the approved execution scope before selecting a fast strategy.", "",
              "Continue the 40-topic queue with distinct economic or mathematical mechanisms. Specify hypotheses before opening later data, report source differences when adapting a paper, track all trials, and require new independent sessions for a final evaluation. Repeated parameter searches on these seven dates will not create a valid holdout.", "",
              "No production trading module, credential state or live order was changed by this batch."]
    (ROOT / "program/BATCH_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"frozen_variants": total_variants, "account_replays": total_replays}))


if __name__ == "__main__":
    main()
