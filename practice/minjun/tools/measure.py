#!/usr/bin/env python3
"""배포 중 무중단 여부를 측정한다 (Mac에서 실행, 표준 라이브러리만 사용).

일정 간격으로 Nginx(18006)의 /version을 호출해 한 줄씩 CSV로 남긴다.
Jenkins 빌드를 누르기 전에 켜고, 빌드가 끝나면 Ctrl+C로 멈춘다.

    python3 tools/measure.py --label A-drain
    python3 tools/measure.py --label C-nodrain --interval 0.2

CSV 컬럼
    t           측정 시작 기준 경과 초
    wall        실제 시각 (Jenkins 로그와 맞춰 보기용)
    code        HTTP 상태코드. 연결 실패/타임아웃은 0
    version     응답 JSON의 version
    host        응답 JSON의 host (app1/app2/app3)
    upstream    X-Upstream 헤더 (Nginx가 실제로 붙은 주소. 재시도했다면 "a, b"처럼 여러 개)
    ms          응답 시간
    error       실패 사유
"""
import argparse
import csv
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime


def probe(url, timeout):
    start = time.perf_counter()
    code, version, host, upstream, error = 0, "", "", "", ""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            code = r.status
            upstream = r.headers.get("X-Upstream", "")
            body = json.loads(r.read().decode())
            version, host = body.get("version", ""), body.get("host", "")
    except urllib.error.HTTPError as e:          # 4xx/5xx — Nginx가 응답은 했다
        code = e.code
        upstream = e.headers.get("X-Upstream", "") if e.headers else ""
        error = "HTTP %d" % e.code
    except Exception as e:                       # 연결 거부, 타임아웃 등
        error = type(e).__name__ + ": " + str(e)[:80]
    ms = (time.perf_counter() - start) * 1000
    return code, version, host, upstream, round(ms, 1), error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://1.201.116.156:18006/version")
    ap.add_argument("--interval", type=float, default=0.2, help="요청 간격(초)")
    ap.add_argument("--timeout", type=float, default=3.0)
    ap.add_argument("--label", default="run", help="파일 이름에 붙일 이름 (예: A-drain)")
    ap.add_argument("--out", default="results")
    ap.add_argument("--duration", type=float, default=0, help="0이면 Ctrl+C까지")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "%s-%s.csv" % (datetime.now().strftime("%m%d-%H%M%S"), a.label))

    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))

    n = fail = 0
    t0 = time.perf_counter()
    last_line = ""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t", "wall", "code", "version", "host", "upstream", "ms", "error"])
        print("measuring %s every %.2fs → %s  (Ctrl+C to stop)" % (a.url, a.interval, path))
        next_at = t0
        while not stop["flag"]:
            t = time.perf_counter() - t0
            if a.duration and t >= a.duration:
                break
            code, version, host, upstream, ms, error = probe(a.url, a.timeout)
            w.writerow(["%.3f" % t, datetime.now().strftime("%H:%M:%S.%f")[:-3],
                        code, version, host, upstream, ms, error])
            f.flush()
            n += 1
            if code != 200:
                fail += 1
                print("\n  ! t=%.1fs code=%s %s" % (t, code, error))
            line = "\r  %5d req  fail=%d  last=%s@%s %sms   " % (n, fail, version or "-", host or "-", ms)
            if line != last_line:
                sys.stdout.write(line)
                sys.stdout.flush()
                last_line = line
            next_at += a.interval                 # 응답이 느려도 간격이 밀리지 않게
            time.sleep(max(0.0, next_at - time.perf_counter()))

    print("\n%d requests, %d failed → %s" % (n, fail, path))
    print("next: python3 tools/analyze.py %s" % path)


if __name__ == "__main__":
    main()
