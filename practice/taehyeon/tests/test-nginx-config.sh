#!/bin/bash
# 실제 파일 교체와 복구를 검증한다. nginx/systemctl만 테스트용 명령으로 대체한다.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
apply="$root/ansible/roles/nginx/files/apply-config.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/bin"
export PATH="$work/bin:$PATH"
export TEST_CURRENT="$work/current.conf" TEST_RELOADS="$work/reloads"
cat > "$work/bin/nginx" <<'MOCK'
#!/bin/bash
! grep -q BAD "$TEST_CURRENT" 2>/dev/null
MOCK
cat > "$work/bin/systemctl" <<'MOCK'
#!/bin/bash
echo reload >> "$TEST_RELOADS"
if [ -f "$TEST_CURRENT.fail-reload" ]; then
    rm "$TEST_CURRENT.fail-reload"
    exit 1
fi
MOCK
chmod +x "$work/bin/nginx" "$work/bin/systemctl"
run_apply() {
    bash "$apply" "$work/staged.conf" "$TEST_CURRENT" "$work/backup.conf" "$work/shared.lock"
}
reset() {
    rm -f "$TEST_CURRENT" "$work/backup.conf" "$TEST_RELOADS" "$TEST_CURRENT.fail-reload"
    echo OLD > "$TEST_CURRENT"
    echo NEW > "$work/staged.conf"
}
reset
run_apply | grep -q RELOADED
test "$(cat "$TEST_CURRENT")" = NEW
test "$(wc -l < "$TEST_RELOADS")" -eq 1
run_apply | grep -q UNCHANGED
test "$(wc -l < "$TEST_RELOADS")" -eq 1

reset
echo BAD > "$work/staged.conf"
if run_apply; then echo 'Expected invalid config to fail' >&2; exit 1; fi
test "$(cat "$TEST_CURRENT")" = OLD
test ! -e "$TEST_RELOADS"

reset
rm "$TEST_CURRENT"
echo BAD > "$work/staged.conf"
if run_apply; then echo 'Expected invalid first install to fail' >&2; exit 1; fi
test ! -e "$TEST_CURRENT"

reset
touch "$TEST_CURRENT.fail-reload"
if run_apply; then echo 'Expected failed reload to fail' >&2; exit 1; fi
test "$(cat "$TEST_CURRENT")" = OLD
test "$(wc -l < "$TEST_RELOADS")" -eq 2

reset
echo BAD > "$TEST_CURRENT"
if run_apply; then echo 'Expected invalid existing config to fail' >&2; exit 1; fi
test "$(cat "$TEST_CURRENT")" = BAD
test ! -e "$TEST_RELOADS"
echo 'PASS: apply, unchanged, syntax rollback, first-install rollback, reload rollback, existing-error protection'
