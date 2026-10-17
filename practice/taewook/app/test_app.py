import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app


class AppTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        env = patch.dict(os.environ, {
            "APP_VERSION": "v1", "GIT_SHA": "abc123",
            "RELEASE_ID": "v1-abc123-1", "INSTANCE": "app1",
        })
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.client.close)

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_release_contract(self):
        self.assertEqual(self.client.get("/version").json(), {
            "service": "taewook-app", "version": "v1", "git_sha": "abc123",
            "release": "v1-abc123-1", "instance": "app1",
        })

    def test_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("버전: v1", response.text)
        self.assertIn("서버: app1", response.text)
        self.assertIn("상태: 정상", response.text)

    def test_missing(self):
        self.assertEqual(self.client.get("/missing").status_code, 404)
