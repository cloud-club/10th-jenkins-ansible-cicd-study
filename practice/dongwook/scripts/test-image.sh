#!/bin/sh
# Run from practice/dongwook with IMAGE_TAG set.
set -eu
mkdir -p .artifacts
docker run -d --label owner=dongwook "$IMAGE_TAG" \
    > .artifacts/test-container
container_id=$(cat .artifacts/test-container)
trap 'docker rm -f "$container_id" >/dev/null' EXIT

# 앱 시작 전의 연결 거부는 예상되는 상태이므로 조용히 재시도한다.
set +x
ready=0
for attempt in $(seq 1 20); do
    if docker exec "$container_id" python -c '
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2)
' >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done

if [ "$ready" -ne 1 ]; then
    echo 'Application did not become ready within 20 attempts' >&2
    docker logs "$container_id" >&2
    exit 1
fi

set -x
docker exec "$container_id" python -c '
import json, os, urllib.request
for path in ("/health", "/version"):
    with urllib.request.urlopen("http://127.0.0.1:8080" + path, timeout=2) as response:
        body = json.load(response)
    assert body["version"] == os.environ["APP_VERSION"]
    assert body["release"] == os.environ["RELEASE_ID"]
    assert body["revision"] == os.environ["GIT_REVISION"]
    if path == "/health":
        assert body["status"] == "ok"
'
echo 'Image HTTP checks passed'
