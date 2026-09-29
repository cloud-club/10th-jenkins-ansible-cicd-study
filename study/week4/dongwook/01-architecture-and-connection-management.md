# Architecture & Connection Management

예제 환경은 Ansible이 설치된 Control Node와 SSH·Python 3·sudo를 사용할 수 있는 Ubuntu 서버다. IP, 사용자, 키 경로는 실습 환경에 맞게 바꾼다.

## 1. Ansible의 기본 구조

| 구성 요소 | 역할 |
| --- | --- |
| Control Node | Ansible 명령을 실행하고 Inventory와 Playbook을 읽는 머신 |
| Managed Node | Ansible이 접속해서 설정을 관리하는 대상 머신 |
| Inventory | 관리 대상과 그룹, 연결 정보를 정의한 목록 |
| Playbook | 대상 서버에 적용할 작업과 원하는 상태를 YAML로 작성한 파일 |

Agentless는 Managed Node에 Ansible 전용 상주 Agent를 설치하지 않는다는 의미다. Linux 서버에서는 일반적으로 SSH로 접속해 모듈을 실행하고 결과를 받는다. 다만 Python으로 작성된 모듈을 실행하려면 대상 서버에도 Python이 필요하다.

```text
Control Node
  ├─ Inventory: 어디에 접속할지
  └─ Playbook: 어떤 상태를 만들지
          │ SSH 연결
          ▼
Managed Node
  └─ 모듈 실행 → 실행 결과 반환
```

Jenkins와 연결하면 Pipeline을 실행하는 Agent가 Ansible Control Node 역할을 맡을 수 있다. Ansible이 관리할 서버에는 별도의 Jenkins Agent가 필요하지 않다.

공식문서: [Introduction to Ansible](https://docs.ansible.com/projects/ansible/latest/getting_started/introduction.html), [ping 모듈의 Python 요구사항](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/ping_module.html)

## 2. SSH 연결과 Key 인증

SSH Key 인증에서는 Control Node가 개인 키를 사용하고, Managed Node의 접속 계정에는 대응하는 공개 키가 등록되어 있어야 한다. Ansible 실행 전에 동일한 계정과 키로 SSH 접속을 확인하면 연결 문제를 분리하기 쉽다.

```bash
ssh -i ~/.ssh/study_ed25519 ubuntu@192.0.2.11
```

최초 접속 시 서버의 Host Key를 확인한다. 사용자 인증용 Key와 서버 신원 확인용 Host Key는 역할이 다르다. Ansible의 Host Key 검증은 기본적으로 활성화되어 있다.

다음 파일을 `inventory.yml`로 작성한다.

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
| --- | --- |
| `ansible_host` | 실제로 접속할 IP 또는 DNS 이름 |
| `ansible_user` | SSH 로그인 계정 |
| `ansible_port` | SSH 포트. 일반적인 기본값은 22 |
| `ansible_ssh_private_key_file` | Control Node에 있는 개인 키의 경로 |

개인 키에 암호가 설정되어 있다면 실행 중인 `ssh-agent`에 `ssh-add ~/.ssh/study_ed25519`로 등록해서 사용할 수 있다.

공식문서: [Connection methods and details](https://docs.ansible.com/projects/ansible/latest/inventory_guide/connection_details.html), [ssh connection plugin](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/ssh_connection.html)

```bash
ansible web -i inventory.yml -m ansible.builtin.ping
```

`ansible.builtin.ping`은 ICMP ping이 아니다. SSH 접속 후 대상 서버에서 Python을 실행할 수 있으면 `pong`을 반환한다.

공식문서: [ping module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/ping_module.html)

## 3. SSH 로그인 계정과 작업 실행 계정

일반 계정으로 SSH에 접속한 뒤 패키지 설치처럼 관리자 권한이 필요한 작업에 `become`을 적용한다.

| 설정 | 의미 |
| --- | --- |
| `ansible_user: ubuntu` | SSH 연결에는 `ubuntu` 사용 |
| `become: true` | 작업 실행 시 권한 전환 활성화 |
| `become_user: root` | 전환할 계정. 기본값은 `root` |
| `become_method: sudo` | 전환 방법. 기본값은 `sudo` |

다음은 Playbook의 `tasks:` 아래에 넣는 Task 예제다.

```yaml
- name: Ensure nginx is installed
  become: true
  become_user: root
  ansible.builtin.package:
    name: nginx
    state: present
```

`become_user`만 지정하면 권한 전환이 활성화되지 않는다. `become: true`가 함께 필요하다. 또한 Ansible이 sudo 권한을 새로 부여하는 것은 아니므로, 접속 계정에 필요한 권한이 미리 설정되어 있어야 한다.

CLI에서는 다음처럼 확인할 수 있다.

```bash
ansible web -i inventory.yml -m ansible.builtin.command -a 'id -un' --become --ask-become-pass
```

결과가 `root`이면 전환된 계정으로 실행된 것이다. 비밀번호 없는 sudo 환경에서는 `--ask-become-pass`를 생략한다. `-b`는 `--become`, `-K`는 `--ask-become-pass`의 단축형이며, `-K`만으로 권한 전환이 켜지지는 않는다. SSH 비밀번호 입력 옵션인 `--ask-pass`와도 구분한다.

공식문서: [Understanding privilege escalation: become](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_privilege_escalation.html)

## 4. Connection Plugin과 Jump Host

Connection Plugin은 대상에 연결하는 방법을 담당하고, 모듈은 연결 후 수행할 작업을 담당한다. 예를 들어 `ssh`로 연결해서 `package` 모듈을 실행한다.

| Plugin | 용도 |
| --- | --- |
| `ansible.builtin.ssh` | Control Node의 SSH 클라이언트로 연결 |
| `ansible.builtin.local` | Control Node에서 직접 실행 |

Inventory의 `ansible_connection` 또는 Play의 `connection`으로 선택할 수 있다. 사용 가능한 Plugin은 다음 명령으로 확인한다.

```bash
ansible-doc -t connection -l
ansible-doc -t connection ansible.builtin.ssh
```

공식문서: [Connection plugins](https://docs.ansible.com/projects/ansible/latest/plugins/connection.html)

Private Network의 서버에 직접 접근할 수 없다면 Bastion을 경유한다.

```text
Control Node → Bastion / Jump Host → Private Managed Node
```

예를 들어 Control Node의 `~/.ssh/config`에 Bastion 연결을 정의한다.

```sshconfig
Host study-bastion
    HostName 203.0.113.10
    User ubuntu
    IdentityFile ~/.ssh/bastion_ed25519
```

대상 그룹의 연결 변수에는 다음을 추가한다. 대상의 `ansible_host`는 실제 Private IP로 변경한다.

```yaml
# inventory.yml의 web.vars에 추가
ansible_ssh_common_args: '-o ProxyJump=study-bastion'
```

이 설정은 SSH뿐 아니라 파일 전송에 사용하는 SCP/SFTP에도 공통 인자를 전달한다. Control Node에서 Bastion과 최종 대상 양쪽의 인증이 가능하고, Bastion에서 대상 SSH 포트에 접근할 수 있어야 한다. Bastion 자체에 Ansible을 설치하거나 개인 키를 복사할 필요는 없다.

공식문서: [Jump Host와 SSH 설정](https://docs.ansible.com/projects/ansible/latest/inventory_guide/connection_details.html), [Inventory의 SSH 연결 변수](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html#connecting-to-hosts-behavioral-inventory-parameters)

다음: [Inventory & Variables](02-Inventory-and-variables.md)
