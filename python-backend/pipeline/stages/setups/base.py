from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional


class SetupPhase(str, Enum):
    IDLE = "IDLE"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class SetupSignal:
    family: str
    direction: str
    armed_at: datetime
    triggered_at: datetime
    expires_at: datetime
    trigger_level: float
    trigger_price: float
    invalidation_price: float
    reason: str
    diagnostics: Dict[str, Any]


def arm_or_trigger(
    tracker: Dict[str, Any],
    *,
    now: datetime,
    family: str,
    direction: str,
    level: float,
    invalidation: float,
    reason: str,
    diagnostics: Dict[str, Any],
    hold_seconds: int,
    expiry_seconds: int,
    rearm_seconds: int = 300,
) -> Optional[SetupSignal]:
    cooldown_until = tracker.get("cooldown_until")
    if cooldown_until:
        try:
            if now < datetime.fromisoformat(str(cooldown_until)):
                return None
        except ValueError:
            tracker.pop("cooldown_until", None)
    identity = f"{family}:{direction}"
    if tracker.get("identity") != identity:
        tracker.clear()
        tracker.update(
            {
                "phase": SetupPhase.ARMED.value,
                "identity": identity,
                "armed_at": now.isoformat(),
                "level": level,
                "invalidation": invalidation,
                "direction": direction,
            }
        )
        return None
    try:
        armed_at = datetime.fromisoformat(str(tracker["armed_at"]))
    except (KeyError, ValueError):
        tracker.clear()
        return None
    if (now - armed_at).total_seconds() < hold_seconds:
        return None
    if tracker.get("phase") == SetupPhase.TRIGGERED.value:
        return None
    tracker["phase"] = SetupPhase.TRIGGERED.value
    tracker["triggered_at"] = now.isoformat()
    tracker["cooldown_until"] = (now + timedelta(seconds=rearm_seconds)).isoformat()
    return SetupSignal(
        family=family,
        direction=direction,
        armed_at=armed_at,
        triggered_at=now,
        expires_at=now + timedelta(seconds=expiry_seconds),
        trigger_level=float(tracker["level"]),
        trigger_price=float(diagnostics["price"]),
        invalidation_price=float(tracker["invalidation"]),
        reason=reason,
        diagnostics=diagnostics,
    )


def reset_tracker(tracker: Dict[str, Any]) -> None:
    cooldown_until = tracker.get("cooldown_until")
    tracker.clear()
    tracker["phase"] = SetupPhase.IDLE.value
    if cooldown_until:
        tracker["cooldown_until"] = cooldown_until
