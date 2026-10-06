#!/bin/bash
set -euo pipefail
staged=${1:?staged config required}
current=${2:?current config required}
backup=${3:?backup path required}
lock=${4:?shared lock path required}

# 파일 적용부터 실패 복구까지 잠금을 유지한다. 다른 배포도 같은 경로를 사용해야 한다.
exec 9>"$lock"
flock -w 60 9
if [ -f "$current" ] && cmp -s "$staged" "$current"; then
    echo UNCHANGED
    exit 0
fi

# 이미 다른 설정에 오류가 있으면 본인 파일도 변경하지 않고 중단한다.
nginx -t
had_previous=false
if [ -f "$current" ]; then
    cp -p "$current" "$backup"
    had_previous=true
fi
restore() {
    if "$had_previous"; then
        cp -p "$backup" "$current"
    else
        rm -f "$current"
    fi
}

if ! install -m 0644 "$staged" "$current"; then
    restore
    echo 'Nginx 설정 적용 실패: 본인 설정 복구' >&2
    exit 1
fi
if ! nginx -t; then
    restore
    echo 'Nginx 문법 검사 실패: 본인 설정 복구' >&2
    exit 1
fi
if ! systemctl reload nginx; then
    restore
    if ! nginx -t || ! systemctl reload nginx; then
        echo 'Nginx 복구 후 reload도 실패: 관리자 확인 필요' >&2
    fi
    echo 'Nginx reload 실패: 본인 설정 복구' >&2
    exit 1
fi
echo RELOADED
