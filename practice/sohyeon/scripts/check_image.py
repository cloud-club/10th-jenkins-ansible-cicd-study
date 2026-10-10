"""파일 역할: 배포 전 임시 컨테이너 안에서 준비 상태·실제 응답·버전·서버 ID를 검사한다."""
import json
import sys
import time
from urllib.request import urlopen

# Jenkins가 전달한 목표 릴리스와 버전을 읽고 준비 대기 기한을 정한다.
release, version = sys.argv[1:]
deadline = time.monotonic() + 60
# 초기 실행 지연을 허용하되 제한 시간 안에 모든 검사를 통과해야 한다.
while True:
    try:
        # 준비 상태와 실제 서비스 응답의 버전·릴리스·테스트 서버 ID를 확인한다.
        for path in ('/ready', '/'):
            with urlopen('http://127.0.0.1' + path, timeout=2) as response:
                data = json.load(response)
            assert data['ready'] is True
            assert data['release_id'] == release and data['version'] == version
            assert data['server_id'] == 'image-test'
        # 프로세스의 HTTP 처리 상태를 health 응답으로 확인한다.
        with urlopen('http://127.0.0.1/health', timeout=2) as response:
            assert response.read().decode().strip() == 'OK'
        # 별도 version 경로도 빌드한 버전과 일치하는지 검사한다.
        with urlopen('http://127.0.0.1/version', timeout=2) as response:
            assert response.read().decode().strip() == version
        print(f'Image check passed: {release}')
        break
    # 실패하면 기한 내에서 재시도하고 기한 초과 시 원래 오류를 반환한다.
    except Exception:
        if time.monotonic() >= deadline:
            raise
        time.sleep(1)
