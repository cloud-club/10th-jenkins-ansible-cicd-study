# Inventory & Variables

## 1. Static Inventory: 관리 대상 정의

Inventory는 Ansible이 관리할 호스트와 그룹을 정의한다. 서버가 고정적이면 파일에 직접 작성하는 Static Inventory로 시작할 수 있다. INI와 YAML을 지원하며, 여기서는 YAML을 사용한다.

```yaml
# inventories/dev/hosts.yml
all:
  children:
    web:
      hosts:
        web01:
          ansible_host: 192.0.2.11
        web02:
          ansible_host: 192.0.2.12
    db:
      hosts:
        db01:
          ansible_host: 192.0.2.21
```

`hosts`는 호스트 목록, `children`은 하위 그룹, `vars`는 그룹 변수를 나타낸다. `web01`은 Inventory에서 사용하는 이름이고, 실제 접속 주소는 `ansible_host`다.

공식문서: [YAML inventory plugin](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/yaml_inventory.html)

모든 호스트는 기본 그룹 `all`에 속한다. `ungrouped`에는 `all` 외의 그룹에 속하지 않은 호스트가 포함된다. 하나의 호스트가 `web`, `prod`처럼 여러 그룹에 속할 수도 있다.

Inventory를 읽은 결과부터 확인한다.

```bash
ansible-inventory -i inventories/dev/hosts.yml --graph
ansible-inventory -i inventories/dev/hosts.yml --host web01
```

`--graph`는 그룹 관계를, `--host`는 해당 호스트의 Inventory 변수를 보여준다. 이 출력에 Play 실행 중 생성되는 `register` 결과까지 포함되는 것은 아니다.

공식문서: [How to build your inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html)

## 2. 환경별 변수 파일 분리

Inventory 파일 옆에 `group_vars/`와 `host_vars/`를 두면 그룹별·호스트별 변수를 분리할 수 있다.

```text
ansible-study/
├── inventories/
│   ├── dev/
│   │   ├── hosts.yml
│   │   ├── group_vars/
│   │   │   ├── all.yml
│   │   │   └── web.yml
│   │   └── host_vars/
│   │       └── web01.yml
│   └── prod/
│       ├── hosts.yml
│       └── group_vars/
│           ├── all.yml
│           └── web.yml
├── site.yml
└── templates/
```

```yaml
# inventories/dev/group_vars/all.yml
ansible_user: ubuntu
ansible_ssh_private_key_file: ~/.ssh/study_ed25519
app_env: dev
```

```yaml
# inventories/dev/group_vars/web.yml
http_port: 8080
server_name: study.local
```

```yaml
# inventories/dev/host_vars/web01.yml
server_name: web01.study.local
```

`group_vars/web.yml`은 `web` 그룹에, `host_vars/web01.yml`은 `web01`에 적용된다. 파일 이름은 실제 IP가 아니라 Inventory의 그룹명·호스트명에 맞춘다. 기본 `host_group_vars` Plugin이 이 YAML 파일들을 읽는다.

공식문서: [host_group_vars plugin](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/host_group_vars_vars.html)

`ansible-playbook`은 Inventory 기준 경로와 Playbook 기준 경로의 변수 디렉토리를 모두 찾을 수 있다. 위 구조에서는 환경별 값을 Inventory 옆에 모아 둔다. 실행할 때는 `-i inventories/dev/hosts.yml` 또는 `-i inventories/prod/hosts.yml`로 환경을 선택한다.

공식문서: [Organizing host and group variables](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html#organizing-host-and-group-variables)

## 3. Magic Variable과 Facts

| 변수 | 의미와 예 |
| --- | --- |
| `inventory_hostname` | 현재 호스트의 Inventory 이름. 예: `web01` |
| `groups` | 그룹별 호스트 이름 목록. 예: `groups['web']` |
| `group_names` | 현재 호스트가 속한 그룹 목록 |
| `hostvars` | 호스트별 변수에 접근하는 사전. 예: `hostvars['web01']['ansible_host']` |
| `ansible_facts` | 대상에서 수집한 OS, 네트워크 등의 정보 |

Inventory에서 정의한 값과 Ansible이 서버에서 수집한 Facts를 구분한다. `inventory_hostname`은 Facts를 수집하지 않아도 사용할 수 있지만, `ansible_facts['hostname']`은 실제 서버에서 수집한 호스트 이름이다.

```yaml
- name: Inspect inventory and facts
  hosts: web
  gather_facts: true
  tasks:
    - name: Show host information
      ansible.builtin.debug:
        msg:
          inventory_name: "{{ inventory_hostname }}"
          os_family: "{{ ansible_facts['os_family'] }}"
          web_hosts: "{{ groups['web'] }}"
          first_web_ip: "{{ hostvars[groups['web'][0]]['ansible_host'] }}"
```

Facts는 기본적으로 Play 시작 시 수집된다. 다른 호스트의 Facts를 `hostvars`로 읽으려면 해당 호스트의 Facts를 먼저 수집했거나 캐시에서 가져올 수 있어야 한다. 위 예제의 `ansible_host`는 Inventory 값이므로 그 조건이 필요하지 않다.

공식문서: [Discovering variables: facts and magic variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_vars_facts.html)

## 4. 변수 우선순위

같은 변수의 정의 위치가 여러 곳이면 우선순위가 높은 값이 적용된다. 자주 사용하는 정의 위치만 비교하면 다음과 같다.

```text
낮음 → 높음
Inventory의 그룹 변수 → Inventory의 호스트 변수 → Play의 vars → Extra vars(-e)
```

위 예제에서 `web01`의 `server_name`은 `web01.study.local`, `web02`는 `study.local`이다. Play의 `vars`에 같은 변수를 선언하면 이 Inventory 값들을 덮어쓴다. `-e`로 전달한 Extra vars는 변수 우선순위가 가장 높다.

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml -e '{"http_port": 9090}'
```

그룹 사이에서는 자식 그룹의 변수가 부모 그룹보다 우선한다. 동일 계층의 여러 그룹에 같은 변수를 정의하면 로딩 순서까지 영향을 주므로 중복을 줄이는 편이 이해하기 쉽다.

`-u ubuntu` 같은 일반 CLI 옵션과 `-e ansible_user=ubuntu`도 다르다. 연결 변수 `ansible_user`가 일반 CLI 옵션 `-u`보다 우선할 수 있다.

환경 공통 값은 `group_vars/all.yml`, 역할별 값은 `group_vars/<group>.yml`, 서버별 예외는 `host_vars/<host>.yml`로 나누면 같은 변수의 중복 정의를 줄일 수 있다.

공식문서: [Using variables — Variable precedence](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#understanding-variable-precedence)

## 5. Dynamic Inventory와 AWS EC2

서버가 자주 생성·삭제되는 환경에서는 파일에 IP를 직접 관리하기 어렵다. Dynamic Inventory는 클라우드 API 같은 외부 소스에서 현재 호스트 목록과 변수를 얻는다. Ansible은 Inventory Plugin과 Script를 지원하며, 공식문서는 Plugin 사용을 권장한다.

```text
AWS EC2 API 조회 → 호스트·그룹·변수 구성 → 같은 Playbook 실행
```

이는 서버를 생성하는 기능이 아니라 관리 대상을 조회하는 기능이다.

공식문서: [Working with dynamic inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_dynamic_inventory.html)

EC2에서는 `amazon.aws.aws_ec2` Plugin을 사용할 수 있다. Control Node에 `amazon.aws` Collection, 호환되는 `boto3`·`botocore`, EC2 조회 권한이 있는 AWS 인증 구성이 필요하다. 이 Collection은 `ansible-core`에 포함되지 않는다.

```bash
ansible-galaxy collection install amazon.aws
```

```yaml
# inventories/dev/study.aws_ec2.yml
plugin: amazon.aws.aws_ec2
regions:
  - ap-northeast-2
filters:
  instance-state-name: running
  tag:Environment: dev
hostnames:
  - instance-id
compose:
  ansible_host: private_ip_address
groups:
  web: "ec2_tags.get('Role', '') == 'web'"
```

파일명은 `aws_ec2.yml` 또는 `aws_ec2.yaml`로 끝나야 한다. 위 예제는 실행 중인 dev 인스턴스를 조회하고, `Role=web` 태그가 있으면 `web` 그룹에 넣는다. `hostnames`는 Inventory 이름을, `compose.ansible_host`는 접속 주소를 정한다. 변수 표현은 사용하는 Collection 버전의 문서와 맞춘다.

```bash
ansible-inventory -i inventories/dev/study.aws_ec2.yml --graph
```

AWS API 조회 성공과 SSH 접속 성공은 별개다. 위 구성은 Private IP를 사용하므로 Control Node에서 해당 네트워크에 접근할 수 있거나 [Bastion 연결](01-architecture-and-connection-management.md)을 구성해야 한다.

공식문서: [amazon.aws.aws_ec2 inventory plugin](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/aws_ec2_inventory.html)

이전: [Architecture & Connection Management](01-architecture-and-connection-management.md) · 다음: [Modules & Idempotency](03-modules-and-idempotency.md)
