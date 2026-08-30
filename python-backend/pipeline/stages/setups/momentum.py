import time
from pipeline.stages.live_state import LiveStockState
from pipeline.stages.setups.base import BaseSetup, SetupState

class MomentumSetup(BaseSetup):
    def __init__(self):
        super().__init__("MomentumContinuation")
        self.arm_threshold_pct = 0.005 # Arm if within 0.5% of level

    def evaluate(self, state: LiveStockState) -> None:
        now = time.time()

        if self.state == SetupState.IDLE:
            # Check for proximity to Opening Range High/Low or VWAP
            if state.opening_range_high and state.latest_price > 0:
                dist_orh = abs(state.latest_price - state.opening_range_high) / state.latest_price
                if dist_orh <= self.arm_threshold_pct and state.latest_price < state.opening_range_high:
                    self.arm("LONG", state.opening_range_high, invalidation_price=state.opening_range_high * 0.99)
                    return
            
            if state.opening_range_low and state.latest_price > 0:
                dist_orl = abs(state.latest_price - state.opening_range_low) / state.latest_price
                if dist_orl <= self.arm_threshold_pct and state.latest_price > state.opening_range_low:
                    self.arm("SHORT", state.opening_range_low, invalidation_price=state.opening_range_low * 1.01)
                    return
                    
            if state.session_vwap and state.latest_price > 0:
                dist_vwap = abs(state.latest_price - state.session_vwap) / state.latest_price
                if dist_vwap <= self.arm_threshold_pct:
                    if state.latest_price > state.session_vwap: # Bullish test of vwap
                         self.arm("LONG", state.session_vwap, invalidation_price=state.session_vwap * 0.99)
                    else:
                         self.arm("SHORT", state.session_vwap, invalidation_price=state.session_vwap * 1.01)
                    return

        elif self.state == SetupState.ARMED:
            # Check for trigger (break of level)
            if self.direction == "LONG" and state.latest_price > self.trigger_level:
                # Require price to hold above level for at least 10 seconds, or just trigger for now
                if now - self.armed_at > 10: 
                    self.trigger(state.latest_price, expiry_seconds=45)
            elif self.direction == "SHORT" and state.latest_price < self.trigger_level:
                if now - self.armed_at > 10:
                    self.trigger(state.latest_price, expiry_seconds=45)
                    
            # Invalidation
            if now - self.armed_at > 300: # 5 mins armed timeout
                self.invalidate()
            elif self.direction == "LONG" and state.latest_price < self.invalidation_price:
                self.invalidate()
            elif self.direction == "SHORT" and state.latest_price > self.invalidation_price:
                self.invalidate()

        elif self.state == SetupState.TRIGGERED:
            # If expired, invalidate
            if self.expires_at and now > self.expires_at:
                self.invalidate()
