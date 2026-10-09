"""Run without external packages: python3 -m unittest discover -s scripts/tests -v."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment_state import read_slots
from verify import verify


HOSTS = ["1.201.118.202", "1.201.118.10", "1.201.118.90"]
INSTANCES = ["dongwook_app1", "dongwook_app2", "dongwook_app3"]


def config(ports=(20003, 20003, 20003)):
    servers = "\n".join(f"    server {host}:{port};" for host, port in zip(HOSTS, ports))
    return f"upstream dongwook_backend {{\n{servers}\n}}\nserver {{ listen 18003; }}\n"


def response(instance="dongwook_app1", **overrides):
    return {"service": "dongwook-app", "status": "ok", "version": "git-abc", "release": "git-abc-7",
            "revision": "abc", "slot": "green", "instance": instance, **overrides}


class SlotDiscoveryTest(unittest.TestCase):
    def test_migrate_existing_blue_to_green(self):
        self.assertEqual(read_slots(config(), "dongwook_backend", HOSTS),
                         {"active_slot": "blue", "target_slot": "green"})

    def test_next_deployment_returns_to_blue(self):
        self.assertEqual(read_slots(config((21003,) * 3), "dongwook_backend", HOSTS),
                         {"active_slot": "green", "target_slot": "blue"})

    def test_reject_mixed_or_unknown_ports(self):
        for ports in [(20003, 21003, 20003), (8080,) * 3]:
            with self.subTest(ports=ports), self.assertRaises(ValueError):
                read_slots(config(ports), "dongwook_backend", HOSTS)

    def test_reject_missing_duplicate_or_foreign_backend(self):
        for modified in [config().replace(f"    server {HOSTS[2]}:20003;", ""),
                         config().replace(HOSTS[2], HOSTS[0]),
                         config().replace(HOSTS[2], "1.2.3.4")]:
            with self.subTest(config=modified), self.assertRaises(ValueError):
                read_slots(modified, "dongwook_backend", HOSTS)

    def test_ignore_comments_and_unrelated_upstreams(self):
        text = "# upstream dongwook_backend {server 1.2.3.4:21003;}\n"
        text += "upstream another_user { server 127.0.0.1:9090; }\n" + config()
        self.assertEqual(read_slots(text, "dongwook_backend", HOSTS)["active_slot"], "blue")

    def test_reject_ambiguous_missing_or_weighted_upstream(self):
        for text in [config() + config(), "", config().replace(":20003;", ":20003 weight=2;")]:
            with self.subTest(config=text), self.assertRaises(ValueError):
                read_slots(text, "dongwook_backend", HOSTS)


class TrafficVerificationTest(unittest.TestCase):
    def check(self, attempts=6):
        verify("http://nginx:18003", "git-abc", "git-abc-7", "abc", "green",
               INSTANCES, attempts=attempts, delay=0)

    @patch("verify.read_response")
    def test_requires_each_backend_on_both_endpoints(self, read):
        # A round robin worker may return different instances on health/version.
        read.side_effect = [response(INSTANCES[i % 3]) for i in range(6)]
        self.check()
        self.assertEqual(read.call_count, 6)
        self.assertEqual({call.args[0] for call in read.call_args_list},
                         {"http://nginx:18003/health", "http://nginx:18003/version"})

    @patch("verify.read_response", return_value=response())
    def test_one_healthy_backend_is_insufficient(self, read):
        with self.assertRaisesRegex(RuntimeError, "Not all backends observed"):
            self.check()

    @patch("verify.read_response")
    def test_rejects_wrong_release_slot_revision_instance_and_health(self, read):
        for override in [{"release": "old"}, {"slot": "blue"}, {"revision": "other"},
                         {"instance": "foreign"}, {"status": "down"}, {"version": "old"}]:
            read.return_value = response(**override)
            with self.subTest(override=override), self.assertRaises(RuntimeError):
                self.check(attempts=2)

    @patch("verify.read_response")
    def test_reload_transient_then_success(self, read):
        read.side_effect = [OSError("reload"), response(release="old")] + [
            response(instance) for instance in INSTANCES for _ in range(2)
        ]
        self.check()

    @patch("verify.read_response")
    def test_mixed_release_discards_prior_observations(self, read):
        read.side_effect = [response(INSTANCES[0]), response(INSTANCES[0]),
                            response(release="old"),
                            response(INSTANCES[1]), response(INSTANCES[1]),
                            response(INSTANCES[2]), response(INSTANCES[2])]
        with self.assertRaises(RuntimeError):
            self.check(attempts=4)

    @patch("verify.read_response", side_effect=OSError("unreachable"))
    def test_connection_failure_has_bounded_retries(self, read):
        with self.assertRaisesRegex(RuntimeError, "after 2 attempts"):
            self.check(attempts=2)
        self.assertEqual(read.call_count, 2)

    @patch("verify.read_response", return_value=["invalid json shape"])
    def test_rejects_non_object_json(self, read):
        with self.assertRaises(RuntimeError):
            self.check(attempts=1)

    @patch("verify.read_response")
    def test_legacy_primary_can_be_verified_after_rollback(self, read):
        read.side_effect = [response(instance, slot="primary") for instance in INSTANCES for _ in range(2)]
        verify("http://nginx:18003", "git-abc", "git-abc-7", "abc", "primary",
               INSTANCES, attempts=3, delay=0)


if __name__ == "__main__":
    unittest.main()
