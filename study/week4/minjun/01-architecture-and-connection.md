# Architecture & Connection Management

## 핵심 구조

- Ansible은 관리 대상 서버에 에이전트를 설치하지 않는다. Control Node가 SSH로 접속해 Managed Node에 파이썬 모듈을 전송하고, 실행한 뒤, 결과를 JSON으로 돌려받고 임시 파일을 정리한다.
- 따라서 Ansible이 동작하려면 대상 서버에 **SSH 접속 경로**와 **파이썬 인터프리터**가 필요하다. "Agentless"는 상주 프로세스가 없다는 뜻이지 의존성이 없다는 뜻이 아니다.

| 구성 | 역할 |
|---|---|
| Control Node | Ansible이 설치된 곳. Playbook을 해석하고 모듈을 전송·실행 지시 |
| Managed Node | 관리 대상. SSH 서버와 파이썬만 있으면 됨 |

Control Node는 Linux/macOS만 지원한다(Windows는 WSL 경유). Managed Node는 제약이 덜하다.

## 실습 환경

Docker 컨테이너 3대(Ubuntu 22.04 + sshd)를 Managed Node로 구성했다.

| 그룹 | 호스트 | 포트 |
|---|---|---|
| webservers | node1, node2 | 2221, 2222 |
| dbservers | node3 | 2223 |

```ini
[webservers]
node1 ansible_host=127.0.0.1 ansible_port=2221
node2 ansible_host=127.0.0.1 ansible_port=2222

[dbservers]
node3 ansible_host=127.0.0.1 ansible_port=2223

[all:vars]
ansible_user=root
ansible_password=root
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
```

연결 확인:

```
$ ansible all -i inventory.ini -m ping
node1 | SUCCESS => { "changed": false, "ping": "pong" }
```

`"changed": false`가 여기서부터 나온다. ping 모듈은 상태를 바꾸지 않기 때문이다.

## SSH 인증 방식

| 방식 | 설정 | 비고 |
|---|---|---|
| 비밀번호 | `ansible_password` | 실습용. `sshpass` 필요 |
| SSH 키 | `ansible_ssh_private_key_file` | 운영 표준 |
| SSH Agent | 별도 설정 없음 | 키를 디스크에 두지 않아도 됨 |

운영에서는 키 인증을 쓴다. 비밀번호를 인벤토리에 평문으로 두면 그 파일이 SCM에 들어가는 순간 노출되기 때문이다(이 문제는 05번 문서에서 다룬다).

---

## become — 권한 상승

### 개념

접속 계정과 실행 계정을 분리하는 장치다. 일반 사용자로 SSH 접속한 뒤 필요한 작업만 root 권한으로 수행한다.

| 지시어 | 의미 |
|---|---|
| `become: yes` | 권한 상승 사용 |
| `become_user` | 상승할 대상 계정 (기본값 root) |
| `become_method` | 방식 (기본값 sudo, 그 외 su, doas 등) |
| `--become` / `-b` | 명령줄 옵션 |

Play, Task, 명령줄 어디서든 지정할 수 있고 좁은 범위가 우선한다.

### 실습

root 접속으로는 권한 상승이 보이지 않으므로, 먼저 Ansible로 일반 사용자를 만들었다.

```yaml
- name: deploy 사용자 생성
  ansible.builtin.user:
    name: deploy
    password: "{{ 'deploy' | password_hash('sha512') }}"
    shell: /bin/bash
    groups: sudo
    append: yes
```

그리고 `ansible_user=deploy`로 접속하는 인벤토리를 따로 만들어 네 가지를 비교했다.

```yaml
- name: 1. 현재 사용자 확인 (become 없음)
  ansible.builtin.command: whoami
  register: no_become
  changed_when: false

- name: 2. become 적용
  ansible.builtin.command: whoami
  become: yes
  register: with_become
  changed_when: false

- name: 3. root 전용 경로 쓰기 시도 (become 없음)
  ansible.builtin.copy:
    content: "test\n"
    dest: /etc/become-test.conf
  ignore_errors: yes

- name: 4. 같은 작업을 become으로
  ansible.builtin.copy:
    content: "test\n"
    dest: /etc/become-test.conf
  become: yes
```

### 결과

```
TASK [결과]
ok: [node1] => { "msg": "become 없이: deploy" }

TASK [결과]
ok: [node1] => { "msg": "become 적용: root" }

TASK [3. root 전용 경로 쓰기 시도 (become 없음)]
fatal: [node1]: FAILED! => {"changed": false, "msg": "Destination /etc not writable"}
...ignoring

TASK [4. 같은 작업을 become으로]
changed: [node1]

PLAY RECAP
node1 : ok=7  changed=1  failed=0  rescued=0  ignored=1
```

### 해석

- 같은 SSH 세션 안에서 실행 주체가 `deploy` → `root`로 바뀌었다.
- 3번과 4번은 **모듈도, 대상 경로도, 내용도 동일하다.** 차이는 `become: yes` 한 줄뿐인데 실패와 성공으로 갈렸다.
- 즉 무엇을 할 수 있는지는 코드가 아니라 **코드 밖의 권한 설정**이 결정한다.
- `ignore_errors: yes`로 처리한 실패는 `failed`가 아니라 **`ignored`** 카운터로 집계됐다. `block/rescue`가 만드는 `rescued`와는 다른 항목이다(04번 문서 참고).

### 운영 관점

- 접속 계정을 root로 두지 않는 것이 기본이다. root 직접 로그인을 막고 일반 계정 + sudo 조합을 쓰면, 누가 어떤 권한 작업을 했는지 sudo 로그에 남는다.
- `NOPASSWD:ALL`은 실습 편의를 위한 설정이다. 운영에서는 필요한 명령만 sudoers에 열거하는 편이 낫다.
- 비밀번호가 필요한 sudo라면 `--ask-become-pass`(`-K`)로 실행 시 입력받는다. 인벤토리에 적지 않는다.

---

## Connection Plugin

Ansible이 대상에 접속하는 방식은 플러그인으로 교체된다.

| 플러그인 | 용도 |
|---|---|
| `ssh` | 기본값. OpenSSH 클라이언트 사용 |
| `local` | Control Node 자기 자신 |
| `docker` | 실행 중인 컨테이너에 직접 |
| `kubectl` | 쿠버네티스 Pod |
| `winrm` | Windows |

`ansible_connection` 변수로 지정한다. 실습 환경은 컨테이너지만 SSH 서버를 띄웠기 때문에 기본 `ssh` 플러그인을 그대로 썼다.

## Bastion / Jump Host

### 왜 필요한가

운영 환경의 서버는 대개 사설 네트워크 안에 있고 인터넷에서 직접 접근할 수 없다. 이때 접근 가능한 서버 한 대(Bastion)를 경유해 내부 서버에 접속한다.

이번 실습은 모든 대상이 로컬 포트로 직접 접근 가능했으므로 Bastion 구성은 하지 않았다. 구성 방식만 정리한다.

### 설정 방법

`ansible_ssh_common_args`에 SSH의 ProxyJump 옵션을 넣는다.

```ini
[internal:vars]
ansible_ssh_common_args='-o ProxyJump=bastion-user@bastion.example.com'
```

또는 `~/.ssh/config`에 정의하고 Ansible은 그대로 사용하게 한다.

```
Host internal-*
    ProxyJump bastion.example.com
```

여러 단계를 거쳐야 하면 `ProxyJump`를 쉼표로 이어 쓴다.

### 보안 관점

Bastion은 편의 장치가 아니라 통제 장치다.

- 내부 서버로 향하는 접근 경로가 **한 곳으로 모인다.** 방화벽 규칙이 단순해지고, 접속 로그가 한 지점에 쌓인다.
- 감사 지점이 하나가 되므로 "누가 언제 어느 서버에 들어갔는가"를 추적할 수 있다.
- 반대로 Bastion이 뚫리면 내부 전체가 노출된다. 그래서 Bastion 자체는 최소 기능만 두고, MFA와 세션 기록을 붙이는 것이 일반적이다.

앞선 주차에서 확인한 것이 "누가 코드를 넣을 수 있는가"였다면, Bastion은 "누가 서버에 닿을 수 있는가"를 다룬다. 같은 층위의 통제다.

---

## 실습 중 발생한 문제

### 1. 대상 서버 파이썬 버전

초기에 `ubuntu-sshd:18.04` 이미지를 사용했을 때:

```
File "/root/.ansible/tmp/.../AnsiballZ_ping.py", line 3
    from __future__ import annotations
SyntaxError: future feature annotations is not defined
```

`from __future__ import annotations`는 Python 3.7 이상 문법이다. 해당 이미지의 파이썬이 3.6이라 전송된 모듈을 파싱하지 못했다. Ubuntu 22.04 기반 이미지로 교체해 해결했다.

**"에이전트리스이지만 대상에 파이썬 의존성이 있다"**는 사실이 실제로 드러난 지점이다.

### 2. SSH 호스트 키 충돌

컨테이너를 삭제하고 같은 포트로 새로 띄웠을 때:

```
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
Offending ED25519 key in /Users/shanks/.ssh/known_hosts:3
Password authentication is disabled to avoid man-in-the-middle attacks.
```

새 컨테이너가 새 호스트 키를 생성했는데 `known_hosts`에는 이전 키가 같은 주소로 남아 있었다.

**주목할 점은 `StrictHostKeyChecking=no`가 이미 설정되어 있었는데도 막혔다는 것이다.** 이 옵션은 *처음 보는 호스트*를 자동 수락하게 하는 설정이고, *이미 저장된 키와 충돌*하는 경우는 별개로 처리된다. SSH가 "모르는 상대"와 "신원이 바뀐 상대"를 다르게 취급한다는 뜻이다.

`ssh-keygen -R "[127.0.0.1]:2221"`로 항목을 제거하거나, `UserKnownHostsFile=/dev/null`을 추가해 호스트 키를 기록하지 않도록 했다.

후자는 **대상 서버의 신원 검증을 포기하는 설정**이다. 컨테이너를 자주 재생성하는 로컬 환경에서는 합리적이지만, 실제 서버 대상으로는 중간자 공격 방어를 스스로 끄는 것이다. 운영에서는 호스트 키를 사전 배포하거나 `ssh-keyscan`으로 수집해 관리한다.

## 참고 자료

- [Ansible 공식 문서 - Ansible concepts](https://docs.ansible.com/ansible/latest/getting_started/basic_concepts.html)
- [Ansible 공식 문서 - Understanding privilege escalation](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_privilege_escalation.html)
- [Ansible 공식 문서 - Connection plugins](https://docs.ansible.com/ansible/latest/plugins/connection.html)
