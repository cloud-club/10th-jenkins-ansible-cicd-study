import json
import os
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from test_ansible_releases import ReleaseFixture, ANSIBLE
from release_fixtures import IMAGE_ID, META, container, image, state

class RollbackTests(ReleaseFixture, unittest.TestCase):
    # Inherit fixture helpers, not archive tests.
    def setUp(self):
        super().setUp()
        self.bin = self.root / 'bin'; self.bin.mkdir()
        wrapper = self.bin / 'docker'
        wrapper.write_text('#!/bin/sh\nexec ' + os.sys.executable + ' ' + str(Path(__file__).with_name('fake_docker.py')) + ' "$@"\n')
        wrapper.chmod(0o755)
        self.data = {'containers': {'taehyeon-app-a': container('app1','a'),
            'taehyeon-app-b': container('app1','b')}, 'images': {IMAGE_ID: image()}, 'load_image': image()}
        (self.root / 'docker-state.json').write_text(json.dumps(self.data))
        self.variables = {'active_slot': 'a', 'deploy_slot': 'b', 'release_manifest': self.manifest,
            'release_image_tar': str(self.image_tar), 'expected_image_id': IMAGE_ID}
        self.extra_env = {'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                          'FAKE_DOCKER_ROOT': str(self.root)}

    def serve(self, port=21001, status=200):
        test = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                payload = dict(META, instance='app1', status='UP')
                self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(json.dumps(payload).encode())
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)

    def run_ensure(self):
        return self.run_release_fixture('../roles/app/tasks/ensure.yml', self.variables, host='app1')

    def calls(self):
        p = self.root / 'docker-calls.json'
        return json.loads(p.read_text()) if p.exists() else []

    def test_reuses_only_matching_image_runtime_and_apis(self):
        self.serve()
        result = self.run_ensure(); self.assert_ok(result)
        self.assertFalse(any(c[0] in ('run', 'load') or c[:2] == ['container','rm'] for c in self.calls()))

    def test_recreates_missing_or_wrong_inactive_container(self):
        self.serve()
        self.data['containers'].pop('taehyeon-app-b')
        self.data['images'] = {}
        (self.root / 'docker-state.json').write_text(json.dumps(self.data))
        result = self.run_ensure(); self.assert_ok(result)
        runs = [c for c in self.calls() if c[0] == 'run']
        self.assertEqual(len(runs), 1); self.assertEqual(runs[0][-1], IMAGE_ID)
        self.assertIn('taehyeon-app-a', json.loads((self.root / 'docker-state.json').read_text())['containers'])

    def test_archive_corruption_blocks_load_and_remove(self):
        self.image_tar.write_bytes(b'tampered after planning')
        result = self.run_ensure()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] in ('load','run') or c[:2] == ['container','rm'] for c in self.calls()))

    def test_rollbacks_ignore_current_http_failure(self):
        self.serve(20001, 500); self.serve()
        result = self.run_ensure(); self.assert_ok(result)

    def test_prepare_requires_matching_pending_operation(self):
        result = self.run_release_fixture('rollback-owner.yml', {'operation_id':'build-42-ROLLBACK',
            'pending_operation': {'operation_id':'other', 'action':'ROLLBACK'},
            'current_state':state(), 'target_state':state()})
        self.assertNotEqual(result.returncode, 0)

    def test_route_state_mismatch_blocks_prepare(self):
        config = self.root / 'nginx.conf'; config.write_text('wrong live configuration\n')
        result = self.run_release_fixture('release-routing-check.yml', {'current_state':state(),
            'nginx_config_path':str(config), 'nginx_listen_port':18001})
        self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__': unittest.main()
