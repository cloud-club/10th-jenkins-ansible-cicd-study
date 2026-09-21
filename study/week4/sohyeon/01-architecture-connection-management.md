## **1. Architecture & Connection Management**

### 1-1) Control Node / Managed Node 및 Agentless Architecture 이해

```
Control Node
    │
    │ SSH
    ▼
Managed Node 1
Managed Node 2
Managed Node 3
```

**Control Node**

- Ansible이 설치된 시스템
- `ansible` 또는 `ansible-inventory`와 같은 ansible 명령어를 실행한다.

**Managed Node**

- Ansible이 제어하는 원격 시스템/호스트

**Inventory**

- Manged Node 목록
- Ansible에게 호스트 배포를 설명하기 위해 control node에 inventory를 생성한다.

**Ansible의 특징**

- 복잡성을 줄이고 어디에서나 실행할 수 있는 오픈 소스 자동화를 제공한다.
    - 플레이북이라는 스크립트를 통해서 작업 자동화
    - 플레이북에 로컬/원격 시스템에 대한 원하는 상태를 선언하면 Ansible은 시스템이 선언한 상태를 유지하도록 보장한다.

**Ansible의 원칙**

- Agent-less architecture
    - 인프라 전반에 추가 소프트웨어를 설치할 필요가 없기에 유지 보수 부담이 적다.
    - Jenkins처럼 Managed Node에 별도의 agent 프로그램을 일일이 설치하지 않고, SSH와 같은 통신 프로토콜로 접속한다.
    - 설치하는 프로그램이 없으니 프로그램에 대한 관리 비용 등이 사라지므로 유지 보수가 훨씬 쉬워진다.
- Simplicity (단순성)
    - 자동화 플레이북의 읽기 쉬운 YAML 문법을 사용한다.
    - Ansible은 분산형 구조로, 기존 OS 자격 증명과 SSH를 통해 원격 머신에 액세스한다.
- Scalability and flexibility (확장성과 유연성)
    - 다양한 운영 체제, 클라우드 플랫폼 및 네트워크 장치를 지원하는 모듈식 설계를 통해서 자동화 시스템을 빠르고 쉽게 확장할 수 있다.
- Idempotence and predictability (멱등성과 예측 가능성)
    - 시스템이 플레이북이 선언한 상태라면, Ansible은 플레이북이 여러 번 돌아가더라도 아무것도 바꾸지 않는다.

**Ansible의 사용 사례**

- 반복 잡업 제거 및 워크플로우 단순화
- 시스템 구성 관리 및 유지 보수
- 복잡한 소프트웨어의 지속적 배포
- 무중단 롤링 업데이트

### 1-2) SSH 기반 연결 및 SSH Key 인증 방식

```
Control Node
    │
    │ private key
    │
    ├── SSH ──> Managed Node 1
    ├── SSH ──> Managed Node 2
    └── SSH ──> Managed Node 3
                  ↑
             authorized_keys
```

**인벤토리란**

- 인벤토리는 Managed node를 중앙 파일에 정리하여 Ansible에게 시스템 정보와 네트워크 위치를 제공한다.
- 인벤토리 파일을 통해서 하나의 명령으로 수많은 호스트를 관리할 수 있다.
- 인벤토리를 작성하기 위해서는 호스트 시스템에 대한 IP 주소 또는 fully qualified domain name(FQDN)이 필요하며, 각 호스트의 authorized_keys 파일에 공용 SSH 키가 추가되어 있어야 한다.
    - managed node의 authorized_keys에 control node의 공용 SSH 키가 등록되어 있는 상황이 전제되어 진행된다.
    - SSH key 인증이 정상적으로 구성된 뒤, Ansible을 올리는 방식이라고 볼 수 있다.
- 변수는 IP 주소, FQDN, 운영체제, SSH 사용자 등 managed node의 값을 설정하여 명령마다 매번 새롭게 전달할 필요가 없도록 한다.
    - 변수는 특정 호스트 또는 그룹의 모든 호스트에도 적용할 수 있다.

**ssh와 인벤토리**

- 인벤토리는 Ansible이 ssh로 어떤 managed node에, 어떤 사용자로, 어떤 방식으로 접속할지 시작하는 파일이다.
- Ansible은 control node가 ssh를 통해 managed node에 직접 접속하는데, 이때 먼저 인벤토리를 확인하여 접속할 managed node의 위치와 접속 정보를 확인한다.
    
    ```yaml
    Control Node
         │
         │  1. Inventory 확인
         │     - 어떤 서버인가?
         │     - IP/FQDN은?
         │     - SSH 사용자는?
         ▼
    Inventory
         │
         │  2. 해당 정보를 바탕으로 SSH 연결
         ▼
    Managed Node
    ```
    
- 접속할 호스트를 192.168.10.11 이라고 하고, ssh key 인증까지 포함한 방식은 아래와 같다.
    
    ```yaml
    Inventory에서 접속 정보 확인
            ↓
    192.168.10.11 / ubuntu
            ↓
    Control Node의 Private Key로 SSH 인증 시도
            ↓
    Managed Node의 ~/.ssh/authorized_keys
            ↓
    등록된 Public Key와 대응되는지 확인
            ↓
    SSH 연결 성공
            ↓
    Ansible Module 실행
    ```
    

**ssh 플러그인**

- 시스템 관리 기본 프로토콜
- Ansible에서 가장 많이 사용되는 프로토콜

**ssh 키 설정**

- 위와 동일하게 Ansible은 원격 연결 시 SSH 키를 사용한다.
- Ansible은 기본 연결 플러그인인 ssh 사용 시, SSH 키의 암호를 해독하기 위해서 사용자와 ssh 프로세스 간에 비밀번호를 수동으로 입력 받는 채널을 제공하지 않으니, `ssh-agent` 사용을 강력히 권장한다.
    - 다만 필요한 경우 `--ask-pass` 옵션으로 비밀번호 인증을 사용할 수 있다.
    - 권한 승격을 위한 비밀번호가 필요한 경우에는 `--ask-become-pass` 옵션을 사용한다.
- `ssh-agent`를 설정하는 방법
    
    ```yaml
    $ ssh-agent bash
    $ ssh-add ~/.ssh/id_rsa
    
    # .pem 파일 지정 시
    $ ssh-agent bash
    $ ssh-add ~/.ssh/keypair.pem
    ```
    
- `ssh-agent`를 사용하지 않고 개인 키 파일을 추가하는 다른 방법은 인벤토리 파일에서 `ansible_ssh_private_key_file` 변수를 사용하는 것이다.

### 1-3) `become`, `become_user`를 활용한 권한 상승

**권한 상승이란**

- Ansible은 기존 권한 상승 시스템을 사용하여 root 권한이나 다른 사용자 권한으로 태스크를 실행한다.
- 로그인한 사용자와 다른 사용자로 전환할 수 있게 해주는 기능이므로 이를 `become`이라고 한다.
- sudo, su, pfexec, doas, pbrun, dzdo, ksu, runas, machinectl 등 기존 권한 상승 도구를 사용한다.

**become 지시어**

| `become` | 권한 상승 활성화하려면 `true` 로 설정한다. |
| --- | --- |
| `become_user` | 원하는 권한을 가진 사용자로 설정한다. (기본값 root) |
| `become_method` | ancible.cfg에 설정된 기본 방식을 재정의하며, Become 플러그인 중 하나를 사용하도록 설정한다. |
| `become_flags` | 태스크나 역할에 특정 플래그 사용을 허용한다. (ex - 셸이 nologin으로 설정되어 있을 때 사용자를 nobody로 변경한다.) |
- become: true를 별도로 설정해야 become_user를 통한 권한 상승이 활성화된다.
- sudo 비밀번호를 지정하려면 ansible-playbook 실행 시 `--ask-become-pass` 옵션을 사용한다.
- become을 사용하는 플레이북을 실행했을 때 멈춘 것처럼 보인다면, 권한 상승 프롬프트에서 대기 중일 가능성이 높다. `CTRL-c`로 중단 후 적절한 비밀번호를 사용하여 다시 실행하도록 한다.

**become 예제**

- apache 사용자 권한으로
    
    ```yaml
    - name: Run a command as the apache user
      command: somecommand
      become: true
      become_user: apache
    ```
    
- nologin일 때 nobody 사용자로
    
    ```yaml
    - name: Run a command as nobody
      command: somecommand
      become: true
      become_method: su
      become_user: nobody
      become_flags: '-s /bin/sh'
    ```
    

**become 연결 변수**

- 각 Managed node나 그룹마다 다른 become 옵션을 정의할 수 있다.
- 인벤토리에 정의하거나 일반 변수로 사용할 수 있다.

| `ansible_become` | `become` 지시어를 재정의하며 권한 상승 사용 여부를 결정한다. |
| --- | --- |
| `ansible_become_method` | 사용할 권한 상승 방식을 지정한다. |
| `ansible_become_user` | 권한 상승을 통해 전환할 사용자를 설정한다. |
| `ansible_become_password` | 권한 상승 비밀번호를 설정한다. |
| `ansible_common_remote_group` | `setfacl` 및 `chown`이 모두 실패할 경우 Ansible이 임시 파일의 그룹을 특정 그룹으로 변경할지 여부를 결정한다. |

```yaml
webserver ansible_user=manager ansible_become=true
```

**become 커맨드라인 옵션**

| `--ask-become-pass` , `-K`  | 권한 상승 비밀번호를 요청한다. |
| --- | --- |
| `--become` , `-b`  | `become` 을 사용하여 작업을 실행한다. |
| `--become-method=BECOME_METHOD`  | 사용할 권한 상승 방식을 지정한다. |
| `--become-user=BECOME_USER`  | 지정한 사용자로 작업을 실행한다. |

**become의 위험 및 제한 사항**

- 일반 사용자 A가 일반 사용자 B로 전환할 때의 보안 위험
    - 원인 : A 계정으로 접속해서 B 계정의 권한으로 작업하려고 할 때, A가 만든 임시 파일(민감 데이터 포함)을 B가 읽을 수 있어야 한다.
        - A 또는 B 둘 중 하나가 root라면 문제 없다.
    - 문제 : OS 환경상 권한 공유 설정이 실패하면 Ansible이 파일 권한을 누구나 읽을 수 있는 상태로 풀어버릴 수도 있다.
    - 해결
        - root로 접속하거나, root로 전환한다.
        - 설정에서 `pipelinging = True`를 켜서 임시 파일을 생성하지 않고 바로 실행한다.
- 주요 제한 사항
    - 메서드 체이닝 불가 : 한 번에 여러 단계의 권한 상승은 지원하지 않고, 호스트 당 한 가지 전환 방식만 사용 가능하다. (ex - `sudo`와 `su` 동시 불가능)
    - 권한 상승의 일반성 : 특정 명령어 실행만 허용하는 restriction/sudoers 설정은 Ansible의 임시 파일 기반 모듈 실행 구조와 충돌하므로 제대로 동작하지 않을 수 있다.
    - 환경 변수 누락 : systemd 기반 시스템에서 become 사용 시, 새로운 로그인 세션을 완전히 차리지 않아서 일부 사용자 환경 변수가 로드되지 않을 수 있다.
    - 연결 플러그인 지원X : 일부 연결 플러그인은 become을 지원하지 않거나 무시한다.

**become 및 네트워크 자동화**

- Ansible 2.6부터 enable 모드를 지원하는 네트워크 장비에서 become을 사용할 수 있다.
    - 기존 공유 디렉토리의 authorize 및 auth_pass 옵션을 대체한다.
    - `connection: ~` 연결 타입을 설정해야 한다.

**become 및 Windows**

- Ansible 2.3부터 Windows에서는 runas 방식으로 become을 지원한다.
    - become_user 기본값이 없으므로 사용자를 반드시 지정해야 한다.

### 1-4) Connection Plugin 구조 및 Bastion / Jump Host 구성 방식 이해

**Connection plugins이란**

- Ansible에는 여러 연결 플러그인이 포함되어 있지만, 호스트 당 한 번에 하나의 플러그인만 사용할 수 있다.
- 주로 인벤토리 파일 내부에서 `ansible_connection` 변수를 통해서 지정한다.
- 플러그인의 유형 예시 : paramiko SSH, 기본 ssh, local 연결 방식 등
- 필요한 경우에는 커스텀 연결 플러그인을 생성할 수도 있다.
- 연결 플러그인을 변경하려면 `connection` 키워드를 사용하면 된다.
    
    ```yaml
    [webservers]
    web01 ansible_host=10.0.1.10 ansible_connection=ssh
    ```
    

**Connection plugins의 사용 방법**

- configuration을 통해 전역으로 설정, 커맨드 라인 옵션, 플레이 내의 키워드, 인벤토리 내의 변수로 설정할 수 있다.
- 대부분의 connection plugin은 최소한의 설정만으로 작동할 수 있다.
    - `ansible_host` : 접속할 호스트 이름
    - `ansible_port` : SSH 포트 번호 (기본값 22)
    - `ansible user` : 로그인에 사용할 기본 사용자 이름 (기본값 현재 사용자)
    - 일반 버전을 오버라이드할 수도 있다. (ex - `ansible_ssh_host`)
    
    ```yaml
    web01 ansible_host=10.0.1.10 ansible_user=ubuntu ansible_port=22
    ```
    

**Bastion host란**

- 네트워크 경계에 위치하며 외부에서 접근 가능하고, 내부 서버로 향하는 ssh 연결의 프록시 역할을 하는 서버
- AWS 같은 실제 환경에서는 보안을 위해 DB 서버나 애플리케이션 서버에 Public IP를 주지 않는 경우가 많기 때문에 중간에 둔 외부에서 접속할 수 있는 서버

```yaml
--------------Public Network--------------    ----Private Network----
|                                        |    |                     |
|Ansible Control Node -ssh-> Bastion Host+----+>Web / DB/ APP Server|
|                                        |    |                     |
------------------------------------------    -----------------------
```

- Public Network : Ansible control node → (ssh) → Bastion host
- Private Network : Bastion host → (ssh) → Server
- ssh 연결 방식
    - ProxyJump (권장)
        - ssh 자체에 있는 중간 서버를 거쳐 목적지에 접속하는 기능
        
        ```yaml
        # ansible.cfg에서 설정
        # webservers에 SSH로 접속할 때 admin@bastion.example.com을 중간 경유지로 사용하도록 설정
        [ssh_connection]
        ssh_args = -o ProxyJump=bastion_user@bastion.example.com
        ```
        
        ```yaml
        # inventory/hosts 인벤토리의 호스트 그룹별 설정
        [bastion]
        bastion01 ansible_host=bastion.example.com ansible_user=admin
        
        [webservers]
        web01 ansible_host=10.0.1.10
        web02 ansible_host=10.0.1.11
        
        [dbservers]
        db01 ansible_host=10.0.2.10
        
        [webservers:vars]
        ansible_ssh_common_args=-o ProxyJump=admin@bastion.example.com
        
        [dbservers:vars]
        ansible_ssh_common_args=-o ProxyJump=admin@bastion.example.com
        ```
        
        ```yaml
        # inventory/hosts 호스트 개별 설정
        [internal_servers]
        web01 ansible_host=10.0.1.10 ansible_ssh_common_args="-o ProxyJump=admin@bastion-east.example.com"
        web02 ansible_host=10.0.1.11 ansible_ssh_common_args="-o ProxyJump=admin@bastion-east.example.com"
        db01 ansible_host=10.0.2.10 ansible_ssh_common_args="-o ProxyJump=admin@bastion-west.example.com"
        ```
        
    - ProxyCommand (구형)
    - SSH 설정 파일 (~/.ssh/config)
    - group_vars
        
        ```yaml
        # group_vars/internal_servers.yml
        ansible_ssh_common_args: >-
          -o ProxyJump=admin@bastion.example.com
          -o StrictHostKeyChecking=no
        ansible_user: deploy
        ansible_ssh_private_key_file: ~/.ssh/internal_key
        ```
        
        ```yaml
        # 순차적인 두 개의 점프 호스트 (Multiple Jump Hosts)
        ansible_ssh_common_args="-o ProxyJump=admin@bastion1.example.com,admin@bastion2.internal"
        ```
        
        ```yaml
        # ~/.ssh/config (Multiple Jump Hosts)
        Host bastion1
            HostName bastion1.example.com
            User admin
        
        Host bastion2
            HostName bastion2.internal
            User admin
            ProxyJump bastion1
        
        Host 10.0.*
            ProxyJump bastion2
        ```
        

### 1-5) 실습

- inventory.ini
    
    ```yaml
    [managed]
    node1 ansible_host=1.201.117.194
    node2 ansible_host=1.201.116.180
    node3 ansible_host=1.201.116.156
    node4 ansible_host=1.201.118.202
    node5 ansible_host=1.201.118.10
    node6 ansible_host=1.201.118.90
    
    [managed:vars]
    ansible_user=sohyeon
    ```
    
- 아키텍쳐 구조 및 연결 확인
    
    ```yaml
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible-inventory -i inventory.ini --graph
    @all:
      |--@ungrouped:
      |--@managed:
      |  |--node1
      |  |--node2
      |  |--node3
      |  |--node4
      |  |--node5
      |  |--node6
    soso@DESKTOP-JM4DKDH:~/ansible-practice/ansible-study1$ ansible managed -i inventory.ini -m ansible.builtin.ping
    node5 | SUCCESS => {
        "ansible_facts": {
            "discovered_interpreter_python": "/usr/bin/python3"
        },
        "changed": false,
        "ping": "pong"
    }
    node4 | SUCCESS => {
        "ansible_facts": {
            "discovered_interpreter_python": "/usr/bin/python3"
        },
        "changed": false,
        "ping": "pong"
    }
    node2 | SUCCESS => {
        "ansible_facts": {
            "discovered_interpreter_python": "/usr/bin/python3"
        },
        "changed": false,
        "ping": "pong"
    }
    node1 | SUCCESS => {
        "ansible_facts": {
            "discovered_interpreter_python": "/usr/bin/python3"
        },
        "changed": false,
        "ping": "pong"
    }
    node3 | SUCCESS => {
        "ansible_facts": {
            "discovered_interpreter_python": "/usr/bin/python3"
        },
        "changed": false,
        "ping": "pong"
    }
    node6 | SUCCESS => {
        "ansible_facts": {
            "discovered_interpreter_python": "/usr/bin/python3"
        },
        "changed": false,
        "ping": "pong"
    }
    ```
    

### 1-6) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/getting_started/index.html
- https://docs.ansible.com/projects/ansible/latest/getting_started/introduction.html
- https://docs.ansible.com/projects/ansible/latest/plugins/connection.html
- https://docs.ansible.com/projects/ansible/latest/getting_started/get_started_inventory.html
- https://docs.ansible.com/projects/ansible/latest/plugins/connection.html
- https://docs.ansible.com/projects/ansible/latest/inventory_guide/connection_details.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_privilege_escalation.html
- https://oneuptime.com/blog/post/2026-02-21-how-to-use-ansible-with-jump-hosts-bastion-hosts/view