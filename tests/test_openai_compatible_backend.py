import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from digital_child.llm import OpenAICompatibleBackend


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/v1/models":
            body = json.dumps({"data": [{"id": "test-model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for token in ["При", "вет"]:
                event = {
                    "choices": [{"delta": {"content": token}}],
                }
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            return
        body = json.dumps(
            {"choices": [{"message": {"content": "Привет"}}]},
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def test_health_and_sse_streaming() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        backend = OpenAICompatibleBackend(
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="test-model",
            timeout=5,
        )
        health = backend.health_check()
        chunks = list(
            backend._stream_chat(
                {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "test"}],
                    "stream": True,
                }
            )
        )
        assert health.healthy is True
        assert "".join(chunks) == "Привет"
    finally:
        server.shutdown()
        server.server_close()
