import unittest
from observe import classify, verdict


class ObserveTest(unittest.TestCase):
    def rows(self, candidates):
        return [{'slot': 'candidate' if i < candidates else 'stable', 'instance': f'app{i % 3 + 1}'} for i in range(300)]

    def test_expected_ratios(self):
        for target in (0, 10, 50, 100):
            self.assertTrue(verdict(self.rows(target*3), target)['passed'])

    def test_single_error_is_not_hidden(self):
        rows = self.rows(30)
        rows[100]['error'] = 'HTTP 503'
        self.assertFalse(verdict(rows, 10)['passed'])

    def test_wrong_ratio_or_missing_server(self):
        self.assertFalse(verdict(self.rows(150), 10)['passed'])
        rows = self.rows(30)
        for row in rows:
            row['instance'] = 'app1'
        self.assertFalse(verdict(rows, 10)['passed'])

    def test_wrong_release_rejected(self):
        with self.assertRaises(ValueError):
            classify({'status': 'ok', 'service': 'taewook-app', 'instance': 'app1', 'release': 'unknown'},
                     {'stable_release': 'old', 'stable_version': 'v1', 'stable_sha': 'a'},
                     {'release_id': 'new', 'app_version': 'v2', 'git_sha': 'b'})
