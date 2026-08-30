import time
from pipeline.stages.live_state import LiveStockState
from pipeline.stages.setups.base import BaseSetup, SetupState

class MeanReversionSetup(BaseSetup):
    def __init__(self):
        super().__init__("MeanReversion")
        self.stretch_threshold_pct = 0.015 # Arm if > 1.5% from VWAP
        self.reclaim_pct = 0.005 # Trigger if reclaims 0.5% from extreme

    def evaluate(self, state: LiveStockState) -> None:
        now = time.time()

        if self.state == SetupState.IDLE:
            if state.session_vwap and state.latest_price > 0:
                dist_vwap = (state.latest_price - state.session_vwap) / state.session_vwap
                
                if dist_vwap >= self.stretch_threshold_pct:
                    # Stretched to upside, look for short
                    self.arm("SHORT", state.latest_price * (1 - self.reclaim_pct), invalidation_price=state.latest_price * 1.01)
                elif dist_vwap <= -self.stretch_threshold_pct:
                    # Stretched to downside, look for long
                    self.arm("LONG", state.latest_price * (1 + self.reclaim_pct), invalidation_price=state.latest_price * 0.99)

        elif self.state == SetupState.ARMED:
            # Update extremes while armed
            if self.direction == "SHORT" and state.latest_price > (self.trigger_level / (1 - self.reclaim_pct)):
                # Made a new high, re-arm with new levels
                self.arm("SHORT", state.latest_price * (1 - self.reclaim_pct), invalidation_price=state.latest_price * 1.01)
            elif self.direction == "LONG" and state.latest_price < (self.trigger_level / (1 + self.reclaim_pct)):
                # Made a new low, re-arm with new levels
                self.arm("LONG", state.latest_price * (1 + self.reclaim_pct), invalidation_price=state.latest_price * 0.99)
                
            # Trigger logic
            if self.direction == "SHORT" and state.latest_price < self.trigger_level:
                self.trigger(state.latest_price, expiry_seconds=45)
            elif self.direction == "LONG" and state.latest_price > self.trigger_level:
                self.trigger(state.latest_price, expiry_seconds=45)

            # Invalidation logic
            if now - self.armed_at > 300: # 5 mins armed timeout
                self.invalidate()

        elif self.state == SetupState.TRIGGERED:
            # If expired, invalidate
            if self.expires_at and now > self.expires_at:
                self.invalidate()
