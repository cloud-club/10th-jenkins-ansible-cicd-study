#!/usr/bin/env python3
import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description="Record availability and version during a rolling deployment")
    parser.add_argument("--url", default="http://1.201.116.156:18005")
    parser.add_argument("--duration", type=int, default=180)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--output", default="rolling-results.csv")
    args = parser.parse_args()
    end = time.monotonic() + args.duration
    total = failures = 0
    seen = {}
    with open(args.output, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["time_utc", "http_status", "version", "release", "instance", "error"])
        while time.monotonic() < end:
            status, body, error = 0, {}, ""
            try:
                with urllib.request.urlopen(args.url + "/version", timeout=2) as response:
                    status = response.status
                    body = json.load(response)
            except (OSError, ValueError, urllib.error.HTTPError) as exc:
                error = str(exc)
            total += 1
            if status != 200:
                failures += 1
            key = (body.get("version", ""), body.get("instance", ""))
            if key != ("", ""):
                seen[key] = seen.get(key, 0) + 1
            writer.writerow([
                datetime.now(timezone.utc).isoformat(), status, body.get("version", ""),
                body.get("release", ""), body.get("instance", ""), error,
            ])
            file.flush()
            time.sleep(args.interval)
    print(f"requests={total} failures={failures} success_rate={(total - failures) / total:.2%}")
    print("responses_by_version_and_instance=", seen)
    print("csv=", args.output)


if __name__ == "__main__":
    main()
