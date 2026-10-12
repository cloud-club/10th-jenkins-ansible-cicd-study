import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def payload(path):
    result = {
        "service": "doyeon-app",
        "version": os.environ.get("APP_VERSION", "v1"),
        "release": os.environ.get("RELEASE_ID", "local"),
        "instance": os.environ.get("INSTANCE_ID", "local"),
    }
    if path == "/health":
        result["status"] = "ok"
    return result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health", "/version"):
            self.send_error(404)
            return
        body = json.dumps(payload(self.path)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
