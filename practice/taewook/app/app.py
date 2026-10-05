"""Week 1: dependency-free HTTP application for deployment verification."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        data = {
            "service": "taewook-app",
            "version": os.environ.get("APP_VERSION", "dev"),
            "git_sha": os.environ.get("GIT_SHA", "local"),
            "release": os.environ.get("RELEASE_ID", "local"),
            "instance": os.environ.get("INSTANCE", "local"),
        }
        if path == "/health":
            data["status"] = "ok"
        elif path != "/version":
            self.send_json(404, {"error": "not found"})
            return
        self.send_json(200, data)

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
