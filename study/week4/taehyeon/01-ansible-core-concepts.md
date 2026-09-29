# Ansible 핵심 개념

### Ansible 이란?

> 복잡성을 줄이고 어디에서나 실행되는 오픈 소스 자동화를 제공합니다
인프라를 자동화 한다는 것
> 

| 항목 | **Ansible** | **Terraform** |
| --- | --- | --- |
| 목적 | **구성 관리(Configuration Management)** | **인프라 프로비저닝(Infrastructure Provisioning)** |
| 상태 관리 | **상태를 따로 저장하지 않음 (stateless)** | **상태(state)를 저장하고 비교 (stateful)** |
| 언어 | YAML (Playbook) | HashiCorp Configuration Language (HCL) |
| 실행 방식 | **SSH나 에이전트 없이** 대상 서버에 직접 명령 실행 | **API 기반**으로 리소스 생성 (AWS, Azure 등) |
| 주요 사용처 | **서버 설정, 패키지 설치**, 데몬 재시작, **배포** 등 | VM 생성, 네트워크 구성, 클라우드 리소스 구축 |
| idempotency (중복 실행해도 상태 동일) | 지원하지만 명시적으로 관리해야 함 | 기본적으로 강력하게 지원 |
| 배포 방식 | 푸시(Push 방식) – 제어 서버에서 대상 서버로 실행 | 풀(Pull 방식) – 클라우드 API와 상태 비교하여 갱신 |

Terraform은 클라우드 인프라 전체를 구성하는 설계자

Ansible은 이미 만들어진 서버나 시스템을 설정/운영하는 도구

### Terraform

- 클라우드 등에 api로 접근해 가상서버, 네트워크, 보안그룹 등 인프라를 새로 구성하는 것을 자동화 하는 것
- 상태를 저장해 변경을 추적하고 재적용 가능
- 주로 처음부터 인프라를 구성할 때 사용

```
terraform/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
├── terraform.tfvars
└── modules/
    ├── vpc/
    ├── ec2/
    └── rds/
```

### Ansible

- 이미 존재하는 서버에 접속하여 작업을 실행
- 운영체제 설정, 패키지 설치, 설정 배포, 서비스 재시작 등 구성 관리
- SSH 기반 푸시 방식, 별도 에이전트 설치 불필요
- 운영 자동화에 적합
- 멱등성을 지원한다고 하지만, 절대적인 보장은 아님

### Ansible 구조

---

#### 컨트롤 노드(제어노드)

- Ansible이 설치된 서버
- 컨트롤 노드는 Master라고 이 게시글에서 칭함
- 모든 명렁어를 실행하며, Worker 서버에 SSH로 접속
- 컨트롤 노드(제어 노드) SSH 키를 생성하고, 관리 노드들에게 SSH 공개 키 전송

#### 관리 노드

- Ansible이 SSH로 접속하여 명령을 실행하는 대상 서버들
- 관리 노드는 Worker라고 이 게시글에서 칭함

#### 인벤토리 (Inventory)

- 관리 대상 서버들의 IP/Host 목록들을 정의한 파일
- .ini or yaml로 관리된다

```yaml
# inventory.ini

[webservers]
192.168.10.101
192.168.10.102

[dbservers]
192.168.10.201 ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/id_rsa
---
[master]
10.10.10.10

[worker]
100.100.100.1
100.100.100.2
100.100.100.3
```

### 흐름

- 플레이북 → 여러개의 task 구성 → apt, copy, service 등 모듈 호출 → Control Node가 대상 Managed Node에 접속

#### 플레이북(playbook)

- YAML 문법으로 작성된 작업 시나리오
- 여러 Task를 순차적으로 정의
- 관리 노드에서 실행할 모듈
- 자동화 작업을 순차적으로 정의하는 파일

```yaml
# playbook.yml
- name: 웹 서버 세팅
  hosts: webservers    # 인벤토리 그룹 이름
  become: true         # sudo 권한 사용 (루트 권한으로 실행)
  tasks:
    - name: apt 업데이트
      apt:             # ansible 내장 모듈인 apt
        update_cache: yes
        
    - name: nginx 설치
      apt:
        name: nginx
        state: present # state: present 패키지 설치에 사용
                       # 이미 설치되어 있으면 아무 일도 하지 않고, 설치되어 있지 않으면 설치
                       
    - name: nginx 서비스 실행
      service:
        name: nginx
        state: started # 실행 중이라면 패스, 실행 중이지 않다면 실행
        enabled: true  # 서버가 부팅될 때 이 서비스가 자동으로 시작되도록 설정
```

#### 작업(Task)

- 플레이북에서 선언된 모듈 실행 단위
- Playbook 내에서 실행되는 단일 작업
- 하나의 작업은 하나의 모듈 호출과 그에 필요한 매개변수 옵션을 제공
- task 하나가 서버에 대한 단일행동을 수행

#### 모듈

- apt, yum, copy, file 등과 같이 특정 작업을 수행하는 단위 기능
- 내부적으로 python으로 구현된 작업 단위 코드
- 사용자가 YAML로 모듈을 호출하면, Ansible이 해당 python 코드를 원격 서버에 전송하고 실행
- 모듈은 호스트에 패키지를 설치하고, 데이터베이스 사용자를 관리
- 하나의 모듈은 하나의 작업을 실행할 수 있고, 플레이북을 이용해 여러 모듈을 선언해 여러 작업을 수행할 수 있음

```yaml
tasks:
    - name: Nginx 설치
      ansible.builtin.apt:
        name: nginx
        state: present

    - name: Nginx 설정 파일 복사
      ansible.builtin.copy:
        src: ./nginx.conf
        dest: /etc/nginx/nginx.conf
      notify: Restart Nginx

    - name: Nginx 실행
      ansible.builtin.service:
        name: nginx
        state: started
        enabled: true
```

#### 역할

- Playbook을 더 구조화한 형태
- 관련된 task, variable, handler, template, file등을 하나의 폴더 구조로 묶은 것
- 규모가 커졌을 때 코드 재사용, 역할별 분리, 유지보수가 훨씬 쉬워짐

```yaml
Terraform
├── EC2 생성
├── RDS 생성
├── VPC 구성
└── Security Group 구성

Ansible
├── nginx 설치
├── Java 설치
├── 애플리케이션 설정
└── 모니터링 구성

roles/
└── nginx/
    ├── tasks/
    │   └── main.yml           # 실행할 작업들
    ├── handlers/
    │   └── main.yml           # 조건부로 실행되는 작업들 (예: 서비스 재시작)
    ├── vars/
    │   └── main.yml           # 변수 정의
    ├── templates/
    │   └── nginx.conf.j2      # 템플릿 파일
    ├── files/
    │   └── index.html         # 복사할 정적 파일
    └── meta/
        └── main.yml           # 메타 정보 (의존성 등, 생략 가능)
```

#### 핸들러

- Handler는 일반 Task와 유사하지만, 명시적으로 ‘호출될 때만’ 실행 됨
- Task가 실제로 변경을 일으켰을 때만 실행되는 후속 작업
- 보통 notify와 함께 사용된다. ( ex. 설정 파일을 바꾸면 nginx를 재시작)
- 하나의 플레이북 내에서 여러 작업이 특정 handler를 호출할 수 있음

```yaml
# Handler
- name: nginx 설정 파일 배포
  temmplate:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  notify: restart nginx
```