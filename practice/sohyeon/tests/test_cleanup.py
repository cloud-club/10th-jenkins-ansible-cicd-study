"""Cleanup regression checks: recovery protection, changed resources and archive gates."""
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cleanup
from cleanup_workspace import cleanup as clean_workspace


OWNED = {'Labels': {'io.sohyeon.project': 'sohyeon-cicd', 'io.sohyeon.owner': 'sohyeon'}}


class CleanupTests(unittest.TestCase):
    def test_lb_down_check_ignores_comments_but_rejects_disabled_upstream(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'sohyeon.conf'
            (root / 'nginx.previous.conf').write_text('recovery')
            with patch.object(cleanup, 'STATE', root), patch.object(cleanup, 'CONFIG', config):
                config.write_text('# A server can be marked down during deployment\nserver 127.0.0.1:20007;\n')
                self.assertEqual(cleanup.make_plan('lb', 'v1-aaaaaaaaaaaa-1')['candidates'], [])
                config.write_text('# comment\nserver 127.0.0.1:20007 down;\n')
                with self.assertRaisesRegex(ValueError, 'still excluded'):
                    cleanup.make_plan('lb', 'v1-aaaaaaaaaaaa-1')

    def test_sudo_docker_reads_keep_state_in_deployment_account_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            current = {'Image': 'previous', 'State': {'Running': True}}
            with patch.object(cleanup, 'STATE', state), patch.dict(os.environ, {'SOHYEON_DOCKER_SUDO': '1'}), patch.object(cleanup.subprocess, 'check_output', return_value=json.dumps([current])) as run:
                cleanup.snapshot('v2-aaaaaaaaaaaa-2')
                run.assert_called_once_with(
                    ['sudo', '-n', '--', 'docker', '--host', 'unix:///var/run/docker.sock',
                     'container', 'inspect', 'sohyeon-cicd-app'], text=True)
            saved = state / 'previous-container.json'
            self.assertEqual(saved.stat().st_uid, os.getuid())
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(saved.read_text())['container'], current)

    def test_privileged_helper_rejects_docker_mutations(self):
        with patch.dict(os.environ, {'SOHYEON_DOCKER_SUDO': '1'}), patch.object(cleanup.subprocess, 'check_output') as run:
            for args in [('container', 'rm', 'other'), ('image', 'rm', 'other'),
                         ('system', 'prune'), ('run', 'other'), ('load', '-i', 'other.tar')]:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    cleanup.docker(*args)
            run.assert_not_called()

    def test_image_archive_rejects_foreign_tags_labels_and_extra_images(self):
        release = 'v2-aaaaaaaaaaaa-2'
        own_labels = dict(OWNED['Labels'], **{'io.sohyeon.release': release})
        own_manifest = {'Config': 'config.json', 'RepoTags': [f'{cleanup.APP}:{release}']}
        cases = [([own_manifest], own_labels, True),
                 ([dict(own_manifest, RepoTags=['other:latest'])], own_labels, False),
                 ([dict(own_manifest, RepoTags=[f'{cleanup.APP}:{release}', 'other:latest'])], own_labels, False),
                 ([own_manifest, own_manifest], own_labels, False),
                 ([own_manifest], {}, False),
                 ([own_manifest], dict(own_labels, **{'io.sohyeon.owner': 'other'}), False),
                 ([own_manifest], dict(own_labels, **{'io.sohyeon.release': 'wrong'}), False)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.tar'
            for manifest, labels, allowed in cases:
                with self.subTest(manifest=manifest, labels=labels):
                    with tarfile.open(path, 'w') as archive:
                        for name, data in [('manifest.json', manifest), ('config.json', {'config': {'Labels': labels}})]:
                            body = json.dumps(data).encode()
                            member = tarfile.TarInfo(name)
                            member.size = len(body)
                            archive.addfile(member, io.BytesIO(body))
                    if allowed:
                        cleanup.validate_archive(path, release)
                    else:
                        with self.assertRaises(ValueError):
                            cleanup.validate_archive(path, release)

    def test_lb_cleanup_removes_recorded_files_and_preserves_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / 'state'
            state.mkdir()
            config = root / 'sohyeon.conf'
            candidate = root / 'sohyeon.candidate'
            backup = root / 'sohyeon.conf.123.2026-10-10@12:00:00~'
            unrecorded = root / 'sohyeon.conf.456.2026-10-09@12:00:00~'
            previous = state / 'nginx.previous.conf'
            foreign = root / 'other.conf'
            for path in (config, candidate, backup, unrecorded, previous, foreign):
                path.write_text('keep or clean according to ownership')
            with patch.object(cleanup, 'STATE', state), patch.object(cleanup, 'CONFIG', config), patch.object(cleanup, 'CANDIDATE', candidate):
                cleanup.record_file('lb', candidate)
                cleanup.record_file('lb', backup)
                plan = cleanup.make_plan('lb', 'v2-aaaaaaaaaaaa-2')
                self.assertEqual({item['path'] for item in plan['candidates']},
                                 {str(candidate), str(backup)})
                cleanup.apply(plan, None, state / 'result.json')
                self.assertFalse(candidate.exists())
                self.assertFalse(backup.exists())
                for path in (config, previous, unrecorded, foreign):
                    self.assertTrue(path.exists(), path)
                self.assertEqual(cleanup.make_plan('lb', 'v2-aaaaaaaaaaaa-2')['candidates'], [])

    def test_lb_modified_backup_stops_archived_plan_before_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'sohyeon.conf'
            backup = root / 'sohyeon.conf.123.2026-10-10@12:00:00~'
            config.write_text('active config')
            backup.write_text('original backup')
            (root / 'nginx.previous.conf').write_text('recovery')
            with patch.object(cleanup, 'STATE', root), patch.object(cleanup, 'CONFIG', config):
                cleanup.record_file('lb', backup)
                plan = cleanup.make_plan('lb', 'v2-aaaaaaaaaaaa-2')
                backup.write_text('modified after planning')
                with self.assertRaises(ValueError):
                    cleanup.apply(plan, None, root / 'result.json')
                self.assertEqual(backup.read_text(), 'modified after planning')
                self.assertTrue(json.loads((root / 'result.json').read_text())['failed'])

    def test_snapshot_keeps_original_recovery_reference_on_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            with patch.object(cleanup, 'STATE', state), patch.object(cleanup, 'inspect') as inspect:
                inspect.return_value = {'Image': 'previous', 'State': {'Running': True}}
                cleanup.snapshot('v2-aaaaaaaaaaaa-2')
                inspect.return_value = {'Image': 'current', 'State': {'Running': True}}
                cleanup.snapshot('v2-aaaaaaaaaaaa-2')
                data = json.loads((state / 'previous-container.json').read_text())
                self.assertEqual(data['container']['Image'], 'previous')
                self.assertEqual((state / 'previous-container.json').stat().st_mode & 0o777, 0o600)

    def test_app_protects_previous_current_and_all_container_references(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / 'previous-container.json').write_text(json.dumps({
                'target': 'v2-aaaaaaaaaaaa-2', 'container': {'Image': 'old'}}))
            def inspect(kind, ref):
                if kind == 'container':
                    return {'Image': 'new', 'State': {'Running': True}}
                return {'Id': 'new' if ':' in ref else ref}
            with patch.object(cleanup, 'STATE', state), patch.object(cleanup, 'inspect', side_effect=inspect), patch.object(cleanup, 'containers', return_value=[{'Image': 'other-app'}, {'Image': 'stopped'}]):
                protected = cleanup.protected_images('app', 'v2-aaaaaaaaaaaa-2', None)
            self.assertEqual(protected, {'new', 'old', 'other-app', 'stopped'})

    def test_only_exact_project_repository_is_selected(self):
        def docker(*args):
            if '--format' in args:
                return 'sohyeon-cicd-app:old\nsohyeon-cicd-app:current\nother:old\nsohyeon-cicd-app:<none>'
            return ''
        with patch.object(cleanup, 'protected_images', return_value={'current'}), patch.object(cleanup, 'containers', return_value=[]), patch.object(cleanup, 'docker', side_effect=docker), patch.object(cleanup, 'inspect', side_effect=lambda kind, ref: {'Id': ref.split(':')[1], 'Config': OWNED}):
            plan = cleanup.make_plan('agent', 'v2-aaaaaaaaaaaa-2', '.')
        self.assertEqual(plan['candidates'], [{'kind': 'image', 'ref': 'sohyeon-cicd-app:old', 'id': 'old'}])

    def test_same_repository_without_owner_label_is_preserved(self):
        def docker(*args):
            return 'sohyeon-cicd-app:old' if '--format' in args else ''
        for config in ({}, {'Labels': {'io.sohyeon.project': 'sohyeon-cicd'}},
                       {'Labels': {'io.sohyeon.project': 'sohyeon-cicd', 'io.sohyeon.owner': 'someone-else'}}):
            with patch.object(cleanup, 'protected_images', return_value=set()), patch.object(cleanup, 'containers', return_value=[]), patch.object(cleanup, 'docker', side_effect=docker), patch.object(cleanup, 'inspect', return_value={'Id': 'old', 'Config': config}):
                self.assertEqual(cleanup.make_plan('agent', 'v2-aaaaaaaaaaaa-2', '.')['candidates'], [])

    def test_unrecorded_and_modified_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tracked = root / 'tracked.tar'
            foreign = root / 'foreign.tar'
            tracked.write_text('ours')
            foreign.write_text('theirs')
            with patch.object(cleanup, 'STATE', root), patch.object(cleanup, 'allowed_file', return_value=True):
                self.assertEqual(cleanup.recorded_files('app'), [])
                cleanup.record_file('app', tracked)
                self.assertEqual([item['path'] for item in cleanup.recorded_files('app')], [str(tracked)])
                tracked.write_text('changed by another task')
                self.assertEqual(cleanup.recorded_files('app'), [])
                self.assertEqual(foreign.read_text(), 'theirs')

    def test_post_cleanup_refuses_foreign_container_with_same_name(self):
        with patch.object(cleanup, 'docker', return_value='foreign-id') as docker, patch.object(cleanup, 'inspect', return_value={'Config': {'Labels': {}}}):
            with self.assertRaises(ValueError):
                cleanup.remove_test('sohyeon-cicd-test-42', 'v2-aaaaaaaaaaaa-42')
            self.assertEqual(docker.call_count, 1)  # Listing only; no rm.

    def test_ownership_registry_rejects_other_project_paths(self):
        for path in ('/tmp/someone-else.tar', '/etc/nginx/conf.d/other.conf', '/etc/nginx/nginx.conf'):
            self.assertFalse(cleanup.allowed_file('app', path))
            self.assertFalse(cleanup.allowed_file('lb', path))

    def test_plan_change_prevents_all_deletion_and_records_failure(self):
        plan = {'scope': 'agent', 'release': 'release', 'protected_images': [], 'candidates': []}
        with tempfile.TemporaryDirectory() as directory, patch.object(cleanup, 'make_plan', return_value={}), patch.object(cleanup, 'docker') as docker:
            result = Path(directory) / 'result.json'
            with self.assertRaises(ValueError):
                cleanup.apply(plan, '.', result)
            docker.assert_not_called()
            self.assertTrue(json.loads(result.read_text())['failed'])

    def test_image_becoming_referenced_is_not_removed(self):
        plan = {'scope': 'agent', 'release': 'release', 'protected_images': [],
                'candidates': [{'kind': 'image', 'ref': 'sohyeon-cicd-app:old', 'id': 'old'}]}
        with tempfile.TemporaryDirectory() as directory, patch.object(cleanup, 'make_plan', return_value=plan), patch.object(cleanup, 'inspect', return_value={'Id': 'old', 'Config': OWNED}), patch.object(cleanup, 'protected_images', return_value={'old'}), patch.object(cleanup, 'docker') as docker:
            with self.assertRaises(ValueError):
                cleanup.apply(plan, '.', Path(directory) / 'result.json')
            docker.assert_not_called()

    def test_successful_image_cleanup_uses_exact_reference_without_force(self):
        plan = {'scope': 'agent', 'release': 'release', 'protected_images': ['current'],
                'candidates': [{'kind': 'image', 'ref': 'sohyeon-cicd-app:old', 'id': 'old'}]}
        with tempfile.TemporaryDirectory() as directory, patch.object(cleanup, 'make_plan', return_value=plan), patch.object(cleanup, 'inspect', return_value={'Id': 'old', 'Config': OWNED}), patch.object(cleanup, 'protected_images', return_value={'current'}), patch.object(cleanup, 'docker') as docker:
            result = Path(directory) / 'result.json'
            cleanup.apply(plan, '.', result)
            docker.assert_called_once_with('image', 'rm', '--no-prune', 'sohyeon-cicd-app:old')
            self.assertEqual(json.loads(result.read_text())['failed'], [])

    def test_docker_failure_is_reported_and_stops_later_deletions(self):
        plan = {'scope': 'agent', 'release': 'release', 'protected_images': [],
                'candidates': [{'kind': 'image', 'ref': 'sohyeon-cicd-app:old', 'id': 'old'},
                               {'kind': 'image', 'ref': 'sohyeon-cicd-app:older', 'id': 'older'}]}
        with tempfile.TemporaryDirectory() as directory, patch.object(cleanup, 'make_plan', return_value=plan), patch.object(cleanup, 'inspect', return_value={'Id': 'old', 'Config': OWNED}), patch.object(cleanup, 'protected_images', return_value=set()), patch.object(cleanup, 'docker', side_effect=RuntimeError('Docker refused deletion')) as docker:
            result = Path(directory) / 'result.json'
            with self.assertRaises(RuntimeError):
                cleanup.apply(plan, '.', result)
            self.assertEqual(docker.call_count, 1)
            self.assertEqual(json.loads(result.read_text())['deleted'], [])
            self.assertIn('Docker refused deletion', json.loads(result.read_text())['failed'])

    def test_file_deletion_and_result_are_repeatably_planned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'candidate'
            path.write_text('old config')
            plan = {'scope': 'lb', 'release': 'release', 'protected_images': [],
                    'candidates': [cleanup.file_entry(path)]}
            result = Path(directory) / 'result.json'
            with patch.object(cleanup, 'make_plan', return_value=plan):
                cleanup.apply(plan, None, result)
            self.assertFalse(path.exists())
            self.assertEqual(json.loads(result.read_text())['deleted'], plan['candidates'])

    def test_module_guard_does_not_delete_and_records_partial_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'candidate'
            target.write_text('temporary')
            plan = {'scope': 'lb', 'release': 'release', 'protected_images': [],
                    'candidates': [cleanup.file_entry(target)]}
            args = SimpleNamespace(result=root / 'result.json', protection_dir=None,
                                   index=0, error='module failed')
            with patch.object(cleanup, 'make_plan', return_value=plan):
                cleanup.module_action('validate-plan', plan, args)
            cleanup.module_action('check-item', plan, args)
            self.assertTrue(target.exists())
            target.unlink()  # The external Ansible module performs the deletion.
            cleanup.module_action('record-deleted', plan, args)
            cleanup.module_action('record-failure', plan, args)
            result = json.loads(args.result.read_text())
            self.assertEqual(result['deleted'], plan['candidates'])
            self.assertEqual(result['failed'], ['module failed'])

    def test_symlink_is_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_text('keep')
            (root / 'link').symlink_to(root / 'real')
            with self.assertRaises(ValueError):
                cleanup.file_entry(root / 'link')
            self.assertEqual((root / 'real').read_text(), 'keep')

    def test_workspace_only_removes_successfully_archived_numbered_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('1', '2', 'unrelated'):
                (root / name).mkdir()
                (root / name / 'report').write_text('evidence')
            (root / '1' / '.archived').write_text(json.dumps({'owner': 'sohyeon', 'project': 'sohyeon-cicd', 'job': 'our-job'}))
            (root / 'unrelated' / '.archived').touch()
            (root / '2' / '.archived').write_text(json.dumps({'owner': 'sohyeon', 'project': 'sohyeon-cicd', 'job': 'other-job'}))
            clean_workspace(root, 'our-job')
            self.assertFalse((root / '1').exists())
            self.assertTrue((root / '2' / 'report').exists())
            self.assertTrue((root / 'unrelated' / 'report').exists())


if __name__ == '__main__':
    unittest.main()
