import importlib.util
from copy import deepcopy
from pathlib import Path
import unittest
from release_fixtures import container, image, manifest, state

PLUGIN = Path(__file__).resolve().parents[1] / 'ansible/filter_plugins/release_validation.py'

class ReleaseValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PLUGIN.exists():
            return
        spec = importlib.util.spec_from_file_location('release_validation', PLUGIN)
        cls.validation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.validation)

    def setUp(self):
        self.assertTrue(PLUGIN.exists(), 'release validation is not implemented')
        self.v = self.validation

    def test_rejects_release_path_traversal(self):
        for value in ('../x', 'a/b', '$(id)', '', 'a' * 129, '.', '..', None, 7):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.v.validate_release_id(value)
        self.assertEqual(self.v.validate_release_id('build-41-oldsha'), 'build-41-oldsha')

    def test_manifest_requires_exact_three_hosts_and_matching_metadata(self):
        self.assertEqual(self.v.validate_release_manifest(manifest())['image']['id'], 'sha256:' + '1' * 64)
        variants = []
        m = manifest(); del m['runtime']['app3']; variants.append(m)
        m = manifest(); m['runtime']['app4'] = m['runtime']['app1']; variants.append(m)
        m = manifest(); m['metadata']['release'] = 'another'; variants.append(m)
        m = manifest(); m['runtime']['app2']['environment']['APP_INSTANCE'] = 'app1'; variants.append(m)
        m = manifest(); m['image']['archive_name'] = '../image.tar'; variants.append(m)
        m = manifest(); m['image']['archive_sha256'] = 'bad'; variants.append(m)
        m = manifest(); m['image']['id'] = 'latest'; variants.append(m)
        m = manifest(); m['runtime']['app1']['environment']['SECRET'] = 'private'; variants.append(m)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.v.validate_release_manifest(value)

    def test_state_only_accepts_legacy_when_explicit(self):
        old = {'active_slot': 'a', 'metadata': manifest()['metadata']}
        with self.assertRaises(ValueError): self.v.validate_release_state(old)
        self.assertEqual(self.v.validate_release_state(old, True), old)
        self.assertEqual(self.v.validate_release_state(state())['previous_release'], None)
        for changes in ({'active_slot': 'c'}, {'release_id': 'another'},
                        {'previous_release': '../other'}, {'operation_type': 'unknown'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.v.validate_release_state(dict(state(), **changes))

    def test_runtime_captures_only_supported_settings(self):
        runtime = self.v.capture_release_runtime(container(), image(), 'app1', 'a')
        self.assertEqual(runtime, manifest()['runtime']['app1'])
        legacy = container(); legacy['Name'] = '/taehyeon-app'
        self.assertEqual(self.v.capture_release_runtime(legacy, image(), 'app1', 'a'), runtime)

    def test_runtime_rejects_unrecorded_container_options(self):
        variants = []
        c = container(); c['Mounts'] = [{'Type': 'bind', 'Source': '/secret'}]; variants.append(c)
        c = container(); c['HostConfig']['PortBindings']['9000/tcp'] = []; variants.append(c)
        c = container(); c['HostConfig']['Privileged'] = True; variants.append(c)
        c = container(); c['HostConfig']['NetworkMode'] = 'host'; variants.append(c)
        c = container(); c['Config']['Entrypoint'] = ['another']; variants.append(c)
        c = container(); c['Config']['Cmd'] = ['custom']; variants.append(c)
        c = container(); c['Config']['Env'].append('SECRET=do-not-log-me'); variants.append(c)
        c = container(); c['Config']['Env'][0] = 'PATH=/changed'; variants.append(c)
        c = container(); c['Config']['Env'][-1] = 'APP_INSTANCE=app2'; variants.append(c)
        c = container(); c['Image'] = 'sha256:' + '4' * 64; variants.append(c)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError) as error:
                self.v.capture_release_runtime(value, image(), 'app1', 'a')
            self.assertNotIn('do-not-log-me', str(error.exception))

    def test_runtime_rejects_init_option(self):
        c=container(); c['HostConfig']['Init']=True
        with self.assertRaises(ValueError): self.v.capture_release_runtime(c,image(),'app1','a')

    def test_runtime_rejects_custom_shared_memory(self):
        c=container(); c['HostConfig']['ShmSize']=134217728
        with self.assertRaises(ValueError): self.v.capture_release_runtime(c,image(),'app1','a')

    def test_runtime_rejects_different_logging_driver(self):
        c=container(); c['HostConfig']['LogConfig']={'Type':'none','Config':{}}
        with self.assertRaises(ValueError): self.v.capture_release_runtime(c,image(),'app1','a')

if __name__ == '__main__': unittest.main()
