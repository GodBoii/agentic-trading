"""Persist and enforce Dhan order-placement readiness.

The gate verifies Dhan's detected source IP and ordersAllowed flag at startup and
on a fixed interval. A DH-905 order response blocks it immediately between checks.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable, Dict, Optional

from pipeline.services.convex_service import ConvexService
from pipeline.services.storage_service import StorageService

BROKER = "dhan"
DEFAULT_VERIFY_INTERVAL_SECONDS = 6 * 60 * 60
ORDER_PLACEMENT_ALLOWED = "ORDER_PLACEMENT_ALLOWED"
ORDER_PLACEMENT_UNKNOWN = "ORDER_PLACEMENT_UNKNOWN"
ORDER_PLACEMENT_VERIFICATION_FAILED = "ORDER_PLACEMENT_VERIFICATION_FAILED"
DHAN_IP_NOT_ALLOWED = "DHAN_IP_NOT_ALLOWED"
DH905_INVALID_IP = "DH-905_INVALID_IP"


def _text(value: Any) -> Optional[str]:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _is_dh905(response: Any) -> bool:
    if isinstance(response, dict):
        remarks = response.get("remarks")
        code = remarks.get("error_code") if isinstance(remarks, dict) else response.get("error_code")
        normalized = str(code or "").strip().lower().removeprefix("dh-")
        if normalized == "905":
            return True
    try:
        return "dh-905" in json.dumps(response, ensure_ascii=True, default=str).lower()
    except Exception:
        return "dh-905" in str(response).lower()


def _broker_error_message(response: Any) -> str:
    if not isinstance(response, dict):
        return _text(response) or "Invalid IP"
    remarks = response.get("remarks")
    if isinstance(remarks, dict):
        return _text(remarks.get("error_message") or remarks.get("errorMessage")) or "Invalid IP"
    return _text(remarks) or "Invalid IP"


@dataclass(frozen=True)
class OrderPlacementState:
    allowed: bool
    status_code: str
    reason: str
    verified_at: str
    next_verification_at: str
    detected_ip: Optional[str] = None
    primary_ip: Optional[str] = None
    secondary_ip: Optional[str] = None
    orders_allowed: Optional[bool] = None
    broker_message: Optional[str] = None

    @classmethod
    def unknown(cls, now: datetime) -> "OrderPlacementState":
        timestamp = now.isoformat()
        return cls(
            allowed=False,
            status_code=ORDER_PLACEMENT_UNKNOWN,
            reason="order_placement_not_verified",
            verified_at=timestamp,
            next_verification_at=timestamp,
        )

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "OrderPlacementState":
        return cls(
            allowed=bool(record.get("allowed")),
            status_code=str(
                record.get("status_code")
                or record.get("statusCode")
                or ORDER_PLACEMENT_UNKNOWN
            ),
            reason=str(record.get("reason") or "order_placement_not_verified"),
            verified_at=str(record.get("verified_at") or record.get("verifiedAt") or ""),
            next_verification_at=str(
                record.get("next_verification_at") or record.get("nextVerificationAt") or ""
            ),
            detected_ip=_text(record.get("detected_ip") or record.get("detectedIp")),
            primary_ip=_text(record.get("primary_ip") or record.get("primaryIp")),
            secondary_ip=_text(record.get("secondary_ip") or record.get("secondaryIp")),
            orders_allowed=(
                bool(record.get("orders_allowed"))
                if "orders_allowed" in record
                else bool(record.get("ordersAllowed"))
                if "ordersAllowed" in record
                else None
            ),
            broker_message=_text(record.get("broker_message") or record.get("brokerMessage")),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OrderPlacementStateService:
    @staticmethod
    def load(path: Path) -> Optional[OrderPlacementState]:
        if ConvexService.configured():
            record = ConvexService.get_order_placement_state(BROKER)
            return OrderPlacementState.from_record(record) if record else None
        if ConvexService.required():
            raise RuntimeError("Convex persistence is required for order-placement state.")
        payload = StorageService.load_snapshot(Path(path))
        return OrderPlacementState.from_record(payload) if isinstance(payload, dict) else None

    @staticmethod
    def save(path: Path, state: OrderPlacementState) -> None:
        payload = state.as_dict()
        if ConvexService.configured():
            args: Dict[str, Any] = {
                "broker": BROKER,
                "allowed": state.allowed,
                "statusCode": state.status_code,
                "reason": state.reason,
                "verifiedAt": state.verified_at,
                "nextVerificationAt": state.next_verification_at,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }
            optional = {
                "detectedIp": state.detected_ip,
                "primaryIp": state.primary_ip,
                "secondaryIp": state.secondary_ip,
                "ordersAllowed": state.orders_allowed,
                "brokerMessage": state.broker_message,
            }
            args.update({key: value for key, value in optional.items() if value is not None})
            ConvexService.set_order_placement_state(args)
        elif ConvexService.required():
            raise RuntimeError("Convex persistence is required for order-placement state.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        StorageService.save_snapshot(Path(path), payload)

    @staticmethod
    def is_allowed(path: Path) -> bool:
        state = OrderPlacementStateService.load(path)
        return bool(state and state.allowed)


class OrderPlacementGate:
    """Shared process gate for admission and final Dhan placement calls."""

    def __init__(
        self,
        dhan: Any,
        state_path: Path,
        *,
        interval_seconds: Optional[int] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._dhan = dhan
        self._state_path = Path(state_path)
        configured_interval = interval_seconds or int(
            os.getenv(
                "DHAN_ORDER_PLACEMENT_VERIFY_INTERVAL_SECONDS",
                str(DEFAULT_VERIFY_INTERVAL_SECONDS),
            )
        )
        self.interval_seconds = max(60, configured_interval)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._state_lock = Lock()
        self.placement_lock = Lock()
        self._stop = Event()
        self._dh905_latched = Event()
        self._verification_thread: Optional[Thread] = None
        self._on_verified: Optional[Callable[[OrderPlacementState], None]] = None
        try:
            initial = OrderPlacementStateService.load(self._state_path)
        except Exception as exc:
            print(f"[Order Gate] state load failed: {type(exc).__name__}: {exc}", flush=True)
            initial = None
        self._state = initial or OrderPlacementState.unknown(self._now())
        if self._state.status_code == DH905_INVALID_IP:
            self._dh905_latched.set()

    @property
    def state(self) -> OrderPlacementState:
        with self._state_lock:
            return self._state

    @property
    def allowed(self) -> bool:
        return self.state.allowed

    def refresh_from_store(self) -> OrderPlacementState:
        if self._dh905_latched.is_set():
            return self.state
        try:
            persisted = OrderPlacementStateService.load(self._state_path)
        except Exception as exc:
            persisted = OrderPlacementState(
                allowed=False,
                status_code=ORDER_PLACEMENT_VERIFICATION_FAILED,
                reason="order_placement_state_unavailable",
                verified_at=self._now().isoformat(),
                next_verification_at=self._next_verification(self._now()).isoformat(),
                broker_message=f"{type(exc).__name__}: {exc}",
            )
        self._set_local(persisted or OrderPlacementState.unknown(self._now()))
        return self.state

    def verify(self) -> OrderPlacementState:
        checked_at = self._now()
        try:
            response = self._dhan.fetch_static_ips()
            state = self._state_from_verification(response, checked_at)
        except Exception as exc:
            state = OrderPlacementState(
                allowed=False,
                status_code=ORDER_PLACEMENT_VERIFICATION_FAILED,
                reason="dhan_ip_verification_failed",
                verified_at=checked_at.isoformat(),
                next_verification_at=self._next_verification(checked_at).isoformat(),
                broker_message=f"{type(exc).__name__}: {exc}",
            )
        self._publish(state)
        effective = self.state
        print(
            "[Order Gate] "
            f"allowed={effective.allowed} status={effective.status_code} "
            f"detected_ip={effective.detected_ip or 'unknown'} "
            f"orders_allowed={effective.orders_allowed}",
            flush=True,
        )
        return effective

    def block_from_order_response(self, response: Any) -> Optional[OrderPlacementState]:
        if not _is_dh905(response):
            return None
        checked_at = self._now()
        message = _broker_error_message(response)
        previous = self.state
        blocked = OrderPlacementState(
            allowed=False,
            status_code=DH905_INVALID_IP,
            reason="dhan_rejected_order_source_ip",
            verified_at=checked_at.isoformat(),
            next_verification_at=self._next_verification(checked_at).isoformat(),
            detected_ip=previous.detected_ip,
            primary_ip=previous.primary_ip,
            secondary_ip=previous.secondary_ip,
            orders_allowed=False,
            broker_message=message or "Invalid IP",
        )
        # Stop sibling placements before performing persistence I/O.
        self._dh905_latched.set()
        self._set_local(blocked)
        self._persist(blocked)
        print("[Order Gate] Dhan returned DH-905. Order placement is blocked.", flush=True)
        return blocked

    def start_periodic_verification(
        self,
        *,
        verify_now: bool = True,
        on_verified: Optional[Callable[[OrderPlacementState], None]] = None,
    ) -> None:
        self._on_verified = on_verified
        if verify_now:
            state = self.verify()
            if self._on_verified is not None:
                self._on_verified(state)
        if self._verification_thread and self._verification_thread.is_alive():
            return
        self._verification_thread = Thread(
            target=self._verification_loop,
            name="dhan-order-placement-verifier",
            daemon=True,
        )
        self._verification_thread.start()

    def stop_periodic_verification(self) -> None:
        self._stop.set()

    def _verification_loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            state = self.verify()
            if self._on_verified is not None:
                try:
                    self._on_verified(state)
                except Exception as exc:
                    print(
                        f"[Order Gate] verification callback failed: {type(exc).__name__}: {exc}",
                        flush=True,
                    )

    def _state_from_verification(
        self,
        response: Any,
        checked_at: datetime,
    ) -> OrderPlacementState:
        if not isinstance(response, dict) or str(response.get("status") or "").lower() == "failure":
            message = str(response.get("remarks") if isinstance(response, dict) else "invalid_response")
            return OrderPlacementState(
                allowed=False,
                status_code=ORDER_PLACEMENT_VERIFICATION_FAILED,
                reason="dhan_ip_verification_failed",
                verified_at=checked_at.isoformat(),
                next_verification_at=self._next_verification(checked_at).isoformat(),
                broker_message=message,
            )
        data = response.get("data")
        if not isinstance(data, dict):
            return OrderPlacementState(
                allowed=False,
                status_code=ORDER_PLACEMENT_VERIFICATION_FAILED,
                reason="dhan_ip_verification_missing_data",
                verified_at=checked_at.isoformat(),
                next_verification_at=self._next_verification(checked_at).isoformat(),
            )
        detected = _text(data.get("detectedIP") or data.get("detectedIp"))
        primary = _text(data.get("primaryIP"))
        secondary = _text(data.get("secondaryIP"))
        raw_orders_allowed = data.get("ordersAllowed")
        orders_allowed = raw_orders_allowed if isinstance(raw_orders_allowed, bool) else None
        ip_matches = bool(detected and detected in {primary, secondary})
        allowed = orders_allowed is True and ip_matches
        return OrderPlacementState(
            allowed=allowed,
            status_code=ORDER_PLACEMENT_ALLOWED if allowed else DHAN_IP_NOT_ALLOWED,
            reason="dhan_order_placement_verified" if allowed else "dhan_ip_or_order_permission_invalid",
            verified_at=checked_at.isoformat(),
            next_verification_at=self._next_verification(checked_at).isoformat(),
            detected_ip=detected,
            primary_ip=primary,
            secondary_ip=secondary,
            orders_allowed=orders_allowed,
            broker_message=_text(data.get("message")),
        )

    def _next_verification(self, checked_at: datetime) -> datetime:
        return checked_at + timedelta(seconds=self.interval_seconds)

    def _publish(self, state: OrderPlacementState) -> None:
        if not state.allowed:
            self._set_local(state)
            self._persist(state)
            return
        if self._persist(state):
            self._set_local(state)
            self._dh905_latched.clear()
            return
        failed = OrderPlacementState(
            allowed=False,
            status_code=ORDER_PLACEMENT_VERIFICATION_FAILED,
            reason="order_placement_state_persistence_failed",
            verified_at=state.verified_at,
            next_verification_at=state.next_verification_at,
            detected_ip=state.detected_ip,
            primary_ip=state.primary_ip,
            secondary_ip=state.secondary_ip,
            orders_allowed=state.orders_allowed,
            broker_message="Verified state could not be persisted.",
        )
        self._set_local(failed)

    def _set_local(self, state: OrderPlacementState) -> None:
        with self._state_lock:
            self._state = state

    def _persist(self, state: OrderPlacementState) -> bool:
        try:
            OrderPlacementStateService.save(self._state_path, state)
            return True
        except Exception as exc:
            print(
                f"[Order Gate] state persistence failed: {type(exc).__name__}: {exc}",
                flush=True,
            )
            return False
