"""Jenkins Agent에서 Nginx 경유 응답 상태와 배포 버전을 검사한다."""

import argparse
import json
import urllib.request


def verify(base_url, version, release):
    for path, expected in (
        ("/health", {"status": "ok", "release": release}),
        ("/version", {"version": version, "release": release}),
    ):
        with urllib.request.urlopen(base_url + path, timeout=5) as response:
            body = json.load(response)
        if any(body.get(field) != value for field, value in expected.items()):
            raise RuntimeError(f"{base_url}{path}: expected {expected!r}, got {body!r}")
        print(f"PASS {base_url}{path} {body}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--release", required=True)
    args = parser.parse_args()
    verify("http://1.201.116.156:18003", args.version, args.release)
