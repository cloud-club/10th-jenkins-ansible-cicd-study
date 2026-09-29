# Modules & Idempotency

예제는 [Inventory & Variables](02-Inventory-and-variables.md)의 `inventories/dev/hosts.yml`과 변수 파일을 사용한다. YAML Task는 Playbook의 `tasks:` 아래에 작성하고, 시스템 변경 작업에는 `become: true`를 설정한다.

## 1. Ad-hoc Command: 모듈 하나 실행하기

Playbook 없이 하나의 작업을 실행할 때 `ansible` 명령을 사용한다. 연결 확인, 정보 조회, 간단한 상태 변경에 적합하다.

```bash
ansible <host-pattern> -i <inventory> -m <module> -a '<arguments>'
```

| 옵션 | 역할 |
| --- | --- |
| `web` 같은 Host Pattern | 실행 대상 호스트·그룹 |
| `-i` | Inventory 선택 |
| `-m` | 모듈 선택 |
| `-a` | 모듈에 전달할 인자 |
| `--become` | 권한 전환 |

```bash
ansible web -i inventories/dev/hosts.yml -m ansible.builtin.ping
ansible web -i inventories/dev/hosts.yml -m ansible.builtin.command -a 'uptime'
ansible web -i inventories/dev/hosts.yml -m ansible.builtin.package -a 'name=nginx state=present' --become
```

`-m`을 생략하면 기본적으로 `command` 모듈을 사용한다. 여러 작업의 순서와 조건을 저장해 반복 실행하려면 Playbook을 사용한다.

공식문서: [Introduction to ad hoc commands](https://docs.ansible.com/projects/ansible/latest/command_guide/intro_adhoc.html)

## 2. FQCN으로 모듈 명확히 지정하기

FQCN은 Fully Qualified Collection Name으로, `namespace.collection.module` 형식이다.

```text
ansible.builtin.copy
   │       │     └─ 모듈
   │       └─────── Collection
   └─────────────── Namespace
```

`ansible.builtin`은 `ansible-core`에 포함된 모듈과 Plugin을 제공한다. 짧은 이름 `copy`도 사용할 수 있지만, FQCN을 사용하면 다른 Collection의 같은 이름과 혼동하지 않고 공식문서를 찾기 쉽다.

```bash
ansible-doc ansible.builtin.copy
ansible-doc ansible.builtin.systemd_service
```

공식문서: [Ansible.Builtin](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/index.html), [copy module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/copy_module.html)

## 3. 원하는 상태에 맞는 모듈 선택

| 모듈 | 주된 용도 | 핵심 인자 |
| --- | --- | --- |
| `ansible.builtin.command` | Shell을 거치지 않고 명령 실행 | `cmd` 또는 `argv`, `creates` |
| `ansible.builtin.shell` | 파이프·리다이렉션 등 Shell 문법 실행 | `cmd`, `executable` |
| `ansible.builtin.copy` | 정적 파일 또는 내용을 대상에 복사 | `src` / `content`, `dest` |
| `ansible.builtin.file` | 디렉토리, 링크, 소유권, 권한 관리 | `path`, `state`, `mode` |
| `ansible.builtin.template` | Jinja2로 생성한 설정 파일 배포 | `src`, `dest` |
| `ansible.builtin.package` | OS에 맞는 패키지 관리자로 설치·제거 | `name`, `state` |
| `ansible.builtin.service` | 여러 서비스 관리 시스템의 공통 기능 | `name`, `state`, `enabled` |
| `ansible.builtin.systemd_service` | systemd 서비스와 Unit 관리 | `name`, `state`, `daemon_reload` |

### 3.1 `command`와 `shell`

`command`는 Shell을 실행하지 않으므로 `|`, `>`, `&&` 같은 문법을 처리하지 않는다. 단순 실행에는 `command`, Shell 기능이 필요할 때만 `shell`을 사용한다.

```yaml
- name: Read kernel information
  ansible.builtin.command:
    argv:
      - uname
      - -r
  changed_when: false

- name: Count lines using a shell pipeline
  ansible.builtin.shell:
    cmd: 'cat /etc/os-release | wc -l'
  changed_when: false
```

두 예제는 조회 작업이므로 변경으로 보고하지 않는다. 외부 입력을 Shell 명령에 넣을 때는 `quote` Filter 등으로 인자를 안전하게 처리해야 한다. 가능하면 전용 모듈이나 `command`의 `argv`로 인자를 분리한다.

공식문서: [command module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/command_module.html), [shell module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/shell_module.html)

### 3.2 `file`, `copy`, `template`

```yaml
- name: Ensure study directory exists
  ansible.builtin.file:
    path: /etc/ansible-study
    state: directory
    owner: root
    group: root
    mode: '0755'

- name: Write a static message
  ansible.builtin.copy:
    content: "Managed by Ansible\n"
    dest: /etc/ansible-study/message.txt
    owner: root
    group: root
    mode: '0644'
```

`file`은 경로의 상태와 속성을, `copy`는 파일 내용까지 관리한다. `file`의 `state: file`만으로 없는 파일을 생성하지는 않는다. 권한은 `'0644'`처럼 문자열로 작성한다.

`copy.src`는 기본적으로 Control Node의 파일이다. 서버마다 다른 값을 넣어야 한다면 `template`을 사용한다. 설정 파일 예제는 [Jinja2 & Safe Execution](05-jinja2-and-safe-execution.md)을 참고한다.

공식문서: [file module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/file_module.html), [copy module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/copy_module.html), [template module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/template_module.html)

### 3.3 `package`, `service`, `systemd_service`

```yaml
- name: Ensure nginx is installed
  ansible.builtin.package:
    name: nginx
    state: present

- name: Ensure nginx is running and enabled
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: true
```

`package`는 OS의 패키지 관리자를 선택해 호출하지만, 패키지 이름까지 배포판 간에 변환해 주지는 않는다. `present`는 설치된 상태를 요구하며, `latest`는 저장소의 최신 버전으로 갱신할 수 있다.

서비스의 `state: started`는 현재 실행 상태, `enabled: true`는 부팅 시 시작 여부다. `restarted`는 호출할 때마다 재시작하므로 일반 Task에서 반복하기보다 변경이 있을 때 실행하는 Handler에 배치할 수 있다.

systemd 고유 기능이 필요하면 다음처럼 사용한다. `ansible.builtin.systemd`는 `systemd_service`로 연결되는 기존 이름이다.

```yaml
- name: Reload systemd units and ensure nginx is running
  ansible.builtin.systemd_service:
    name: nginx
    daemon_reload: true
    state: started
    enabled: true
```

`daemon_reload`는 systemd가 Unit 정의를 다시 읽는 동작이다. Nginx의 설정 파일을 다시 읽게 하는 `state: reloaded`와 구분한다.

공식문서: [package module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/package_module.html), [service module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/service_module.html), [systemd_service module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/systemd_service_module.html)

## 4. 멱등성과 실행 결과

멱등성은 같은 작업을 반복해도 최종 상태가 같다는 성질이다. 예를 들어 `state: present`로 패키지 설치를 요청하면 처음에는 설치하고, 이미 설치되어 있으면 추가 변경 없이 끝낼 수 있다. 모든 모듈과 Playbook이 자동으로 멱등성을 갖는 것은 아니다.

| Task 결과 | 의미 |
| --- | --- |
| `ok` | 성공했으며 변경이 없다고 보고 |
| `changed` | 성공했으며 변경이 있다고 보고 |
| `failed` | 작업 실행 실패 |
| `unreachable` | 연결·인증 등의 문제로 대상에 접근 실패 |
| `skipped` | 조건 불충족 등으로 실행 생략 |

`command`와 `shell`은 명령의 의미를 모르기 때문에 실행하면 기본적으로 변경으로 보고한다. 조회 명령도 `changed`로 표시될 수 있으므로 실제 변경 여부와 구분해야 한다. 마지막 `PLAY RECAP`에서는 성공한 변경 Task도 `ok` 집계에 포함되므로 `ok`와 `changed`를 별개의 성공 건수로 더하지 않는다.

공식문서: [Playbook execution and idempotency](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_intro.html), [Common return values](https://docs.ansible.com/projects/ansible/latest/reference_appendices/common_return_values.html), [command module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/command_module.html)

명령을 한 번만 수행해야 한다면 실제 상태를 확인하는 실행 조건이 필요하다.

```yaml
# initialize.sh가 성공 시 /opt/study/.initialized를 생성한다고 가정
- name: Initialize the study application once
  ansible.builtin.command:
    cmd: /opt/study/initialize.sh
    creates: /opt/study/.initialized
```

`creates`에 지정한 파일이 이미 있으면 명령을 실행하지 않는다. 파일의 존재가 초기화 완료를 정확히 나타내도록 설계해야 한다.

## 5. `changed_when`과 `failed_when`

명령의 반환값을 `register`에 저장한 뒤 변경·실패 기준을 지정할 수 있다. `rc`, `stdout`, `stderr` 같은 반환 필드는 모듈별 문서에서 확인한다.

```yaml
# 두 파일이 대상에 존재한다고 가정
- name: Compare current and candidate configuration
  ansible.builtin.command:
    argv:
      - diff
      - /etc/ansible-study/current.conf
      - /etc/ansible-study/candidate.conf
  register: config_diff
  changed_when: false
  failed_when: config_diff.rc not in [0, 1]
```

`diff`의 반환 코드 0은 동일, 1은 차이 존재, 2 이상은 오류다. 비교 자체는 조회이므로 변경으로 보고하지 않고, 차이가 있다는 이유만으로 Task를 실패시키지도 않는다.

실제 변경을 수행하는 스크립트라면 `changed_when: result.rc == 2`처럼 그 스크립트가 정의한 반환 규약에 맞춰 변경 여부를 판단할 수 있다. 이때 `failed_when`도 성공·변경·오류 코드를 구분해야 한다.

`changed_when`은 결과 표시와 Handler 알림 조건을 바꾼다. 명령 실행을 생략하는 조건은 아니다. 변경 명령에 `changed_when: false`를 붙여도 멱등성이 생기지 않는다. 두 조건문에는 `{{ }}`를 쓰지 않으며, 여러 조건을 목록으로 쓰면 AND로 결합된다. OR가 필요하면 하나의 표현식에 `or`를 사용한다.

공식문서: [Error handling — Defining failure / changed](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)

이전: [Inventory & Variables](02-Inventory-and-variables.md) · 다음: [Playbook Development](04-playbook-development.md)
