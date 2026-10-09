"""Reconcile saved candle trades, daily ledgers and frozen implementation hashes."""

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    track = Path(__file__).resolve().parent
    output = track / "candle-runs/initial-v1"
    daily = pd.read_csv(output / "daily.csv")
    trades = pd.read_csv(output / "trades.csv")
    plan = json.loads((output / "plan.json").read_text(encoding="utf-8"))
    if sha256((track / "candle_run.py").read_bytes()).hexdigest() != plan["source_sha256"]:
        raise ValueError("implementation changed after frozen run")
    if sha256((track / "candle-hypotheses.json").read_bytes()).hexdigest() != plan["hypotheses_sha256"]:
        raise ValueError("candle hypotheses changed after frozen run")
    if not np.allclose(trades.net_pnl, trades.gross_pnl - trades.fees, atol=1e-8):
        raise ValueError("trade fee accounting does not reconcile")
    if not ((trades.entry_index >= 1) & (trades.exit_index >= trades.entry_index) & (trades.exit_index <= 374)).all():
        raise ValueError("causal candle execution index failed")
    keys = ["security_id", "variant", "slippage_bps", "date"]
    actual = trades.groupby(keys)[["gross_pnl", "fees", "net_pnl"]].sum()
    expected = daily.set_index(keys)[["gross_pnl", "fees", "net_pnl"]]
    aligned = actual.reindex(expected.index, fill_value=0)
    if not np.allclose(aligned, expected, atol=1e-6):
        raise ValueError("daily ledger differs from saved trade ledger")
    for _, sleeve in daily.groupby(keys[:3]):
        ordered = sleeve.sort_values("date")
        starts = ordered.starting_equity.to_numpy()
        ends = ordered.ending_equity.to_numpy()
        if starts[0] != 100_000 or not np.allclose(starts[1:], ends[:-1], atol=1e-8):
            raise ValueError("sleeve capital continuity failed")
        if not np.allclose(ends - starts, ordered.net_pnl, atol=1e-8):
            raise ValueError("daily equity accounting failed")
    report = {"verified": True, "daily_ledger_rows": len(daily), "trade_ledger_rows": len(trades),
              "checks": ["frozen_source_hash", "frozen_specification_hash", "trade_fee_accounting",
                         "next_bar_execution_indexes", "daily_trade_reconciliation", "sleeve_capital_continuity"]}
    (output / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
