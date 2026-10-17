"""Verify the release and every backend through Nginx, including after reload."""

import argparse
import json
import time
import urllib.error
import urllib.request


def read_response(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={"Connection": "close", "Cache-Control": "no-cache"})
    with opener.open(request, timeout=5) as response:
        return json.load(response)


def verify(base_url, version, release, revision=None, slot=None, instances=(), attempts=30, delay=1):
    expected = {"service": "dongwook-app", "version": version, "release": release}
    if revision is not None:
        expected["revision"] = revision
    if slot is not None:
        expected["slot"] = slot
    required = set(instances)
    seen = {"/health": set(), "/version": set()}
    last_error = "No responses"
    for attempt in range(attempts):
        try:
            for path in seen:
                body = read_response(base_url.rstrip("/") + path)
                fields = {**expected, **({"status": "ok"} if path == "/health" else {})}
                if not isinstance(body, dict) or any(body.get(key) != value for key, value in fields.items()):
                    raise ValueError(f"{path}: expected {fields!r}, got {body!r}")
                instance = body.get("instance")
                if required and instance not in required:
                    raise ValueError(f"Unexpected backend: {instance!r}")
                seen[path].add(instance)
            if all(required <= observed for observed in seen.values()):
                print(f"PASS {base_url}: release={release}, slot={slot}, backends={sorted(required)}")
                return
            last_error = f"Not all backends observed: {seen!r}"
        except (OSError, urllib.error.URLError, ValueError) as error:
            last_error = str(error)
            # Discard observations before a mixed release or a transient reload error.
            seen = {path: set() for path in seen}
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise RuntimeError(f"Nginx verification failed after {attempts} attempts: {last_error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://1.201.116.156:18003")
    parser.add_argument("--version", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--revision")
    parser.add_argument("--slot", choices=["blue", "green", "primary"])
    parser.add_argument("--instances", nargs="+", default=[])
    args = parser.parse_args()
    verify(args.base_url, args.version, args.release, args.revision, args.slot, args.instances)
