from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ResearchConfig
from .io import write_json
from .replay import QuoteBook
from .strategies import strategy_library


def evidence_from_row(row: dict, book: QuoteBook, config: ResearchConfig) -> dict:
    """Historical agent context excludes future labels and replay outcomes."""
    at = row["decision_at"]
    snapshot = book.snapshot(at)
    candidates = []
    if snapshot:
        expiry = min(quote["expiry"] for quote in snapshot.values())
        quotes = {(quote["option_type"], quote["strike"]): quote for quote in snapshot.values() if quote["expiry"] == expiry}
        atm = min({strike for _, strike in quotes}, key=lambda strike: abs(strike - row["close"]))
        for strategy in strategy_library(quotes, atm, expiry):
            candidates.append({"candidate_id": f"{row['date']}:{expiry}:{atm}:{strategy.name}",
                               "strategy": strategy.name, "legs": [leg.__dict__ for leg in strategy.legs],
                               "expiry_payoff": strategy.expiry_risk(config.lot_size),
                               "execution_available": False, "margin": None, "greeks": None,
                               "quote_times": {leg.security_id: snapshot[leg.security_id]["timestamp"].isoformat()
                                               for leg in strategy.legs}})
    feature_names = ["ret_1_bps", "ret_5_bps", "rv_5_bps", "range_5_bps", "spread_bps", "oi_change_bps",
                     "imbalance_5", "imbalance_20", "imbalance_200", "imbalance_points_10", "imbalance_weighted"]
    return {"mode": "historical_research", "decision_at": at.isoformat(), "date": row["date"],
            "security_id": row["security_id"], "source_at": row["source_at"].isoformat(),
            "depth_at": row["depth_at"].isoformat(), "horizon_minutes": config.horizon_minutes,
            "features": {key: float(row[key]) for key in feature_names},
            "forecasts_bps": {key.removeprefix("prediction_"): float(value)
                              for key, value in row.items() if key.startswith("prediction_")},
            "candidates": candidates, "allowed_actions": ["no_trade", "record_research_hypothesis"],
            "execution_available": False,
            "missing_evidence": ["Current live session", "Quote sizes and original timestamps", "Synchronized spot",
                                 "IV and Greeks", "Margin", "News", "Fresh independent validation"]}


def build_evidence_bundle(output: Path, config: ResearchConfig) -> None:
    predictions = pd.read_parquet(output / "predictions.parquet").sort_values("decision_at")
    for row in reversed(predictions.to_dict("records")):
        path = output / "sessions" / row["date"] / "options.parquet"
        if path.exists():
            book = QuoteBook(pd.read_parquet(path), config.option_quote_age_seconds)
            bundle = evidence_from_row(row, book, config)
            bundle["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
            write_json(output / "historical-agent-evidence.json", bundle)
            return
    write_json(output / "historical-agent-evidence.json", {"mode": "unavailable", "execution_available": False})
