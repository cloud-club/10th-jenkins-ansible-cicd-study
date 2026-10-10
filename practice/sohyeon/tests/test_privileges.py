"""Checks for shared-server privilege and ownership boundaries."""
import copy
from pathlib import Path
import tempfile
import unittest

import yaml

from test_ansible import AnsibleTests
from test_week2 import ROOT


class PrivilegeTests(unittest.TestCase):
    def test_privileged_lb_deletion_rejects_paths_outside_project(self):
        tasks = yaml.safe_load((ROOT / 'ansible/roles/cleanup/tasks/delete_item.yml').read_text())[0]['block']
        guard = next(task for task in tasks if task['name'] ==
                     'Limit privileged deletion to the assigned Nginx temporary paths')
        play = [{'hosts': 'app1', 'gather_facts': False,
                 'vars': {'cleanup_scope': 'lb', 'cleanup_item': {'kind': 'file', 'path': ''}},
                 'tasks': [guard]}]
        for path, allowed in (
            ('/etc/nginx/sohyeon.candidate', True),
            ('/etc/nginx/conf.d/sohyeon.conf.123.2026-10-10@12:00:00~', True),
            ('/etc/nginx/conf.d/sohyeon.conf', False),
            ('/etc/nginx/nginx.conf', False),
            ('/etc/nginx/conf.d/other.conf', False),
            ('/etc/nginx/conf.d/../nginx.conf', False),
        ):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                result = AnsibleTests().execute(play, directory,
                    {'cleanup_item': {'kind': 'file', 'path': path}})
                self.assertEqual(result.returncode == 0, allowed, result.stdout + result.stderr)

    def test_become_is_limited_to_docker_and_nginx_operations(self):
        allowed = {
            'ansible/roles/nginx_lb/tasks/main.yml',
            'ansible/roles/nginx_lb/handlers/main.yml',
            'ansible/playbook/prepare.yml',
            'ansible/playbook/deploy.yml',
            'ansible/roles/ownership/tasks/main.yml',
            'ansible/roles/app/tasks/main.yml',
            'ansible/roles/cleanup/tasks/delete_item.yml',
        }
        for path in (ROOT / 'ansible').rglob('*.yml'):
            if 'become: true' in path.read_text():
                self.assertIn(str(path.relative_to(ROOT)), allowed, str(path))
        self.assertFalse((ROOT / 'ansible/playbook/admin_setup.yml').exists())

        def walk(tasks):
            for task in tasks:
                yield task
                for key in ('tasks', 'pre_tasks', 'block', 'rescue', 'always'):
                    yield from walk(task.get(key, []))

        for path in (ROOT / 'ansible').rglob('*.yml'):
            content = yaml.safe_load(path.read_text())
            if not isinstance(content, list):
                continue
            for task in walk(content):
                if any(key.startswith('community.docker.') for key in task):
                    self.assertIs(task.get('become'), True, task['name'])
                argv = task.get('ansible.builtin.command', {})
                if isinstance(argv, dict) and 'cleanup.py' in str(argv):
                    self.assertNotEqual(task.get('become'), True, task['name'])
        for name in ('prepare', 'deploy', 'cleanup'):
            for play in yaml.safe_load((ROOT / f'ansible/playbook/{name}.yml').read_text()):
                if 'hosts' in play:
                    self.assertIs(play.get('become'), False)

    def test_nginx_role_has_only_assigned_scope(self):
        text = (ROOT / 'ansible/roles/nginx_lb/tasks/main.yml').read_text()
        self.assertIn("nginx_config == '/etc/nginx/conf.d/sohyeon.conf'", text)
        self.assertIn('lb_port | int == 18007', text)
        self.assertIn('host_port | int == 20007', text)
        self.assertIn('excluded_hosts | length <= 1', text)
        self.assertNotIn('/usr/local/sbin/sohyeon-nginx', text)

    def test_ownership_role_rejects_foreign_ports_and_unapproved_legacy(self):
        tasks = yaml.safe_load((ROOT / 'ansible/roles/ownership/tasks/main.yml').read_text())
        tasks = [task for task in tasks if 'community.docker.docker_container_info' not in task]
        own = {'exists': True, 'container': {'Id': 'a' * 64, 'Name': '/sohyeon-cicd-app',
            'Config': {'Labels': {'io.sohyeon.owner': 'sohyeon', 'io.sohyeon.project': 'sohyeon-cicd'}},
            'HostConfig': {'PortBindings': {'80/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '20007'}]}}}}

        def execute(container, bootstrap=False, approved=None):
            play = [{'hosts': 'app1', 'gather_facts': False, 'vars': {
                'app_name': 'sohyeon-cicd-app', 'image_name': 'sohyeon-cicd-app',
                'host_port': 20007, 'container_port': 80, 'owned_container': container,
                'bootstrap': bootstrap, 'legacy_container_ids': approved or {}}, 'tasks': tasks}]
            with tempfile.TemporaryDirectory() as directory:
                return AnsibleTests().execute(play, directory)

        self.assertEqual(execute(own).returncode, 0)
        foreign = copy.deepcopy(own)
        foreign['container']['Config']['Labels']['io.sohyeon.owner'] = 'someone-else'
        self.assertNotEqual(execute(foreign).returncode, 0)
        self.assertNotEqual(execute(foreign, True, {'app1': 'a' * 64}).returncode, 0)
        legacy = copy.deepcopy(own)
        legacy['container']['Config']['Labels'] = None
        self.assertNotEqual(execute(legacy, True).returncode, 0)
        self.assertEqual(execute(legacy, True, {'app1': 'a' * 64}).returncode, 0)
        legacy['container']['Config']['Labels'] = {'maintainer': 'base image publisher'}
        self.assertEqual(execute(legacy, True, {'app1': 'a' * 64}).returncode, 0)
        self.assertNotEqual(execute(legacy, False, {'app1': 'a' * 64}).returncode, 0)
        mismatch = execute(legacy, True, {'app1': 'b' * 64})
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn('approved_legacy_id_matches=False', mismatch.stdout)
        legacy['container']['Config']['Labels']['io.sohyeon.project'] = 'other-project'
        self.assertNotEqual(execute(legacy, True, {'app1': 'a' * 64}).returncode, 0)
        wrong_port = copy.deepcopy(own)
        wrong_port['container']['HostConfig']['PortBindings']['80/tcp'][0]['HostPort'] = '20008'
        self.assertNotEqual(execute(wrong_port).returncode, 0)


if __name__ == '__main__':
    unittest.main()
