import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import Handler


class HTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {
            "APP_VERSION": "v1", "GIT_SHA": "abc123",
            "RELEASE_ID": "v1-abc123-1", "INSTANCE": "app1",
        })
        cls.env.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()
        cls.env.stop()

    def read(self, path):
        with urllib.request.urlopen(self.url + path, timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "application/json")
            return json.load(response)

    def test_health(self):
        self.assertEqual(self.read("/health")["status"], "ok")

    def test_release_and_instance(self):
        self.assertEqual(self.read("/version"), {
            "service": "taewook-app", "version": "v1", "git_sha": "abc123",
            "release": "v1-abc123-1", "instance": "app1",
        })

    def test_unknown_endpoint(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.read("/missing")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
