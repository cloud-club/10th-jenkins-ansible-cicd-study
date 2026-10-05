#!/bin/sh
set -eu
container="taewook-test-${BUILD_NUMBER}"
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$container" --label owner=taewook --env INSTANCE=smoke "$IMAGE_REF"
# No shared Agent host port is opened. Retry startup, then fail on wrong content.
docker exec -i "$container" python - <<'PY'
import json, os, time, urllib.error, urllib.request
for attempt in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2) as response:
            data = json.load(response)
        assert data["status"] == "ok"
        break
    except (urllib.error.URLError, TimeoutError):
        if attempt == 29:
            raise
        time.sleep(1)
for path in ("/health", "/version"):
    with urllib.request.urlopen("http://127.0.0.1:8080" + path, timeout=2) as response:
        data = json.load(response)
    assert data["version"] == os.environ["APP_VERSION"], data
    assert data["git_sha"] == os.environ["GIT_SHA"], data
    assert data["release"] == os.environ["RELEASE_ID"], data
    assert data["instance"] == "smoke", data
print("PASS: tested deployment image /health and /version")
PY
