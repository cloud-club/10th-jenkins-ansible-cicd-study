#!/bin/sh
set -eu

image=${1:?Usage: test-image.sh IMAGE EXPECTED_VERSION EXPECTED_GIT_SHA EXPECTED_RELEASE}
expected_version=${2:?Usage: test-image.sh IMAGE EXPECTED_VERSION EXPECTED_GIT_SHA EXPECTED_RELEASE}
expected_git_sha=${3:?Expected Git SHA is required}
expected_release=${4:?Expected release is required}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
container_id=''

# 테스트 성공 여부와 관계없이 이번 실행에서 만든 컨테이너만 정리한다.
cleanup() {
    result=$?
    trap - EXIT HUP INT TERM
    if [ -n "$container_id" ]; then
        if [ "$result" -ne 0 ]; then
            docker logs "$container_id" >&2 || true
        fi
        if ! docker rm --force "$container_id" >/dev/null; then
            echo "테스트 컨테이너 정리 실패: $container_id" >&2
            result=1
        fi
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM

# Ansible 실행 환경의 Python 3를 사용해 JSON 응답을 검사한다.
command -v python3 >/dev/null
container_id=$(docker run --detach \
    --publish 127.0.0.1::8080 \
    --env APP_INSTANCE=smoke-test \
    "$image")
port=$(docker port "$container_id" 8080/tcp | sed 's/.*://')

# 이미지에 저장된 메타데이터를 검증한다. 실행 시 덮어쓰지 않는다.
python3 "$script_dir/verify.py" \
    --url "http://127.0.0.1:$port" \
    --version "$expected_version" \
    --git-sha "$expected_git_sha" \
    --release "$expected_release" \
    --instances smoke-test
