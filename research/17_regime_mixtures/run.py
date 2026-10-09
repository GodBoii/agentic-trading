"""Fit development-only normalization/mixture and freeze four later evaluations."""

from pathlib import Path
import json

from research.common.data import DEVELOPMENT, DATES, load_manifest, load_ticks
from research.common.runner import Variant, run_track
from .strategy import RegimePolicy, VARIANTS, fit_model


def main() -> None:
    folder = Path(__file__).parent
    model_folder = folder / "models" / "initial-v1"
    if model_folder.exists():
        raise ValueError("model evidence exists; use a new frozen specification")
    sessions = {day: load_ticks(day) for day in DEVELOPMENT}
    models, reports = {}, {}
    for mode in ("recent_trade", "receipt_proxy"):
        models[mode], reports[mode] = fit_model(sessions, mode)
        reports[mode]["input_hashes"] = {day: load_manifest(day)["cache_sha256"] for day in DEVELOPMENT}
    model_folder.mkdir(parents=True)
    for mode, report in reports.items():
        (model_folder / f"{mode}.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    variants = [Variant(name=name,
                        factory=lambda cfg: RegimePolicy(cfg, models[cfg.freshness_mode], DEVELOPMENT),
                        parameters={"features": ["five_minute_log_return_bps", "std_one_minute_returns_bps", "path_efficiency"],
                                    "completed_bars": 6, "em_iterations": 30, "seed": 17,
                                    "minimum_training_rows": 200, "minimum_rows_per_training_day": 20,
                                    "posterior_threshold": .8, "move_range_bps": [15, 100],
                                    "confirmation_bps": 1, "frozen_models": reports,
                                    "posterior_semantics": "density responsibility, not profit probability",
                                    "temporal_model": "independent mixture, no Markov transition or future smoothing"},
                        policy_overrides={"target_bps": 30, "stop_bps": 20, "horizon_seconds": 600,
                                          "cooldown_seconds": 600, "require_cost_room": True}) for name in VARIANTS]
    run_track(folder, variants, dates=list(DATES[3:]))


if __name__ == "__main__":
    main()
