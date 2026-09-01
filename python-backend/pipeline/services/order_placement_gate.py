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
from zoneinfo import ZoneInfo

from pipeline.services.convex_service import ConvexService
from pipeline.services.storage_service import StorageService

BROKER = "dhan"
DEFAULT_VERIFY_INTERVAL_SECONDS = 6 * 60 * 60
DEFAULT_DAILY_VERIFY_TIME_IST = "08:30"
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
        self._market_timezone = ZoneInfo("Asia/Kolkata")
        self._daily_verify_hour, self._daily_verify_minute = self._parse_daily_verify_time(
            os.getenv("DHAN_DAILY_VERIFICATION_TIME_IST", DEFAULT_DAILY_VERIFY_TIME_IST)
        )
        self._state_lock = Lock()
        self.placement_lock = Lock()
        self._trade_slot_lock = Lock()
        self._trade_slot_reservations: Dict[str, datetime] = {}
        self.trade_slot_reservation_grace_seconds = max(
            5,
            int(os.getenv("AI_TRADING_SLOT_RESERVATION_GRACE_SECONDS", "30")),
        )
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

    def reserve_trade_slot(self, security_id: int) -> None:
        with self._trade_slot_lock:
            self._trade_slot_reservations[str(int(security_id))] = self._now()

    def active_trade_slots(self, broker_security_ids: set[str]) -> set[str]:
        """Merge broker state with recent placements that may not be visible yet."""
        now = self._now()
        normalized_broker_ids = {
            str(value) for value in broker_security_ids if str(value).strip()
        }
        with self._trade_slot_lock:
            for security_id, reserved_at in list(self._trade_slot_reservations.items()):
                if security_id in normalized_broker_ids:
                    continue
                if (now - reserved_at).total_seconds() > self.trade_slot_reservation_grace_seconds:
                    self._trade_slot_reservations.pop(security_id, None)
            return normalized_broker_ids | set(self._trade_slot_reservations)

    def current_active_trade_slots(self) -> Optional[set[str]]:
        """Read current broker positions/orders and merge recent reservations."""
        try:
            responses = (
                self._dhan.fetch_positions(),
                self._dhan.fetch_order_book(),
                self._dhan.fetch_super_orders(),
            )
        except Exception:
            return None
        if not all(self._broker_response_succeeded(response) for response in responses):
            return None
        positions, orders, super_orders = responses
        active: set[str] = set()
        for row in self._broker_rows(positions):
            if str(row.get("productType") or "").upper() != "INTRADAY":
                continue
            try:
                if float(row.get("netQty") or 0.0) == 0:
                    continue
            except (TypeError, ValueError):
                continue
            security_id = str(row.get("securityId") or row.get("security_id") or "")
            if security_id:
                active.add(security_id)
        active_statuses = {
            "PENDING", "TRANSIT", "PART_TRADED", "AMO_REQ_RECEIVED",
            "AFTER_MARKET_ORDER", "TRADED_PENDING",
        }
        for row in [*self._broker_rows(orders), *self._broker_rows(super_orders)]:
            row_active = str(row.get("orderStatus") or "").upper() in active_statuses
            legs = row.get("legDetails")
            row_active = row_active or isinstance(legs, list) and any(
                isinstance(leg, dict)
                and str(leg.get("orderStatus") or "").upper() in active_statuses
                for leg in legs
            )
            if not row_active:
                continue
            security_id = str(row.get("securityId") or row.get("security_id") or "")
            if security_id:
                active.add(security_id)
        return self.active_trade_slots(active)

    @staticmethod
    def _broker_response_succeeded(response: Any) -> bool:
        if isinstance(response, list):
            return True
        return isinstance(response, dict) and str(response.get("status") or "").lower() == "success"

    @staticmethod
    def _broker_rows(response: Any) -> list[Dict[str, Any]]:
        if isinstance(response, list):
            return [row for row in response if isinstance(row, dict)]
        if not isinstance(response, dict):
            return []
        data = response.get("data")
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [row for row in data["data"] if isinstance(row, dict)]
        return []

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
        while not self._stop.wait(
            min(self.interval_seconds, self._seconds_until_daily_verification())
        ):
            state = self.verify()
            if self._on_verified is not None:
                try:
                    self._on_verified(state)
                except Exception as exc:
                    print(
                        f"[Order Gate] verification callback failed: {type(exc).__name__}: {exc}",
                        flush=True,
                    )

    @staticmethod
    def _parse_daily_verify_time(raw: str) -> tuple[int, int]:
        try:
            parsed = datetime.strptime(raw.strip(), "%H:%M")
        except ValueError as exc:
            raise ValueError("DHAN_DAILY_VERIFICATION_TIME_IST must use HH:MM format.") from exc
        return parsed.hour, parsed.minute

    def _seconds_until_daily_verification(self) -> float:
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        local_now = now.astimezone(self._market_timezone)
        target = local_now.replace(
            hour=self._daily_verify_hour,
            minute=self._daily_verify_minute,
            second=0,
            microsecond=0,
        )
        if target <= local_now:
            target += timedelta(days=1)
        return max(0.0, (target - local_now).total_seconds())

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
