"""Run real Ansible tasks against temporary files; replace only external Docker."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from release_fixtures import IMAGE_ID, META, container, image, manifest, state

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'ansible'

@dataclass
class FixtureResult:
    returncode: int
    stdout: str
    stderr: str
    files: dict
    docker_calls: list

class ReleaseFixture:
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.releases = self.root / 'persistent'
        self.reports = self.root / 'reports'
        self.reports.mkdir()
        self.image_tar = self.root / 'input.tar'
        self.image_tar.write_bytes(b'original docker image archive')
        self.config = 'personal nginx configuration\n'
        self.manifest = manifest()
        self.manifest['image']['archive_sha256'] = hashlib.sha256(self.image_tar.read_bytes()).hexdigest()
        self.manifest['nginx_sha256'] = hashlib.sha256(self.config.encode()).hexdigest()

    def run_release_fixture(self, entrypoint, variables=None, files=None, extra_tasks=None, host='localhost', extra_variables=None):
        for path, contents in (files or {}).items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
        tasks = [{'ansible.builtin.include_tasks': str(ANSIBLE / 'tasks' / entrypoint)}]
        tasks += extra_tasks or []
        fixture_vars = {'release_root': str(self.releases), 'canary_report_dir': str(self.reports),
            'archive_manifest': self.manifest, 'archive_image_tar': str(self.image_tar),
            'archive_nginx_config': self.config, 'requested_release': 'build-41-oldsha',
            'ansible_python_interpreter': os.sys.executable}
        fixture_vars.update(variables or {})
        play = self.root / 'fixture.json'
        play.write_text(json.dumps([{'hosts': host, 'connection': 'local', 'gather_facts': False,
            'vars': fixture_vars, 'tasks': tasks}]))
        environment = dict(os.environ, **getattr(self, 'extra_env', {}))
        environment.update(ANSIBLE_CONFIG=str(ANSIBLE / 'ansible.cfg'),
            ANSIBLE_LOCAL_TEMP=str(self.root / 'ansible-local'), ANSIBLE_REMOTE_TEMP=str(self.root / 'ansible-remote'))
        inventory = self.root / 'inventory.json'
        inventory.write_text(json.dumps({'all': {'hosts': {'localhost': {}}, 'children': {
            'app_servers': {'hosts': {h: {'ansible_host':'127.0.0.1'} for h in ('app1','app2','app3')}},
            'load_balancer': {'hosts': {'nginx': {'ansible_host':'127.0.0.1'}}}}}}))
        command = ['ansible-playbook', '-i', str(inventory), str(play)]
        if extra_variables is not None:
            command += ['-e', json.dumps(extra_variables)]
        result = subprocess.run(command, cwd=ANSIBLE,
            env=environment, capture_output=True, text=True)
        snapshot = {str(p.relative_to(self.releases)): p.read_bytes()
            for p in self.releases.rglob('*') if p.is_file()} if self.releases.exists() else {}
        return FixtureResult(result.returncode, result.stdout, result.stderr, snapshot, [])

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def store(self, **changes):
        return self.run_release_fixture('release-store.yml', changes)

class AnsibleReleaseTests(ReleaseFixture, unittest.TestCase):
    def test_archive_is_complete_before_publish(self):
        result = self.store()
        self.assert_ok(result)
        prefix = 'releases/build-41-oldsha/'
        self.assertEqual(set(result.files), {prefix + x for x in ('manifest.json', 'image.tar', 'nginx.conf')})
        self.assertEqual(result.files[prefix + 'image.tar'], b'original docker image archive')
        self.assertEqual(json.loads(result.files[prefix + 'manifest.json'])['metadata'], META)

    def test_existing_release_is_immutable(self):
        self.assert_ok(self.store())
        original = (self.releases / 'releases/build-41-oldsha/manifest.json').read_bytes()
        changed = dict(self.manifest, created_at='2026-10-20T00:00:00Z', bootstrap=False)
        self.assert_ok(self.store(archive_manifest=changed))
        self.assertEqual((self.releases / 'releases/build-41-oldsha/manifest.json').read_bytes(), original)
        changed = json.loads(json.dumps(self.manifest)); changed['image']['id'] = 'sha256:' + '4' * 64
        self.assertNotEqual(self.store(archive_manifest=changed).returncode, 0)
        self.assertEqual((self.releases / 'releases/build-41-oldsha/manifest.json').read_bytes(), original)

    def test_archive_failure_does_not_publish_partial_release(self):
        self.image_tar.write_bytes(b'changed before storage')
        result = self.store()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.releases / 'releases/build-41-oldsha').exists())

    def test_load_rejects_missing_or_corrupt_archive(self):
        self.assertNotEqual(self.run_release_fixture('release-load.yml').returncode, 0)
        self.assert_ok(self.store())
        self.assert_ok(self.run_release_fixture('release-load.yml'))
        (self.releases / 'releases/build-41-oldsha/image.tar').write_bytes(b'corrupted')
        self.assertNotEqual(self.run_release_fixture('release-load.yml').returncode, 0)

    def test_bootstrap_captures_actual_image_and_preserves_legacy_state(self):
        # Snapshot includes extended state without losing previous-release history.
        current = state(); current.update(previous_release='build-40-older', operation_id='build-41-DEPLOY', operation_type='DEPLOY')
        result = self.run_release_fixture('release-snapshot.yml', {'stored_state': current,
            'stable_slot': 'a', 'stable_metadata': META, 'snapshot_path': str(self.reports / 'state.json')})
        self.assert_ok(result)
        self.assertEqual(json.loads((self.reports / 'state.json').read_text()), current)
        result = self.run_release_fixture('release-snapshot.yml', {'stored_state': {},
            'stable_slot': 'a', 'stable_metadata': META, 'snapshot_path': str(self.reports / 'legacy.json')})
        self.assert_ok(result)
        self.assertEqual(json.loads((self.reports / 'legacy.json').read_text()), {'active_slot': 'a', 'metadata': META})

    def test_three_active_hosts_must_agree(self):
        records = {host: {'captured_image_id': IMAGE_ID, 'captured_runtime': self.manifest['runtime'][host]}
            for host in ('app1', 'app2', 'app3')}
        result = self.run_release_fixture('release-agreement.yml', {'captured_hosts': records, 'archive_metadata': META})
        self.assert_ok(result)
        records['app3']['captured_image_id'] = 'sha256:' + '4' * 64
        self.assertNotEqual(self.run_release_fixture('release-agreement.yml', {'captured_hosts': records,
            'archive_metadata': META}).returncode, 0)

if __name__ == '__main__': unittest.main()
