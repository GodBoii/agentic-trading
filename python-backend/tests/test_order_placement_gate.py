from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pipeline.services.convex_service import ConvexService
from pipeline.services.order_placement_gate import (
    DH905_INVALID_IP,
    DHAN_IP_NOT_ALLOWED,
    ORDER_PLACEMENT_ALLOWED,
    OrderPlacementGate,
    OrderPlacementStateService,
)


class FakeDhan:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def fetch_static_ips(self):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def success_response(*, detected="1.2.3.4", orders_allowed=True):
    return {
        "status": "success",
        "data": {
            "detectedIP": detected,
            "primaryIP": "1.2.3.4",
            "secondaryIP": "5.6.7.8",
            "ordersAllowed": orders_allowed,
        },
    }


class OrderPlacementGateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "order-placement.json"
        self.convex_configured = patch.object(ConvexService, "configured", return_value=False)
        self.convex_required = patch.object(ConvexService, "required", return_value=False)
        self.convex_configured.start()
        self.convex_required.start()

    def tearDown(self):
        self.convex_required.stop()
        self.convex_configured.stop()
        self.temp_dir.cleanup()

    def gate(self, dhan):
        return OrderPlacementGate(
            dhan,
            self.state_path,
            interval_seconds=21600,
            now=lambda: datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc),
        )

    def test_matching_detected_ip_and_orders_allowed_opens_gate(self):
        gate = self.gate(FakeDhan(success_response()))

        state = gate.verify()

        self.assertTrue(state.allowed)
        self.assertEqual(state.status_code, ORDER_PLACEMENT_ALLOWED)
        self.assertTrue(OrderPlacementStateService.is_allowed(self.state_path))

    def test_mismatch_or_false_orders_allowed_closes_gate(self):
        for response in (
            success_response(detected="9.9.9.9"),
            success_response(orders_allowed=False),
        ):
            with self.subTest(response=response):
                gate = self.gate(FakeDhan(response))
                state = gate.verify()
                self.assertFalse(state.allowed)
                self.assertEqual(state.status_code, DHAN_IP_NOT_ALLOWED)

    def test_dh905_blocks_immediately_and_persists_across_restart(self):
        gate = self.gate(FakeDhan(success_response()))
        self.assertTrue(gate.verify().allowed)

        state = gate.block_from_order_response(
            {
                "status": "failure",
                "remarks": {
                    "error_code": "DH-905",
                    "error_type": "Input_Exception",
                    "error_message": "Invalid IP",
                },
            }
        )

        self.assertIsNotNone(state)
        self.assertFalse(gate.allowed)
        self.assertEqual(gate.state.status_code, DH905_INVALID_IP)
        restarted = self.gate(FakeDhan(success_response()))
        self.assertFalse(restarted.allowed)

    def test_numeric_905_response_also_blocks(self):
        gate = self.gate(FakeDhan(success_response()))
        self.assertTrue(gate.verify().allowed)

        gate.block_from_order_response({"remarks": {"error_code": "905"}})

        self.assertFalse(gate.allowed)
        self.assertEqual(gate.state.status_code, DH905_INVALID_IP)

    def test_successful_later_verification_recovers_automatically(self):
        dhan = FakeDhan(success_response(orders_allowed=False))
        gate = self.gate(dhan)
        self.assertFalse(gate.verify().allowed)

        dhan.response = success_response(orders_allowed=True)
        recovered = gate.verify()

        self.assertTrue(recovered.allowed)
        self.assertTrue(OrderPlacementStateService.is_allowed(self.state_path))

    def test_dh905_local_latch_cannot_be_overwritten_by_stale_allowed_state(self):
        gate = self.gate(FakeDhan(success_response()))
        self.assertTrue(gate.verify().allowed)
        with patch.object(OrderPlacementStateService, "save", side_effect=RuntimeError("write failed")):
            gate.block_from_order_response({"remarks": {"error_code": "DH-905"}})

        refreshed = gate.refresh_from_store()

        self.assertFalse(refreshed.allowed)
        self.assertEqual(refreshed.status_code, DH905_INVALID_IP)

    def test_verification_exception_fails_closed(self):
        gate = self.gate(FakeDhan(RuntimeError("network unavailable")))

        state = gate.verify()

        self.assertFalse(state.allowed)
        self.assertEqual(state.reason, "dhan_ip_verification_failed")

    def test_recent_trade_slot_reservation_covers_broker_visibility_delay(self):
        clock = [datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)]
        gate = OrderPlacementGate(
            FakeDhan(success_response()),
            self.state_path,
            interval_seconds=21600,
            now=lambda: clock[0],
        )

        gate.reserve_trade_slot(111)
        self.assertEqual(gate.active_trade_slots(set()), {"111"})
        self.assertEqual(gate.active_trade_slots({"222"}), {"111", "222"})

        clock[0] += timedelta(seconds=31)
        self.assertEqual(gate.active_trade_slots(set()), set())


if __name__ == "__main__":
    unittest.main()
