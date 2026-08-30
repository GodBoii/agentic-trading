from __future__ import annotations

from datetime import datetime
from typing import List

from pipeline.stages.live_state import LiveStockState
from pipeline.stages.setups.base import SetupSignal
from pipeline.stages.setups.mean_reversion import MeanReversionDetector
from pipeline.stages.setups.momentum import MomentumDetector


class SetupEngine:
    def __init__(self) -> None:
        self.detectors = (MomentumDetector(), MeanReversionDetector())

    def evaluate(self, state: LiveStockState, now: datetime) -> List[SetupSignal]:
        if not state.is_hot:
            return []
        signals: List[SetupSignal] = []
        for detector in self.detectors:
            signals.extend(detector.evaluate(state, now))
        return signals
