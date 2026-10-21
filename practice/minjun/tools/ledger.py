#!/usr/bin/env python3
"""서명된 배포 기록 (Deploy Ledger) — 3주차.

롤백은 "직전 정상 버전이 무엇이었나"라는 기록을 믿고 실행된다.
그 기록이 서버(LB)에만 있으면 서버 root 권한을 가진 사람이 기록을 바꿔서
"롤백"이라는 이름으로 원하는 이미지를 3대 전체에 배포하게 만들 수 있다.

그래서 기록의 각 줄에 HMAC-SHA256 서명을 붙이고, 앞 줄의 서명까지 넣어 계산한다(해시 체인).
  - 한 줄의 내용을 바꾸면       → 그 줄의 서명이 맞지 않는다
  - 중간 줄을 지우거나 순서를 바꾸면 → 다음 줄의 prev_mac이 맞지 않는다
서명 키는 Jenkins Credential(minjun-ledger-hmac)에만 있고 환경변수 LEDGER_KEY로만 받는다.
명령줄 인자로 받지 않는다(ps·로그에 남는다). 서버에는 키가 없다.

한계: 뒤쪽 줄을 통째로 잘라내는 것(truncation)은 체인만으로는 못 잡는다.
      → Jenkins Archive Artifacts에 매 빌드 기록 사본과 head(seq, mac)를 남겨 대조할 수 있게 한다.

사용법 (Jenkins sh에서, 표준 라이브러리만 사용)
  ledger.py verify  LEDGER
  ledger.py check-deployable LEDGER TAG              격리(QUARANTINE)된 태그면 exit 3
  ledger.py rollback-target  LEDGER OUT.json          현재 배포와 롤백 대상(서명 검증된 ID 포함)
  ledger.py append  LEDGER --event E --tag T [--ids IDS.json] [--build N] [--commit C]
                    [--from-tag F] [--approver A] [--reason R]
  ledger.py head    LEDGER                             마지막 seq와 mac (Archive용)

event: DEPLOY(정상 배포) / ROLLBACK(롤백으로 배포) / QUARANTINE(이 태그는 다시 배포 금지)
"""
import argparse
import datetime
import hashlib
import hmac
import json
import os
import sys

GENESIS = "0" * 64
EVENTS = ("DEPLOY", "ROLLBACK", "QUARANTINE")


class LedgerError(Exception):
    pass


def key():
    k = os.environ.get("LEDGER_KEY", "")
    if len(k) < 32:
        raise LedgerError("LEDGER_KEY is missing or too short (expected Jenkins credential minjun-ledger-hmac)")
    return k.encode()


def canonical(entry):
    body = {k: v for k, v in entry.items() if k != "mac"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign(entry):
    return hmac.new(key(), canonical(entry), hashlib.sha256).hexdigest()


def load(path):
    """파일을 읽고 체인 전체를 검증한다. 하나라도 틀리면 LedgerError."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    entries = []
    prev = GENESIS
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                raise LedgerError("line %d: not JSON" % lineno)
            if e.get("seq") != len(entries) + 1:
                raise LedgerError("line %d: seq %r, expected %d (line removed or reordered)"
                                  % (lineno, e.get("seq"), len(entries) + 1))
            if e.get("prev_mac") != prev:
                raise LedgerError("line %d (seq %s): prev_mac does not match previous line (chain broken)"
                                  % (lineno, e.get("seq")))
            if not hmac.compare_digest(e.get("mac", ""), sign(e)):
                raise LedgerError("line %d (seq %s, %s %s): signature mismatch (content changed)"
                                  % (lineno, e.get("seq"), e.get("event"), e.get("tag")))
            entries.append(e)
            prev = e["mac"]
    return entries


def quarantined(entries):
    return {e["tag"] for e in entries if e["event"] == "QUARANTINE"}


def deployments(entries):
    """실제로 서비스된 배포(DEPLOY, ROLLBACK)만 시간 순서대로."""
    return [e for e in entries if e["event"] in ("DEPLOY", "ROLLBACK")]


def rollback_target(entries):
    deps = deployments(entries)
    if not deps:
        raise LedgerError("no deployment recorded yet — nothing to roll back")
    current = deps[-1]
    bad = quarantined(entries) | {current["tag"]}
    for e in reversed(deps[:-1]):
        if e["tag"] not in bad:
            return current, e
    raise LedgerError("no earlier non-quarantined deployment to roll back to (current=%s)" % current["tag"])


def cmd_verify(a):
    entries = load(a.ledger)
    deps = deployments(entries)
    print("LEDGER_OK entries=%d current=%s quarantined=%s"
          % (len(entries), deps[-1]["tag"] if deps else "none", sorted(quarantined(entries))))
    for e in entries:
        print("  #%d %-10s %-14s build=%s %s%s" % (
            e["seq"], e["event"], e["tag"], e.get("build", "-"),
            ("from=%s " % e["from_tag"]) if e.get("from_tag") else "",
            ("approver=%s reason=%s" % (e["approver"], e["reason"])) if e.get("approver") else ""))


def cmd_check(a):
    entries = load(a.ledger)
    if a.tag in quarantined(entries):
        seq = max(e["seq"] for e in entries if e["event"] == "QUARANTINE" and e["tag"] == a.tag)
        print("QUARANTINED: %s was quarantined at ledger #%d — refusing to deploy it again" % (a.tag, seq))
        sys.exit(3)
    print("DEPLOYABLE: %s is not quarantined" % a.tag)


def cmd_target(a):
    entries = load(a.ledger)
    current, target = rollback_target(entries)
    out = {
        "current_tag": current["tag"],
        "target_tag": target["tag"],
        "target_seq": target["seq"],
        "target_version": target["tag"].split("-", 1)[0],
        "target_git_sha": target["tag"].split("-", 1)[1],
        "expected_ids": target["image_ids"],
    }
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print("ROLLBACK_TARGET %s (ledger #%d) ← current %s" % (target["tag"], target["seq"], current["tag"]))


def cmd_append(a):
    entries = load(a.ledger)          # 덧붙이기 전에 기존 체인부터 검증
    if a.event not in EVENTS:
        raise LedgerError("unknown event %s" % a.event)
    ids = {}
    if a.ids:
        with open(a.ids) as f:
            ids = json.load(f)
        if not ids or any(not str(v).startswith("sha256:") for v in ids.values()):
            raise LedgerError("image ids look wrong: %r" % ids)
    if a.event in ("DEPLOY", "ROLLBACK") and not ids:
        raise LedgerError("%s needs --ids" % a.event)
    e = {
        "seq": len(entries) + 1,
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": a.event,
        "tag": a.tag,
        "image_ids": ids,
        "build": a.build,
        "commit": a.commit,
        "prev_mac": entries[-1]["mac"] if entries else GENESIS,
    }
    for k in ("from_tag", "approver", "reason"):
        v = getattr(a, k)
        if v:
            e[k] = v
    e["mac"] = sign(e)
    with open(a.ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    print("LEDGER_APPEND #%d %s %s" % (e["seq"], e["event"], e["tag"]))


def cmd_head(a):
    entries = load(a.ledger)
    if entries:
        print("seq=%d mac=%s" % (entries[-1]["seq"], entries[-1]["mac"]))
    else:
        print("seq=0 mac=%s" % GENESIS)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("verify"); s.add_argument("ledger"); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("check-deployable"); s.add_argument("ledger"); s.add_argument("tag"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("rollback-target"); s.add_argument("ledger"); s.add_argument("out"); s.set_defaults(fn=cmd_target)
    s = sub.add_parser("head"); s.add_argument("ledger"); s.set_defaults(fn=cmd_head)
    s = sub.add_parser("append"); s.add_argument("ledger")
    s.add_argument("--event", required=True); s.add_argument("--tag", required=True)
    s.add_argument("--ids"); s.add_argument("--build", default="manual"); s.add_argument("--commit", default="")
    s.add_argument("--from-tag", dest="from_tag"); s.add_argument("--approver"); s.add_argument("--reason")
    s.set_defaults(fn=cmd_append)
    a = p.parse_args()
    try:
        a.fn(a)
    except LedgerError as e:
        print("LEDGER_REJECTED: %s" % e)
        sys.exit(2)


if __name__ == "__main__":
    main()
