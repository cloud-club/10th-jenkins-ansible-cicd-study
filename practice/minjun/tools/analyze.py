#!/usr/bin/env python3
"""measure.py가 만든 CSV를 요약한다 (표준 라이브러리만 사용).

    python3 tools/analyze.py results/1008-213000-A-drain.csv [results/...C-nodrain.csv]

출력
  1) 비교 표 (요청 수, 실패, 성공률, Nginx 재시도 횟수, 최대 응답 시간)
  2) 서버별 타임라인 — 1초 칸마다 그 서버가 어떤 버전으로 응답했는지
       1,2,3… : 그 버전으로 응답 (버전 문자열의 마지막 글자)
       ·      : 그 1초 동안 이 서버로 간 요청 없음 (drain 또는 다운)
       X      : 실패한 요청이 있었던 칸 (맨 아래 줄)
  3) 구간 분석 — 서버별 빠진 구간, 구·신버전이 섞여 응답한 구간
"""
import csv
import sys
from collections import Counter, defaultdict


def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["t"] = float(r["t"])
        r["code"] = int(r["code"])
        r["ms"] = float(r["ms"])
    return rows


def summary(path, rows):
    n = len(rows)
    fail = sum(1 for r in rows if r["code"] != 200)
    retried = sum(1 for r in rows if "," in r["upstream"])   # Nginx가 다른 서버로 다시 보낸 요청
    return {
        "file": path.rsplit("/", 1)[-1],
        "n": n,
        "fail": fail,
        "rate": 100.0 * (n - fail) / n if n else 0,
        "retried": retried,
        "max_ms": max((r["ms"] for r in rows), default=0),
        "dur": rows[-1]["t"] if rows else 0,
    }


def gaps(times, min_gap):
    """응답 시각 목록에서 min_gap초보다 긴 공백 구간을 찾는다."""
    out = []
    for a, b in zip(times, times[1:]):
        if b - a >= min_gap:
            out.append((a, b))
    return out


def analyze(path):
    rows = load(path)
    s = summary(path, rows)
    ok = [r for r in rows if r["code"] == 200]
    hosts = sorted({r["host"] for r in ok})
    versions = []
    for r in ok:
        if r["version"] not in versions:
            versions.append(r["version"])

    print("\n" + "=" * 70)
    print(s["file"])
    print("=" * 70)
    print("versions seen (in order): %s" % versions)

    # --- 타임라인 ------------------------------------------------------------
    end = int(rows[-1]["t"]) + 1 if rows else 0
    print("\ntimeline (1 char = 1s)")
    for h in hosts:
        line = []
        for sec in range(end):
            vs = {r["version"] for r in ok if r["host"] == h and int(r["t"]) == sec}
            line.append("*" if len(vs) > 1 else (vs.pop()[-1] if vs else "·"))
        print("  %-6s %s" % (h, "".join(line)))
    err = ["X" if any(r["code"] != 200 and int(r["t"]) == sec for r in rows) else " " for sec in range(end)]
    print("  %-6s %s" % ("fail", "".join(err)))
    ruler = "".join(str((i // 10) % 10) if i % 10 == 0 else " " for i in range(end))
    print("  %-6s %s  (tens of seconds)" % ("", ruler))

    # --- 구간 분석 ------------------------------------------------------------
    interval = (rows[-1]["t"] / max(len(rows) - 1, 1)) if rows else 0.2
    min_gap = 4.0   # 라운드로빈·Verify 잡음(1~3초)과 실제 drain(약 10초)을 구분하는 기준
    print("\nper-host windows with no traffic (≥ %.1fs):" % min_gap)
    for h in hosts:
        ts = [r["t"] for r in ok if r["host"] == h]
        g = gaps(ts, min_gap)
        desc = ", ".join("%.1f–%.1fs (%.1fs)" % (a, b, b - a) for a, b in g) or "none"
        first_new = next((r["t"] for r in ok if r["host"] == h and r["version"] == versions[-1]), None)
        print("  %-6s gaps: %s | first %s at %s" % (
            h, desc, versions[-1], "%.1fs" % first_new if first_new is not None else "-"))

    if len(versions) >= 2:
        old, new = versions[0], versions[-1]
        first_new = min(r["t"] for r in ok if r["version"] == new)
        last_old = max(r["t"] for r in ok if r["version"] == old)
        print("\nmixed window (%s and %s both answering): %.1fs → %.1fs = %.1fs" % (
            old, new, first_new, last_old, max(0.0, last_old - first_new)))

    fails = [r for r in rows if r["code"] != 200]
    if fails:
        print("\nfailures:")
        for r in fails[:20]:
            print("  t=%.2fs code=%d %s" % (r["t"], r["code"], r["error"]))
        reasons = Counter(r["error"].split(":")[0] for r in fails)
        print("  by reason: %s" % dict(reasons))
    retried = [r for r in rows if "," in r["upstream"]]
    if retried:
        print("\nnginx retried to another server (request still succeeded): %d" % len(retried))
        for r in retried[:5]:
            print("  t=%.2fs upstream=%s → %s" % (r["t"], r["upstream"], r["host"]))
    return s


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sums = [analyze(p) for p in sys.argv[1:]]
    print("\n| run | requests | failed | success | nginx retries | max ms | duration |")
    print("|---|---|---|---|---|---|---|")
    for s in sums:
        print("| %s | %d | %d | %.2f%% | %d | %.0f | %.0fs |" % (
            s["file"], s["n"], s["fail"], s["rate"], s["retried"], s["max_ms"], s["dur"]))


if __name__ == "__main__":
    main()
