import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE = ROOT / 'ansible'
OLD = {'version': '41', 'gitSha': 'oldsha', 'release': 'old-release'}
NEW = {'version': '42', 'gitSha': 'newsha', 'release': 'new-release'}


class AnsibleCanaryTests(unittest.TestCase):
    def test_handler_applies_live_difference_once_even_when_staged_file_is_unchanged(self):
        # 실제 Role/Handler와 적용 스크립트를 실행하고 외부 Nginx 서비스 명령만 대체한다.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / 'taehyeon.conf'
            live = root / 'live.conf'
            staged.write_text('new configuration\n')
            live.write_text('old configuration\n')
            shutil.copy2(ANSIBLE / 'roles/nginx/files/apply-config.sh', root / 'apply-config.sh')
            commands = root / 'bin'
            commands.mkdir()
            for name, contents in {'flock': 'exit 0', 'nginx': 'exit 0',
                                   'systemctl': 'echo reloaded >> "$RELOAD_LOG"'}.items():
                path = commands / name
                path.write_text('#!/bin/sh\n' + contents + '\n')
                path.chmod(0o755)
            playbook = root / 'handler.yml'
            playbook.write_text(json.dumps([{'hosts': 'localhost', 'gather_facts': False,
                'roles': [str(ANSIBLE / 'roles/nginx')], 'vars': {
                    'nginx_stage_dir': str(root), 'nginx_config_path': str(live),
                    'nginx_lock_path': str(root / 'lock')}}]))
            environment = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ['PATH'],
                               RELOAD_LOG=str(root / 'reloads'))
            command = ['ansible-playbook', '-i', 'localhost,', '-c', 'local', str(playbook), '--tags', 'apply']
            for run in range(2):
                result = subprocess.run(command, cwd=ANSIBLE, env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(live.read_text(), 'new configuration\n')
                self.assertEqual((root / 'reloads').read_text().splitlines(), ['reloaded'])

    def plan_route(self, directory, **changes):
        variables = {'active_slot': 'a', 'metadata': OLD, 'traffic_percent': 10,
                     'app_version': '42', 'git_sha': 'newsha', 'release_id': 'new-release',
                     'backend_snapshot_path': str(Path(directory) / 'backends.json')}
        variables.update(changes)
        source = Path(directory) / 'vars.json'
        source.write_text(json.dumps(variables))
        result = subprocess.run(['ansible-playbook', '-i', 'inventory/hosts.ini',
                                 'playbooks/canary-route.yml', '--tags', 'plan', '-e', '@' + str(source)],
                                cwd=ANSIBLE, capture_output=True, text=True)
        snapshot = Path(variables['backend_snapshot_path'])
        return result, json.loads(snapshot.read_text()) if snapshot.exists() else None

    def test_ansible_derives_weights_and_alternates_slots_without_ssh(self):
        cases = [('a', 0, [('app1', 20001, 1), ('app2', 20001, 1), ('app3', 20001, 1)]),
                 ('a', 10, [('app1', 20001, 3), ('app2', 20001, 3), ('app3', 20001, 3), ('app1', 21001, 1)]),
                 ('a', 50, [('app1', 20001, 1), ('app2', 20001, 1), ('app3', 20001, 1),
                            ('app1', 21001, 1), ('app2', 21001, 1), ('app3', 21001, 1)]),
                 ('b', 100, [('app1', 20001, 1), ('app2', 20001, 1), ('app3', 20001, 1)]),
                 ('b', 0, [('app1', 21001, 1), ('app2', 21001, 1), ('app3', 21001, 1)])]
        for slot, percent, expected in cases:
            with self.subTest(slot=slot, percent=percent), tempfile.TemporaryDirectory() as directory:
                result, targets = self.plan_route(directory, active_slot=slot, traffic_percent=percent)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIsNotNone(targets, 'Ansible must export the actual observation targets')
                self.assertEqual([(t['host'], t['port'], t['weight']) for t in targets], expected)
                self.assertEqual(targets[-1]['metadata'], NEW if percent else OLD)

    def test_bad_traffic_plan_does_not_export_targets(self):
        for changes in ({'active_slot': 'unknown'}, {'traffic_percent': 20},
                        {'release_id': 'old-release'}, {'git_sha': ''}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                result, targets = self.plan_route(directory, **changes)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIsNone(targets)

    def run_validation(self, playbook, variables):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as source:
            json.dump(variables, source)
            source.flush()
            return subprocess.run(['ansible-playbook', '-i', 'inventory/hosts.ini', 'playbooks/' + playbook,
                                   '--tags', 'validate', '-e', '@' + source.name], cwd=ANSIBLE,
                                  capture_output=True, text=True)

    def test_canary_playbooks_exist_and_parse(self):
        for name in ('state', 'app', 'route', 'commit', 'recover'):
            path = ANSIBLE / 'playbooks' / f'canary-{name}.yml'
            self.assertTrue(path.exists(), f'missing {path.name}')
            result = subprocess.run(['ansible-playbook', '-i', 'inventory/hosts.ini', str(path), '--syntax-check'],
                                    cwd=ANSIBLE, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_inactive_slot_validation_and_shared_resource_guards(self):
        valid = {'deploy_hosts': 'app1', 'active_slot': 'a', 'deploy_slot': 'b',
                 'app_version': '42', 'git_sha': 'newsha', 'release_id': 'new-release',
                 'image_tag': 'new-release', 'image_tar': '/tmp/image.tar'}
        result = self.run_validation('canary-app.yml', valid)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for changes in ({'deploy_slot': 'a'}, {'app_host_port': 20002}, {'app_container_name': 'someone-else'},
                        {'app_name': 'someone-else'}, {'active_slot': 'unknown'}):
            with self.subTest(changes=changes):
                result = self.run_validation('canary-app.yml', dict(valid, **changes))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_app_playbook_selects_inactive_slot_when_jenkins_only_supplies_active_slot(self):
        for slot in ('a', 'b'):
            result = self.run_validation('canary-app.yml',
                {'deploy_hosts': 'app1', 'active_slot': slot, 'app_version': '42',
                 'git_sha': 'newsha', 'release_id': 'new-release'})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_commit_selects_candidate_and_recovery_selects_original_state_without_ssh(self):
        for active, restore, wanted_slot, wanted_metadata in (
                ('a', False, 'b', NEW), ('b', False, 'a', NEW), ('b', True, 'b', OLD)):
            with self.subTest(active=active, restore=restore), tempfile.TemporaryDirectory() as directory:
                variables = {'active_slot': active, 'metadata': OLD, 'restore_previous': restore,
                             'app_version': '42', 'git_sha': 'newsha', 'release_id': 'new-release',
                             'canary_report_dir': directory}
                source = Path(directory) / 'vars.json'
                source.write_text(json.dumps(variables))
                result = subprocess.run(['ansible-playbook', '-i', 'inventory/hosts.ini',
                    'playbooks/canary-commit.yml', '--tags', 'plan,validate', '-e', '@' + str(source)],
                    cwd=ANSIBLE, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads((Path(directory) / 'selected-state.json').read_text()),
                                 {'active_slot': wanted_slot, 'metadata': wanted_metadata})

    def test_nginx_scope_validation_rejects_foreign_target_and_port(self):
        valid = {'nginx_backends': [{'host': 'app1', 'port': 21001, 'weight': 1, 'metadata': NEW}]}
        result = self.run_validation('canary-route.yml', valid)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for changes in ({'host': 'someone-else'}, {'port': 20002}, {'weight': 0}, {'weight': -1}):
            with self.subTest(changes=changes):
                invalid = {'nginx_backends': [dict(valid['nginx_backends'][0], **changes)]}
                result = self.run_validation('canary-route.yml', invalid)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_renders_explicit_ports_weights_and_passive_error_visibility(self):
        from jinja2 import Environment, StrictUndefined
        template = Environment(undefined=StrictUndefined).from_string(
            (ANSIBLE / 'roles/nginx/templates/taehyeon.conf.j2').read_text())
        targets = [{'host': 'app1', 'port': 20001, 'weight': 3, 'metadata': OLD},
                   {'host': 'app1', 'port': 21001, 'weight': 1, 'metadata': NEW}]
        rendered = template.render(nginx_targets=targets, hostvars={'app1': {'ansible_host': '1.201.118.202'}},
                                   nginx_listen_port=18001)
        self.assertIn('server 1.201.118.202:20001 weight=3;', rendered)
        self.assertIn('server 1.201.118.202:21001 weight=1;', rendered)
        self.assertIn('proxy_next_upstream off;', rendered)
        self.assertIn('listen 18001;', rendered)


if __name__ == '__main__':
    unittest.main()
