import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/observe.py'
OLD = {'version': '41', 'gitSha': 'oldsha', 'release': 'old-release'}
NEW = {'version': '42', 'gitSha': 'newsha', 'release': 'new-release'}
TEN = [{'host': 'app1', 'port': 20001, 'weight': 3, 'metadata': OLD},
       {'host': 'app2', 'port': 20001, 'weight': 3, 'metadata': OLD},
       {'host': 'app3', 'port': 20001, 'weight': 3, 'metadata': OLD},
       {'host': 'app1', 'port': 21001, 'weight': 1, 'metadata': NEW}]
FIFTY = [{'host': host, 'port': port, 'weight': 1, 'metadata': metadata}
         for metadata, port in ((OLD, 20001), (NEW, 21001)) for host in ('app1', 'app2', 'app3')]


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = None
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location('observe', SCRIPT)
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)

    def setUp(self):
        self.assertIsNotNone(self.mod, 'HTTP-only observer is missing')

    def sample(self, metadata, host='app1', path='/version', **changes):
        return dict({'ok': True, 'path': path, 'elapsed_ms': 2,
                     'body': dict(metadata, instance=host, status='UP')}, **changes)

    def test_response_must_match_one_complete_backend(self):
        self.mod.validate_response(dict(OLD, instance='app2'), TEN, '/version')
        for body in (dict(NEW, instance='app2', status='UP'),
                     dict(NEW, instance='app1', gitSha='oldsha', status='UP'),
                     dict(NEW, instance='app1', status='DOWN')):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.mod.validate_response(body, TEN, '/health')

    def test_all_http_responses_count_so_alternating_endpoints_do_not_alias(self):
        samples = [self.sample(target['metadata'], target['host'],
                               '/health' if i % 2 == 0 else '/version')
                   for i in range(120) for target in [FIFTY[i % 6]]]
        result = self.mod.check_samples(samples, FIFTY, 50, 50, 2000)
        self.assertEqual(result['candidate_percent'], 50)
        self.assertEqual(len(result['responses']), 6)

    def test_missing_backend_wrong_ratio_error_latency_and_short_observation_fail(self):
        valid = [self.sample(NEW if i % 10 == 9 else OLD,
                             'app1' if i % 10 == 9 else f'app{i % 3 + 1}') for i in range(100)]
        self.assertEqual(self.mod.check_samples(valid, TEN, 10, 100, 2000)['candidate_percent'], 10)
        for rows in ([], [self.sample(OLD)] * 100,
                     valid[:50] + [self.sample(NEW)] * 50,
                     valid + [self.sample(NEW, ok=False)],
                     valid + [self.sample(NEW, elapsed_ms=3000)], valid[:10]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                self.mod.check_samples(rows, TEN, 10, 100, 2000)

    def test_full_switch_requires_all_three_new_instances(self):
        with self.assertRaises(ValueError):
            self.mod.check_samples([self.sample(NEW)] * 100, FIFTY[3:], 100, 100, 2000)

    def test_availability_summary_preserves_failures_and_latency(self):
        rows = [self.sample(OLD), self.sample(NEW, path='/health'),
                self.sample(NEW, ok=False, error='HTTP 500'), self.sample(NEW, elapsed_ms=2500)]
        summary = self.mod.summarize(rows, 2000)
        self.assertEqual(summary['samples'], 4)
        self.assertEqual(summary['failures'], 2)
        self.assertEqual(summary['availability_percent'], 50)
        self.assertEqual(summary['max_response_ms'], 2500)


if __name__ == '__main__':
    unittest.main()
