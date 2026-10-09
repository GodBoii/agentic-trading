"""Replay the preregistered standalone and agreement rules without tuning."""

from pathlib import Path
from hashlib import sha256

from research.common.runner import Variant, run_track
from .strategy import GithubMethodsPolicy, VARIANTS


def main() -> None:
    folder = Path(__file__).parent
    variants = [Variant(name=name, factory=GithubMethodsPolicy, parameters={
        "completed_minute_bars": True, "warmup_bars": 20,
        "kalman_state": ["relative_log_price_bps", "slope_bps_per_minute"],
        "F": [[1, 1], [0, 1]], "H": [1, 0], "Q": [[0.25, 0], [0, 0.04]],
        "R": 9, "initial_mean": [0, 0], "initial_P": [[25, 0], [0, 4]],
        "kalman_forecast_minutes": 5, "kalman_forecast_minimum_bps": 15,
        "kalman_slope_standard_error_multiple": 2,
        "kalman_five_minute_move_bps": [10, 100],
        "cusum_threshold_log_return_bps": 15, "cusum_crossing": "strict",
        "cusum_reset": "triggered side only", "combination": "same-direction AND",
        "training": "none; fixed parameters before replay; no EM or smoothing",
        "source_manifest": "upstream/manifest.json",
        "source_manifest_sha256": sha256((folder / "upstream/manifest.json").read_bytes()).hexdigest(),
        "hypotheses_sha256": sha256((folder / "hypotheses.md").read_bytes()).hexdigest(),
    }, policy_overrides={"target_bps": 30, "stop_bps": 20, "horizon_seconds": 600,
                         "cooldown_seconds": 600, "require_cost_room": True}) for name in VARIANTS]
    run_track(folder, variants)


if __name__ == "__main__":
    main()
