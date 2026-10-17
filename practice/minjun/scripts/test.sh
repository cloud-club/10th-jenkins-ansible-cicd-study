#!/usr/bin/env bash
# 빌드한 이미지를 Agent에서 실행해 /health, /version을 검사한다.
# 공용 Agent라 호스트 포트를 publish하지 않는다 (다른 사람 테스트와 포트 충돌 방지).
# 대신 docker exec로 컨테이너 안에서 직접 호출한다.
set -euo pipefail

IMAGE="$1"            # 예: minjun-app:v1-a1b2c3d
EXPECT_VERSION="$2"   # 예: v1
NAME="minjun-test-${BUILD_NUMBER:-local}"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" "$IMAGE" >/dev/null

get() {
  docker exec "$NAME" python -c \
    "import urllib.request,sys; print(urllib.request.urlopen('http://127.0.0.1:8080$1', timeout=2).read().decode())"
}

echo "== /health"
ok=0
for i in $(seq 1 15); do
  if out=$(get /health 2>/dev/null); then echo "$out"; ok=1; break; fi
  sleep 1
done
if [ "$ok" -ne 1 ]; then
  echo "FAIL: /health did not respond"
  docker logs "$NAME" || true
  exit 1
fi

echo "== /version"
ver=$(get /version)
echo "$ver"
echo "$ver" | python3 -c '
import json, sys
d = json.load(sys.stdin)
want = sys.argv[1]
if d.get("version") != want:
    sys.exit("FAIL: version=%r, expected %r" % (d.get("version"), want))
print("PASS: version", want)
' "$EXPECT_VERSION"
