"""Run Stage 2 with a sanitized liveness/readiness endpoint."""

from __future__ import annotations

import json
import os
import signal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from pipeline.stages.intra_finder import IntraFinder


class IntraFinderHealthHandler(BaseHTTPRequestHandler):
    service: IntraFinder

    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        if self.path.rstrip("/") != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        healthy, payload = self.service.health_payload()
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    service = IntraFinder()
    IntraFinderHealthHandler.service = service
    server = ThreadingHTTPServer(
        ("0.0.0.0", int(os.getenv("INTRA_FINDER_HEALTH_PORT", "8040"))),
        IntraFinderHealthHandler,
    )
    health_thread = Thread(target=server.serve_forever, daemon=True)
    health_thread.start()

    def _stop(_signum: int, _frame: Any) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        service.enforce_retention()
        service.run_forever()
    finally:
        server.shutdown()
        server.server_close()
        service.close()


if __name__ == "__main__":
    main()
