from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from pipeline.runtime.run_intra_finder import IntraFinderHealthHandler


class IntraFinderHealthHandlerTests(TestCase):
    @staticmethod
    def _handler(*, path="/health", write_error=None, headers_error=None):
        handler = object.__new__(IntraFinderHealthHandler)
        handler.path = path
        handler.service = SimpleNamespace(
            health_payload=lambda: (
                False,
                {"status": "unhealthy", "reason": "universe_unavailable"},
            )
        )
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock(side_effect=headers_error)
        handler.wfile = SimpleNamespace(write=Mock(side_effect=write_error))
        return handler

    def test_returns_unhealthy_payload(self):
        handler = self._handler()

        handler.do_GET()

        handler.send_response.assert_called_once_with(503)
        handler.wfile.write.assert_called_once_with(
            b'{"status":"unhealthy","reason":"universe_unavailable"}'
        )

    def test_liveness_stays_healthy_while_readiness_is_waiting(self):
        handler = self._handler(path="/live")

        handler.do_GET()

        handler.send_response.assert_called_once_with(200)
        handler.wfile.write.assert_called_once_with(
            b'{"status":"healthy","readiness":"unhealthy","reason":"universe_unavailable"}'
        )

    def test_ignores_client_disconnect_while_writing_body(self):
        handler = self._handler(write_error=BrokenPipeError())

        handler.do_GET()

    def test_ignores_client_disconnect_while_writing_headers(self):
        handler = self._handler(headers_error=ConnectionResetError())

        handler.do_GET()
