"""파일 역할: 배포 전·중·후에 LB로 HTTP 요청을 보내 처리 서버·버전·성공률을 기록하고 배포 결과와 함께 판정한다."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import urlopen


def utc():
    """요청 및 배포 로그에 사용할 현재 UTC 시각을 문자열로 반환한다."""
    return datetime.now(timezone.utc).isoformat()


def sample(url, timeout, servers, bootstrap=False):
    """LB에 한 번 요청해 상태 코드·처리 서버·릴리스를 검사하고 오류와 응답 시간을 기록한다."""
    row = {'started_at': utc(), 'status': None, 'error': None, 'valid': False}
    started = time.monotonic()
    try:
        with urlopen(url, timeout=timeout) as response:
            row['status'] = response.status
            row['upstream'] = response.headers.get('X-Upstream-Addr', '')
            raw = response.read().decode()
        try:
            data = json.loads(raw)
        except ValueError:
            if not bootstrap or raw.strip() != 'Sohyeon Jenkins + Ansible CI/CD':
                raise ValueError('Response is not the expected service JSON')
            matches = [name for name, address in servers.items() if address == row['upstream']]
            if len(matches) != 1:
                raise ValueError('Cannot identify the legacy server from X-Upstream-Addr')
            data = {'server_id': matches[0], 'version': 'legacy', 'release_id': 'legacy', 'ready': True}
        if not isinstance(data, dict):
            raise ValueError('Service JSON must be an object')
        for key in ('server_id', 'version', 'release_id'):
            if not isinstance(data.get(key), str) or not data[key]:
                raise ValueError(f'Missing {key}')
            row[key] = data[key]
        if data['server_id'] not in servers or data.get('ready') is not True:
            raise ValueError('Unknown server or service is not ready')
        if data['version'] != 'legacy' and data.get('service') != 'sohyeon-cicd-app':
            raise ValueError('Unexpected service')
        row['valid'] = row['status'] == 200
    except HTTPError as error:
        row['status'], row['error'] = error.code, f'HTTP {error.code}'
    except Exception as error:
        row['error'] = f'{type(error).__name__}: {error}'
    row['finished_at'] = utc()
    row['latency_ms'] = round((time.monotonic() - started) * 1000, 3)
    return row


def summarize(rows):
    """요청 원본에서 성공률·실패 수·지연 통계·서버별 릴리스·단계별 집계를 계산한다."""
    total = len(rows)
    latencies = sorted(r['latency_ms'] for r in rows)
    valid = sum(r['valid'] for r in rows)
    return {
        'attempts': total,
        'http_success_rate': round(100 * sum(r['status'] == 200 for r in rows) / total, 3) if total else 0,
        'valid_success_rate': round(100 * valid / total, 3) if total else 0,
        'failed_requests': total - valid,
        'errors': dict(Counter(r['error'] for r in rows if r['error'])),
        'latency_ms': {'mean': round(sum(latencies) / total, 3) if total else None,
                       'p95': latencies[math.ceil(total * .95) - 1] if total else None,
                       'max': max(latencies) if total else None},
        'missed_sampling_slots': sum(r.get('missed_slots', 0) for r in rows),
        'server_releases': dict(Counter(f"{r.get('server_id', '?')} / {r.get('release_id', '?')}" for r in rows)),
        'phases': {phase: {'attempts': len(selected),
                           'failed_requests': sum(not r['valid'] for r in selected)}
                   for phase in ('before', 'rolling', 'after')
                   if (selected := [r for r in rows if r['phase'] == phase])},
    }


def run(args):
    """배포 전 측정이 정상일 때 배포 명령을 실행하고 배포 후 측정까지 모아 최종 결과를 저장한다."""
    inventory = json.loads(Path(args.inventory).read_text())
    hosts = inventory['_meta']['hostvars']
    app_hosts = inventory['app_servers']['hosts']
    lb = inventory['load_balancer']['hosts'][0]
    servers = {name: f"{hosts[name]['ansible_host']}:{hosts[name].get('host_port', 20007)}" for name in app_hosts}
    url = args.url or f"http://{hosts[lb]['ansible_host']}:{hosts[lb].get('lb_port', 18007)}/"
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows, baseline = [], {}
    phase = 'before'
    finished = threading.Event()
    interrupted = threading.Event()
    collector_errors = []
    child = None
    command_rc = None
    complete = False
    error = None

    def stop(signum, _frame):
        """중단 신호를 기록하고 실행 중인 배포 명령의 프로세스 그룹에 종료 신호를 전달한다."""
        interrupted.set()
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)

    def collect():
        """별도 스레드에서 HTTP 요청을 반복하며 단계별 허용 릴리스를 검사하고 JSONL 원본을 저장한다."""
        try:
            with (output / 'availability.jsonl').open('w', buffering=1) as raw:
                while not finished.is_set():
                    start = time.monotonic()
                    current_phase = phase
                    row = sample(url, args.timeout, servers, args.bootstrap and current_phase != 'after')
                    row['phase'] = current_phase
                    if row['valid'] and current_phase != 'before':
                        server = row['server_id']
                        allowed = {args.release} if current_phase == 'after' and command_rc == 0 else {baseline.get(server), args.release}
                        if row['release_id'] not in allowed or (row['release_id'] == args.release and row['version'] != args.version):
                            row['valid'], row['error'] = False, 'Unexpected release/version for this server and phase'
                    elapsed = time.monotonic() - start
                    row['missed_slots'] = max(0, int(elapsed / args.interval) - 1)
                    rows.append(row)
                    raw.write(json.dumps(row) + '\n')
                    finished.wait(max(0, args.interval - elapsed))
        except Exception as exc:
            collector_errors.append(str(exc))
            interrupted.set()
            if child is not None and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    thread = threading.Thread(target=collect)
    thread.start()
    try:
        print(f'PROBE baseline: {url}, {args.before}s', flush=True)
        if interrupted.wait(args.before):
            raise RuntimeError('Measurement interrupted before deployment')
        initial = list(rows)
        if not initial or any(not r['valid'] for r in initial):
            raise RuntimeError('Baseline requests failed; deployment was not started')
        for row in initial:
            server = row['server_id']
            if server in baseline and baseline[server] != row['release_id']:
                raise RuntimeError('Starting release changed during baseline measurement')
            baseline[server] = row['release_id']
        if set(baseline) != set(servers):
            raise RuntimeError('Baseline did not observe all three servers')
        if not args.bootstrap and len(set(baseline.values())) != 1:
            raise RuntimeError('Baseline contains mixed releases')
        phase = 'rolling'
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            raise ValueError('A deployment command is required after --')
        print('PROBE rolling: starting deployment', flush=True)
        with (output / 'deployment.log').open('w', buffering=1) as log:
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, start_new_session=True)
            for line in child.stdout:
                stamped = f'{utc()} {line}'
                print(stamped, end='', flush=True)
                log.write(stamped)
            child.stdout.close()
            command_rc = child.wait()
        phase = 'after'
        print(f'PROBE after: exit={command_rc}, observing {args.after}s', flush=True)
        complete = not interrupted.wait(args.after)
    except Exception as exc:
        error = str(exc)
    finally:
        finished.set()
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        thread.join()
        summary = summarize(rows)
        final_hosts = {r.get('server_id') for r in rows if r['phase'] == 'after' and r['valid']}
        passed = (complete and command_rc == 0 and not error and not collector_errors
                  and summary['failed_requests'] == 0 and final_hosts == set(servers))
        summary.update(url=url, baseline=baseline, target_release=args.release,
                       command_exit_code=command_rc, observation_complete=complete,
                       interrupted=interrupted.is_set(), error=error,
                       collector_errors=collector_errors, passed=passed)
        (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2), flush=True)
    return 0 if passed else (command_rc if command_rc and command_rc > 0 else 1)


# 직접 실행한 경우에만 명령행 처리 또는 테스트 실행을 시작한다.
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, help='ansible-inventory --list output')
    parser.add_argument('--url', help='Optional external measurement URL')
    parser.add_argument('--release', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', default='.artifacts')
    parser.add_argument('--before', type=float, default=30)
    parser.add_argument('--after', type=float, default=60)
    parser.add_argument('--interval', type=float, default=.2)
    parser.add_argument('--timeout', type=float, default=2)
    parser.add_argument('--bootstrap', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if min(args.before, args.after, args.interval, args.timeout) <= 0:
        parser.error('Measurement durations must be positive')
    raise SystemExit(run(args))
