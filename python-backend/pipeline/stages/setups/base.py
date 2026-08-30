from enum import Enum
import time
from typing import Optional, Dict, Any
from pipeline.stages.live_state import LiveStockState

class SetupState(Enum):
    IDLE = 1
    ARMED = 2
    TRIGGERED = 3
    INVALIDATED = 4

class BaseSetup:
    def __init__(self, name: str):
        self.name = name
        self.state = SetupState.IDLE
        self.direction: Optional[str] = None
        self.armed_at: Optional[float] = None
        self.triggered_at: Optional[float] = None
        self.expires_at: Optional[float] = None
        self.trigger_price: Optional[float] = None
        self.trigger_level: Optional[float] = None
        self.invalidation_price: Optional[float] = None
        
    def reset(self):
        self.state = SetupState.IDLE
        self.direction = None
        self.armed_at = None
        self.triggered_at = None
        self.expires_at = None
        self.trigger_price = None
        self.trigger_level = None
        self.invalidation_price = None

    def evaluate(self, state: LiveStockState) -> None:
        """Evaluate the setup against the current live state."""
        raise NotImplementedError

    def arm(self, direction: str, trigger_level: float, invalidation_price: float):
        self.state = SetupState.ARMED
        self.direction = direction
        self.armed_at = time.time()
        self.trigger_level = trigger_level
        self.invalidation_price = invalidation_price

    def trigger(self, price: float, expiry_seconds: int = 60):
        self.state = SetupState.TRIGGERED
        self.triggered_at = time.time()
        self.trigger_price = price
        self.expires_at = self.triggered_at + expiry_seconds

    def invalidate(self):
        self.state = SetupState.INVALIDATED

    def to_contract(self, state: LiveStockState) -> Dict[str, Any]:
        """Convert triggered setup to short-lived contract payload."""
        return {
            "setup_family": self.name,
            "direction": self.direction,
            "detected_at": self.armed_at,
            "triggered_at": self.triggered_at,
            "expires_at": self.expires_at,
            "trigger_level": self.trigger_level,
            "trigger_price": self.trigger_price,
            "invalidation_price": self.invalidation_price,
            "volume_pace_percentile": state.volume_pace_percentile,
            "realized_volatility_percentile": state.realized_volatility_percentile,
        }
