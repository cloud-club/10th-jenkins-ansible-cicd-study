from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
import threading
import unittest
from test_ansible_releases import ReleaseFixture
from release_fixtures import META, NGINX_A, NGINX_B, manifest, state

class OperationTests(ReleaseFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.before = state()
        self.after = {'schema_version':1, 'active_slot':'b',
            'metadata': {'version':'42','gitSha':'newsha','release':'build-42-newsha'},
            'release_id':'build-42-newsha', 'previous_release':'build-41-oldsha',
            'operation_id':'build-42-DEPLOY', 'operation_type':'DEPLOY'}
        self.live = self.root / 'live.conf'; self.live.write_text(NGINX_A)
        self.releases.mkdir()
        self.write_state(self.before)
        for operating, config in ((self.before, NGINX_A), (self.after, NGINX_B)):
            m = manifest(); m['release_id'] = operating['release_id']; m['metadata'] = operating['metadata']
            m['origin']['git_sha'] = operating['metadata']['gitSha']
            m['image']['archive_sha256'] = hashlib.sha256(self.image_tar.read_bytes()).hexdigest()
            m['nginx_sha256'] = hashlib.sha256(config.encode()).hexdigest()
            for host in ('app1','app2','app3'):
                m['runtime'][host]['environment'].update(APP_VERSION=m['metadata']['version'],
                    GIT_SHA=m['metadata']['gitSha'], RELEASE_ID=m['release_id'])
            directory = self.releases / 'releases' / m['release_id']; directory.mkdir(parents=True)
            (directory / 'manifest.json').write_text(json.dumps(m))
            (directory / 'image.tar').write_bytes(self.image_tar.read_bytes())
            (directory / 'nginx.conf').write_text(config)
        self.bin = self.root / 'bin'; self.bin.mkdir()
        for name, script in {'nginx':'exit 0', 'flock':'exit 0', 'systemctl':'echo reload >> "$RELOAD_LOG"'}.items():
            p=self.bin/name; p.write_text('#!/bin/sh\n'+script+'\n'); p.chmod(0o755)
        self.extra_env={'PATH':str(self.bin)+os.pathsep+os.environ['PATH'], 'RELOAD_LOG':str(self.root/'reloads')}
        self.params={'operation_id':'build-42-DEPLOY', 'operation_action':'DEPLOY',
            'before_state':self.before, 'target_state':self.after,
            'nginx_config_path':str(self.live), 'nginx_listen_port':18001,
            'nginx_stage_dir':str(self.root/'nginx-stage'), 'nginx_lock_path':str(self.root/'nginx.lock'),
            'observe_seconds':1,'min_samples':1,'max_response_ms':2000}

    def write_state(self, value):
        (self.releases/'state.json').write_text(json.dumps(value))

    def run_phase(self, phase, **changes):
        return self.run_release_fixture('operation-'+phase+'.yml', dict(self.params, **changes))

    def serve(self, status=200):
        test=self; count=0
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal count
                count+=1
                build=META if ':20001' in test.live.read_text() else test.after['metadata']
                payload=dict(build, instance=('app1','app2','app3')[count%3], status='UP')
                self.send_response(status); self.send_header('Content-Type','application/json'); self.end_headers()
                self.wfile.write(json.dumps(payload).encode())
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0), Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        self.params['operation_observe_url']='http://127.0.0.1:'+str(server.server_port)

    def test_begin_does_not_overwrite_pending(self):
        self.assert_ok(self.run_phase('begin'))
        pending=(self.releases/'pending-operation.json').read_bytes()
        self.assertNotEqual(self.run_phase('begin',operation_id='another-operation').returncode,0)
        self.assertEqual((self.releases/'pending-operation.json').read_bytes(),pending)

    def test_finalize_checks_before_state_and_operation_owner(self):
        self.assert_ok(self.run_phase('begin')); self.live.write_text(NGINX_B)
        self.assertNotEqual(self.run_phase('finalize',operation_id='another-operation').returncode,0)
        self.assertEqual(json.loads((self.releases/'state.json').read_text()), self.before)

    def test_deploy_records_actual_previous_release(self):
        self.assert_ok(self.run_phase('begin')); self.live.write_text(NGINX_B)
        self.assert_ok(self.run_phase('finalize'))
        result=json.loads((self.releases/'state.json').read_text())
        self.assertEqual(result['previous_release'],'build-41-oldsha')
        self.assertEqual(result['release_id'],'build-42-newsha')
        self.assertFalse((self.releases/'pending-operation.json').exists())

    def test_rollback_clears_previous_target(self):
        self.write_state(self.after); self.live.write_text(NGINX_B)
        target=dict(self.before, operation_id='build-43-ROLLBACK',operation_type='ROLLBACK')
        self.params.update(before_state=self.after, target_state=target,
            operation_id='build-43-ROLLBACK', operation_action='ROLLBACK')
        self.assert_ok(self.run_phase('begin')); self.live.write_text(NGINX_A)
        self.assert_ok(self.run_phase('finalize'))
        self.assertIsNone(json.loads((self.releases/'state.json').read_text())['previous_release'])
        self.assertNotEqual(self.run_phase('begin',before_state=target,target_state=self.after).returncode,0)

    def test_recover_uncommitted_restores_before_routing(self):
        self.serve(); self.assert_ok(self.run_phase('begin')); self.live.write_text(NGINX_B)
        self.assert_ok(self.run_phase('recover'))
        self.assertEqual(self.live.read_text(),NGINX_A)
        self.assertEqual(json.loads((self.releases/'state.json').read_text()),self.before)
        self.assertFalse((self.releases/'pending-operation.json').exists())

    def test_recover_committed_does_not_restore_old_routing(self):
        self.serve(); self.assert_ok(self.run_phase('begin')); self.live.write_text(NGINX_B)
        self.write_state(self.after)
        self.assert_ok(self.run_phase('recover'))
        self.assertEqual(self.live.read_text(),NGINX_B)
        self.assertFalse((self.root/'reloads').exists())
        self.assertFalse((self.releases/'pending-operation.json').exists())

    def test_failed_recovery_retains_pending(self):
        self.serve(500); self.assert_ok(self.run_phase('begin')); self.live.write_text(NGINX_B)
        self.assertNotEqual(self.run_phase('recover').returncode,0)
        self.assertTrue((self.releases/'pending-operation.json').exists())

    def test_recovery_uses_no_original_workspace_path(self):
        self.serve(); self.assert_ok(self.run_phase('begin')); self.live.write_text(NGINX_B)
        shutil.rmtree(self.reports); self.reports=self.root/'new-workspace'; self.reports.mkdir()
        self.assert_ok(self.run_phase('recover'))
        status=json.loads((self.reports/'operation-status.json').read_text())
        self.assertEqual(status['resolution'],'recovered')

    def test_malformed_pending_does_not_restore_outside_root(self):
        self.assert_ok(self.run_phase('begin'))
        p=self.releases/'pending-operation.json'; pending=json.loads(p.read_text())
        pending['before_nginx_file']='../outside'; p.write_text(json.dumps(pending))
        self.assertNotEqual(self.run_phase('recover').returncode,0)
        self.assertEqual(self.live.read_text(),NGINX_A)

if __name__=='__main__': unittest.main()
