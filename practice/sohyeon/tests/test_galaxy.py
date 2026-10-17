"""Exercise the pinned Galaxy image removal module against a local fake Docker API."""
import copy
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, unquote, urlparse

from test_week2 import ROOT, serve

try:
    import yaml
except ImportError:
    yaml = None


@unittest.skipUnless(yaml and shutil.which('ansible-playbook') and
                     (ROOT / '.ansible/collections/ansible_collections/community/docker/MANIFEST.json').exists(),
                     'Install the pinned Galaxy collections first')
class GalaxyTests(unittest.TestCase):
    def test_real_image_remove_module_never_forces_or_prunes_parents(self):
        requests = []
        image_id = 'sha256:' + 'a' * 64
        image = {'Id': image_id, 'RepoTags': ['sohyeon-cicd-app:old'], 'RepoDigests': []}

        class API(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, data, status=200):
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = re.sub(r'^/v[0-9.]+', '', unquote(urlparse(self.path).path))
                if path == '/version':
                    self.reply({'ApiVersion': '1.44', 'Version': '25.0.0'})
                elif path == '/images/json':
                    self.reply([image])
                elif path == f'/images/{image_id}/json':
                    self.reply(image)
                else:
                    self.reply({'message': path}, 404)

            def do_DELETE(self):
                requests.append(urlparse(self.path))
                self.reply([{'Untagged': 'sohyeon-cicd-app:old'}])

        with tempfile.TemporaryDirectory() as directory, serve(API) as base:
            root = Path(directory)
            task = next(task for task in yaml.safe_load((ROOT / 'ansible/roles/cleanup/tasks/delete_item.yml').read_text())[0]['block']
                        if 'community.docker.docker_image_remove' in task)
            task = copy.deepcopy(task)
            self.assertIs(task['become'], True)
            # This test talks only to a local fake API; it must not invoke sudo.
            task['become'] = False
            task.pop('no_log')
            task['community.docker.docker_image_remove']['docker_host'] = base.replace('http:', 'tcp:')
            play = [{'hosts': 'localhost', 'gather_facts': False, 'connection': 'local',
                     'vars': {'ansible_python_interpreter': sys.executable,
                              'cleanup_item': {'kind': 'image', 'ref': 'sohyeon-cicd-app:old'}},
                     'tasks': [task]}]
            path = root / 'test.yml'
            path.write_text(yaml.safe_dump(play))
            result = subprocess.run(['ansible-playbook', '-i', 'localhost,', str(path)],
                                    env=dict(os.environ, ANSIBLE_CONFIG=str(ROOT / 'ansible.cfg'),
                                             ANSIBLE_LOCAL_TEMP=str(root / 'local'), ANSIBLE_REMOTE_TEMP=str(root / 'remote')),
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(requests), 1)
        self.assertTrue(unquote(requests[0].path).endswith('/images/sohyeon-cicd-app:old'))
        self.assertEqual(parse_qs(requests[0].query), {'force': ['False'], 'noprune': ['True']})
