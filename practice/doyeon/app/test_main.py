import unittest
from unittest.mock import patch
from main import payload


class ApiTest(unittest.TestCase):
    def test_health_and_version(self):
        with patch.dict("os.environ", {"FAILURE_SCENARIO": "none"}):
            self.assertEqual(payload("/health")["status"], "ok")
            self.assertIn("version", payload("/version"))
            self.assertIn("instance", payload("/version"))

    def test_intentional_health_failure(self):
        with patch.dict("os.environ", {"FAILURE_SCENARIO": "health"}):
            self.assertEqual(payload("/health")["status"], "fail")


if __name__ == "__main__":
    unittest.main()
