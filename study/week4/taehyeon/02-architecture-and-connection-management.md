# Architecture & Connection Management

## 1. Ansible Architecture란?

---

Ansible은 **Control Node가 Managed Node에 연결해 작업을 실행하는 Agentless 자동화 구조**다.

- **Control Node**: Ansible 명령과 Playbook을 실행하는 서버/개발 머신
- **Managed Node**: 실제 설정 변경이 수행되는 대상 서버
- **Agentless**: 대상 서버에 Ansible 전용 Agent를 상시 설치하지 않음

Linux/Unix 환경에서는 주로 SSH를 사용한다.

```
Control Node
  ├── Inventory
  ├── Playbook
  └── Ansible Core
        │ SSH
        ▼
Managed Nodes
```

### 1-1. 기본 실행 흐름

---

```
ansible-playbook 실행
        ↓
Inventory에서 대상 선택
        ↓
Connection Plugin으로 연결
        ↓
필요하면 become으로 권한 상승
        ↓
Module 실행
        ↓
ok / changed / failed / unreachable
```

### 1-2. SSH 기반 연결

---

Ansible이 Linux 서버를 관리하려면 먼저 **Control Node → Managed Node SSH 연결**이 가능해야 한다.

#### SSH Key란?

SSH Key는 **비밀번호 대신 공개키 암호 방식으로 SSH 인증을 수행하는 키 쌍**이다.

- **Private Key**: Control Node가 보관
- **Public Key**: Managed Node의 `authorized_keys`에 등록

```bash
ssh-keygen -t ed25519
```

기본 생성 파일:

```
~/.ssh/id_ed25519      # Private Key
~/.ssh/id_ed25519.pub  # Public Key
```

직접 접속:

```bash
ssh deploy@10.0.1.10
```

Ansible 연결 확인:

```bash
ansible all -i inventory.yml -m ansible.builtin.ping
```

#### Inventory의 주요 연결 변수

```yaml
all:
  hosts:
    web01:
      ansible_host: 10.0.1.10
      ansible_user: deploy
      ansible_port: 22
      ansible_ssh_private_key_file: ~/.ssh/id_ed25519
```

- `inventory_hostname`: Inventory상의 논리적 이름
- `ansible_host`: 실제 접속 IP/DNS
- `ansible_user`: SSH 사용자
- `ansible_port`: SSH 포트
- `ansible_ssh_private_key_file`: Private Key 경로

### 1-3. become / become_user

---

`become`은 **SSH로 로그인한 사용자에서 다른 사용자 권한으로 상승해 Task를 실행하는 기능**이다.

보통 일반 사용자로 접속한 뒤 필요한 작업에만 `sudo`를 사용한다.

```yaml
- name: Install nginx
  hosts: web
  become: true
  become_user: root

  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present
```

- `become: true`: 권한 상승 사용
- `become_user: root`: 전환할 사용자

<aside>
🤔

**고민할 점:** 모든 Task에 root 권한을 주기보다 실제로 필요한 작업에만 권한을 부여하는 편이 안전하다.

</aside>

### 1-4. Connection Plugin

---

Connection Plugin은 **Control Node가 대상 시스템에 어떤 방식으로 연결할지 담당하는 기능**이다.

> Module = 무엇을 할지 / Connection Plugin = 어떻게 연결할지
> 

대표적인 예:

- `ansible.builtin.ssh`: 일반 Linux/Unix SSH
- `ansible.builtin.local`: Control Node에서 로컬 실행
- `ansible.builtin.paramiko_ssh`: Paramiko 기반 SSH
- Windows: WinRM 계열 연결

```bash
ansible-doc -t connection -l
```

### 1-5. Bastion / Jump Host

---

Bastion / Jump Host는 **외부에서 직접 접근할 수 없는 내부 서버에 접속하기 위해 거치는 중간 SSH 서버**다.

> 내부 서버를 인터넷에 직접 노출하지 않고 Bastion만 외부 진입점으로 사용한다.
> 

```
Control Node
     │ SSH
     ▼
Bastion
     │ SSH
     ▼
Private Server
```

#### 왜 사용할까?

- Private Server를 외부에 직접 노출하지 않기 위해
- SSH 진입점을 한 곳으로 제한하기 위해
- Security Group, 접근 권한, 로그 관리를 단순화하기 위해

#### Bastion과 Jump Host 차이

실무에서는 거의 비슷하게 사용한다.

- **Bastion Host**: 보안 진입점 의미를 강조
- **Jump Host**: 접속 경유지 의미를 강조

Ansible에서는 둘 다 SSH 중간 경유지로 이해하면 충분하다.

#### Ansible에서는 어떻게 사용할까?

SSH의 `ProxyJump`를 사용할 수 있다.

```bash
ssh -J bastion-user@203.0.113.10 ec2-user@10.0.10.11
```

Inventory 예시:

```yaml
all:
  hosts:
    app01:
      ansible_host: 10.0.10.11
      ansible_user: ec2-user
      ansible_ssh_common_args: >-
        -o ProxyJump=bastion-user@203.0.113.10
```

<aside>
🤔

**고민할 점:** Bastion은 중요한 진입점이므로 IP 제한, 최소 권한, SSH Key 관리, 접근 로그 같은 보안 통제가 필요하다.

</aside>

### 1-6. 연결 문제 확인 순서

---

연결 오류는 **네트워크 → SSH → 인증 → Ansible** 순서로 확인하면 빠르다.

1. 일반 `ssh` 접속이 되는가?
2. `ansible_host`, `ansible_user`, Port가 맞는가?
3. Private Key가 맞는가?
4. Security Group / Firewall / Routing이 열려 있는가?
5. Bastion 사용 시 ProxyJump가 맞는가?
6. 필요하면 `-vvv` 로그를 확인한다.

```bash
ansible web01 -i inventory.yml -m ansible.builtin.ping -vvv
```

### 1-7. 실습

---

- [ ]  Control Node에서 SSH Key 생성
- [ ]  Managed Node에 Public Key 등록
- [ ]  일반 SSH 접속 확인
- [ ]  Inventory에 Host 등록
- [ ]  `ansible.builtin.ping` 실행
- [ ]  `--become`으로 권한 상승 확인
- [ ]  가능하면 Bastion/ProxyJump 구성

### 1-8. 여기서 생각해볼 질문

---

1. Agentless 구조의 장점은 무엇인가?
2. `inventory_hostname`과 `ansible_host`는 무엇이 다른가?
3. SSH 사용자와 `become_user`를 분리하는 이유는?
4. SSH는 되는데 Ansible이 `UNREACHABLE`이면 무엇부터 확인할까?
5. Private Server에 Bastion을 두는 이유는?

### 1-9. 참고 자료

---

- [Ansible 공식 문서 - Connection Plugins](https://docs.ansible.com/projects/ansible/latest/plugins/connection.html)
- [Ansible 공식 문서 - Playbook Keywords](https://docs.ansible.com/projects/ansible/latest/reference_appendices/playbooks_keywords.html)