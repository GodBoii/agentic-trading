"""Fit three fixed prior dates, then evaluate four later dates without retraining."""

from dataclasses import replace
from pathlib import Path
import json

from research.common.data import DEVELOPMENT, DATES, load_manifest, load_ticks
from research.common.runner import Variant, run_track
from .strategy import SeasonalityPolicy, VARIANTS, fit_model


def main() -> None:
    folder = Path(__file__).parent
    model_folder = folder / "models" / "initial-v1"
    if model_folder.exists():
        raise ValueError("frozen model evidence already exists; use a new run specification")
    sessions = {day: load_ticks(day) for day in DEVELOPMENT}
    modes = ("recent_trade", "receipt_proxy")
    models, reports = {}, {}
    for mode in modes:
        models[mode], reports[mode] = fit_model(sessions, mode)
        reports[mode]["input_hashes"] = {day: load_manifest(day)["cache_sha256"] for day in DEVELOPMENT}
    model_folder.mkdir(parents=True)
    for mode in modes:
        (model_folder / f"{mode}.json").write_text(json.dumps(reports[mode], indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    variants = [Variant(name=name,
                        factory=lambda cfg: SeasonalityPolicy(cfg, models[cfg.freshness_mode]),
                        parameters={"slot_seconds": 1800, "slot_anchor_ist": "09:15",
                                    "entry_slots": list(range(1, 11)), "first_quote_tolerance_seconds": 10,
                                    "training_dates": list(DEVELOPMENT), "minimum_prior_sessions": 3,
                                    "minimum_absolute_mean_bps": 10,
                                    "frozen_models": reports,
                                    "transfer": "short-history own-stock adaptation; not paper replication"},
                        policy_overrides={"target_bps": 30, "stop_bps": 20, "horizon_seconds": 1790,
                                          "cooldown_seconds": 1800, "require_cost_room": True}) for name in VARIANTS]
    run_track(folder, variants, dates=list(DATES[3:]))


if __name__ == "__main__":
    main()
