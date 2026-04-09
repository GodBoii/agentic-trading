import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

from pipeline.config import PipelineConfig
from pipeline.services.dhan_service import DhanService


class MarketDataGatewayHandler(BaseHTTPRequestHandler):
    dhan: DhanService

    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - stdlib hook
        print(f"gateway | {self.address_string()} | {format % args}")

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}

        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        return json.loads(raw_body.decode("utf-8"))

    def _write_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = self.path.rstrip("/")
        routes: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            "/health": lambda _: {"status": "ok"},
            "/v1/user-profile": lambda _: self.dhan.fetch_user_profile(),
            "/v1/daily-history": lambda body: self.dhan.fetch_daily_history(
                int(body["security_id"]),
                days=int(body.get("days", 30)),
                retries=int(body.get("retries", 3)),
                exchange_segment=str(body.get("exchange_segment", "BSE_EQ")),
                instrument_candidates=body.get("instrument_candidates"),
            ),
            "/v1/intraday-history": lambda body: self.dhan.fetch_intraday_history(
                int(body["security_id"]),
                days=int(body.get("days", 5)),
                interval=int(body.get("interval", 1)),
                retries=int(body.get("retries", 3)),
                exchange_segment=str(body.get("exchange_segment", "BSE_EQ")),
                instrument_candidates=body.get("instrument_candidates"),
            ),
            "/v1/quote-batch": lambda body: self.dhan.fetch_quote_batch(
                [int(item) for item in body.get("security_ids", [])]
            ),
            "/v1/ohlc-batch": lambda body: self.dhan.fetch_ohlc_batch(
                [int(item) for item in body.get("security_ids", [])]
            ),
        }

        if path not in routes:
            raise KeyError(f"Unknown route: {path}")
        return {"ok": True, "data": routes[path](payload)}

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        if self.path.rstrip("/") != "/health":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        self._write_json(HTTPStatus.OK, {"ok": True, "data": {"status": "ok"}})

    def do_POST(self) -> None:  # noqa: N802 - stdlib signature
        try:
            payload = self._read_json()
            response = self._dispatch(payload)
            self._write_json(HTTPStatus.OK, response)
        except KeyError as exc:
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
        except Exception as exc:  # pragma: no cover - runtime safety
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(exc)},
            )


def main() -> None:
    config = PipelineConfig()
    handler_class = MarketDataGatewayHandler
    handler_class.dhan = DhanService(config, prefer_gateway=False)

    server = ThreadingHTTPServer(
        (config.market_data_gateway_host, config.market_data_gateway_port),
        handler_class,
    )

    print("=" * 60)
    print("MARKET DATA GATEWAY")
    print("=" * 60)
    print(
        "Listening on "
        f"{config.market_data_gateway_host}:{config.market_data_gateway_port}"
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
