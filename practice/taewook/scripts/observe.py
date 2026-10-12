"""단계별 비율 검사와 배포 전체의 HTTP 관측."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import random
from pathlib import Path
import time
import urllib.request


def classify(data, state, deploy):
    if data.get('status') != 'ok' or data.get('service') != 'taewook-app':
        raise ValueError('비정상 health 응답')
    if data.get('instance') not in ('app1', 'app2', 'app3'):
        raise ValueError('알 수 없는 서버')
    if (data.get('release'), data.get('version'), data.get('git_sha')) == (deploy['release_id'], deploy['app_version'], deploy['git_sha']):
        return 'candidate'
    if (data.get('release'), data.get('version'), data.get('git_sha')) == (state['stable_release'], state['stable_version'], state['stable_sha']):
        return 'stable'
    raise ValueError('예상하지 않은 릴리스')


def verdict(rows, target):
    good = [row for row in rows if not row.get('error')]
    count = Counter(row['slot'] for row in good)
    ratio = count['candidate'] / len(good) * 100 if good else 0
    seen = {row['instance'] for row in good if row['slot'] == ('stable' if target == 0 else 'candidate')}
    passed = len(rows) >= 300 and len(good) == len(rows) and seen == {'app1', 'app2', 'app3'}
    passed = passed and (ratio == target if target in (0, 100) else abs(ratio - target) <= 5)
    return {'passed': passed, 'requests': len(rows), 'failures': len(rows)-len(good), 'candidate_pct': round(ratio, 2), 'target_pct': target, 'instances': sorted(seen)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--target', type=int, choices=[0, 10, 50, 100])
    parser.add_argument('--continuous', action='store_true')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--url', default='http://1.201.116.156:18004/health')
    args = parser.parse_args()
    build = Path('build')
    state = json.loads((build/'state.json').read_text())
    deploy = json.loads((build/'deploy-vars.json').read_text())
    rows = []
    start = time.monotonic()
    with (build/f'{args.name}.jsonl').open('w') as log:
        while True:
            if args.continuous:
                if (build/'monitor.stop').exists():
                    break
            elif time.monotonic()-start >= args.seconds and len(rows) >= 300:
                break
            tick = time.monotonic()
            row = {'time': datetime.now(timezone.utc).isoformat()}
            try:
                with urllib.request.urlopen(args.url, timeout=3) as response:
                    data = json.load(response)
                    row.update(http=response.status, slot=classify(data, state, deploy), **data)
            except Exception as error:
                row['error'] = str(error)
                # 뒤에 성공 응답이 와도 앞선 오류를 지우지 않는다.
                (build/'monitor.failed').touch()
            row['elapsed_ms'] = round((time.monotonic()-tick)*1000, 2)
            rows.append(row)
            log.write(json.dumps(row, ensure_ascii=False)+'\n'); log.flush()
            if row.get('error'):
                break
            # 관측 요청끼리 같은 순서에 고정되지 않도록 간격을 조금 바꾼다.
            time.sleep(random.uniform(0.1, 0.2))
    if args.continuous:
        summary = {'passed': bool(rows) and not any(row.get('error') for row in rows), 'requests': len(rows), 'failures': sum(bool(row.get('error')) for row in rows)}
    else:
        summary = verdict(rows, args.target)
    (build/f'{args.name}.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, ensure_ascii=False))
    if not summary['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
