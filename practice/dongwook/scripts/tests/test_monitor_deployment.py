import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitor_deployment import baseline_from, INSTANCES, run, sample, summarize, target_from

OLD = {"version": "v1", "release": "v1-build1", "revision": "aaa", "slot": "primary"}
NEW = {"version": "git-bbb", "release": "git-bbb-2", "revision": "bbb", "slot": "green"}
EXPECTED = {"app_version": NEW["version"], "release_id": NEW["release"], "git_revision": NEW["revision"]}


def record(instance, phase="before", metadata=None, **overrides):
    return {"timestamp": "2026-10-09T00:00:00.000+00:00", "elapsed_s": 0,
            "latency_ms": 2, "phase": phase, "http_status": 200, "ok": True,
            "error": None, "instance": instance, "hostname": "container1",
            **(metadata or OLD), **overrides}


def samples():
    return ([record(instance) for instance in INSTANCES]
            + [record(INSTANCES[0], "during", NEW)]
            + [record(instance, "after", NEW) for instance in INSTANCES])


class SampleTest(unittest.TestCase):
    @patch("monitor_deployment.urllib.request.build_opener")
    def test_records_http_status_and_backend_metadata(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = json.dumps({"service": "dongwook-app", "status": "ok",
                                               **record(INSTANCES[0])}).encode()
        observed = sample("http://example/health", "during", 0, 2)
        self.assertTrue(observed["ok"])
        self.assertEqual(observed["slot"], "primary")
        self.assertEqual(observed["instance"], INSTANCES[0])
        self.assertEqual(observed["http_status"], 200)
        self.assertGreaterEqual(observed["latency_ms"], 0)

    @patch("monitor_deployment.urllib.request.build_opener")
    def test_http_error_and_timeout_are_counted_without_retry(self, opener):
        for error in [urllib.error.HTTPError("http://example/health", 502, "bad gateway", {}, None),
                      TimeoutError("timed out")]:
            opener.return_value.open.reset_mock()
            opener.return_value.open.side_effect = error
            observed = sample("http://example/health", "during", 0, 2)
            self.assertFalse(observed["ok"])
            self.assertTrue(observed["error"])
            opener.return_value.open.assert_called_once()

    @patch("monitor_deployment.urllib.request.build_opener")
    def test_http_200_with_invalid_body_is_failure(self, opener):
        response = opener.return_value.open.return_value.__enter__.return_value
        response.status = 200
        for body in [b"not JSON", b"[]", b'{"service":"dongwook-app","status":"ok"}']:
            response.read.return_value = body
            self.assertFalse(sample("http://example/health", "during", 0, 2)["ok"])


class AvailabilityTest(unittest.TestCase):
    def summary(self, records, returncode=0):
        return summarize(records, OLD, NEW, INSTANCES, returncode, True)

    def test_healthy_transition_records_both_versions_all_servers_and_success_rate(self):
        result = self.summary(samples())
        self.assertTrue(result["passed"])
        self.assertEqual(result["availability_pct"], 100)
        self.assertEqual(result["requests"], 7)
        self.assertEqual(result["by_phase"]["during"]["requests"], 1)
        self.assertEqual([item["release"] for item in result["transitions"]], [OLD["release"], NEW["release"]])
        self.assertEqual(len(result["traffic"]), 6)

    def test_single_failure_is_not_hidden_by_later_success(self):
        rows = samples()
        rows.insert(3, record(INSTANCES[0], "during", http_status=502, ok=False, error="HTTP 502"))
        result = self.summary(rows)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["availability_pct"], 87.5)
        self.assertEqual(result["by_phase"]["during"]["availability_pct"], 50)
        self.assertEqual(result["errors"], {"HTTP 502": 1})

    def test_unknown_backend_or_release_fails_even_with_http_200(self):
        for overrides in [{"instance": "foreign"}, {"release": "unexpected"}, {"revision": "wrong"}]:
            rows = samples()
            rows.insert(3, {**record(INSTANCES[0], "during", NEW), **overrides})
            result = self.summary(rows)
            self.assertFalse(result["passed"])
            self.assertEqual(result["http_200_pct"], 100)
            self.assertEqual(result["failures"], 1)

    def test_deployment_failure_cannot_pass_when_availability_is_100(self):
        rows = [record(instance) for instance in INSTANCES]
        rows += [record(instance, "after") for instance in INSTANCES]
        result = self.summary(rows, returncode=2)
        self.assertEqual(result["availability_pct"], 100)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["deployment_succeeded"])

    def test_requires_every_new_backend_and_final_target_responses(self):
        rows = [record(instance) for instance in INSTANCES]
        rows += [record(INSTANCES[0], "during", NEW), record(INSTANCES[0], "after")]
        result = self.summary(rows)
        self.assertFalse(result["checks"]["all_new_backends_observed"])
        self.assertFalse(result["checks"]["final_samples_on_target"])

    def test_baseline_rejects_missing_mixed_and_unhealthy_servers(self):
        valid = [record(instance) for instance in INSTANCES]
        self.assertEqual(baseline_from(valid, INSTANCES), OLD)
        for invalid in [valid[:2], [*valid[:2], record(INSTANCES[2], metadata=NEW)],
                        [*valid[:2], record(INSTANCES[2], ok=False)]]:
            with self.assertRaises(ValueError):
                baseline_from(invalid, INSTANCES)

    def test_target_slot_alternates_and_migrates_legacy(self):
        for old_slot, new_slot in [("primary", "green"), ("blue", "green"), ("green", "blue")]:
            self.assertEqual(target_from(EXPECTED, {**OLD, "slot": old_slot})["slot"], new_slot)


class MonitorRunnerTest(unittest.TestCase):
    def invoke(self, directory, rows, returncode=0):
        expected_path = Path(directory) / "deploy-vars.json"
        expected_path.write_text(json.dumps(EXPECTED))
        args = argparse.Namespace(expected_file=str(expected_path), output_dir=directory,
                                  base_url="http://example", timeout=2, interval=.2,
                                  baseline_samples=3, post_seconds=4, instances=list(INSTANCES),
                                  command=["ansible-playbook", "deploy.yml"])
        process = Mock(returncode=returncode)
        process.poll.return_value = returncode
        with patch("monitor_deployment.sample", side_effect=rows), \
             patch("monitor_deployment.time.sleep"), \
             patch("monitor_deployment.time.monotonic", side_effect=range(20)), \
             patch("monitor_deployment.subprocess.Popen", return_value=process) as popen, \
             contextlib.redirect_stdout(io.StringIO()):
            code = run(args)
        return code, popen, json.loads((Path(directory) / "summary.json").read_text())

    def test_wrapper_samples_all_phases_and_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            code, popen, result = self.invoke(directory, samples())
            self.assertEqual(code, 0)
            popen.assert_called_once_with(["ansible-playbook", "deploy.yml"], start_new_session=True)
            logs = (Path(directory) / "requests.jsonl").read_text().splitlines()
            self.assertEqual(len(logs), 7)
            self.assertEqual(set(result["by_phase"]), {"before", "during", "after"})

    def test_bad_baseline_prevents_deployment_and_still_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [record(INSTANCES[0])] * 3
            code, popen, result = self.invoke(directory, rows)
            self.assertEqual(code, 1)
            popen.assert_not_called()
            self.assertFalse(result["command_started"])
            self.assertIn("Baseline", result["run_error"])

    def test_nonzero_command_exit_fails_wrapper_even_if_samples_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            code, _, result = self.invoke(directory, samples(), returncode=2)
            self.assertEqual(code, 1)
            self.assertEqual(result["command_returncode"], 2)
            self.assertEqual(result["availability_pct"], 100)


if __name__ == "__main__":
    unittest.main()
