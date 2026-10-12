import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import time
import unittest
import urllib.request

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/observe.py'
spec = importlib.util.spec_from_file_location('canary_http', SCRIPT)
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)
OLD = {'version': '41', 'gitSha': 'oldsha', 'release': 'old-release'}
NEW = {'version': '42', 'gitSha': 'newsha', 'release': 'new-release'}
TEN = [{'host': host, 'port': 20001, 'weight': 3, 'metadata': OLD} for host in ('app1', 'app2', 'app3')]
TEN += [{'host': 'app1', 'port': 21001, 'weight': 1, 'metadata': NEW}]


class HttpObservationTests(unittest.TestCase):
    def serve(self, status=200, malformed=False):
        class Handler(BaseHTTPRequestHandler):
            index = 0
            def do_GET(self):
                type(self).index += 1
                index = type(self).index - 1
                candidate = index % 10 == 9
                body = dict(NEW if candidate else OLD,
                            instance='app1' if candidate else f'app{index % 3 + 1}', status='UP')
                self.send_response(status)
                self.end_headers()
                self.wfile.write(b'invalid-json' if malformed else json.dumps(body).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f'http://127.0.0.1:{server.server_port}'

    def test_real_http_observer_records_mixed_releases_and_summary(self):
        url = self.serve()
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'observations.jsonl'
            result = canary.observe(url, TEN, 10,
                                    duration=1.2, min_samples=10, max_response_ms=2000, report_path=report)
            self.assertTrue(report.with_suffix('.summary.json').exists())
            rows = [json.loads(line) for line in report.read_text().splitlines()]
            self.assertTrue(all(row['http_status'] == 200 for row in rows))
            self.assertEqual({row['body']['release'] for row in rows}, {'old-release', 'new-release'})
            self.assertGreaterEqual(result['samples'], 10)

    def test_real_http_500_and_invalid_json_stop_observation(self):
        for status, malformed in ((500, False), (200, True)):
            with self.subTest(status=status, malformed=malformed), tempfile.TemporaryDirectory() as directory:
                url = self.serve(status, malformed)
                with self.assertRaises(ValueError):
                    canary.observe(url, TEN, 10,
                                   duration=1, min_samples=1, max_response_ms=2000,
                                   report_path=Path(directory) / 'failed.jsonl')
                summary = json.loads((Path(directory) / 'failed.summary.json').read_text())
                self.assertFalse(summary['passed'])
                self.assertEqual(summary['failures'], 1)

    def test_monitor_cli_signals_readiness_and_fails_without_waiting_for_stop_on_http_error(self):
        url = self.serve(500)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backends.json').write_text(json.dumps(TEN))
            process = subprocess.Popen([sys.executable, str(SCRIPT), 'monitor', '--url', url,
                '--backends-file', str(root / 'backends.json'), '--report', str(root / 'whole.jsonl'),
                '--ready-file', str(root / 'ready'), '--stop-file', str(root / 'stop'), '--timeout', '5'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 4
                while not (root / 'whole.jsonl').exists() or not (root / 'whole.jsonl').stat().st_size:
                    if process.poll() is not None or time.monotonic() > deadline:
                        self.fail('monitor did not start HTTP requests')
                    time.sleep(0.02)
                self.assertTrue((root / 'ready').exists())
                try:
                    stdout, stderr = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    self.fail('HTTP error must fail the Jenkins parallel branch immediately')
                self.assertNotEqual(process.returncode, 0, stdout + stderr)
                summary = json.loads((root / 'whole.summary.json').read_text())
                self.assertGreater(summary['failures'], 0)
                self.assertFalse(summary['passed'])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_stage_cli_writes_summary_and_rejects_nonpositive_parameters(self):
        url = self.serve()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            targets = root / 'backends.json'
            targets.write_text(json.dumps(TEN))
            command = [sys.executable, str(SCRIPT), 'stage', '--url', url, '--backends-file', str(targets),
                       '--report', str(root / 'stage.jsonl'), '--percent', '10',
                       '--seconds', '2', '--min-samples', '10']
            result = subprocess.run(command, capture_output=True, text=True, timeout=6)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads((root / 'stage.summary.json').read_text())
            self.assertTrue(summary['passed'])
            self.assertEqual(summary['availability_percent'], 100)
            result = subprocess.run(command + ['--seconds', '0'], capture_output=True, text=True, timeout=6)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
