"""minjun-app: /health, /version 두 엔드포인트만 가진 최소 앱.

외부 라이브러리 없이 표준 라이브러리만 사용한다.
공용 Agent에서 pip 설치 없이 빌드되게 하려는 선택이다.
"""
import json
import os
import signal
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_PORT = 8080  # 컨테이너 내부 포트. 호스트 포트(20006/21006)는 docker가 매핑한다.


def version_info():
    # version, git_sha: 이미지 빌드 시점에 고정된다 (Dockerfile ARG -> ENV).
    # host, color, port: 배포 시점에 Ansible이 환경변수로 넣어준다.
    return {
        "app": "minjun-app",
        "version": os.getenv("APP_VERSION", "dev"),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "host": os.getenv("APP_HOST", socket.gethostname()),
        "color": os.getenv("APP_COLOR", "none"),
        "port": os.getenv("APP_PORT", str(LISTEN_PORT)),
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path in ("/version", "/"):
            self._send(200, version_info())
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)

    # 컨테이너에서 PID 1은 기본 시그널 처리가 없어서 docker stop 시 10초를 기다린다.
    # SIGTERM을 직접 받아 바로 종료되게 한다.
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    print("minjun-app listening on :%d %s" % (LISTEN_PORT, version_info()), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
