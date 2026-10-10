"""파일 역할: 앱의 상태·준비 여부·빌드 버전·요청 처리 서버를 HTTP 응답으로 제공하는 실습 서버다."""
import json
import os
from pathlib import Path
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


def load_metadata(path):
    """이미지 내부 JSON에서 버전·릴리스·커밋을 읽고 필수 문자열이 비어 있지 않은지 검사한다."""
    data = json.loads(Path(path).read_text())
    for key in ('version', 'release_id', 'git_revision'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'Missing metadata: {key}')
    return {key: data[key] for key in ('version', 'release_id', 'git_revision')}


def make_handler(metadata, server_id):
    """빌드 메타데이터와 서버 ID를 사용해 경로별 응답을 처리할 HTTP 핸들러를 만든다."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """요청 경로에 맞춰 상태·준비 여부·버전·서버 정보를 반환하고 알 수 없는 경로는 404로 응답한다."""
            ready = bool(metadata and server_id)
            body = dict(metadata or {}, service='sohyeon-cicd-app',
                        server_id=server_id, ready=ready)
            status, content_type = 200, 'text/plain'
            if self.path == '/health':
                content = 'OK\n'
            elif self.path == '/version':
                status = 200 if ready else 503
                content = body.get('version', 'unavailable') + '\n'
            elif self.path in ('/', '/ready'):
                status = 200 if ready else 503
                content_type = 'application/json'
                content = json.dumps(body) + '\n'
            else:
                status, content = 404, 'Not found\n'
            encoded = content.encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(encoded)
    return Handler


def main():
    """메타데이터와 서버 ID로 HTTP 서버를 시작하고 종료 신호를 받으면 요청 처리를 마친 뒤 닫는다."""
    try:
        metadata = load_metadata(os.environ.get('METADATA_PATH', '/app/release.json'))
    except (OSError, ValueError) as error:
        print(f'Readiness failed: {error}', flush=True)
        metadata = None
    server = ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '80'))),
                                 make_handler(metadata, os.environ.get('SERVER_ID', '')))
    # SIGTERM 이후 server_close가 진행 중인 요청 처리 스레드의 종료를 기다리게 한다.
    server.daemon_threads = False
    def stop(*_):
        """신호 처리 흐름이 막히지 않도록 별도 스레드에서 HTTP 서버 종료를 요청한다."""
        Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f'Listening on {server.server_address[1]} server_id={os.environ.get("SERVER_ID", "")}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


# 직접 실행한 경우에만 명령행 처리 또는 테스트 실행을 시작한다.
if __name__ == '__main__':
    main()
