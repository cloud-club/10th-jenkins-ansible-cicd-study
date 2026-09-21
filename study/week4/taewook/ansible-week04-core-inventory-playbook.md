# 4주차: Ansible Core, Inventory & Playbook

> **목표**: Ansible의 기본 구조와 실행 방식을 이해하고, Inventory와 Playbook을 활용해 여러 서버를 안정적으로 제어할 수 있는 기반을 구축한다.
>
> 기준 환경: Ansible Core 2.21, Control Node `ansible-control`, Managed Node `node1`·`node2`

---

## 0. 전체 흐름 먼저 보기

Ansible은 Control Node에서 Inventory와 Playbook을 읽고, 대상 호스트에 연결한 뒤 모듈을 실행하여 원하는 상태를 만든다.

```text
Inventory로 대상 결정
    → 변수 병합
    → SSH 연결
    → 필요한 모듈 전송·실행
    → 결과(JSON) 수집
    → 다음 Task 또는 Handler 실행
```

핵심은 단순히 원격 명령을 보내는 것이 아니다. Playbook에 **원하는 상태(desired state)** 를 선언하고, 현재 상태와 다를 때만 변경하는 것이 Ansible의 기본 운영 방식이다.

---

# 1. Architecture & Connection Management

## 1.1 Control Node와 Managed Node

### Control Node

Ansible이 설치되고 명령이 실행되는 관리 서버다.

- Inventory와 Playbook을 보관한다.
- 대상 호스트와 연결하고 작업을 지시한다.
- Linux, macOS 등 Python이 설치된 Unix 계열 환경을 사용한다.
- 일반 Windows는 네이티브 Control Node로 지원하지 않으며 WSL을 사용할 수 있다.

현재 실습 환경에서는 `ansible-control`이 Control Node다.

### Managed Node

Ansible이 설정을 변경하거나 상태를 조회하는 대상 서버다.

- 일반적인 Linux 관리에서는 SSH 접속이 가능해야 한다.
- Ansible 자체를 설치할 필요는 없다.
- 대부분의 POSIX 모듈을 실행하려면 Python이 필요하다.
- `raw` 모듈이나 일부 네트워크 장비용 모듈처럼 Python이 필요하지 않은 예외도 있다.

현재 실습 환경에서는 `node1`, `node2`가 Managed Node다.

## 1.2 Agentless Architecture

Ansible은 Managed Node에 상주하는 전용 Agent나 Daemon을 설치하지 않는다. 기존 SSH와 사용자 계정을 이용해 필요할 때만 접속한다.

### 일반적인 실행 과정

1. Control Node가 Inventory에서 대상 호스트와 변수를 읽는다.
2. Playbook의 각 Task에 사용할 모듈을 결정한다.
3. Connection Plugin을 통해 대상 호스트에 연결한다.
4. 필요한 모듈 코드와 인자를 대상 호스트에서 실행한다.
5. 실행 결과를 받아 `ok`, `changed`, `failed` 등으로 표시한다.
6. 임시 실행 파일을 정리하고 다음 Task로 진행한다.

### 장점

- Managed Node에 별도 Agent를 배포하고 업데이트할 필요가 없다.
- SSH가 이미 열려 있다면 도입이 쉽다.
- 중앙에서 여러 서버를 같은 방식으로 관리할 수 있다.

### 주의점

- Agent가 없다는 것이 사전 준비가 전혀 필요 없다는 뜻은 아니다.
- SSH 계정, 인증 키, Python, `sudo` 권한 등은 준비해야 한다.
- 많은 호스트를 동시에 관리하면 Control Node의 CPU, 네트워크, SSH 연결 수가 병목이 될 수 있다.

## 1.3 SSH 기반 연결과 SSH Key 인증

기본 Linux 연결 방식은 `ansible.builtin.ssh` Connection Plugin이다.

### 키 생성

```bash
ssh-keygen -t ed25519 -C "ansible-control"
```

### 공개 키 등록

```bash
ssh-copy-id ansible@172.30.1.151
ssh-copy-id ansible@172.30.1.152
```

### Ansible 실행 전 직접 확인

```bash
ssh ansible@172.30.1.151
ssh ansible@172.30.1.152
```

직접 SSH 접속이 되지 않으면 Ansible 문제를 보기 전에 SSH 설정부터 해결해야 한다.

### Inventory의 연결 변수

```ini
[web]
node1 ansible_host=172.30.1.151
node2 ansible_host=172.30.1.152

[all:vars]
ansible_user=ansible
ansible_python_interpreter=/usr/bin/python3
```

주요 연결 변수는 다음과 같다.

| 변수 | 의미 |
|---|---|
| `ansible_host` | 실제 접속 IP 또는 DNS 이름 |
| `ansible_user` | SSH 로그인 사용자 |
| `ansible_port` | SSH 포트, 기본값 22 |
| `ansible_connection` | 사용할 Connection Plugin |
| `ansible_ssh_private_key_file` | 사용할 개인 키 경로 |
| `ansible_python_interpreter` | 원격에서 사용할 Python 경로 |
| `ansible_ssh_common_args` | `ProxyJump` 등 공통 SSH 옵션 |

`inventory_hostname`은 Inventory 안의 이름인 `node1`이고, `ansible_host`는 실제 접속 주소인 `172.30.1.151`이다. 둘은 같은 개념이 아니다.

개인 키에 Passphrase가 있다면 키 파일을 평문처럼 다루지 말고 `ssh-agent`에 등록하는 방식이 적절하다.

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

## 1.4 `become`과 `become_user`

SSH 로그인 사용자와 실제 작업을 수행할 사용자를 분리할 때 권한 상승을 사용한다.

```yaml
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
  become: true
```

- `become: true`: 권한 상승을 활성화한다.
- `become_user: root`: 전환할 사용자다. 기본값은 `root`다.
- `become_method: sudo`: 권한 상승 방식이다. Linux 기본 사용 방식은 보통 `sudo`다.

다른 서비스 계정으로 실행할 수도 있다.

```yaml
- name: Run maintenance as application user
  ansible.builtin.command: /opt/myapp/bin/maintenance
  become: true
  become_user: myapp
```

`become_user`만 지정해도 `become`이 자동으로 켜지지는 않는다. 두 설정은 별개다.

sudo 비밀번호가 필요한 환경에서는 다음과 같이 실행한다.

```bash
ansible-playbook -i inventory.ini site.yml --ask-become-pass
# 축약형
ansible-playbook -i inventory.ini site.yml -K
```

자동화 환경에서는 비밀번호를 Inventory에 평문으로 넣지 않는다. 제한된 명령에 대해 비밀번호 없는 sudo를 구성하거나, Ansible Vault 또는 외부 Secret 관리 도구를 사용한다.

## 1.5 Connection Plugin

Connection Plugin은 Control Node가 Managed Node에 **어떤 방식으로 연결할지** 결정한다.

| Plugin | 용도 |
|---|---|
| `ansible.builtin.ssh` | 일반적인 Linux/Unix SSH 연결 |
| `ansible.builtin.local` | Control Node 자기 자신에서 실행 |
| `ansible.builtin.paramiko_ssh` | Python Paramiko 기반 SSH 연결 |
| `ansible.builtin.winrm` / `psrp` | Windows 원격 관리 |
| `ansible.netcommon.network_cli` | 네트워크 장비 CLI 관리 |

대부분의 Linux 서버에서는 기본 SSH Plugin을 그대로 사용하면 된다. Plugin을 바꾸기 전에 SSH 자체와 Inventory 변수를 먼저 확인하는 것이 맞다.

## 1.6 Bastion / Jump Host

외부에서 내부 서버로 직접 SSH 접속할 수 없을 때 Bastion Host를 경유한다.

```text
ansible-control → bastion → private-node
```

대상 그룹에 `ProxyJump` 옵션을 지정할 수 있다.

```yaml
# group_vars/private.yml
ansible_ssh_common_args: >-
  -o ProxyJump=bastion-user@203.0.113.10
```

Inventory 예시는 다음과 같다.

```ini
[private]
app1 ansible_host=10.0.10.11
app2 ansible_host=10.0.10.12

[private:vars]
ansible_user=ansible
```

Control Node의 `~/.ssh/config`에 구성하는 방법도 있다.

```sshconfig
Host bastion
    HostName 203.0.113.10
    User bastion-user
    IdentityFile ~/.ssh/id_ed25519

Host 10.0.10.*
    User ansible
    ProxyJump bastion
```

```yaml
# group_vars/private.yml
ansible_ssh_common_args: "-o ProxyJump=bastion"
```

`ProxyJump`는 Control Node의 SSH 연결을 중계하는 것이므로, 일반적으로 개인 키를 Bastion 서버에 복사할 필요가 없다.

---

# 2. Inventory & Variables

## 2.1 Static Inventory

Static Inventory는 관리할 호스트와 그룹을 파일에 직접 정의한다. 대표 형식은 INI와 YAML이다.

### INI 형식

```ini
# inventory.ini
[web]
node1 ansible_host=172.30.1.151
node2 ansible_host=172.30.1.152

[db]
db1 ansible_host=172.30.1.161

[production:children]
web
db

[all:vars]
ansible_user=ansible
ansible_python_interpreter=/usr/bin/python3
```

- `[web]`, `[db]`: 호스트 그룹
- `[production:children]`: 여러 그룹을 묶은 상위 그룹
- `[all:vars]`: 모든 호스트가 상속하는 변수
- 한 호스트는 여러 그룹에 동시에 속할 수 있다.
- 어떤 사용자 정의 그룹에도 속하지 않은 호스트는 `ungrouped`에 속한다.

### YAML 형식

```yaml
# inventory.yml
all:
  vars:
    ansible_user: ansible
    ansible_python_interpreter: /usr/bin/python3
  children:
    web:
      hosts:
        node1:
          ansible_host: 172.30.1.151
        node2:
          ansible_host: 172.30.1.152
    db:
      hosts:
        db1:
          ansible_host: 172.30.1.161
```

YAML Inventory는 Boolean, 숫자, 문자열 타입이 비교적 명확하다. INI의 `[group:vars]` 값은 문자열로 해석되는 등 위치에 따라 타입 해석이 달라질 수 있으므로, 규모가 커지면 YAML이 관리하기 편하다.

### Inventory 확인

```bash
ansible-inventory -i inventory.ini --graph
ansible-inventory -i inventory.ini --list
ansible-inventory -i inventory.ini --host node1
```

실행 전에 `--graph`로 그룹 구조를 확인하는 습관이 좋다.

## 2.2 `group_vars/`와 `host_vars/`

호스트 목록과 변수를 Inventory 한 파일에 전부 넣으면 금방 복잡해진다. 공통 변수는 `group_vars/`, 개별 호스트 변수는 `host_vars/`로 분리한다.

```text
ansible-lab/
├── ansible.cfg
├── inventory.ini
├── group_vars/
│   ├── all.yml
│   └── web.yml
├── host_vars/
│   └── node1.yml
├── playbooks/
│   └── site.yml
└── templates/
    └── motd.j2
```

```yaml
# group_vars/all.yml
ansible_user: ansible
ansible_python_interpreter: /usr/bin/python3
timezone: Asia/Seoul
```

```yaml
# group_vars/web.yml
web_package: nginx
web_service: nginx
http_port: 80
```

```yaml
# host_vars/node1.yml
http_port: 8080
```

`node1`은 `web` 그룹의 `http_port: 80`을 상속하지만, 호스트 전용 값 `8080`이 이를 덮어쓴다.

파일명은 Inventory의 호스트명 또는 그룹명과 정확히 맞춰야 한다.

## 2.3 Inventory 관련 특수 변수

Ansible이 자체적으로 제공하는 특수 변수는 직접 같은 이름으로 정의하지 않는다.

### `inventory_hostname`

현재 실행 중인 호스트의 Inventory 이름이다.

```yaml
- name: Show inventory name
  ansible.builtin.debug:
    msg: "현재 호스트는 {{ inventory_hostname }}"
```

### `groups`

그룹별 호스트 목록이 들어 있는 Dictionary다.

```yaml
- name: Show web members
  ansible.builtin.debug:
    var: groups['web']
```

Jinja2 Template에서도 사용할 수 있다.

```jinja2
{% for host in groups['web'] %}
server {{ hostvars[host].ansible_host }}:{{ hostvars[host].http_port }}
{% endfor %}
```

### `hostvars`

다른 호스트의 변수를 조회할 수 있는 Dictionary다.

```yaml
- name: Show node1 address
  ansible.builtin.debug:
    msg: "{{ hostvars['node1']['ansible_host'] }}"
```

다른 호스트의 Fact를 `hostvars`로 읽으려면 그 호스트의 Fact가 이미 수집되었거나 Fact Cache에 있어야 한다.

### 그 밖의 주요 변수

| 변수 | 의미 |
|---|---|
| `group_names` | 현재 호스트가 속한 그룹 목록 |
| `ansible_play_hosts` | 현재 Play에서 활성 상태인 호스트 목록 |
| `ansible_play_batch` | `serial` 적용 시 현재 실행 배치의 호스트 목록 |
| `playbook_dir` | 실행 중인 Playbook이 위치한 디렉터리 |
| `ansible_facts` | Fact Gathering으로 수집한 시스템 정보 |

## 2.4 Variable Precedence

같은 이름의 변수가 여러 위치에 있으면 우선순위가 높은 값이 낮은 값을 덮어쓴다.

설정 전체의 큰 범주는 낮은 순서부터 다음과 같다.

```text
ansible.cfg 설정
  < 일반 명령행 옵션
  < Playbook Keyword
  < 변수
  < 일부 직접 할당
```

주의할 점은 `-u`, `--become` 같은 일반 명령행 옵션이 모든 변수를 이기는 것이 아니라는 점이다. 반면 `-e`, `--extra-vars`로 전달한 변수는 변수 중 가장 강한 우선순위를 가진다.

변수끼리의 실무용 단순화 순서는 대략 다음과 같다. 아래로 갈수록 강하다.

| 단계 | 대표 위치 | 용도 |
|---:|---|---|
| 1 | Role Defaults | 쉽게 덮어쓸 기본값 |
| 2 | `group_vars/all.yml` | 모든 호스트 공통값 |
| 3 | `group_vars/<group>.yml` | 그룹 공통값 |
| 4 | `host_vars/<host>.yml` | 호스트별 차이 |
| 5 | Play의 `vars`, `vars_files` | 해당 Play 전용값 |
| 6 | Role Vars, Block Vars, Task Vars | 좁은 실행 범위의 강한 값 |
| 7 | `include_vars`, `set_fact`, 등록 변수 | 실행 중 생성된 값 |
| 8 | Role/Include Parameter | 호출 시 전달한 값 |
| 9 | `--extra-vars`, `-e` | 실행 시 강제한 값 |

전체 우선순위는 더 세분화되어 있으므로 외워서 충돌을 해결하려 하지 않는 편이 낫다.

### 권장 관리 전략

- 한 변수는 가능한 한 한 위치에서 정의한다.
- 모든 호스트 공통값은 `group_vars/all.yml`에 둔다.
- 역할별 차이는 해당 `group_vars/`에 둔다.
- 정말 예외인 값만 `host_vars/`에 둔다.
- Role에서 사용자가 바꿔도 되는 값은 `defaults/main.yml`에 둔다.
- `-e`는 배포 버전처럼 실행 시 반드시 주입할 값에 제한적으로 사용한다.
- 비밀번호와 Token은 Git에 평문으로 저장하지 않는다.

현재 최종값을 확인할 때는 다음 명령이 유용하다.

```bash
ansible-inventory -i inventory.ini --host node1
```

## 2.5 환경별 Inventory 분리

개발·스테이징·운영 환경은 Inventory를 분리하는 편이 안전하다.

```text
inventories/
├── dev/
│   ├── hosts.yml
│   └── group_vars/
└── prod/
    ├── hosts.yml
    └── group_vars/
```

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml
ansible-playbook -i inventories/prod/hosts.yml site.yml
```

같은 Inventory에서 `environment: dev`만 바꾸는 방식보다, 대상 호스트 자체가 다른 환경은 Inventory 경계를 분리하는 것이 사고를 줄이기 쉽다.

## 2.6 Dynamic Inventory

클라우드에서는 인스턴스가 자주 생성되고 삭제되므로 호스트 IP를 Static Inventory에 직접 유지하기 어렵다. Dynamic Inventory Plugin은 AWS EC2 같은 외부 시스템의 API에서 현재 호스트 목록과 메타데이터를 가져온다.

### AWS EC2 예시

필요한 Collection과 Python 라이브러리를 설치한다.

```bash
ansible-galaxy collection install amazon.aws
pipx inject ansible boto3 botocore
```

```yaml
# inventory.aws_ec2.yml
plugin: amazon.aws.aws_ec2

regions:
  - ap-northeast-2

filters:
  instance-state-name: running
  tag:ManagedBy: ansible

hostnames:
  - private-ip-address

keyed_groups:
  - key: tags.Environment
    prefix: env
  - key: tags.Role
    prefix: role

compose:
  ansible_host: private_ip_address
```

확인 명령은 다음과 같다.

```bash
ansible-inventory -i inventory.aws_ec2.yml --graph
ansible-inventory -i inventory.aws_ec2.yml --list
```

예를 들어 EC2 Tag가 `Environment=prod`, `Role=web`이면 Plugin 설정에 따라 `env_prod`, `role_web` 같은 그룹이 자동 생성될 수 있다.

AWS Access Key를 Inventory 파일에 직접 쓰지 않는다. AWS Profile, 환경 변수, EC2 Instance Role 등 표준 AWS 자격 증명 체인을 이용한다.

---

# 3. Modules & Idempotency

## 3.1 Ad-hoc Command

Ad-hoc Command는 Playbook을 작성하지 않고 한 번의 작업을 빠르게 실행하는 방식이다.

```bash
ansible <대상 패턴> -i <inventory> -m <모듈> -a '<인자>'
```

예시:

```bash
ansible all -i inventory.ini -m ansible.builtin.ping

ansible web -i inventory.ini \
  -m ansible.builtin.command \
  -a 'uname -a'

ansible web -i inventory.ini \
  -m ansible.builtin.package \
  -a 'name=curl state=present' \
  --become
```

Ad-hoc Command는 상태 확인, 긴급한 단발 작업, 모듈 테스트에 적합하다. 반복할 작업과 변경 이력을 남겨야 하는 작업은 Playbook으로 작성한다.

## 3.2 FQCN

FQCN은 Fully Qualified Collection Name으로, 모듈의 전체 이름이다.

```yaml
# 짧은 이름
- package:
    name: nginx
    state: present

# FQCN
- ansible.builtin.package:
    name: nginx
    state: present
```

`ansible.builtin.package`처럼 FQCN을 쓰면 어느 Collection의 모듈인지 명확하고, 같은 짧은 이름을 가진 모듈 간 충돌을 피할 수 있다. 학습 자료와 팀 Playbook에서는 FQCN 사용을 권장한다.

## 3.3 주요 모듈

### `ansible.builtin.command`

원격 호스트에서 명령을 직접 실행한다. Shell을 거치지 않으므로 파이프(`|`), 리다이렉션(`>`), `&&`, 변수 확장 같은 Shell 문법은 동작하지 않는다.

```yaml
- name: Read kernel version
  ansible.builtin.command: uname -r
  register: kernel_result
  changed_when: false
```

인자를 안전하게 분리하려면 `argv`를 사용할 수 있다.

```yaml
- name: Run command with argv
  ansible.builtin.command:
    argv:
      - /usr/bin/test
      - -f
      - /etc/nginx/nginx.conf
  changed_when: false
```

`command`는 실행 자체가 시스템을 바꿨는지 판단하기 어려워 기본적으로 `changed`가 될 수 있다. 조회 명령은 `changed_when: false`를 지정하는 것이 좋다.

### `ansible.builtin.shell`

Shell 문법이 반드시 필요할 때 사용한다.

```yaml
- name: Count error lines
  ansible.builtin.shell: >-
    set -o pipefail && grep ERROR /var/log/myapp.log | wc -l
  args:
    executable: /bin/bash
  register: error_count
  changed_when: false
```

가능하면 전용 모듈이나 `command`를 먼저 사용한다. `shell`은 quoting, Shell injection, 환경 차이 때문에 더 취약하다. 외부 입력을 명령에 넣어야 한다면 `quote` Filter 등을 사용하고 입력을 신뢰할 수 있는지 확인한다.

### `ansible.builtin.copy`

Control Node의 파일이나 직접 작성한 내용을 Managed Node로 복사한다.

```yaml
- name: Copy static configuration
  ansible.builtin.copy:
    src: files/myapp.conf
    dest: /etc/myapp/myapp.conf
    owner: root
    group: root
    mode: '0644'
    backup: true
  become: true
```

내용과 권한이 이미 같으면 `ok`, 다르면 복사 후 `changed`가 된다.

### `ansible.builtin.file`

파일 자체의 내용을 작성하는 모듈이 아니라 디렉터리, 권한, 소유권, 링크, 삭제 상태 등을 관리한다.

```yaml
- name: Ensure application directory exists
  ansible.builtin.file:
    path: /opt/myapp
    state: directory
    owner: myapp
    group: myapp
    mode: '0750'
  become: true
```

`state: touch`는 실행할 때마다 수정 시간이 바뀔 수 있으므로, 단순히 빈 파일의 존재만 보장하려는 경우 멱등성에 주의한다.

### `ansible.builtin.template`

Jinja2 Template을 렌더링하여 호스트별 설정 파일을 만든다.

```yaml
- name: Render nginx configuration
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    owner: root
    group: root
    mode: '0644'
    backup: true
    validate: '/usr/sbin/nginx -t -c %s'
  become: true
  notify: Restart nginx
```

`validate`를 지원하는 설정 파일은 배치 전에 문법 검증을 넣는 편이 안전하다. `%s`에는 임시 파일 경로가 들어간다.

### `ansible.builtin.package`

OS별 Package Manager 차이를 추상화한다.

```yaml
- name: Ensure required packages are installed
  ansible.builtin.package:
    name:
      - curl
      - git
      - vim
    state: present
  become: true
```

`state: present`는 설치 여부를 보장한다. `state: latest`는 실행 시점의 최신 버전으로 올리므로 운영 환경에서는 예상하지 않은 업그레이드가 발생할 수 있다.

배포판별 세부 기능이 필요하면 `ansible.builtin.apt`, `ansible.builtin.dnf`처럼 전용 모듈을 사용한다.

### `ansible.builtin.service`와 `ansible.builtin.systemd_service`

서비스의 실행·중지·자동 시작 상태를 관리한다.

```yaml
- name: Ensure nginx is enabled and running
  ansible.builtin.systemd_service:
    name: nginx
    enabled: true
    state: started
  become: true
```

```yaml
- name: Reload systemd units
  ansible.builtin.systemd_service:
    daemon_reload: true
  become: true
```

- `service`: 여러 Init System을 추상화한 범용 모듈
- `systemd_service`: systemd의 `daemon_reload`, `masked` 등 세부 기능까지 제어
- `state: started`: 이미 실행 중이면 보통 `ok`
- `state: restarted`: 실행할 때마다 재시작하므로 항상 변경을 유발할 수 있음

## 3.4 Idempotency

멱등성은 같은 Playbook을 여러 번 실행해도 최종 상태가 같고, 이미 원하는 상태라면 불필요한 변경을 하지 않는 성질이다.

예를 들어 다음 Task는 멱등적이다.

```yaml
- name: Ensure nginx is installed
  ansible.builtin.package:
    name: nginx
    state: present
```

- 첫 실행: nginx가 없으면 설치하고 `changed`
- 두 번째 실행: 이미 설치되어 있으면 `ok`

반면 다음 Task는 매번 파일에 한 줄을 추가할 수 있다.

```yaml
- name: Bad example
  ansible.builtin.shell: "echo hello >> /tmp/example.txt"
```

전용 모듈로 원하는 상태를 표현해야 한다.

```yaml
- name: Ensure line exists exactly once
  ansible.builtin.lineinfile:
    path: /tmp/example.txt
    line: hello
    create: true
```

모든 모듈과 모든 명령이 자동으로 멱등적인 것은 아니다. 특히 `command`, `shell`, `raw`는 작성자가 결과 상태를 직접 고려해야 한다.

## 3.5 실행 상태

| 상태 | 의미 |
|---|---|
| `ok` | Task가 성공했고 변경하지 않음 |
| `changed` | Task가 성공했고 대상 상태를 변경함 |
| `failed` | 연결은 되었지만 Task 실행 실패 |
| `unreachable` | SSH, DNS, 인증 등의 문제로 연결 실패 |
| `skipped` | `when`, Tag, Check Mode 조건 등으로 실행하지 않음 |
| `rescued` | 실패했지만 `rescue` 흐름에서 처리됨 |
| `ignored` | 실패했지만 `ignore_errors` 등에 의해 진행함 |

`changed`는 성공의 반대가 아니다. **성공하면서 변경이 발생했다**는 의미다.

## 3.6 `changed_when`과 `failed_when`

모듈의 기본 판정을 실제 의미에 맞게 재정의할 수 있다.

### 조회 명령은 변경 없음으로 처리

```yaml
- name: Check nginx status
  ansible.builtin.command: systemctl is-active nginx
  register: nginx_status
  changed_when: false
```

### 특정 출력이 있을 때만 변경 처리

```yaml
- name: Run migration tool
  ansible.builtin.command: /opt/myapp/bin/migrate
  register: migration_result
  changed_when: "'migration applied' in migration_result.stdout"
```

### 허용할 Return Code 지정

`grep`은 일치 결과가 없을 때 `rc=1`을 반환하지만 반드시 시스템 오류인 것은 아니다.

```yaml
- name: Search optional setting
  ansible.builtin.command:
    argv:
      - grep
      - -q
      - feature=true
      - /etc/myapp/app.conf
  register: grep_result
  changed_when: false
  failed_when: grep_result.rc not in [0, 1]
```

여러 조건을 List로 작성하면 기본적으로 `and`로 결합된다.

```yaml
failed_when:
  - result.rc != 0
  - "'already stopped' not in result.stderr"
```

하나만 만족해도 실패하게 하려면 문자열 안에 `or`를 명시한다.

```yaml
failed_when: >-
  result.rc >= 2 or
  'fatal' in result.stderr
```

`when`, `changed_when`, `failed_when`은 이미 Jinja2 Expression으로 평가되므로 보통 `{{ }}`를 쓰지 않는다.

---

# 4. Playbook Development

## 4.1 Playbook, Play, Task, Module

구조는 다음과 같다.

```text
Playbook
└── Play: 어떤 호스트에 어떤 조건으로 실행할지 정의
    ├── Task: 수행할 작업 한 단위
    │   └── Module: 실제 기능 수행
    └── Handler: 변경 알림을 받았을 때 실행할 Task
```

기본 예시:

```yaml
---
- name: Configure web servers
  hosts: web
  become: true
  gather_facts: true

  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Ensure nginx is running
      ansible.builtin.service:
        name: nginx
        enabled: true
        state: started
```

- `hosts`: Inventory에서 선택할 대상 Pattern
- `become`: 이 Play의 Task에 권한 상승 적용
- `gather_facts`: 시작 시 시스템 정보 수집
- `tasks`: 순서대로 실행할 Task 목록
- 하나의 Playbook에는 여러 Play를 넣을 수 있다.

## 4.2 `vars`

Play 안에서 사용할 변수를 정의한다.

```yaml
- name: Configure application
  hosts: web
  vars:
    app_name: demo
    app_port: 8080
    app_packages:
      - curl
      - jq

  tasks:
    - name: Show configuration
      ansible.builtin.debug:
        msg: "{{ app_name }} listens on {{ app_port }}"
```

재사용할 환경 변수는 Playbook 안보다 `group_vars/`, `host_vars/`, Role Defaults로 분리하는 것이 좋다.

## 4.3 `register`

Task 결과를 변수에 저장한다.

```yaml
- name: Read kernel version
  ansible.builtin.command: uname -r
  register: kernel_result
  changed_when: false

- name: Print kernel version
  ansible.builtin.debug:
    var: kernel_result.stdout
```

등록 결과에는 모듈에 따라 다음 값이 들어올 수 있다.

- `stdout`, `stdout_lines`
- `stderr`, `stderr_lines`
- `rc`
- `changed`, `failed`, `skipped`
- 그 밖의 모듈별 반환값

Loop가 적용된 Task의 등록 변수에는 각 반복 결과가 `results` List로 들어간다.

## 4.4 `when`

조건이 참인 호스트에서만 Task를 실행한다.

```yaml
- name: Install apt package on Debian family
  ansible.builtin.apt:
    name: nginx
    state: present
    update_cache: true
  when: ansible_facts['os_family'] == 'Debian'
  become: true
```

여러 조건을 List로 쓰면 모두 참이어야 한다.

```yaml
when:
  - ansible_facts['os_family'] == 'Debian'
  - app_enabled | bool
```

조건식에는 보통 `{{ }}`를 쓰지 않는다.

## 4.5 `loop`

같은 Task를 여러 값에 대해 반복한다.

```yaml
- name: Install common packages
  ansible.builtin.package:
    name: "{{ item }}"
    state: present
  loop:
    - curl
    - git
    - vim
  become: true
```

모듈이 List 입력을 지원한다면 다음처럼 한 번에 전달하는 편이 더 효율적일 수 있다.

```yaml
- name: Install common packages in one transaction
  ansible.builtin.package:
    name:
      - curl
      - git
      - vim
    state: present
  become: true
```

중첩된 Include나 여러 Loop가 겹치면 변수명을 바꾼다.

```yaml
loop: "{{ users }}"
loop_control:
  loop_var: user_item
```

## 4.6 `notify`와 `handlers`

Handler는 Task가 실제로 `changed`가 되었을 때만 알림을 받아 실행된다.

```yaml
- name: Configure nginx
  hosts: web
  become: true

  tasks:
    - name: Deploy nginx configuration
      ansible.builtin.template:
        src: nginx.conf.j2
        dest: /etc/nginx/nginx.conf
        mode: '0644'
        validate: '/usr/sbin/nginx -t -c %s'
      notify: Restart nginx

  handlers:
    - name: Restart nginx
      ansible.builtin.service:
        name: nginx
        state: restarted
```

핵심 동작은 다음과 같다.

- Template 내용이 바뀌면 Task가 `changed`가 되고 Handler가 예약된다.
- 내용이 같아 `ok`라면 Handler는 실행되지 않는다.
- 여러 Task가 같은 Handler를 호출해도 기본적으로 한 번만 실행된다.
- Handler는 `notify`에 적힌 순서가 아니라 `handlers`에 정의된 순서로 실행된다.
- 보통 해당 작업 구간의 끝에서 실행된다.

즉시 Handler를 실행해야 할 때는 다음을 사용할 수 있다.

```yaml
- name: Apply pending handlers now
  ansible.builtin.meta: flush_handlers
```

중간 Task가 실패하면 이전에 예약된 Handler가 해당 호스트에서 실행되지 않을 수 있다. 필요하면 Play에 `force_handlers: true`를 검토하지만, 실패 이후 재시작이 안전한지 먼저 판단해야 한다.

## 4.7 `pre_tasks`, `tasks`, `post_tasks`

Play의 실행 순서는 다음과 같다.

1. Fact Gathering
2. `pre_tasks`
3. Role과 `tasks`
4. `post_tasks`
5. 각 구간에서 예약된 Handler 실행

```yaml
- name: Deploy application
  hosts: web

  pre_tasks:
    - name: Check maintenance window
      ansible.builtin.debug:
        msg: Starting deployment

  tasks:
    - name: Deploy application
      ansible.builtin.debug:
        msg: Deploying

  post_tasks:
    - name: Verify application
      ansible.builtin.uri:
        url: http://127.0.0.1/health
        status_code: 200
```

- `pre_tasks`: 본 작업 전 사전 점검, Load Balancer 제외 등
- `tasks`: 실제 설치·설정·배포
- `post_tasks`: Health Check, Load Balancer 복귀, 결과 확인 등

## 4.8 `block`, `rescue`, `always`

관련 Task를 묶고 공통 조건, 권한 상승, 예외 처리 흐름을 적용한다.

```yaml
- name: Deploy with recovery
  block:
    - name: Stop application
      ansible.builtin.service:
        name: myapp
        state: stopped

    - name: Install new application package
      ansible.builtin.copy:
        src: myapp.bin
        dest: /opt/myapp/myapp.bin
        mode: '0755'

    - name: Start application
      ansible.builtin.service:
        name: myapp
        state: started

  rescue:
    - name: Restore backup
      ansible.builtin.copy:
        remote_src: true
        src: /opt/myapp/myapp.bin.bak
        dest: /opt/myapp/myapp.bin

    - name: Start restored application
      ansible.builtin.service:
        name: myapp
        state: started

  always:
    - name: Record deployment end
      ansible.builtin.debug:
        msg: "Deployment flow finished on {{ inventory_hostname }}"

  become: true
```

- `block`: 정상 작업
- `rescue`: `block` 안의 Task가 `failed`일 때 복구 작업
- `always`: 성공·실패·복구 여부와 관계없이 실행할 정리 작업

`rescue`는 일반적인 Task 실패를 처리하지만, 잘못된 YAML 문법이나 Host `unreachable`까지 복구하는 만능 예외 처리 장치는 아니다.

복구 흐름에서는 다음 특수 변수를 활용할 수 있다.

- `ansible_failed_task`: 실패한 Task 정보
- `ansible_failed_result`: 실패 결과

실제 Rollback은 사전에 백업 파일이나 이전 Artifact가 존재해야 가능하다. `rescue`를 썼다는 이유만으로 자동 복구가 보장되지는 않는다.

## 4.9 Tags

Task 일부만 선택해서 실행하거나 제외할 수 있다.

```yaml
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
  tags:
    - install
    - nginx

- name: Configure nginx
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  tags:
    - config
    - nginx
```

```bash
ansible-playbook -i inventory.ini site.yml --list-tags
ansible-playbook -i inventory.ini site.yml --tags config
ansible-playbook -i inventory.ini site.yml --skip-tags install
```

Tag는 작업 선택 기능이지 의존성 관리 기능이 아니다. `config` Task가 Package 설치를 전제로 한다면 `--tags config`만 실행했을 때 실패할 수 있다.

## 4.10 `--limit`

Play의 `hosts` 대상 안에서 실제 실행 호스트를 더 좁힌다.

```bash
ansible-playbook -i inventory.ini site.yml --limit node1
ansible-playbook -i inventory.ini site.yml --limit web
ansible-playbook -i inventory.ini site.yml --limit 'web:&production'
```

- `node1`: 한 호스트만 실행
- `web`: web 그룹만 실행
- `web:&production`: web과 production 그룹에 모두 속한 호스트만 실행

`--limit`은 Playbook에 정의된 대상을 확장하지 않는다. `hosts: web`인데 `--limit db1`을 주면 교집합이 없어서 실행 대상이 없다.

---

# 5. Jinja2 & Safe Execution

## 5.1 Jinja2 Template

Jinja2를 사용하면 호스트와 환경에 따라 다른 설정 파일을 하나의 Template으로 관리할 수 있다.

```jinja2
{# templates/myapp.conf.j2 #}
app_name = {{ app_name }}
listen_port = {{ app_port }}
environment = {{ app_environment | default('dev') }}

{% if tls_enabled | default(false) | bool %}
tls = true
certificate = {{ tls_certificate }}
{% else %}
tls = false
{% endif %}

{% for backend in groups['web'] %}
backend = {{ hostvars[backend].ansible_host }}:{{ hostvars[backend].app_port }}
{% endfor %}
```

Playbook에서 Template을 배포한다.

```yaml
- name: Deploy application configuration
  ansible.builtin.template:
    src: myapp.conf.j2
    dest: /etc/myapp/myapp.conf
    owner: root
    group: root
    mode: '0644'
    backup: true
  become: true
  notify: Restart myapp
```

## 5.2 변수 치환과 기본 Filter

```jinja2
{{ variable }}
```

값 전체가 변수 표현식으로 시작하면 YAML에서는 따옴표로 감싸는 것이 안전하다.

```yaml
dest: "{{ config_directory }}/app.conf"
```

주요 Filter는 다음과 같다.

| Filter | 예시 | 의미 |
|---|---|---|
| `default` | `{{ port | default(8080) }}` | 미정의 값에 기본값 사용 |
| `mandatory` | `{{ api_token | mandatory }}` | 값이 없으면 명시적으로 실패 |
| `bool` | `{{ feature_enabled | bool }}` | Boolean으로 변환 |
| `int` | `{{ port | int }}` | 정수로 변환 |
| `lower` / `upper` | `{{ env | lower }}` | 대·소문자 변환 |
| `join` | `{{ packages | join(',') }}` | List를 문자열로 결합 |
| `unique` | `{{ users | unique }}` | 중복 제거 |
| `to_nice_yaml` | `{{ data | to_nice_yaml }}` | 읽기 쉬운 YAML로 변환 |
| `quote` | `{{ user_input | quote }}` | Shell 인자용 Quoting 보조 |

`default('x')`는 기본적으로 **미정의 변수**에만 적용한다. `false`, 빈 문자열, `0` 같은 값도 기본값으로 대체하려면 `default('x', true)`를 사용하지만, 의도한 유효 값까지 덮을 수 있으므로 주의한다.

## 5.3 `--check`

Check Mode는 실제 변경 없이 어떤 변경이 발생할지 모의 실행한다.

```bash
ansible-playbook -i inventory.ini site.yml --check
```

단, 완전한 Dry Run이나 Rollback 기능은 아니다.

- 모듈이 Check Mode를 지원해야 정확히 예측할 수 있다.
- 지원하지 않는 모듈은 아무 작업도 하지 않고 결과가 제한적일 수 있다.
- 앞 Task의 `register` 결과에 의존하는 뒤 Task는 실제 실행과 다르게 동작할 수 있다.
- 외부 API나 직접 작성한 `shell` 명령의 부작용을 모두 예측하지 못한다.

특정 Task의 Check Mode 동작을 강제할 수 있다.

```yaml
- name: Always simulate this task
  ansible.builtin.template:
    src: app.conf.j2
    dest: /etc/app.conf
  check_mode: true
```

```yaml
- name: Must run even during check mode
  ansible.builtin.command: /usr/local/bin/read-only-check
  check_mode: false
  changed_when: false
```

`check_mode: false`는 `--check` 중에도 실제로 실행하므로 읽기 전용 작업인지 확실히 확인해야 한다.

## 5.4 `--diff`

파일 변경 전후 차이를 출력한다.

```bash
ansible-playbook -i inventory.ini site.yml --check --diff
```

`copy`, `template`, `lineinfile` 등 Diff Mode를 지원하는 모듈에서 특히 유용하다.

주의할 점:

- 설정 파일에 비밀번호나 Token이 있으면 터미널과 CI Log에 노출될 수 있다.
- 민감한 Task에는 `no_log: true` 또는 `diff: false`를 검토한다.
- `no_log: true`는 디버깅 정보도 숨기므로 필요한 범위에만 사용한다.

```yaml
- name: Deploy secret configuration
  ansible.builtin.template:
    src: secret.conf.j2
    dest: /etc/myapp/secret.conf
    mode: '0600'
  become: true
  no_log: true
  diff: false
```

## 5.5 한 호스트에서 안전하게 검증하기

운영 변경은 다음 순서로 범위를 단계적으로 넓히는 것이 안전하다.

### 1단계: YAML과 Playbook 문법 확인

```bash
ansible-playbook -i inventory.ini site.yml --syntax-check
```

### 2단계: Inventory와 대상 확인

```bash
ansible-inventory -i inventory.ini --graph
ansible-playbook -i inventory.ini site.yml --list-hosts
```

### 3단계: 한 호스트에서 모의 실행

```bash
ansible-playbook -i inventory.ini site.yml \
  --limit node1 \
  --check \
  --diff
```

### 4단계: 한 호스트에 실제 적용

```bash
ansible-playbook -i inventory.ini site.yml \
  --limit node1 \
  --diff
```

### 5단계: 결과와 서비스 상태 확인

```bash
ansible node1 -i inventory.ini \
  -m ansible.builtin.command \
  -a 'systemctl is-active nginx'
```

조회 명령도 Ad-hoc `command`에서는 `changed`로 보일 수 있다. 상태 의미가 중요한 검증은 Playbook Task로 만들고 `changed_when: false`를 지정하는 편이 정확하다.

### 6단계: 전체 그룹으로 확대

```bash
ansible-playbook -i inventory.ini site.yml --limit web
```

호스트가 많다면 Play에 `serial`을 설정해 일부씩 순차 배포한다.

```yaml
- name: Rolling update web servers
  hosts: web
  serial: 1
  tasks:
    - name: Apply update
      ansible.builtin.debug:
        msg: "Updating {{ inventory_hostname }}"
```

`--limit`은 사용자가 지정한 시험 대상이고, `serial`은 선택된 대상 안에서 동시에 처리할 배치 크기다.

---

# 6. 통합 실습 예제

## 6.1 파일 구조

```text
ansible-lab/
├── ansible.cfg
├── inventory.ini
├── group_vars/
│   ├── all.yml
│   └── web.yml
├── playbooks/
│   └── web.yml
└── templates/
    └── index.html.j2
```

## 6.2 설정 파일

```ini
# ansible.cfg
[defaults]
inventory = inventory.ini
host_key_checking = True
interpreter_python = auto_silent
retry_files_enabled = False
```

`host_key_checking = False`로 경고를 없애는 방식은 편하지만, 서버 위장 여부를 확인하는 SSH 보호 기능까지 끈다. 학습 환경에서도 Host Key를 정상 등록하는 쪽이 낫다.

```ini
# inventory.ini
[web]
node1 ansible_host=172.30.1.151
node2 ansible_host=172.30.1.152
```

```yaml
# group_vars/all.yml
ansible_user: ansible
ansible_python_interpreter: /usr/bin/python3
```

```yaml
# group_vars/web.yml
web_package: nginx
web_service: nginx
web_root: /var/www/html
```

```jinja2
{# templates/index.html.j2 #}
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8">
    <title>Ansible Lab</title>
  </head>
  <body>
    <h1>{{ inventory_hostname }}</h1>
    <p>Managed by Ansible</p>
    <p>Address: {{ ansible_host }}</p>
  </body>
</html>
```

## 6.3 Playbook

```yaml
---
- name: Configure web servers
  hosts: web
  become: true
  gather_facts: true
  serial: 1

  pre_tasks:
    - name: Show deployment target
      ansible.builtin.debug:
        msg: "Configuring {{ inventory_hostname }} ({{ ansible_host }})"
      tags: always

  tasks:
    - name: Install web package
      ansible.builtin.package:
        name: "{{ web_package }}"
        state: present
      tags:
        - install

    - name: Ensure web root exists
      ansible.builtin.file:
        path: "{{ web_root }}"
        state: directory
        owner: root
        group: root
        mode: '0755'
      tags:
        - config

    - name: Deploy index page
      ansible.builtin.template:
        src: ../templates/index.html.j2
        dest: "{{ web_root }}/index.html"
        owner: root
        group: root
        mode: '0644'
        backup: true
      notify: Restart web service
      tags:
        - config

    - name: Ensure web service is enabled and running
      ansible.builtin.systemd_service:
        name: "{{ web_service }}"
        enabled: true
        state: started
      tags:
        - service

  post_tasks:
    - name: Verify local HTTP response
      ansible.builtin.uri:
        url: http://127.0.0.1/
        status_code: 200
      register: healthcheck
      changed_when: false
      tags:
        - verify

  handlers:
    - name: Restart web service
      ansible.builtin.systemd_service:
        name: "{{ web_service }}"
        state: restarted
```

## 6.4 실행 순서

```bash
# 연결 확인
ansible all -m ansible.builtin.ping

# 문법 확인
ansible-playbook playbooks/web.yml --syntax-check

# 대상 확인
ansible-playbook playbooks/web.yml --list-hosts

# node1 모의 실행 및 차이 확인
ansible-playbook playbooks/web.yml --limit node1 --check --diff

# node1 실제 적용
ansible-playbook playbooks/web.yml --limit node1 --diff

# node1 재실행: 불필요한 changed가 없는지 확인
ansible-playbook playbooks/web.yml --limit node1

# 전체 web 그룹 적용
ansible-playbook playbooks/web.yml --limit web
```

두 번째 실행에서 대부분의 Task가 `ok`이고 `changed=0`이라면 멱등성이 잘 유지되고 있다는 뜻이다. 의도 없이 매번 `changed`가 발생하는 Task가 있으면 원인을 확인한다.

---

# 7. 핵심 정리

1. Ansible은 Control Node에서 실행되고, Managed Node에는 전용 Agent가 필요 없다.
2. 먼저 직접 SSH 접속과 Key 인증을 확인한 뒤 Ansible 연결 문제를 진단한다.
3. `become_user`는 전환 대상을 정할 뿐이며, `become: true`를 자동 활성화하지 않는다.
4. Inventory는 대상 목록이고, `group_vars/`와 `host_vars/`는 대상별 차이를 관리한다.
5. 같은 변수의 중복 정의를 줄이는 것이 복잡한 Variable Precedence를 외우는 것보다 중요하다.
6. 단발 작업은 Ad-hoc Command, 반복·검토·이력 관리가 필요한 작업은 Playbook을 사용한다.
7. `shell`보다 전용 모듈이나 `command`를 우선 사용한다.
8. `ok`는 변경 없음, `changed`는 성공하면서 변경 발생, `failed`는 작업 실패다.
9. Handler는 변경이 발생했을 때만 서비스 재시작 같은 후속 작업을 수행한다.
10. `--syntax-check → --list-hosts → --limit node1 --check --diff → 실제 적용` 순서로 변경 범위를 넓힌다.
11. Check Mode는 완전한 Dry Run도 Rollback도 아니므로 실제 결과 검증이 필요하다.
12. 동일 Playbook을 다시 실행해 불필요한 `changed`가 없는지 확인하는 것이 멱등성 검증의 기본이다.

---

# 8. 공식 문서

- [Introduction to Ansible](https://docs.ansible.com/projects/ansible/latest/getting_started/introduction.html)
- [Installing Ansible and node requirements](https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html)
- [How to build your inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html)
- [Working with dynamic inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_dynamic_inventory.html)
- [Using variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)
- [Facts and magic variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_vars_facts.html)
- [General precedence rules](https://docs.ansible.com/projects/ansible/latest/reference_appendices/general_precedence.html)
- [Privilege escalation: become](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_privilege_escalation.html)
- [Handlers](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html)
- [Blocks and error handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html)
- [Check mode and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)
- [Ansible Builtin Collection](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/)

