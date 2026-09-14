# Inventory & Module

## 핵심 개념

- Ansible은 관리 대상 서버에 에이전트를 설치하지 않는다. SSH로 접속해서 파이썬 모듈을 전송하고, 실행한 뒤, 결과를 JSON으로 돌려받고 정리한다.
- 따라서 Ansible이 동작하려면 대상 서버에 SSH 접속 경로와 파이썬 인터프리터가 있어야 한다.
- Inventory는 "어떤 서버를 관리할 것인가"를, Module은 "그 서버에서 무엇을 할 것인가"를 정의한다.

## Inventory

- 관리 대상 호스트 목록을 정의하는 파일이다. INI 또는 YAML 형식을 쓴다.
- 호스트를 그룹으로 묶어 그룹 단위로 작업을 지정할 수 있다.
- 기본 경로는 `/etc/ansible/hosts`이지만, `-i` 옵션으로 직접 지정하는 것이 일반적이다.

### 실습에서 사용한 Inventory

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

### 기본 그룹

- `all` — 모든 호스트가 자동으로 속한다. `[all:vars]`로 전체 공통 변수를 지정할 수 있다.
- `ungrouped` — 어떤 그룹에도 속하지 않은 호스트

### 주요 연결 변수

- `ansible_host` — 실제 접속 주소
- `ansible_port` — SSH 포트
- `ansible_user` — 접속 계정
- `ansible_python_interpreter` — 대상 서버의 파이썬 경로. 명시하지 않으면 Ansible이 자동 탐색하고 경고를 남긴다
- `ansible_ssh_common_args` — SSH 클라이언트에 그대로 전달되는 옵션

## Module

- 실제 작업을 수행하는 단위다. Ansible이 대상 서버로 전송해 실행하는 파이썬 코드다.
- 대부분의 모듈은 **원하는 상태(state)를 선언**하면 현재 상태와 비교해 필요한 경우에만 변경을 수행한다.

### 실습에서 사용한 모듈

- `ping` — 연결과 파이썬 실행 가능 여부를 확인한다. 네트워크 ICMP ping이 아니라 모듈이 정상 실행되는지 보는 것이다.
- `apt` — 패키지 설치. `state: present`로 원하는 상태를 선언한다.
- `file` — 디렉터리·파일 생성, 권한 설정
- `copy` — 파일 배포. `content:`로 내용을 직접 지정할 수 있다.
- `command` — 임의 명령 실행. 셸 해석 없이 실행된다.
- `debug` — 변수 값이나 메시지를 출력한다.

### Ad-hoc 명령

Playbook 없이 모듈을 즉시 실행할 수 있다.

```bash
ansible all -i inventory.ini -m ping
```

```
node1 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

`"changed": false`가 이미 여기서 나온다. ping 모듈은 시스템 상태를 바꾸지 않기 때문이다. 이 필드가 Ansible 전체를 관통하는 개념인 멱등성의 신호다.

## 실습 중 발생한 문제 — SSH 호스트 키 충돌

실습 환경을 재구성하는 과정에서 다음 오류가 발생했다.

```
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
Offending ED25519 key in /Users/shanks/.ssh/known_hosts:3
Password authentication is disabled to avoid man-in-the-middle attacks.
```

### 원인

- 이전 컨테이너를 삭제하고 같은 포트(2221~2223)로 새 컨테이너를 띄웠다.
- 새 컨테이너는 새로운 호스트 키를 생성했는데, `~/.ssh/known_hosts`에는 이전 컨테이너의 키가 같은 주소로 남아 있었다.
- SSH는 "같은 주소인데 키가 바뀌었다"를 중간자 공격 가능성으로 판단하고 접속을 거부한다.

### `StrictHostKeyChecking=no`로 해결되지 않은 이유

- 이 옵션은 **처음 보는 호스트**를 자동으로 수락하게 만드는 설정이다.
- **이미 저장된 키와 충돌**하는 경우는 별개로 처리되며, 이 옵션으로 무시되지 않는다.
- 즉 "모르는 상대는 일단 믿는다"와 "알던 상대의 신원이 바뀌었다"는 SSH가 다르게 취급한다.

### 조치

```bash
ssh-keygen -R "[127.0.0.1]:2221"
```

또는 Inventory에 `UserKnownHostsFile=/dev/null`을 추가해 호스트 키를 아예 기록하지 않도록 했다.

### 여기서 확인한 것

- Ansible은 SSH 위에서 동작하는 도구이므로, SSH의 신뢰 모델이 그대로 Ansible의 전제가 된다.
- 실습 편의를 위해 `StrictHostKeyChecking=no`와 `UserKnownHostsFile=/dev/null`을 쓰면, 대상 서버의 신원 검증을 포기하는 것이다. 컨테이너를 자주 재생성하는 로컬 환경에서는 합리적이지만, 실제 서버 대상으로는 중간자 공격 방어를 스스로 끄는 설정이다.
- 운영 환경에서는 호스트 키를 사전에 배포하거나 `ssh-keyscan`으로 수집해 관리하는 방식을 쓴다.

## 실습 중 발생한 문제 — 대상 서버 파이썬 버전

초기에 사용한 `ubuntu-sshd:18.04` 이미지에서 다음 오류가 발생했다.

```
File "/root/.ansible/tmp/.../AnsiballZ_ping.py", line 3
    from __future__ import annotations
SyntaxError: future feature annotations is not defined
```

- `from __future__ import annotations`는 Python 3.7 이상에서만 유효한 구문이다.
- 해당 이미지의 파이썬이 3.6이라 최신 ansible-core가 전송한 모듈을 파싱하지 못했다.
- Ubuntu 22.04 기반 이미지로 교체해 해결했다.
- 이 오류는 "Ansible은 에이전트리스이지만 대상 서버에 파이썬 의존성이 있다"는 사실이 실제로 드러나는 지점이다.

## 참고 자료

- [Ansible 공식 문서 - How to build your inventory](https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html)
- [Ansible 공식 문서 - Introduction to ad hoc commands](https://docs.ansible.com/ansible/latest/command_guide/intro_adhoc.html)
- [Ansible 공식 문서 - Module Index](https://docs.ansible.com/ansible/latest/collections/index_module.html)
