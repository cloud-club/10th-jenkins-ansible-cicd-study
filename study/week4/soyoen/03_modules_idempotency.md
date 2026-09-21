# Modules & Idempotency

Module은 Ansible이 Managed Node에서 실제 작업을 수행하는 기능 단위다.

## 1. Module과 Ad-hoc Command

Playbook의 Task는 일반적으로 하나의 Module을 호출한다.

```yaml
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
```

자주 사용하는 Module:

| Module | 용도 |
|---|---|
| `command` | 명령 직접 실행 |
| `shell` | Shell을 통한 명령 실행 |
| `copy` | 파일 복사 |
| `file` | 파일·디렉터리 상태 관리 |
| `template` | Jinja2 설정 파일 생성 |
| `package` | 패키지 관리 |
| `service` | 서비스 상태 관리 |

Playbook 없이 한 번만 실행할 때는 Ad-hoc Command를 사용할 수 있다.

```bash
ansible web -i inventory.yml \
  -m ansible.builtin.command \
  -a "uptime"
```

공식문서: [Introduction to ad hoc commands](https://docs.ansible.com/projects/ansible/latest/command_guide/intro_adhoc.html)

---

## 2. FQCN과 command / shell

공식 문서에서는 Module 이름을 명확하게 나타내기 위해 FQCN 사용을 권장한다.

```text
package
        ↓
ansible.builtin.package
```

`command`와 `shell`의 차이:

```yaml
- name: Run command
  ansible.builtin.command: df -h
```

```yaml
- name: Use shell pipe
  ansible.builtin.shell: ps aux | grep nginx
```

| Module | 특징 |
|---|---|
| `command` | Shell을 거치지 않음 |
| `shell` | `\|`, `>`, `&&` 등 Shell 기능 사용 가능 |

가능하면 다음처럼 Shell 명령보다 목적에 맞는 Module을 사용하는 편이 좋다.

```yaml
ansible.builtin.package:
  name: nginx
  state: present
```

공식문서: [command](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/command_module.html), [shell](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/shell_module.html)

---

## 3. Idempotency

멱등성은 **같은 작업을 반복 실행해도 이미 원하는 상태라면 불필요하게 변경하지 않는 성질**이다.

```text
현재 상태 + 원하는 상태
        ↓
차이가 있는가?
```

```text
YES   → changed
NO    → ok
ERROR → failed
```

예:

```yaml
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
```

첫 실행:

```text
nginx 없음 → 설치 → changed
```

두 번째 실행:

```text
nginx 존재 → 변경 없음 → ok
```

이 때문에 Ansible은 단순 원격 명령 실행보다 **원하는 상태를 유지하는 구성 관리**에 적합하다.

---

## 4. changed_when / failed_when

`command`처럼 Ansible이 실제 변경 여부를 알기 어려운 작업은 상태 판단 기준을 직접 정의할 수 있다.

조회 명령을 항상 `ok`로 처리:

```yaml
- name: Check application
  ansible.builtin.command: /opt/app/status
  register: app_status
  changed_when: false
```

실패 조건 지정:

```yaml
- name: Health check
  ansible.builtin.command: /opt/app/health
  register: health
  failed_when: health.rc not in [0, 1]
```

`register`로 저장한 결과의 `rc`, `stdout`, `stderr` 등을 조건에 활용할 수 있다.

공식문서: [Error handling in playbooks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)

> **핵심:** Module은 **무엇을 실행할지** 정의하고, 멱등성은 반복 실행에서도 **원하는 상태만 유지하도록 불필요한 변경을 막는 개념**이다.
