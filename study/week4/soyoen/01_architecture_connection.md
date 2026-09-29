# Architecture & Connection Management

예제 환경은 Ansible이 설치된 Control Node와 SSH·Python 3·sudo를 사용할 수 있는 Ubuntu 서버다. IP, 사용자, 키 경로는 실습 환경에 맞게 바꾼다.

## 1. Ansible의 기본 구조

| 구성 요소 | 역할 |
|---|---|
| Control Node | Ansible 명령을 실행하는 머신 |
| Managed Node | Ansible이 접속해 설정을 관리하는 대상 |
| Inventory | 관리 대상과 연결 정보를 정의 |
| Playbook | 대상에 적용할 작업을 YAML로 작성 |

Ansible은 **Agentless** 구조다. Managed Node에 Ansible 전용 Agent를 상주시킬 필요 없이 일반적으로 SSH를 통해 접속한다. 단, 대부분의 Linux용 모듈 실행에는 대상 서버의 Python이 필요하다.

```text
Control Node
  ├─ Inventory : 어디에 접속할지
  └─ Playbook  : 무엇을 실행할지
           │ SSH
           ▼
Managed Node
  └─ Module 실행 → 결과 반환
```

Jenkins와 연결할 경우 Pipeline을 수행하는 Agent가 Ansible Control Node 역할을 맡을 수도 있다.

공식문서: [Introduction to Ansible](https://docs.ansible.com/projects/ansible/latest/getting_started/introduction.html)

---

## 2. SSH 연결과 Key 인증

Inventory에 SSH 접속 정보를 작성할 수 있다.

```yaml
all:
  children:
    web:
      hosts:
        web01:
          ansible_host: 192.0.2.11
      vars:
        ansible_user: ubuntu
        ansible_ssh_private_key_file: ~/.ssh/study_ed25519
```

| 변수 | 의미 |
|---|---|
| `ansible_host` | 실제 IP 또는 DNS |
| `ansible_user` | SSH 로그인 사용자 |
| `ansible_port` | SSH 포트 |
| `ansible_ssh_private_key_file` | 개인 키 경로 |

먼저 일반 SSH 접속을 확인하면 문제를 분리하기 쉽다.

```bash
ssh -i ~/.ssh/study_ed25519 ubuntu@192.0.2.11
```

Ansible 연결 확인:

```bash
ansible web -i inventory.yml -m ansible.builtin.ping
```

`ansible.builtin.ping`은 ICMP Ping이 아니라 SSH 접속 후 Python 실행 가능 여부를 확인하는 모듈이다.

공식문서: [Connection methods and details](https://docs.ansible.com/projects/ansible/latest/inventory_guide/connection_details.html), [ping module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/ping_module.html)

---

## 3. become을 이용한 권한 상승

SSH 로그인 사용자와 실제 작업 실행 사용자는 다를 수 있다.

```yaml
- name: Ensure nginx is installed
  become: true
  ansible.builtin.package:
    name: nginx
    state: present
```

| 설정 | 의미 |
|---|---|
| `ansible_user` | SSH 로그인 사용자 |
| `become: true` | 권한 상승 활성화 |
| `become_user` | 전환할 사용자, 기본값은 `root` |
| `become_method` | 권한 상승 방식, 일반적으로 `sudo` |

```text
ubuntu로 SSH 접속
        ↓
become / sudo
        ↓
root 권한으로 Task 실행
```

`become_user`만 작성해서는 권한 상승이 활성화되지 않는다. `become: true`가 필요하다.

공식문서: [Privilege escalation](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_privilege_escalation.html)

---

## 4. Connection Plugin과 Jump Host

Connection Plugin은 **어떻게 연결할지**, Module은 **연결 후 무엇을 할지** 담당한다.

| Plugin | 용도 |
|---|---|
| `ansible.builtin.ssh` | SSH를 통한 원격 연결 |
| `ansible.builtin.local` | Control Node에서 직접 실행 |

Private Network의 서버는 Bastion을 거쳐 접속할 수 있다.

```text
Control Node → Bastion / Jump Host → Private Managed Node
```

예:

```yaml
ansible_ssh_common_args: '-o ProxyJump=study-bastion'
```

이는 Ansible 전용 터널이 아니라 기존 SSH의 ProxyJump 기능을 활용하는 방식이다.

공식문서: [Connection plugins](https://docs.ansible.com/projects/ansible/latest/plugins/connection.html)

> **핵심:** Control Node가 Inventory를 읽고 SSH로 Managed Node에 연결하며, 필요한 경우 `become`으로 권한을 상승해 작업을 수행한다.