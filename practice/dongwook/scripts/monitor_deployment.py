"""Run a deployment while recording uninterrupted HTTP samples and availability evidence."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request

FIELDS = ("version", "release", "revision", "instance", "slot", "hostname")
IDENTITY = ("version", "release", "revision", "slot")
INSTANCES = ("dongwook_app1", "dongwook_app2", "dongwook_app3")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sample(url, phase, origin, timeout):
    started = time.monotonic()
    record = {
        "timestamp": utc_now(),
        "elapsed_s": round(started - origin, 3),
        "phase": phase,
        "http_status": None,
        "ok": False,
        "error": None
    }
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(url, headers={"Connection": "close", "Cache-Control": "no-cache"})
        with opener.open(request, timeout=timeout) as response:
            record["http_status"] = response.status
            body = json.loads(response.read(65536))
        if not isinstance(body, dict):
            raise ValueError("Health response must be a JSON object")
        if body.get("service") != "dongwook-app" or body.get("status") != "ok":
            raise ValueError("Application health is not ok")
        if any(not isinstance(body.get(key), str) or not body[key] for key in FIELDS):
            raise ValueError("Missing or invalid release/instance metadata")
        if body["slot"] not in ("primary", "blue", "green"):
            raise ValueError("Unknown deployment slot")
        record.update({key: body[key] for key in FIELDS})
        record["ok"] = record["http_status"] == 200
        if not record["ok"]:
            record["error"] = f"Unexpected HTTP status {record['http_status']}"
    except urllib.error.HTTPError as error:
        record["http_status"] = error.code
        record["error"] = f"HTTP {error.code}"
    except (OSError, ValueError) as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
    return record


def identity(record):
    return tuple(record.get(key) for key in IDENTITY)


def baseline_from(records, instances):
    valid = [record for record in records if record["ok"]]
    if (not records or len(valid) != len(records)
            or {record["instance"] for record in valid} != set(instances)
            or len({identity(record) for record in valid}) != 1):
        raise ValueError("Baseline requires healthy, identical old releases from every expected server")
    return {key: valid[0][key] for key in IDENTITY}


def target_from(expected, baseline):
    return {"version": expected["app_version"], "release": expected["release_id"],
            "revision": expected["git_revision"],
            "slot": "blue" if baseline.get("slot") == "green" else "green"}


def summarize(records, baseline, target, instances, returncode, command_started, run_error=None):
    allowed = {identity(baseline), identity(target)}
    traffic = Counter()
    errors = Counter()
    phases = {}
    transitions = []
    success = http_success = 0
    target_instances = set()
    post = []
    for record in records:
        valid = (record["ok"] and identity(record) in allowed and record.get("instance") in instances)
        success += int(valid)
        http_success += int(record["http_status"] == 200)
        bucket = phases.setdefault(record["phase"], {"requests": 0, "successes": 0})
        bucket["requests"] += 1
        bucket["successes"] += int(valid)
        if not valid:
            errors[record.get("error") or "Unexpected release, slot or backend"] += 1
        if record["ok"]:
            traffic[tuple(record.get(key) for key in ("version", "release", "revision", "slot", "instance"))] += 1
            transition = {key: record.get(key) for key in IDENTITY}
            if not transitions or identity(transitions[-1]) != identity(record):
                transitions.append({"timestamp": record["timestamp"], **transition})
        if valid and identity(record) == identity(target):
            target_instances.add(record["instance"])
        if record["phase"] == "after":
            post.append(valid and identity(record) == identity(target))
    for bucket in phases.values():
        bucket["failures"] = bucket["requests"] - bucket["successes"]
        bucket["availability_pct"] = round(100 * bucket["successes"] / bucket["requests"], 3)
    checks = {
        "baseline_complete": bool(baseline),
        "deployment_succeeded": command_started and returncode == 0,
        "no_failed_samples": bool(records) and success == len(records),
        "release_changed": bool(baseline) and baseline.get("release") != target.get("release"),
        "all_new_backends_observed": target_instances == set(instances),
        "final_samples_on_target": bool(post) and all(post),
        "monitor_completed": run_error is None,
    }
    latencies = sorted(record["latency_ms"] for record in records)
    return {
        "passed": all(checks.values()), "checks": checks,
        "started_at": records[0]["timestamp"] if records else None, "finished_at": utc_now(),
        "command_started": command_started, "command_returncode": returncode, "run_error": run_error,
        "baseline": baseline, "target": target,
        "display_version_changed": bool(baseline) and baseline.get("version") != target.get("version"),
        "requests": len(records), "successes": success, "failures": len(records) - success,
        "availability_pct": round(100 * success / len(records), 3) if records else 0,
        "http_200_pct": round(100 * http_success / len(records), 3) if records else 0,
        "latency_p95_ms": latencies[math.ceil(len(latencies) * .95) - 1] if latencies else None,
        "latency_max_ms": max(latencies, default=None), "by_phase": phases,
        "errors": dict(errors), "transitions": transitions,
        "traffic": [dict(zip(("version", "release", "revision", "slot", "instance"), key), requests=count)
                    for key, count in sorted(traffic.items())],
    }


def run(args):
    expected = json.loads(Path(args.expected_file).read_text())
    for key in ("app_version", "release_id", "git_revision"):
        if not isinstance(expected.get(key), str) or not expected[key]:
            raise ValueError(f"Invalid deployment metadata: {key}")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records, baseline, target = [], {}, {}
    origin = time.monotonic()
    process = None
    returncode = None
    run_error = None
    url = args.base_url.rstrip("/") + "/health"
    with (output / "requests.jsonl").open("w") as log:
        def collect(phase):
            record = sample(url, phase, origin, args.timeout)
            records.append(record)
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()
            if not record["ok"]:
                print(f"HTTP sample failed: {record['error']}", flush=True)

        try:
            print(f"Monitoring {url} before deployment", flush=True)
            for _ in range(args.baseline_samples):
                collect("before")
                time.sleep(args.interval)
            baseline = baseline_from(records, args.instances)
            target = target_from(expected, baseline)
            if baseline["release"] == target["release"]:
                raise ValueError("Use a new release to demonstrate the version transition")
            print(f"Deploying {baseline['release']} ({baseline['slot']}) -> {target['release']} ({target['slot']})", flush=True)
            process = subprocess.Popen(args.command, start_new_session=True)
            while True:
                collect("during")
                returncode = process.poll()
                if returncode is not None:
                    break
                time.sleep(args.interval)
            deadline = time.monotonic() + args.post_seconds
            while time.monotonic() < deadline:
                collect("after")
                time.sleep(args.interval)
        except (OSError, ValueError, KeyboardInterrupt) as error:
            run_error = f"{type(error).__name__}: {error}"
        finally:
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
            if process is not None:
                returncode = process.returncode
            summary = summarize(records, baseline, target, args.instances, returncode, process is not None, run_error)
            summary["sampling"] = {
                "interval_s": args.interval,
                "request_timeout_s": args.timeout,
                "baseline_samples": args.baseline_samples,
                "post_seconds": args.post_seconds
            }
            (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0 if summary["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://1.201.116.156:18003")
    parser.add_argument("--expected-file", default=".artifacts/deploy-vars.json")
    parser.add_argument("--output-dir", default=".artifacts/availability")
    parser.add_argument("--instances", nargs="+", default=list(INSTANCES))
    parser.add_argument("--interval", type=float, default=.2)
    parser.add_argument("--timeout", type=float, default=2)
    parser.add_argument("--baseline-samples", type=int, default=15)
    parser.add_argument("--post-seconds", type=float, default=5)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command or min(args.interval, args.timeout, args.post_seconds) <= 0 or args.baseline_samples < len(args.instances):
        parser.error("Provide a deployment command after --, positive timings and enough baseline samples")

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
