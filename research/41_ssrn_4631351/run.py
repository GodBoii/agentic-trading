"""Freeze provenance, then run the two declared adaptations on local data."""

from hashlib import sha256
import json
from pathlib import Path

from research.common.runner import Variant, run_track

from .strategy import VARIANTS, VWAPDirectionPolicy


def main() -> None:
    track = Path(__file__).resolve().parent
    specification = track / "hypotheses.json"
    frozen = json.loads(specification.read_text(encoding="utf-8"))
    paper = track.parent / frozen["paper"]
    actual_hash = sha256(paper.read_bytes()).hexdigest()
    if actual_hash != frozen["paper_sha256"]:
        raise ValueError("local paper differs from frozen specification")
    variants = [
        Variant(
            name=name,
            factory=VWAPDirectionPolicy,
            parameters={
                "hypotheses_sha256": sha256(specification.read_bytes()).hexdigest(),
                "paper_sha256": actual_hash,
                "replication_status": frozen["replication_status"],
                "completed_bar_seconds": 60,
                "vwap_source": "vendor field at final observation of completed midpoint bar",
                "combination": frozen["combination"] if name == "vwap_momentum_confirmed" else None,
                "exit_rules": "shared fixed target, stop, horizon; no VWAP reversal exit",
            },
            policy_overrides=frozen["shared_policy"],
        )
        for name in VARIANTS
    ]
    run_track(track, variants, dates=frozen["dates"], modes=tuple(frozen["modes"]))


if __name__ == "__main__":
    main()
