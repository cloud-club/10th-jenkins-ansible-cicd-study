import unittest
from main import payload


class ApiTest(unittest.TestCase):
    def test_health_and_version(self):
        self.assertEqual(payload("/health")["status"], "ok")
        self.assertIn("version", payload("/version"))
        self.assertIn("instance", payload("/version"))


if __name__ == "__main__":
    unittest.main()
