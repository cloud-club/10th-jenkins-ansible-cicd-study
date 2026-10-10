"""Batched checks must still reject unhealthy or mismatched responses."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


PATH = Path(__file__).resolve().parents[1] / 'ansible/roles/verification/files/verify_application.py'
SPEC = importlib.util.spec_from_file_location('verify_application', PATH)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class BatchedVerificationTests(unittest.TestCase):
    def setUp(self):
        self.options = dict(url='http://app:20007', timeout=2, host='app1',
                            app='sohyeon-cicd-app', release='release1', version='v1', bootstrap=False)
        self.data = dict(ready=True, server_id='app1', service='sohyeon-cicd-app',
                         release_id='release1', git_revision='abc', version='v1')
        self.responses = {'/health': 'OK', '/': self.data, '/ready': self.data, '/version': 'v1'}

    def run_check(self, responses, options=None):
        def request(url, timeout):
            self.assertIsInstance(timeout, float)
            value = responses[url.removeprefix(self.options['url'])]
            if isinstance(value, Exception):
                raise value
            body = json.dumps(value) if isinstance(value, dict) else value
            response = io.BytesIO(body.encode())
            response.status = 200
            return response
        with patch.object(helper, 'urlopen', side_effect=request) as get:
            result = helper.verify(options or self.options)
        return result, get.call_count

    def test_all_endpoints_checked_and_responses_preserved(self):
        self.options['timeout'] = '2.0'  # Older Ansible may serialize this as text.
        result, calls = self.run_check(self.responses)
        self.assertEqual(calls, 4)
        self.assertEqual(result['service_response']['json'], self.data)
        self.assertEqual(result['version_response']['content'], 'v1')
        self.assertFalse(result['legacy_response'])

    def test_wrong_identity_release_service_and_readiness_are_rejected(self):
        for key, value in [('server_id', 'other'), ('release_id', 'old'),
                           ('service', 'other'), ('ready', False), ('git_revision', '')]:
            with self.subTest(key=key):
                data = dict(self.data, **{key: value})
                responses = dict(self.responses, **{'/': data, '/ready': data})
                with self.assertRaises(ValueError):
                    self.run_check(responses)

    def test_health_version_readiness_mismatch_and_http_errors_are_rejected(self):
        for path, value in [('/health', 'BAD'), ('/version', 'v2'),
                            ('/ready', dict(self.data, version='v2')),
                            ('/', HTTPError('http://app', 503, 'unavailable', {}, None))]:
            with self.subTest(path=path), self.assertRaises((ValueError, HTTPError)):
                self.run_check(dict(self.responses, **{path: value}))

    def test_legacy_requires_bootstrap_without_expected_release(self):
        responses = {'/health': 'OK', '/': 'Sohyeon Jenkins + Ansible CI/CD', '/version': 'v11'}
        options = dict(self.options, bootstrap=True, release='')
        result, calls = self.run_check(responses, options)
        self.assertTrue(result['legacy_response'])
        self.assertEqual(calls, 3)
        for changes in ({'bootstrap': False}, {'release': 'release1'}):
            with self.assertRaises(ValueError):
                self.run_check(responses, dict(options, **changes))
