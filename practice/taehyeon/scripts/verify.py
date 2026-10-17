#!/usr/bin/env python3
"""이미지 테스트와 Nginx 검증에서 동일한 응답 조건을 사용한다."""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--url', required=True)
parser.add_argument('--version', required=True)
parser.add_argument('--git-sha', required=True)
parser.add_argument('--release', required=True)
parser.add_argument('--instances', nargs='+', required=True)
args = parser.parse_args()
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
expected = {'version': args.version, 'gitSha': args.git_sha, 'release': args.release}


def get_json(path):
    with client.open(args.url.rstrip('/') + path, timeout=3) as response:
        body = json.load(response)
    if not isinstance(body, dict):
        raise ValueError(f'{path}: JSON 객체가 필요합니다: {body}')
    return body


def verify_metadata(path, body):
    for field, value in expected.items():
        if body.get(field) != value:
            sys.exit(f'{path} {field} 불일치: expected={value}, actual={body.get(field)}')
    if body.get('instance') not in args.instances:
        sys.exit(f'{path} instance 불일치: expected={args.instances}, actual={body.get("instance")}')


# 앱 시작을 기다린 뒤 메타데이터 불일치는 즉시 실패로 처리한다.
deadline = time.monotonic() + 90
while True:
    try:
        health = get_json('/health')
        if health.get('status') == 'UP':
            break
        error = f'예상하지 못한 health 응답: {health}'
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        error = str(exc)
    if time.monotonic() >= deadline:
        sys.exit(f'Health Check 실패: {error}')
    time.sleep(2)

verify_metadata('/health', health)
version = get_json('/version')
verify_metadata('/version', version)
print(f'응답 검증 통과: health={health}, version={version}')
