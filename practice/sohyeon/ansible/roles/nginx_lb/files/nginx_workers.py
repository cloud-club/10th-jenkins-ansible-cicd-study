"""파일 역할: reload 전후 Nginx 워커의 PID와 시작 시각을 비교해 기존 요청 처리 워커의 종료를 확인한다."""
import json
from pathlib import Path
import sys
import time


def workers(pid_file):
    """Nginx master의 워커들을 찾아 PID와 프로세스 시작 시각을 반환한다."""
    master = int(Path(pid_file).read_text().strip())
    result = {}
    for entry in Path('/proc').glob('[0-9]*'):
        try:
            stat = (entry / 'stat').read_text().split(') ', 1)[1].split()
            command = (entry / 'cmdline').read_bytes()
            if int(stat[1]) == master and b'nginx: worker process' in command:
                result[entry.name] = stat[19]  # /proc stat의 22번째 필드인 프로세스 시작 시각이다.
        except (FileNotFoundError, ProcessLookupError):
            continue
    return result


def wait_for_drain(pid_file, previous, timeout):
    """이전 워커가 모두 사라지고 새 워커가 확인될 때까지 기다리며 제한 시간을 넘기면 실패한다."""
    deadline = time.monotonic() + timeout
    while True:
        current = workers(pid_file)
        remaining = {pid: stamp for pid, stamp in previous.items()
                     if current.get(pid) == stamp}
        new = {pid: stamp for pid, stamp in current.items()
               if previous.get(pid) != stamp}
        if not remaining and new:
            print('drain complete: old workers exited; new workers running')
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f'Old workers still active or no new workers: {remaining}')
        time.sleep(1)


# 직접 실행한 경우에만 명령행 처리 또는 테스트 실행을 시작한다.
if __name__ == '__main__':
    action, pid_file = sys.argv[1:3]
    if action == 'snapshot':
        current = workers(pid_file)
        if not current:
            raise RuntimeError('No Nginx workers found; cannot prove drain')
        print(json.dumps(current))
    elif action == 'wait':
        wait_for_drain(pid_file, json.loads(sys.argv[3]), int(sys.argv[4]))
    else:
        raise ValueError(action)
