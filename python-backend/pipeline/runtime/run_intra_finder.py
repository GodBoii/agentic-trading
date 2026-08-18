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
        path = self.path.rstrip("/")
        if path not in {"/health", "/live"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        ready, payload = self.service.health_payload()
        if path == "/live":
            healthy = True
            payload = {
                "status": "healthy",
                "readiness": payload.get("status", "unknown"),
                "reason": payload.get("reason", "unknown"),
            }
        else:
            healthy = ready
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except ConnectionError:
            # Health clients are allowed to close as soon as they have read the
            # status line (notably when a 503 makes the probe fail).  The
            # scanner's health and lifecycle are unaffected by that transport
            # race, so do not turn it into a noisy server traceback.
            return


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
