"""파일 역할: 앱 응답·정상 종료·Nginx 검증 도우미·연속 요청 측정 도구를 로컬 환경에서 검증한다."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.server import load_metadata, make_handler
from scripts.probe import sample, summarize


def load_helper(name):
    """테스트할 Nginx 도우미 파일을 경로에서 Python 모듈로 불러온다."""
    spec = importlib.util.spec_from_file_location(name, ROOT / 'ansible/roles/nginx_lb/files' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def serve(handler):
    """임시 로컬 HTTP 서버를 실행하고 테스트가 끝나면 서버와 스레드를 정리한다."""
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


META = dict(version='v2', release_id='v2-test-2', git_revision='abc123')


class ApplicationTests(unittest.TestCase):
    def test_metadata_is_loaded_from_file_and_missing_values_are_rejected(self):
        """메타데이터 파일을 정상적으로 읽고 필수 값이 없으면 거부하는지 검사한다."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.json'
            path.write_text(json.dumps(META))
            self.assertEqual(load_metadata(path), META)
            path.write_text('{"version": "v2"}')
            with self.assertRaises(ValueError):
                load_metadata(path)

    def test_endpoints_and_identity(self):
        """각 HTTP 경로의 응답, 캐시 방지 헤더, 서버 ID와 버전 및 404 처리를 확인한다."""
        handler = make_handler(META, 'app2')
        handler.log_message = lambda *args: None
        with serve(handler) as base:
            for endpoint in ('/', '/ready'):
                with urlopen(base + endpoint) as response:
                    self.assertEqual(response.headers['Cache-Control'], 'no-store')
                    data = json.load(response)
                    self.assertEqual(data['server_id'], 'app2')
                    self.assertEqual(data['release_id'], META['release_id'])
                    self.assertTrue(data['ready'])
            with urlopen(base + '/health') as response:
                self.assertEqual(response.read(), b'OK\n')
            with urlopen(base + '/version') as response:
                self.assertEqual(response.read(), b'v2\n')
            with self.assertRaises(HTTPError) as caught:
                urlopen(base + '/missing')
            self.assertEqual(caught.exception.code, 404)

    def test_invalid_initialization_is_alive_but_not_ready(self):
        """초기화 정보가 부족하면 health만 정상이고 서비스·ready·version은 503인지 확인한다."""
        for metadata, identity in [(None, 'app1'), (META, '')]:
            handler = make_handler(metadata, identity)
            handler.log_message = lambda *args: None
            with serve(handler) as base:
                with urlopen(base + '/health') as response:
                    self.assertEqual(response.status, 200)
                for endpoint in ('/', '/ready', '/version'):
                    with self.assertRaises(HTTPError) as caught:
                        urlopen(base + endpoint)
                    self.assertEqual(caught.exception.code, 503)

    def test_sigterm_stops_server_cleanly(self):
        """실제 앱 프로세스에 SIGTERM을 보내 정상 종료 코드로 끝나는지 확인한다."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.json'
            path.write_text(json.dumps(META))
            # 운영 포트와 충돌하지 않도록 임시 포트를 사용하고 정상 종료 동작을 검사한다.
            child = subprocess.Popen([sys.executable, str(ROOT / 'app/server.py')],
                                     env=dict(os.environ, PORT='0', SERVER_ID='app1', METADATA_PATH=str(path)), stdout=subprocess.PIPE, text=True)
            try:
                self.assertTrue(child.stdout.readline().startswith('Listening on'))
                child.terminate()
                self.assertEqual(child.wait(timeout=3), 0)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
                child.stdout.close()


class NginxTests(unittest.TestCase):
    def test_old_worker_must_exit_and_new_worker_must_exist(self):
        """기존 워커 종료와 새 워커 존재를 모두 요구하고 PID 재사용도 구분하는지 검사한다."""
        workers = load_helper('nginx_workers')
        with patch.object(workers, 'workers', side_effect=[{'10': '100', '20': '200'}, {'20': '200'}]), patch.object(workers.time, 'sleep'):
            workers.wait_for_drain('unused', {'10': '100'}, 10)
        with patch.object(workers, 'workers', return_value={'10': '100'}):
            with self.assertRaises(TimeoutError):
                workers.wait_for_drain('unused', {'10': '100'}, 0)
        # PID가 같더라도 시작 시각이 다르면 새 워커로 구분한다.
        with patch.object(workers, 'workers', return_value={'10': '101'}):
            workers.wait_for_drain('unused', {'10': '100'}, 0)

    def test_candidate_validation_preserves_other_shared_configuration(self):
        """후보 검사에서 다른 공용 설정을 유지하고 원본 파일과 임시 파일 정리가 올바른지 확인한다."""
        helper = load_helper('nginx_candidate')
        with tempfile.TemporaryDirectory() as directory:
            main = Path(directory) / 'nginx.conf'
            original = 'events {}\nhttp {\n include /etc/nginx/conf.d/*.conf;\n include /etc/nginx/sites-enabled/*;\n}\n'
            main.write_text(original)
            project = '/etc/nginx/conf.d/sohyeon.conf'
            other = '/etc/nginx/conf.d/other.conf'
            candidate = Path(directory) / 'candidate'
            candidate.write_text('candidate')
            observed = []
            def run(command, check):
                """nginx 명령 실행을 대신해 검증용 임시 설정 내용을 읽어 테스트에서 비교할 수 있게 한다."""
                observed.append(Path(command[-1]).read_text())
            with patch.object(helper.glob, 'glob', return_value=[project, other]), patch.object(helper.subprocess, 'run', side_effect=run):
                helper.validate(str(candidate), project, str(main))
            self.assertIn(other, observed[0])
            self.assertIn(str(candidate), observed[0])
            self.assertNotIn('include "' + project, observed[0])
            self.assertIn('include /etc/nginx/sites-enabled/*;', observed[0])
            self.assertEqual(main.read_text(), original)
            self.assertEqual(list(Path(directory).glob('.sohyeon-check-*')), [])


class ProbeTests(unittest.TestCase):
    def test_bad_json_unknown_server_and_http_failure_count_as_failures(self):
        """잘못된 JSON, 알 수 없는 서버, HTTP 오류가 모두 실패 집계에 포함되는지 검사한다."""
        class Handler(BaseHTTPRequestHandler):
            mode = 'json'
            def log_message(self, *args):
                """테스트 결과를 읽기 쉽도록 임시 HTTP 서버의 기본 접근 로그를 생략한다."""
                pass
            def do_GET(self):
                """테스트 시나리오에 필요한 정상 또는 오류 HTTP 응답을 만들어 측정 도구에 전달한다."""
                self.send_response(503 if self.mode == 'http' else 200)
                self.end_headers()
                self.wfile.write(b'bad json' if self.mode == 'json' else json.dumps(dict(META, server_id='unknown', ready=True)).encode())
        with serve(Handler) as url:
            rows = []
            for mode in ('json', 'unknown', 'http'):
                Handler.mode = mode
                row = sample(url, 1, {'app1': '127.0.0.1:1'})
                row['phase'] = 'rolling'
                rows.append(row)
                self.assertFalse(row['valid'])
            result = summarize(rows)
            self.assertEqual(result['attempts'], 3)
            self.assertEqual(result['failed_requests'], 3)
            self.assertEqual(result['valid_success_rate'], 0)

    def run_observed_command(self, command_code, bad_baseline=False):
        """세 서버를 모사하는 로컬 LB와 probe를 실행하고 명령 결과·집계·최종 버전을 반환한다."""
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            marker = work / 'version'
            marker.write_text('v1')
            class LB(BaseHTTPRequestHandler):
                count = 0
                def log_message(self, *args):
                    """테스트 결과를 읽기 쉽도록 임시 HTTP 서버의 기본 접근 로그를 생략한다."""
                    pass
                def do_GET(self):
                    """테스트 시나리오에 필요한 정상 또는 오류 HTTP 응답을 만들어 측정 도구에 전달한다."""
                    type(self).count += 1
                    version = marker.read_text()
                    body = dict(service='sohyeon-cicd-app', version=version,
                                release_id=version + '-release', git_revision='abc',
                                server_id='app' + str((self.count % 3) + 1), ready=True)
                    self.send_response(503 if bad_baseline else 200)
                    self.end_headers()
                    self.wfile.write(json.dumps(body).encode())
            with serve(LB) as url:
                inventory = {'_meta': {'hostvars': {name: {'ansible_host': '127.0.0.1'} for name in ['app1', 'app2', 'app3', 'lb']}},
                             'app_servers': {'hosts': ['app1', 'app2', 'app3']}, 'load_balancer': {'hosts': ['lb']}}
                inv = work / 'inventory.json'
                inv.write_text(json.dumps(inventory))
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/probe.py'),
                                         '--inventory', str(inv), '--url', url, '--release', 'v2-release', '--version', 'v2',
                                         '--before', '.35', '--after', '.35', '--interval', '.02', '--output', str(work),
                                         '--', sys.executable, '-c', command_code, str(marker)],
                                        capture_output=True, text=True, timeout=10)
            return result, json.loads((work / 'summary.json').read_text()), marker.read_text()

    def test_successful_transition_and_final_fleet_coverage(self):
        """정상 버전 전환 후 세 서버가 관측되고 성공률과 최종 판정이 정상인지 확인한다."""
        result, summary, _ = self.run_observed_command('import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("v2")')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(summary['passed'])
        self.assertEqual(summary['valid_success_rate'], 100)
        self.assertEqual(len(summary['baseline']), 3)

    def test_command_failure_is_not_hidden_by_healthy_http(self):
        """HTTP 응답이 정상이더라도 배포 명령의 실패 코드가 유지되는지 확인한다."""
        result, summary, _ = self.run_observed_command('import sys; sys.exit(7)')
        self.assertEqual(result.returncode, 7)
        self.assertFalse(summary['passed'])
        self.assertEqual(summary['command_exit_code'], 7)
        self.assertEqual(summary['valid_success_rate'], 100)

    def test_bad_baseline_prevents_command_execution(self):
        """배포 전 요청이 실패하면 배포 명령을 실행하지 않는지 확인한다."""
        result, summary, version = self.run_observed_command('import pathlib,sys; pathlib.Path(sys.argv[1]).write_text("v2")', True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(version, 'v1')
        self.assertIsNone(summary['command_exit_code'])
        self.assertFalse(summary['observation_complete'])


# 직접 실행한 경우에만 명령행 처리 또는 테스트 실행을 시작한다.
if __name__ == '__main__':
    unittest.main()
