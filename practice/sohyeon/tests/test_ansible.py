"""파일 역할: 실제 검증 Role과 Nginx 템플릿을 확인하고, 모의 배포 실패 시 후속 서버가 중단되는지 검사한다."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

try:
    import yaml
except ImportError:
    yaml = None

from test_week2 import ROOT, META, make_handler, serve
from http.server import BaseHTTPRequestHandler


@unittest.skipUnless(yaml and shutil.which('ansible-playbook'), 'Requires Ansible and its PyYAML dependency')
class AnsibleTests(unittest.TestCase):
    def test_lb_preparation_requires_all_three_current_release_markers(self):
        guard = yaml.safe_load((ROOT / 'ansible/playbook/prepare.yml').read_text())[1]['pre_tasks'][0]
        for markers, allowed in ((['target', 'target', 'target'], True),
                                 (['target', '', 'target'], False),
                                 (['target', 'previous', 'target'], False)):
            with self.subTest(markers=markers), tempfile.TemporaryDirectory() as directory:
                play = [{'hosts': 'app1', 'gather_facts': False,
                         'vars': {'image_tag': 'target'}, 'tasks': [
                             {'ansible.builtin.add_host': {'name': '{{ item.name }}',
                                                          'prepared_release': '{{ item.release }}'},
                              'loop': [{'name': f'app{i}', 'release': release}
                                       for i, release in enumerate(markers, 1)]}, guard]}]
                result = self.execute(play, directory)
                self.assertEqual(result.returncode == 0, allowed, result.stdout + result.stderr)

    def execute(self, play, directory, extra=None):
        """임시 로컬 인벤토리와 플레이북을 만들어 원격 접속 없이 Ansible을 실행하고 결과를 반환한다."""
        directory = Path(directory)
        (directory / 'inventory.ini').write_text(
            '[app_servers]\napp1\napp2\napp3\n[all:vars]\nansible_connection=local\n')
        path = directory / 'test.yml'
        path.write_text(yaml.safe_dump(play, allow_unicode=True, sort_keys=False))
        env = dict(os.environ, ANSIBLE_LOCAL_TEMP=str(directory / 'local'),
                   ANSIBLE_REMOTE_TEMP=str(directory / 'remote'), ANSIBLE_NOCOLOR='1')
        return subprocess.run(['ansible-playbook', '-i', str(directory / 'inventory.ini'), str(path),
                               '-e', json.dumps(extra or {})], env=env, text=True,
                              capture_output=True, timeout=60)

    def test_real_verification_role_normal_and_legacy_contracts(self):
        """실제 verification Role이 정상 릴리스를 통과시키고 잘못된 기대 릴리스를 거부하는지 검사한다."""
        handler = make_handler(META, 'app1')
        handler.log_message = lambda *args: None
        with tempfile.TemporaryDirectory() as directory, serve(handler) as url:
            common = yaml.safe_load((ROOT / 'ansible/group_vars/all.yml').read_text())
            common.update(check_host='app1', check_from='app1', check_url=url,
                          expected_release=META['release_id'], app_version='v2', health_retries=1)
            play = [{'hosts': 'app1', 'gather_facts': False, 'vars': common, 'tasks': [
                {'name': 'Verify using production role', 'ansible.builtin.include_role':
                    {'name': str(ROOT / 'ansible/roles/verification')}}]}]
            good = self.execute(play, directory)
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            bad = self.execute(play, directory, {'expected_release': 'wrong-release'})
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('Verify server identity and release', bad.stdout)

    def test_legacy_contract_requires_explicit_bootstrap(self):
        """기존 Week1 응답은 명시적인 bootstrap 모드에서만 허용하는지 확인한다."""
        class Legacy(BaseHTTPRequestHandler):
            def log_message(self, *args):
                """임시 테스트 서버의 접근 로그를 생략해 검사 결과에 집중할 수 있게 한다."""
                pass
            def do_GET(self):
                """기존 Week1 앱의 기본 응답·health·version을 모사한다."""
                self.send_response(200)
                self.end_headers()
                self.wfile.write({'/': b'Sohyeon Jenkins + Ansible CI/CD',
                                  '/health': b'OK', '/version': b'v42'}.get(self.path, b'unknown'))
        with tempfile.TemporaryDirectory() as directory, serve(Legacy) as url:
            common = yaml.safe_load((ROOT / 'ansible/group_vars/all.yml').read_text())
            common.update(check_host='app1', check_from='app1', check_url=url,
                          expected_release='', bootstrap=True, health_retries=1)
            play = [{'hosts': 'app1', 'gather_facts': False, 'vars': common, 'tasks': [
                {'ansible.builtin.include_role': {'name': str(ROOT / 'ansible/roles/verification')}}]}]
            good = self.execute(play, directory)
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
            bad = self.execute(play, directory, {'bootstrap': False})
            self.assertNotEqual(bad.returncode, 0)

    def test_nginx_template_excludes_exactly_one_inventory_server(self):
        """실제 Nginx 템플릿이 지정한 한 서버만 down으로 렌더링하는지 검사한다."""
        template = str(ROOT / 'ansible/roles/nginx_lb/templates/sohyeon.conf.j2')
        play = [{'hosts': 'app1', 'gather_facts': False,
                 'vars': {'host_port': 20007, 'lb_port': 18007, 'excluded_hosts': ['app2']},
                 'tasks': [
                     {'ansible.builtin.set_fact': {'rendered': "{{ lookup('template', '" + template + "') }}"}},
                     {'ansible.builtin.assert': {'that': [
                         "'server 127.0.0.1:20007;' in rendered",
                         "'server 127.0.0.2:20007 down;' in rendered",
                         "'server 127.0.0.3:20007;' in rendered",
                         "rendered.count(' down;') == 1"]}}]}]
        with tempfile.TemporaryDirectory() as directory:
            # 실제 서버 구성처럼 각 테스트 호스트에 서로 다른 주소를 지정한다.
            play[0]['tasks'].insert(0, {'ansible.builtin.add_host': {
                'name': '{{ item.name }}', 'ansible_host': '{{ item.ip }}'},
                'loop': [{'name': f'app{i}', 'ip': f'127.0.0.{i}'} for i in (1, 2, 3)]})
            result = self.execute(play, directory)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_serial_failure_on_app2_prevents_app3_even_after_rescue(self):
        """실제 순차 실행과 rescue 구조에서 app2 실패 후 app3가 실행되지 않는지 확인한다."""
        play = yaml.safe_load((ROOT / 'ansible/playbook/deploy.yml').read_text())[0]
        # 실제 순차 실행·실패 중단·block/rescue 구조를 유지하고 외부 작업만 모의 처리한다.
        def stub(tasks):
            """외부 작업을 모의 작업으로 바꾸되 순차 배포·실패 중단·rescue 제어 구조는 유지한다."""
            result = []
            for task in tasks:
                if 'block' in task:
                    changed = {'name': task['name'], 'block': stub(task['block']), 'rescue': stub(task['rescue'])}
                elif 'ansible.builtin.fail' in task:
                    changed = copy.deepcopy(task)
                else:
                    changed = {'name': task.get('name', 'handler flush'),
                               'ansible.builtin.debug': {'msg': '{{ inventory_hostname }} :: ' + task.get('name', '')}}
                    if task.get('name') == 'ROLLING 3 - Replace the application container':
                        changed = {'name': task['name'], 'ansible.builtin.assert': {
                            'that': "inventory_hostname != 'app2'", 'fail_msg': 'simulated replace failure'}}
                result.append(changed)
            return result
        play['tasks'] = stub(play['tasks'])
        play['pre_tasks'] = stub(play.get('pre_tasks', []))
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute([play], directory)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn('app1 :: ROLLING COMPLETE', result.stdout)
        self.assertIn('app2 :: Keep the failed server out of traffic', result.stdout)
        self.assertNotIn('app3 ::', result.stdout)
        self.assertIn('Next servers are NOT deployed', result.stdout)


# 직접 실행한 경우에만 명령행 처리 또는 테스트 실행을 시작한다.
if __name__ == '__main__':
    unittest.main()
