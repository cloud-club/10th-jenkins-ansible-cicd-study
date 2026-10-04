import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


class DeploymentAPITest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_release_and_instance_are_independent(self):
        release = {
            "APP_VERSION": "v2",
            "RELEASE_ID": "v2-abcdef123456-7",
            "GIT_REVISION": "abcdef123456",
        }
        with patch.dict(os.environ, {**release, "INSTANCE_ID": "app1", "DEPLOYMENT_SLOT": "blue"}):
            blue = self.client.get("/version").json()
        with patch.dict(os.environ, {**release, "INSTANCE_ID": "app2", "DEPLOYMENT_SLOT": "green"}):
            green = self.client.get("/version").json()
        self.assertEqual(blue["version"], "v2")
        self.assertEqual(blue["release"], release["RELEASE_ID"])
        self.assertEqual(blue["revision"], release["GIT_REVISION"])
        self.assertEqual(blue["release"], green["release"])
        self.assertEqual((blue["instance"], blue["slot"]), ("app1", "blue"))
        self.assertEqual((green["instance"], green["slot"]), ("app2", "green"))
        self.assertTrue(blue["hostname"])

    def test_same_display_version_can_have_different_releases(self):
        with patch.dict(os.environ, {"APP_VERSION": "v1", "RELEASE_ID": "v1-abc-1"}):
            first = self.client.get("/version").json()
        with patch.dict(os.environ, {"APP_VERSION": "v1", "RELEASE_ID": "v1-abc-2"}):
            second = self.client.get("/version").json()
        self.assertEqual(first["version"], second["version"])
        self.assertNotEqual(first["release"], second["release"])

    def test_local_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/version")
        self.assertEqual(response.json()["version"], "local")
        self.assertEqual(response.json()["slot"], "primary")
        self.assertEqual(response.json()["instance"], response.json()["hostname"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_unknown_route(self):
        self.assertEqual(self.client.get("/missing").status_code, 404)


if __name__ == "__main__":
    unittest.main()
