#!/usr/bin/env python3
"""HTTP 관찰·집계 전용 도구. 배포 순서는 Jenkins, VM 작업은 Ansible이 담당한다."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys
import threading
import time
import urllib.request

FIELDS = ('version', 'gitSha', 'release')


def validate_response(body, backends, path):
    """서버와 버전 정보가 Ansible이 전달한 대상 중 하나와 정확히 일치해야 한다."""
    if not isinstance(body, dict) or (path == '/health' and body.get('status') != 'UP'):
        raise ValueError(f'{path}: unhealthy or invalid JSON response: {body}')
    if not any(body.get('instance') == target['host'] and
               all(body.get(field) == target['metadata'][field] for field in FIELDS)
               for target in backends):
        raise ValueError(f'{path}: unexpected instance or build metadata: {body}')


def request_sample(client, url, path, backends):
    start = time.monotonic()
    sample = {'time': datetime.now(timezone.utc).isoformat(), 'path': path}
    try:
        # reload 전 연결을 재사용하지 않도록 요청마다 연결을 닫는다.
        request = urllib.request.Request(url.rstrip('/') + path, headers={'Connection': 'close'})
        with client.open(request, timeout=3) as response:
            sample['http_status'] = response.status
            sample['body'] = json.load(response)
        validate_response(sample['body'], backends, path)
        sample['ok'] = True
    except (OSError, ValueError) as error:
        sample.update(ok=False, error=str(error))
    sample['elapsed_ms'] = round((time.monotonic() - start) * 1000, 2)
    return sample


def summarize(samples, max_response_ms):
    """실패한 응답과 지연 초과도 분모에 포함해 관측 구간의 성공률을 계산한다."""
    failures = sum(not row['ok'] or row['elapsed_ms'] > max_response_ms for row in samples)
    counts = Counter((row.get('body', {}).get('release'), row.get('body', {}).get('instance'))
                     for row in samples if isinstance(row.get('body'), dict))
    return {'samples': len(samples), 'failures': failures,
            'availability_percent': (len(samples) - failures) / len(samples) * 100 if samples else 0,
            'max_response_ms': max((row['elapsed_ms'] for row in samples), default=0),
            'responses': [{'release': release, 'instance': instance, 'count': count}
                          for (release, instance), count in counts.items()]}


def check_samples(samples, backends, percent, min_samples, max_response_ms):
    if not samples or summarize(samples, max_response_ms)['failures']:
        raise ValueError('observation contains HTTP/metadata errors or slow responses')
    versions = [row for row in samples if row['path'] == '/version']
    if len(versions) < min_samples:
        raise ValueError(f'insufficient /version samples: {len(versions)} < {min_samples}')
    for row in samples:
        validate_response(row['body'], backends, row['path'])
    expected = {(target['host'], target['metadata']['release']) for target in backends}
    # 두 API 모두 독립적으로 분배되므로 모든 HTTP 응답으로 비율과 대상 분포를 계산한다.
    seen = {(row['body']['instance'], row['body']['release']) for row in samples}
    if expected - seen:
        raise ValueError(f'backends received no observed traffic: {sorted(expected - seen)}')
    candidate = backends[-1]['metadata']['release']
    count = sum(row['body']['release'] == candidate for row in samples) if percent else 0
    actual = count / len(samples) * 100
    if abs(actual - percent) > (0 if percent in (0, 100) else 5):
        raise ValueError(f'candidate ratio {actual:.1f}% outside target {percent}% +/- 5 percentage points')
    return dict(summarize(samples, max_response_ms), version_samples=len(versions), candidate_percent=actual)


def save_summary(report_path, samples, max_response_ms, error=None, **extra):
    summary = dict(summarize(samples, max_response_ms), passed=error is None, **extra)
    if error is not None:
        summary['error'] = str(error)
    Path(report_path).with_suffix('.summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def observe(url, backends, percent, duration, min_samples, max_response_ms, report_path):
    """Jenkins가 지정한 한 단계의 HTTP 응답을 기록하고 검증한다."""
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    samples = []
    error = None
    result = {}
    deadline = time.monotonic() + duration
    try:
        with Path(report_path).open('w') as output:
            while time.monotonic() < deadline:
                for path in ('/health', '/version'):
                    row = request_sample(client, url, path, backends)
                    samples.append(row)
                    output.write(json.dumps(row, ensure_ascii=False) + '\n')
                    output.flush()
                    if not row['ok'] or row['elapsed_ms'] > max_response_ms:
                        raise ValueError(f'observation failed: {row}')
                time.sleep(0.1)
        result = check_samples(samples, backends, percent, min_samples, max_response_ms)
    except BaseException as caught:
        error = caught
        raise
    finally:
        save_summary(report_path, samples, max_response_ms, error,
                     **{key: result[key] for key in ('version_samples', 'candidate_percent') if key in result})
    print(f'PASS observation {percent}%: {json.dumps(result)}', flush=True)
    return result


def monitor(url, backends, report_path, stop_path, ready_path, max_response_ms,
            timeout=2700, cancelled=None):
    """Jenkins의 병렬 분기에서 요청을 계속 보내고 종료 파일이나 취소 신호를 기다린다."""
    cancelled = cancelled or threading.Event()
    samples = []
    error = None
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    try:
        with Path(report_path).open('w') as output:
            Path(ready_path).write_text('ready')
            while not Path(stop_path).exists() and not cancelled.is_set():
                if time.monotonic() >= deadline:
                    raise ValueError('monitor timed out waiting for Jenkins to finish deployment')
                for path in ('/health', '/version'):
                    row = request_sample(client, url, path, backends)
                    samples.append(row)
                    output.write(json.dumps(row, ensure_ascii=False) + '\n')
                    output.flush()
                    # 병렬 관찰 분기를 실패시켜 Jenkins failFast가 후속 배포를 중단하게 한다.
                    if not row['ok'] or row['elapsed_ms'] > max_response_ms:
                        raise ValueError(f'continuous monitor failed: {row}')
                cancelled.wait(0.1)
        if cancelled.is_set():
            raise ValueError('monitor cancelled')
        if not samples or summarize(samples, max_response_ms)['failures']:
            raise ValueError('continuous monitor contains failed or slow responses')
    except BaseException as caught:
        error = caught
        raise
    finally:
        save_summary(report_path, samples, max_response_ms, error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('stage', 'monitor'))
    parser.add_argument('--url', default='http://1.201.116.156:18001')
    parser.add_argument('--backends-file', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--max-response-ms', type=int, default=2000)
    parser.add_argument('--percent', type=int, choices=(0, 10, 50, 100), default=0)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--min-samples', type=int, default=100)
    parser.add_argument('--stop-file')
    parser.add_argument('--ready-file')
    parser.add_argument('--timeout', type=int, default=2700)
    args = parser.parse_args()
    if min(args.max_response_ms, args.seconds, args.min_samples, args.timeout) <= 0:
        parser.error('observation parameters must be positive')
    if args.mode == 'monitor' and not (args.stop_file and args.ready_file):
        parser.error('monitor requires --stop-file and --ready-file')
    targets = json.loads(Path(args.backends_file).read_text())
    if not isinstance(targets, list) or not targets:
        parser.error('backends file must contain a nonempty list')
    if args.mode == 'monitor':
        cancelled = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: cancelled.set())
        monitor(args.url, targets, args.report, args.stop_file, args.ready_file,
                args.max_response_ms, args.timeout, cancelled)
    else:
        observe(args.url, targets, args.percent, args.seconds, args.min_samples,
                args.max_response_ms, args.report)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL observation: {error}', file=sys.stderr)
        sys.exit(1)
