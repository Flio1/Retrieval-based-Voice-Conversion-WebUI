"""Self-hosted HTTP endpoint for the Alexa -> JARVIS bridge (testing / tunnel use).

Run it next to your JARVIS instance:

    cp .env.example .env    # fill it in
    set -a; source .env; set +a
    python lambda/local_server.py          # listens on 0.0.0.0:8088

Alexa requires a PUBLIC HTTPS endpoint with a valid certificate, so put a tunnel
or reverse proxy in front, e.g.:

    cloudflared tunnel --url http://localhost:8088
    # or
    ngrok http 8088

SECURITY: this server does NOT fully verify the Alexa request signature.
Run it only behind a trusted tunnel and with ALEXA_SKILL_ID set, or use AWS Lambda
(lambda_function.py) for production.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from handler import handle_alexa_request

HOST = os.environ.get("BIND_HOST", "0.0.0.0")
PORT = int(os.environ.get("BIND_PORT", "8088"))
MAX_BODY = 256 * 1024  # 256 KiB is plenty for an Alexa request


class _Handler(BaseHTTPRequestHandler):
    server_version = "AlexaJarvisBridge/1.0"

    def do_GET(self):  # simple health check
        if self.path in ("/health", "/healthz"):
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(400, {"error": "bad request"})
            return
        try:
            event = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, {"error": "invalid json"})
            return

        response = handle_alexa_request(event)
        self._send(200, response)

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter default logging
        pass


def main():
    if not os.environ.get("JARVIS_ENDPOINT"):
        raise SystemExit("JARVIS_ENDPOINT is not set (see .env.example)")
    httpd = ThreadingHTTPServer((HOST, PORT), _Handler)
    print("Alexa -> JARVIS bridge listening on http://%s:%d" % (HOST, PORT))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
