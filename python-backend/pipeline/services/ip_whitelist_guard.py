"""Halt AI trading when Dhan rejects orders because this machine's IP is not whitelisted.

Dhan enforces static IP whitelisting on order placement only. Quotes, historical candles
and the market feed keep working from any IP, so a session with a stale whitelist looks
healthy all day, burns model and data quota, and only reveals the problem when an order
comes back as DH-905 / Invalid IP. See `context/dhan_auth.md`, "Setup Static IP".

This guard turns that silent failure into a hard stop plus an operator-actionable log.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import requests

from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.dhan_service import DhanService

LOG_PREFIX = "[IP Guard]"

# Written to the Convex trading configuration so the dashboard can explain the stop.
IP_BLOCK_STATUS_CODE = "DH-905_INVALID_IP"

EGRESS_IP_ENDPOINTS: Tuple[str, ...] = (
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ipv4.icanhazip.com",
)
EGRESS_IP_LOOKUP_TIMEOUT_SECONDS = 5.0

DHAN_STATIC_IP_CONSOLE = "web.dhan.co > My Profile > DhanHQ Trading APIs > Static IP Setting"


def resolve_egress_ip(
    endpoints: Sequence[str] = EGRESS_IP_ENDPOINTS,
    timeout: float = EGRESS_IP_LOOKUP_TIMEOUT_SECONDS,
) -> Optional[str]:
    """Return this machine's public IP, or None when every lookup fails.

    Never raises. This runs on the order-rejection path, where a failed diagnostic
    must not mask the rejection it is trying to explain.
    """
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, timeout=timeout)
            response.raise_for_status()
            return str(ipaddress.ip_address(response.text.strip()))
        except (requests.RequestException, ValueError) as exc:
            print(
                f"{LOG_PREFIX} egress IP lookup failed via {endpoint}: {type(exc).__name__}: {exc}",
                flush=True,
            )
    return None


def _optional_text(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


@dataclass(frozen=True)
class DhanWhitelist:
    """Static IPs Dhan currently accepts, as reported by GET /v2/ip/getIP."""

    primary_ip: Optional[str] = None
    secondary_ip: Optional[str] = None
    modify_date_primary: Optional[str] = None
    modify_date_secondary: Optional[str] = None
    lookup_error: Optional[str] = None

    @classmethod
    def from_response(cls, response: Any) -> "DhanWhitelist":
        if not isinstance(response, dict):
            return cls(lookup_error="unexpected_response_type")
        if str(response.get("status", "")).lower() == "failure":
            return cls(lookup_error=str(response.get("remarks") or "getIP_failed"))
        data = response.get("data")
        if not isinstance(data, dict):
            return cls(lookup_error="getIP_response_missing_data")
        return cls(
            primary_ip=_optional_text(data.get("primaryIP")),
            secondary_ip=_optional_text(data.get("secondaryIP")),
            modify_date_primary=_optional_text(data.get("modifyDatePrimary")),
            modify_date_secondary=_optional_text(data.get("modifyDateSecondary")),
        )

    @property
    def ips(self) -> Tuple[str, ...]:
        return tuple(ip for ip in (self.primary_ip, self.secondary_ip) if ip)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "primary_ip": self.primary_ip,
            "secondary_ip": self.secondary_ip,
            "modify_date_primary": self.modify_date_primary,
            "modify_date_secondary": self.modify_date_secondary,
            "lookup_error": self.lookup_error,
        }


@dataclass(frozen=True)
class IpWhitelistBlock:
    """Everything the operator needs to fix the whitelist, captured when the guard trips."""

    detected_at_utc: str
    egress_ip: Optional[str]
    whitelist: DhanWhitelist
    broker_message: str
    halted_user_ids: Tuple[str, ...]

    @property
    def status_code(self) -> str:
        return IP_BLOCK_STATUS_CODE

    @property
    def already_whitelisted(self) -> bool:
        """True when the rejection is not explained by a drifted egress IP."""
        return bool(self.egress_ip) and self.egress_ip in self.whitelist.ips

    def operator_message(self) -> str:
        current = self.egress_ip or "unknown (public IP lookup failed)"
        allowed = ", ".join(self.whitelist.ips) or (
            f"unavailable ({self.whitelist.lookup_error})"
            if self.whitelist.lookup_error
            else "none configured"
        )
        lines = [
            "Dhan rejected order placement with DH-905 (Invalid IP).",
            f"This machine's public IP : {current}",
            f"Whitelisted on Dhan      : {allowed}",
        ]
        if self.whitelist.modify_date_primary or self.whitelist.modify_date_secondary:
            lines.append(
                "Editable from            : "
                f"primary {self.whitelist.modify_date_primary or 'unknown'}, "
                f"secondary {self.whitelist.modify_date_secondary or 'unknown'}"
            )
        if self.already_whitelisted:
            lines.append(
                "This IP is already whitelisted, so the rejection is not IP drift. "
                "Check that the order was placed from this host and not through a proxy or tunnel."
            )
        elif self.egress_ip:
            lines.append(f"ACTION: set {self.egress_ip} at {DHAN_STATIC_IP_CONSOLE}.")
        else:
            lines.append(
                "ACTION: read this host's public IP (curl https://api.ipify.org) "
                f"and set it at {DHAN_STATIC_IP_CONSOLE}."
            )
        if self.halted_user_ids:
            lines.append(
                f"AI trading disabled for {len(self.halted_user_ids)} user(s). "
                "Re-enable it from the dashboard after the whitelist is fixed."
            )
        else:
            lines.append("No enabled user was found to disable; agents were already off.")
        if self.broker_message:
            lines.append(f"Broker detail: {self.broker_message}")
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": "halted",
            "status_code": self.status_code,
            "reason": "dhan_ip_not_whitelisted",
            "detected_at_utc": self.detected_at_utc,
            "egress_ip": self.egress_ip,
            "whitelist": self.whitelist.as_dict(),
            "halted_user_ids": list(self.halted_user_ids),
            "operator_action": self.operator_message(),
        }


class IpWhitelistGuard:
    """Latches on the first DH-905 order rejection and disables AI trading.

    One instance is shared by every stock agent in a run, so the first rejection stops
    the rest instead of each agent discovering the same dead end. The latch is
    in-memory; the durable stop is the disabled flag written through
    `AITradingStateService`, which every runner checks at the top of its cycle.
    """

    def __init__(
        self,
        dhan: DhanService,
        state_path: Path,
        *,
        egress_ip_resolver: Optional[Callable[[], Optional[str]]] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._dhan = dhan
        self._state_path = Path(state_path)
        self._resolve_egress_ip = egress_ip_resolver or resolve_egress_ip
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lock = Lock()
        self._block: Optional[IpWhitelistBlock] = None

    @property
    def block(self) -> Optional[IpWhitelistBlock]:
        with self._lock:
            return self._block

    @property
    def tripped(self) -> bool:
        return self.block is not None

    def inspect_order_response(self, response: Any) -> Optional[IpWhitelistBlock]:
        """Trip the guard when `response` is a DH-905 rejection. Returns the block, if any."""
        if not DhanService.is_invalid_ip(response):
            return None
        return self._trip(response)

    def _trip(self, response: Any) -> IpWhitelistBlock:
        # Diagnostics and the Convex write happen under the lock so that concurrent
        # stock agents hitting the same rejection produce one halt, not one each.
        with self._lock:
            if self._block is not None:
                return self._block

            _, _, broker_message = DhanService._response_error_details(response)
            block = IpWhitelistBlock(
                detected_at_utc=self._now().isoformat(),
                egress_ip=self._safe_egress_ip(),
                whitelist=self._fetch_whitelist(),
                broker_message=broker_message,
                halted_user_ids=self._halt_ai_trading(),
            )
            self._block = block

        print(f"{LOG_PREFIX} " + "=" * 60, flush=True)
        for line in block.operator_message().splitlines():
            print(f"{LOG_PREFIX} {line}", flush=True)
        print(f"{LOG_PREFIX} " + "=" * 60, flush=True)
        return block

    def _safe_egress_ip(self) -> Optional[str]:
        try:
            return self._resolve_egress_ip()
        except Exception as exc:  # noqa: BLE001 - diagnostics must not mask the rejection
            print(f"{LOG_PREFIX} egress IP resolver raised: {type(exc).__name__}: {exc}", flush=True)
            return None

    def _fetch_whitelist(self) -> DhanWhitelist:
        # getIP is a read endpoint, so it still works while order placement is blocked.
        try:
            return DhanWhitelist.from_response(self._dhan.fetch_static_ips())
        except Exception as exc:  # noqa: BLE001 - diagnostics must not mask the rejection
            print(f"{LOG_PREFIX} getIP lookup raised: {type(exc).__name__}: {exc}", flush=True)
            return DhanWhitelist(lookup_error=f"{type(exc).__name__}: {exc}")

    def _halt_ai_trading(self) -> Tuple[str, ...]:
        """Disable every enabled user. DH-905 is host-level, so it blocks all of them."""
        try:
            state = AITradingStateService.load_state(self._state_path)
        except Exception as exc:  # noqa: BLE001 - must still surface the rejection
            print(
                f"{LOG_PREFIX} could not read AI trading state to halt agents: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            return ()

        enabled_user_ids = [
            str(user_id) for user_id in (state.get("enabled_user_ids") or []) if str(user_id).strip()
        ]
        halted: list[str] = []
        for user_id in enabled_user_ids:
            try:
                # Passing only status_code leaves the saved trade amount and mode intact,
                # so re-enabling from the dashboard does not require re-entering them.
                AITradingStateService.set_user_state(
                    self._state_path,
                    user_id,
                    False,
                    metadata={"status_code": IP_BLOCK_STATUS_CODE},
                )
                halted.append(user_id)
            except Exception as exc:  # noqa: BLE001 - one failure must not skip the rest
                print(
                    f"{LOG_PREFIX} FAILED to disable AI trading for {user_id}: "
                    f"{type(exc).__name__}: {exc}. Disable it manually from the dashboard.",
                    flush=True,
                )
        return tuple(halted)
