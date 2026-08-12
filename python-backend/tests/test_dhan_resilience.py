import base64
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from pipeline.services.dhan_service import DhanService
from pipeline.services.dhan_credentials import CredentialUnavailable
from pipeline.services.dhan_execution_toolkit import DhanExecutionToolkit
from pipeline.services.storage_service import StorageService
from pipeline.runtime.run_executioner import ExecutionerRunner
from pipeline.runtime.run_stock_agent import MultiStockAgentRunner


class FakeHistoricalClient:
    def __init__(self):
        self.payload = None

    def intraday_minute_data(self, **payload):
        self.payload = payload
        return {"status": "success", "remarks": "", "data": {"timestamp": []}}


class FakeMarketClient:
    def __init__(self):
        self.calls = 0

    def quote_data(self, _payload):
        self.calls += 1
        if self.calls == 1:
            return {
                "status": "failure",
                "remarks": {
                    "error_code": "805",
                    "error_type": "Rate_Limit",
                    "error_message": "Too many requests or connections",
                },
                "data": "",
            }
        return {
            "status": "success",
            "data": {
                "status": "success",
                "data": {"BSE_EQ": {"500180": {"last_price": 100.0}}},
            },
        }


class FakeExecutionService:
    def __init__(self):
        self.super_order_payload = None

    def fetch_order_book(self):
        return {"status": "success", "data": []}

    def fetch_positions(self):
        return {"status": "success", "data": []}

    def fetch_super_orders(self):
        return {"status": "success", "data": []}

    def place_super_order(self, **payload):
        self.super_order_payload = payload
        return {"status": "success", "data": {"orderId": "test-order"}}

    def modify_forever_order(self, **payload):
        self.forever_modify_payload = payload
        return {"status": "success", "data": {"orderId": "forever-order"}}


class DhanResilienceTests(unittest.TestCase):
    @staticmethod
    def _jwt(*, issued_at: int, expires_at: int) -> str:
        def encoded(value):
            raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
            return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

        return f"{encoded({'alg': 'none'})}.{encoded({'iat': issued_at, 'exp': expires_at})}.x"

    def test_newer_unexpired_environment_token_beats_expired_runtime_token(self):
        now = int(time.time())
        runtime = SimpleNamespace(
            client_id="runtime-client",
            access_token=self._jwt(issued_at=now - 86400, expires_at=now - 60),
        )
        env_token = self._jwt(issued_at=now, expires_at=now + 86400)

        client_id, token, source = DhanService._select_credentials(
            runtime,
            "environment-client",
            env_token,
        )

        self.assertEqual(client_id, "environment-client")
        self.assertEqual(token, env_token)
        self.assertEqual(source, "environment")

    def test_newer_unexpired_runtime_token_remains_preferred(self):
        now = int(time.time())
        runtime_token = self._jwt(issued_at=now, expires_at=now + 86400)
        runtime = SimpleNamespace(client_id="runtime-client", access_token=runtime_token)
        env_token = self._jwt(issued_at=now - 60, expires_at=now + 3600)

        client_id, token, source = DhanService._select_credentials(
            runtime,
            "environment-client",
            env_token,
        )

        self.assertEqual(client_id, "runtime-client")
        self.assertEqual(token, runtime_token)
        self.assertEqual(source, "runtime")

    def test_credential_reload_keeps_environment_fallback_when_runtime_file_is_unreadable(self):
        service = object.__new__(DhanService)
        service.credential_store = SimpleNamespace(
            mtime_ns=lambda: 42,
            load=lambda required=False: (_ for _ in ()).throw(
                CredentialUnavailable("missing decryption secret")
            ),
        )
        service.credential_mtime_ns = 0
        service.credential_version = 0
        service.client_id = "env-client"
        service.access_token = "env-token"

        changed = service.reload_credentials_if_changed()

        self.assertFalse(changed)
        self.assertEqual(service.credential_mtime_ns, 42)
        self.assertEqual(service.client_id, "env-client")
        self.assertEqual(service.access_token, "env-token")

    def test_sdk_failure_is_not_wrapped_as_success(self):
        service = object.__new__(DhanService)
        response = {
            "status": "failure",
            "remarks": {
                "error_code": "DH-905",
                "error_type": "Input_Exception",
            },
            "data": "",
        }

        normalized = service._normalize_sdk_response(response)

        self.assertEqual(normalized["status"], "failure")
        self.assertEqual(normalized["remarks"]["error_code"], "DH-905")

    def test_no_holdings_is_normalized_to_empty_success(self):
        service = object.__new__(DhanService)
        response = {
            "status": "failure",
            "remarks": {
                "error_code": "DH-1111",
                "error_type": "HOLDING_ERROR",
                "error_message": "No holdings available",
            },
            "data": "",
        }

        normalized = service._normalize_sdk_response(
            response,
            empty_error_codes={"1111", "dh-1111"},
        )

        self.assertEqual(normalized["status"], "success")
        self.assertEqual(normalized["data"], [])

    def test_multi_margin_uses_live_dhan_field_names(self):
        service = object.__new__(DhanService)
        service.client_id = "1000000001"
        captured = {}

        def fake_request(method, path, *, payload):
            captured.update({"method": method, "path": path, "payload": payload})
            return {"status": "success", "data": {}}

        service._request = fake_request
        service.calculate_multi_order_margin(
            scripts=[
                {
                    "exchangeSegment": "NSE_EQ",
                    "transactionType": "BUY",
                    "quantity": 1,
                    "productType": "INTRADAY",
                    "securityId": "1333",
                    "price": 0,
                    "triggerPrice": 0,
                }
            ],
            include_position=True,
            include_orders=True,
        )

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/margincalculator/multi")
        self.assertIn("scripList", captured["payload"])
        self.assertIn("includeOrder", captured["payload"])
        self.assertNotIn("scripts", captured["payload"])
        self.assertNotIn("includeOrders", captured["payload"])

    def test_modify_order_uses_documented_client_id_payload(self):
        service = object.__new__(DhanService)
        service.client_id = "1100000001"
        captured = {}

        def fake_request(method, path, *, payload=None, **_kwargs):
            captured.update(method=method, path=path, payload=payload)
            return {"status": "success", "data": {"orderStatus": "TRANSIT"}}

        service._request = fake_request

        result = service.modify_order(
            order_id="12345",
            order_type="LIMIT",
            quantity=1,
            price=13.20,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(captured["method"], "PUT")
        self.assertEqual(captured["path"], "/orders/12345")
        self.assertEqual(captured["payload"]["dhanClientId"], "1100000001")
        self.assertEqual(captured["payload"]["orderId"], "12345")
        self.assertNotIn("legName", captured["payload"])
        self.assertNotIn("disclosedQuantity", captured["payload"])
        self.assertNotIn("triggerPrice", captured["payload"])

    def test_pnl_exit_includes_required_client_id(self):
        service = object.__new__(DhanService)
        service.client_id = "1100000001"
        captured = {}

        def fake_request(method, path, *, payload=None, **_kwargs):
            captured.update(method=method, path=path, payload=payload)
            return {"status": "success", "data": {"pnlExitStatus": "ACTIVE"}}

        service._request = fake_request

        result = service.configure_pnl_exit(
            profit_value=1000,
            loss_value=500,
            product_types=["INTRADAY"],
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(captured["payload"]["dhanClientId"], "1100000001")

    def test_agent_correlation_id_is_sanitized_and_limited_for_dhan(self):
        raw = "PW/544609/BUY/20260728/093429/01"

        normalized = DhanExecutionToolkit._normalize_correlation_id(raw, prefix="exec-so")

        self.assertLessEqual(len(normalized), 30)
        self.assertRegex(normalized, r"^[A-Za-z0-9 _-]+$")
        self.assertEqual(
            normalized,
            DhanExecutionToolkit._normalize_correlation_id(raw, prefix="exec-so"),
        )

    def test_observed_agent_super_order_correlation_id_is_shortened(self):
        raw = "PW_544609_BUY_20260728_093429_01"

        normalized = DhanExecutionToolkit._normalize_correlation_id(raw, prefix="exec-so")

        self.assertEqual(len(normalized), 30)
        self.assertNotEqual(normalized, raw)

    def test_super_order_tool_passes_normalized_correlation_id_to_dhan(self):
        service = FakeExecutionService()
        toolkit = DhanExecutionToolkit(service, entry_only=True)
        toolkit.allow_live_orders = True
        toolkit.set_allowed_security_id(544609)

        response = toolkit.place_protected_intraday_super_order(
            security_id=544609,
            side="BUY",
            quantity=19,
            entry_price=126.70,
            target_price=128.30,
            stop_loss_price=125.90,
            correlation_id="PW_544609_BUY_20260728_093429_01",
        )

        payload = json.loads(response)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(len(service.super_order_payload["correlation_id"]), 30)
        self.assertEqual(payload["correlation_id"], service.super_order_payload["correlation_id"])

    def test_market_super_order_sends_zero_price_to_dhan(self):
        service = FakeExecutionService()
        toolkit = DhanExecutionToolkit(service, entry_only=True)
        toolkit.allow_live_orders = True
        toolkit.set_allowed_security_id(14366)

        payload = json.loads(
            toolkit.place_protected_intraday_super_order(
                security_id=14366,
                side="BUY",
                quantity=1,
                entry_price=13.19,
                target_price=13.89,
                stop_loss_price=12.49,
                order_type="MARKET",
                exchange_segment="NSE_EQ",
            )
        )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(service.super_order_payload["order_type"], "MARKET")
        self.assertEqual(service.super_order_payload["price"], 0.0)
        self.assertEqual(service.super_order_payload["target_price"], 13.89)
        self.assertEqual(service.super_order_payload["stop_loss_price"], 12.49)

    def test_single_forever_order_modify_defaults_to_live_stop_loss_leg(self):
        service = FakeExecutionService()
        toolkit = DhanExecutionToolkit(service)
        toolkit.allow_live_orders = True

        payload = json.loads(
            toolkit.modify_forever_order(
                order_id="forever-order",
                quantity=1,
                price=11.62,
                trigger_price=11.61,
            )
        )

        self.assertEqual(payload["status"], "success")
        self.assertEqual(service.forever_modify_payload["order_flag"], "SINGLE")
        self.assertEqual(service.forever_modify_payload["leg_name"], "STOP_LOSS_LEG")

    def test_dhan_quote_depth_and_timestamp_are_parsed_for_agents(self):
        runner = object.__new__(ExecutionerRunner)
        runner.market_time = SimpleNamespace(tz=timezone(timedelta(hours=5, minutes=30)))
        quote = {
            "depth": {
                "buy": [{"price": 126.55, "quantity": 50}],
                "sell": [{"price": 126.70, "quantity": 620}],
            },
            "last_trade_time": "28/07/2026 09:34:24",
        }

        self.assertEqual(runner._extract_best_depth_price(quote, "buy"), 126.55)
        self.assertEqual(runner._extract_best_depth_price(quote, "sell"), 126.70)
        self.assertEqual(
            runner._to_market_iso(quote["last_trade_time"]),
            "2026-07-28T09:34:24+05:30",
        )

    def test_failed_trade_attempt_is_not_counted_as_executed(self):
        failed = {"decision": {"action": "trade", "execution_status": "failed"}}
        pending = {"decision": {"action": "pending", "execution_status": "pending"}}
        traded = {"decision": {"action": "trade", "execution_status": "traded"}}
        part_traded = {"decision": {"action": "trade", "execution_status": "part_traded"}}

        self.assertFalse(MultiStockAgentRunner._is_placed_result(failed))
        self.assertFalse(MultiStockAgentRunner._is_placed_result(pending))
        self.assertTrue(MultiStockAgentRunner._is_placed_result(traded))
        self.assertTrue(MultiStockAgentRunner._is_placed_result(part_traded))

    def test_error_805_is_classified_as_rate_limit(self):
        service = object.__new__(DhanService)
        response = {
            "status": "failure",
            "remarks": {
                "error_code": "805",
                "error_message": "Too many requests or connections",
            },
        }
        self.assertEqual(service._normalized_error_code(response), "805")
        self.assertTrue(service._is_rate_limited(response))

    def test_intraday_request_uses_full_market_datetime(self):
        service = object.__new__(DhanService)
        service.gateway_url = None
        service.config = SimpleNamespace(market_open_hour=9, market_open_minute=15)
        service._market_now = lambda: datetime(
            2026,
            7,
            27,
            10,
            0,
            0,
            tzinfo=ZoneInfo("Asia/Kolkata"),
        )
        service._historical_circuit_response_if_open = lambda: None
        service._normalize_historical_instruments = lambda _items: ["EQUITY"]
        service.acquire_data_slot = lambda: None
        service._record_historical_response = lambda _response: None
        client = FakeHistoricalClient()
        service._historical_client = lambda: client

        response = service.fetch_intraday_history(
            500180,
            days=15,
            interval=1,
            exchange_segment="BSE_EQ",
            instrument_candidates=["EQUITY"],
        )

        self.assertEqual(response["status"], "success")
        self.assertEqual(client.payload["from_date"], "2026-07-12 09:15:00")
        self.assertEqual(client.payload["to_date"], "2026-07-27 10:00:00")

    def test_quote_retries_805_and_parses_success(self):
        service = object.__new__(DhanService)
        service.config = SimpleNamespace(quote_request_retries=2)
        service.acquire_quote_slot = lambda: None
        service._compute_rate_limit_delay = lambda _attempt: 0.0
        market_client = FakeMarketClient()
        service._market_client = lambda: market_client

        result = service._fetch_market_batch("quote_data", [500180], "BSE_EQ")

        self.assertEqual(market_client.calls, 2)
        self.assertEqual(result[500180]["last_price"], 100.0)

    def test_quote_retries_blank_sdk_failure_and_parses_success(self):
        service = object.__new__(DhanService)
        service.config = SimpleNamespace(quote_request_retries=2)
        service.acquire_quote_slot = lambda: None
        service._compute_rate_limit_delay = lambda _attempt: 0.0
        responses = iter(
            [
                {"status": "failure", "remarks": "", "data": ""},
                {
                    "status": "success",
                    "data": {
                        "data": {"NSE_EQ": {"2885": {"last_price": 100.0}}}
                    },
                },
            ]
        )
        market_client = SimpleNamespace(ohlc_data=lambda _payload: next(responses))
        service._market_client = lambda: market_client

        result = service._fetch_market_batch("ohlc_data", [2885], "NSE_EQ")

        self.assertEqual(result[2885]["last_price"], 100.0)

    def test_repeated_905_opens_local_historical_circuit(self):
        service = object.__new__(DhanService)
        service.config = SimpleNamespace(
            historical_circuit_breaker_threshold=2,
            historical_circuit_breaker_cooldown_seconds=300,
        )
        from threading import Condition

        service.historical_circuit_condition = Condition()
        service.historical_failure_signature = None
        service.historical_consecutive_failures = 0
        service.historical_circuit_open_until = 0.0
        response = {
            "status": "failure",
            "remarks": {
                "error_code": "DH-905",
                "error_type": "Input_Exception",
                "error_message": "Missing required fields, bad values for parameters etc.",
            },
        }

        service._record_historical_response(response)
        service._record_historical_response(response)

        blocked = service._historical_circuit_response_if_open()
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked["remarks"]["error_code"], "LOCAL-CIRCUIT-OPEN")

    def test_daily_epoch_keeps_ist_calendar_date(self):
        service = object.__new__(DhanService)
        service.config = SimpleNamespace(market_timezone="Asia/Calcutta")
        response = {
            "data": {
                "timestamp": [1784831400],
                "open": [737.5],
                "high": [748.0],
                "low": [737.2],
                "close": [742.6],
                "volume": [1968197],
            }
        }

        frame = service.daily_response_to_df(response)

        self.assertEqual(frame["timestamp"].iloc[0].date().isoformat(), "2026-07-24")

    def test_degraded_stage_snapshots_are_rejected(self):
        stage1 = {
            "stage": "stage1_sanitation",
            "summary": {
                "historical_candidates": 1966,
                "data_retrieved": 828,
                "failed_fetch": 1138,
            },
        }
        stage2 = {
            "stage": "stage2_momentum_ignition",
            "summary": {
                "status": "completed",
                "input_stage1_count": 90,
                "data_retrieved": 0,
                "failed_fetch": 90,
            },
        }

        self.assertFalse(StorageService.is_stage_snapshot_usable(stage1, 0.10))
        self.assertFalse(StorageService.is_stage_snapshot_usable(stage2, 0.10))


if __name__ == "__main__":
    unittest.main()
