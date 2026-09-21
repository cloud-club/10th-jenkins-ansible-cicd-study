# Week 4 — Modules & Idempotency

## Ad-hoc Command

Ad-hoc command는 Playbook을 만들지 않고 Module 하나를 즉시 실행하는 방식이다. 연결 확인, 정보 조회, 일회성 작업에 적합하다.

```bash
ansible <pattern> -i <inventory> -m <module> -a '<arguments>'
```

```bash
ansible web -i inventory.ini -m ansible.builtin.ping
ansible web -i inventory.ini -m ansible.builtin.command -a "uptime"
ansible web -i inventory.ini -b -m ansible.builtin.package -a "name=nginx state=present"
```

- `web`: 대상 Host Pattern
- `-i`: Inventory
- `-m`: 사용할 Module
- `-a`: Module에 전달할 인자
- `-b`: `become`을 사용해 권한 상승

반복 실행하거나 Git으로 관리해야 하는 작업은 Playbook으로 작성한다.

---

## Module과 FQCN

Module은 Task에 정의된 실제 작업을 수행한다. 패키지, 파일, 사용자, 서비스 등 관리 대상별 Module이 제공된다.

```yaml
- name: Ensure Nginx is installed
  ansible.builtin.package:
    name: nginx
    state: present
```

`ansible.builtin.package`는 FQCN(Fully Qualified Collection Name)이다.

```text
ansible.builtin.package
   │       │       │
namespace collection module
```

FQCN은 Module의 출처를 명확하게 하고 이름 충돌을 피한다.

```bash
ansible-doc ansible.builtin.package
ansible-doc ansible.builtin.copy
```

관련 Module과 Plugin, Role 등을 묶어 배포하는 단위를 Collection이라고 한다.

---

## `command`와 `shell`

### `ansible.builtin.command`

대상에서 명령을 직접 실행한다. Shell을 거치지 않기 때문에 pipe, redirect, `&&`, 환경 변수 확장 같은 Shell 기능을 사용할 수 없다.

```yaml
- name: Check Nginx configuration
  ansible.builtin.command:
    cmd: nginx -t
  changed_when: false
```

### `ansible.builtin.shell`

`/bin/sh` 같은 Shell을 거쳐 실행한다. pipe나 redirect가 꼭 필요한 경우에 사용한다.

```yaml
- name: Find recent errors
  ansible.builtin.shell:
    cmd: journalctl -u nginx --since today | grep ERROR
  changed_when: false
```

단순 명령이라면 `shell`보다 `command`를 우선하고, 전용 Module이 있다면 명령 실행보다 전용 Module을 우선한다.

```text
전용 Module > command > shell
```

명령 실행 Module은 실행 자체만으로 최종 상태를 완전히 판단하기 어려운 경우가 많다. `creates`, `removes`, `changed_when` 등을 사용하거나 전용 Module로 바꾼다.

실습에서는 같은 pipe 표현을 두 Module로 실행해 차이를 확인했다.

```bash
ansible web -i ../02-inventory/inventory.local.yml \
  -m ansible.builtin.command -a 'echo hello | tr a-z A-Z'

ansible web -i ../02-inventory/inventory.local.yml \
  -m ansible.builtin.shell -a 'echo hello | tr a-z A-Z'
```

`command`는 `|`를 일반 문자열로 전달해 `hello | tr a-z A-Z`를 출력했다. `shell`은 pipe를 해석해 앞 명령의 출력을 `tr`의 입력으로 전달했고, 결과는 `HELLO`가 되었다.

---

## 주요 Module

### `copy`

Control node의 파일이나 직접 작성한 내용을 Managed node로 복사한다.

```yaml
- name: Copy static Nginx configuration
  ansible.builtin.copy:
    src: files/nginx.conf
    dest: /etc/nginx/nginx.conf
    owner: root
    group: root
    mode: "0644"
    backup: true
```

### `file`

파일과 디렉터리의 존재 여부, 권한, 소유자, symbolic link 등을 관리한다.

```yaml
- name: Ensure application directory exists
  ansible.builtin.file:
    path: /opt/myapp
    state: directory
    owner: app
    group: app
    mode: "0755"
```

### `template`

Jinja2 Template에 변수를 적용해 Managed node의 파일을 만든다.

```yaml
- name: Render Nginx virtual host
  ansible.builtin.template:
    src: templates/app.conf.j2
    dest: /etc/nginx/conf.d/app.conf
    mode: "0644"
```

### `package`

운영체제별 패키지 관리자의 공통 인터페이스다.

```yaml
- name: Ensure Nginx is installed
  ansible.builtin.package:
    name: nginx
    state: present
```

`state: latest`는 실행 시점에 따라 버전이 바뀔 수 있다. 예측 가능한 운영을 위해 `present`나 고정 버전을 사용하는 것을 고려한다.

### `service`와 `systemd_service`

`service`는 여러 init system에 대한 공통 인터페이스이고, `systemd_service`는 systemd 전용 기능을 제공한다.

```yaml
- name: Ensure Nginx is running and enabled
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: true
```

```yaml
- name: Reload systemd and restart application
  ansible.builtin.systemd_service:
    name: myapp
    state: restarted
    daemon_reload: true
```

`state: restarted`는 실행할 때마다 재시작한다. 설정 변경 시에만 재시작하려면 Handler를 사용한다.

실습에서는 먼저 Check Mode로 Nginx 설치 시 발생할 변경을 확인했다.

```bash
ansible web \
  -i ../02-inventory/inventory.local.yml \
  --become \
  -m ansible.builtin.package \
  -a "name=nginx state=present" \
  --check
```

`changed: true`와 설치 예정 패키지가 표시됐지만, Check Mode이므로 이 단계에서는 실제로 설치되지 않았다. 이후 `--check`를 빼고 실행해 Nginx를 설치하고 같은 명령을 다시 실행했을 때 `changed: false`가 되는 것을 확인했다.

마지막에는 설치, 서비스 상태, 실제 HTTP 응답을 하나의 Playbook으로 관리했다.

```yaml
- name: Manage and verify Nginx
  hosts: web
  become: true
  gather_facts: false

  tasks:
    - name: Ensure Nginx is installed
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Ensure Nginx is running and enabled
      ansible.builtin.systemd_service:
        name: nginx
        state: started
        enabled: true

    - name: Verify Nginx HTTP response
      ansible.builtin.uri:
        url: http://localhost
        status_code: 200
```

이미 원하는 상태가 만들어진 뒤 실행했기 때문에 세 Task 모두 `ok`였고, 최종 결과는 `ok=3 changed=0 failed=0`이었다. `package`는 설치 상태, `systemd_service`는 실행 및 자동 시작 상태, `uri`는 실제 HTTP 200 응답을 각각 검증한다.

---

## Idempotency

멱등성이란 같은 작업을 여러 번 실행해도 최종 상태가 동일하게 유지되는 성질이다.

```yaml
- name: Ensure Nginx is installed
  ansible.builtin.package:
    name: nginx
    state: present
```

```text
첫 실행: Nginx 없음 → 설치 → changed
재실행: Nginx 있음 → 변경 없음 → ok
```

Ansible의 대표적인 실행 상태는 다음과 같다.

| 상태 | 의미 |
|---|---|
| `ok` | 실행됐지만 변경할 필요가 없음 |
| `changed` | Managed node의 상태가 변경됨 |
| `failed` | Task 실행 실패 |
| `unreachable` | 연결 실패 |
| `skipped` | 조건에 따라 실행하지 않음 |

다음 `shell` 작업은 실행할 때마다 줄을 추가하므로 멱등적이지 않다.

```yaml
- name: Append text every time
  ansible.builtin.shell:
    cmd: echo "hello" >> /tmp/example.txt
```

전용 Module을 사용하면 원하는 상태를 선언할 수 있다.

```yaml
- name: Ensure line exists once
  ansible.builtin.lineinfile:
    path: /tmp/example.txt
    line: hello
    create: true
```

파일 관리 실습에서는 `/home/doyeon/ansible-lab` 디렉터리를 만들고 Control node의 `files/message.txt`를 Managed node로 복사했다. 첫 실행에서는 두 작업 모두 실제 변경이 발생해 `changed=2`였고, 같은 Playbook을 다시 실행했을 때는 이미 원하는 상태여서 `changed=0`이었다.

---

## `changed_when`

Module의 기본 판단과 실제 변경 여부가 다를 때 `changed_when`으로 상태를 정의한다.

조회 명령은 서버 상태를 바꾸지 않으므로 항상 `ok`로 처리할 수 있다.

```yaml
- name: Check application status
  ansible.builtin.command:
    cmd: systemctl is-active myapp
  register: app_status
  changed_when: false
```

출력에 따라 변경 여부를 판단할 수도 있다.

```yaml
- name: Run migration script
  ansible.builtin.command:
    cmd: /opt/myapp/migrate.sh
  register: migration
  changed_when: "'migrated' in migration.stdout"
```

`changed_when`은 실제 작업을 멱등적으로 만드는 기능이 아니라 Ansible이 보고하는 상태를 조정한다. 실행할 때마다 파일을 추가하는 명령에 `changed_when: false`를 붙여도 실제 부작용은 그대로 발생한다.

실습에서는 `cat`으로 파일을 읽은 결과를 `file_content`에 등록하고 `changed_when: false`를 지정했다. 조회 작업은 서버 상태를 바꾸지 않으므로 실행 결과가 `changed`가 아닌 `ok`로 표시됐다.

---

## `failed_when`

명령의 return code나 출력이 실제 성공 기준과 다를 때 실패 조건을 직접 정의한다.

```yaml
- name: Validate Nginx configuration
  ansible.builtin.command:
    cmd: nginx -t
  register: nginx_test
  changed_when: false
  failed_when: nginx_test.rc != 0
```

특정 문자열도 함께 확인할 수 있다.

```yaml
- name: Check application health
  ansible.builtin.command:
    cmd: curl --fail --silent http://localhost:8080/health
  register: health
  changed_when: false
  failed_when: health.rc != 0 or 'UP' not in health.stdout
```

목록 형태로 작성한 여러 조건은 기본적으로 모두 참일 때 실패한다. 위 예제처럼 연결 실패 또는 잘못된 응답 중 하나만 발생해도 실패해야 한다면 `or`를 명시한다.

실습에서는 파일 읽기 명령의 종료 코드와 파일 내용을 함께 검사했다.

```yaml
- name: Read managed file
  ansible.builtin.command:
    cmd: cat /home/doyeon/ansible-lab/message.txt
  register: file_check
  changed_when: false
  failed_when: >
    file_check.rc != 0 or
    expected_text not in file_check.stdout
```

기본값인 `expected_text: Ansible`로 실행했을 때는 `ok=2 failed=0`이었다. 다음과 같이 검사 문자열을 `Jenkins`로 덮어쓰자 명령 자체는 `rc=0`으로 성공했지만 문자열 조건을 만족하지 않아 `failed=1`이 되었다.

```bash
ansible-playbook \
  -i ../02-inventory/inventory.local.yml \
  validate-result.yml \
  --extra-vars '{"expected_text": "Jenkins"}'
```

이는 명령 실행의 성공과 작업의 업무상 성공 조건이 다를 수 있으며, `failed_when`으로 그 기준을 명시할 수 있음을 보여준다.

---

## 반복 실행으로 확인하기

Playbook은 한 번 성공하는 것보다 두 번째 실행 결과가 중요하다.

```bash
ansible-playbook -i inventory.ini site.yml
ansible-playbook -i inventory.ini site.yml
```

두 번째 실행에서 의도하지 않은 `changed`가 반복된다면 다음을 점검한다.

- 명령 실행 대신 전용 Module을 사용할 수 있는가
- 파일 내용이나 순서가 실행할 때마다 달라지는가
- `state: restarted`처럼 매번 변경되는 값을 사용했는가
- 현재 상태를 확인하지 않고 생성이나 추가 작업을 반복하는가
- `changed_when`이 실제 변경 기준과 일치하는가

---

## 참고 자료

- [Introduction to ad hoc commands](https://docs.ansible.com/projects/ansible/latest/command_guide/intro_adhoc.html)
- [Ansible Builtin Collection](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/index.html)
- [Command module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/command_module.html)
- [Shell module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/shell_module.html)
- [Defining changed and failure](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)
