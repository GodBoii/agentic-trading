from pathlib import Path

from research.common.runner import Variant, run_track
from .strategy import PeerResidualPolicy


def main() -> None:
    variants = []
    for direction in ("continuation", "reversal", "confirmed_reversal"):
        variants.append(Variant(
            name=f"peer_{direction}",
            factory=lambda cfg, direction=direction: PeerResidualPolicy(cfg, direction=direction),
            parameters={"direction": direction, "residual_threshold_bps": 10,
                        "minimum_peers": 4, "peer_weight": "equal", "hedged": False}))
    run_track(Path(__file__).parent, variants)


if __name__ == "__main__":
    main()
