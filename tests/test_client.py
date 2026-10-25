from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest

from deepsignal_s1.client import ModelClient


@pytest.fixture
def service():
    class Handler(BaseHTTPRequestHandler):
        status = 200
        body = {"choice": "extend_5s", "model_version": "DeepSignal-S1-1.0"}
        payload = None

        def do_POST(self):
            Handler.payload = json.loads(
                self.rfile.read(int(self.headers["Content-Length"]))
            )
            self.send_response(Handler.status)
            self.end_headers()
            self.wfile.write(json.dumps(Handler.body).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", Handler
    server.shutdown()
    server.server_close()
    thread.join()


def test_actual_http_request_and_version(service):
    url, handler = service
    result = ModelClient(url).decide(
        {"legal_actions": ["extend_5s"]}, [b"a", b"b", b"c"]
    )
    assert result["choice"] == "extend_5s"
    assert result["round_trip_ms"] > 0
    assert handler.payload["frames"] == ["YQ==", "Yg==", "Yw=="]


@pytest.mark.parametrize("status", [401, 403])
def test_unapproved_access_does_not_fallback(service, status):
    url, handler = service
    handler.status = status
    with pytest.raises(RuntimeError, match="access denied"):
        ModelClient(url).decide({"legal_actions": ["extend_5s"]}, [b"a"] * 3)


def test_illegal_response_is_an_error(service):
    url, handler = service
    handler.body = {"choice": "wrong", "model_version": "test"}
    with pytest.raises(RuntimeError, match="legal action"):
        ModelClient(url).decide({"legal_actions": ["extend_5s"]}, [b"a"] * 3)


def test_unidentified_model_is_an_error(service):
    url, handler = service
    handler.body = {"choice": "extend_5s"}
    with pytest.raises(RuntimeError, match="model_version"):
        ModelClient(url).decide({"legal_actions": ["extend_5s"]}, [b"a"] * 3)
