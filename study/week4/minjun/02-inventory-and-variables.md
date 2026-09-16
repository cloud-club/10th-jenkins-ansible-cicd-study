# Inventory & Variables

## Static Inventory

관리 대상 호스트 목록을 정의하는 파일이다. INI 또는 YAML 형식을 쓰며, `-i` 옵션으로 지정한다.

```ini
[webservers]
node1 ansible_host=127.0.0.1 ansible_port=2221
node2 ansible_host=127.0.0.1 ansible_port=2222

[dbservers]
node3 ansible_host=127.0.0.1 ansible_port=2223

[all:vars]
ansible_user=root
ansible_python_interpreter=/usr/bin/python3
```

### 기본 그룹

- `all` — 모든 호스트가 자동으로 속한다
- `ungrouped` — 어떤 그룹에도 속하지 않은 호스트

### 그룹의 그룹

```ini
[production:children]
webservers
dbservers
```

호스트는 여러 그룹에 동시에 속할 수 있다. 역할별(web, db)과 환경별(prod, stage)로 교차 분류하는 것이 일반적이다.

### 주요 연결 변수

| 변수 | 역할 |
|---|---|
| `ansible_host` | 실제 접속 주소 |
| `ansible_port` | SSH 포트 |
| `ansible_user` | 접속 계정 |
| `ansible_python_interpreter` | 대상의 파이썬 경로. 생략 시 자동 탐색하며 경고를 남긴다 |
| `ansible_ssh_common_args` | SSH 클라이언트에 그대로 전달되는 옵션 |

## 변수 정의 위치

| 위치 | 적용 범위 |
|---|---|
| `group_vars/<그룹명>.yml` | 해당 그룹의 모든 호스트 |
| `host_vars/<호스트명>.yml` | 특정 호스트 |
| Inventory의 `[group:vars]` | 해당 그룹 |
| Playbook `vars:` | Play 범위 |
| Task `vars:` | 해당 태스크 |
| `--extra-vars` (`-e`) | 최우선 |

`group_vars/`와 `host_vars/`는 Playbook 또는 Inventory 파일과 같은 디렉터리에 두면 자동으로 로드된다.

## 실습: 변수 우선순위

`group_vars/all.yml`
```yaml
app_dir: /opt/default
env_name: study
```

`group_vars/webservers.yml`
```yaml
app_dir: /opt/webapp
app_port: 8080
```

확인용 Playbook을 실행한 결과:

```
ok: [node1] => { "msg": "app_dir=/opt/webapp env=study" }
ok: [node2] => { "msg": "app_dir=/opt/webapp env=study" }
```

### 해석

- `app_dir`은 양쪽에 정의되어 있는데 **더 구체적인 그룹인 `webservers` 쪽이 이겼다.**
- `env_name`은 `webservers.yml`에 없으므로 `all.yml`에서 올라왔다.
- 변수는 덮어쓰기 방식이며 범위가 좁을수록 우선한다.

### 전체 우선순위

공식 문서 기준으로 20단계가 넘는다. 실무에서 기억할 기준은 다음 정도다.

1. `-e`(extra-vars)는 **항상 최상위**다. 다른 무엇으로도 덮을 수 없다.
2. Task 범위 > Play 범위 > Inventory 범위
3. `host_vars` > `group_vars`
4. 구체적인 그룹 > `all`

복잡한 구성에서는 같은 변수를 여러 곳에 정의하지 않는 편이 안전하다. 우선순위를 외우는 것보다 정의 위치를 하나로 통일하는 쪽이 사고를 줄인다.

## Inventory 관련 특수 변수

| 변수 | 내용 |
|---|---|
| `inventory_hostname` | Inventory에 정의된 호스트 이름 |
| `inventory_hostname_short` | 도메인을 제외한 짧은 이름 |
| `group_names` | 이 호스트가 속한 그룹 목록 |
| `groups` | 전체 그룹과 소속 호스트 딕셔너리 |
| `hostvars` | **다른 호스트의 변수에 접근** |
| `ansible_play_hosts` | 현재 Play의 대상 호스트 목록 |

### 실습: `groups`와 `hostvars`

Jinja2 템플릿에서 다른 호스트의 정보를 참조했다.

```jinja
server_name = {{ inventory_hostname }}

{% for host in groups['webservers'] %}
peer = {{ host }} ({{ hostvars[host]['ansible_host'] }}:{{ hostvars[host]['ansible_port'] }})
{% endfor %}

# 전체 호스트 수: {{ groups['all'] | length }}
```

node1에 생성된 파일:

```
# node1 설정
server_name = node1
environment  = study
port         = 8080

# 같은 그룹의 다른 서버들
peer = node1 (127.0.0.1:2221)
peer = node2 (127.0.0.1:2222)

# 전체 호스트 수: 2
```

node2에도 같은 템플릿으로 생성했는데 `server_name`만 `node2`로 바뀌고 peer 목록은 동일했다.

### 확인한 것

**각 서버가 다른 서버의 정보를 알고 있다.** 이것이 `hostvars`의 핵심이다. 실무에서 다음과 같은 경우에 쓴다.

- 로드밸런서 설정에 백엔드 서버 목록 자동 생성
- 클러스터 노드가 서로의 주소를 알아야 하는 경우(etcd, Cassandra 등)
- 모니터링 에이전트 설정에 수집 대상 나열

호스트 목록을 사람이 설정 파일마다 적는 대신 **Inventory 하나를 진실의 원천으로 두고 파생시키는** 구조다.

`groups['all'] | length`가 2로 나온 점에 주의한다. `hosts: webservers`로 실행했기 때문에 Play 대상이 2대이고, 이 시점의 `groups`는 Play 범위를 반영한다.

## Dynamic Inventory

### 왜 필요한가

Static Inventory는 호스트 목록이 고정된 환경을 전제한다. 그런데 클라우드 환경에서는 오토스케일링으로 인스턴스가 수시로 생성·삭제되고, IP도 매번 달라진다. 목록을 사람이 관리하는 것이 불가능해진다.

Dynamic Inventory는 **인벤토리를 파일이 아니라 조회 결과로 만든다.** 인벤토리 플러그인이 실행 시점에 클라우드 API를 호출해 호스트 목록을 구성한다.

이번 실습은 로컬 컨테이너를 대상으로 했으므로 Static Inventory만 사용했다. 구조만 정리한다.

### 구성 예 (AWS EC2)

`inventory_aws_ec2.yml`
```yaml
plugin: amazon.aws.aws_ec2
regions:
  - ap-northeast-2
keyed_groups:
  - key: tags.Role
    prefix: role
  - key: placement.availability_zone
    prefix: az
filters:
  instance-state-name: running
```

```bash
ansible-inventory -i inventory_aws_ec2.yml --graph
```

- `plugin`이 조회 방식을 결정한다. AWS, Azure, GCP, VMware, OpenStack 등 대부분의 인프라에 플러그인이 있다.
- `keyed_groups`는 태그나 속성을 기준으로 그룹을 자동 생성한다. `Role=web` 태그가 붙은 인스턴스는 `role_web` 그룹이 된다.
- `filters`로 조회 범위를 제한한다.

### 확인할 점

- **인프라의 상태가 곧 인벤토리가 된다.** 새 인스턴스가 뜨면 다음 실행부터 자동으로 대상에 포함된다.
- 그룹 분류의 기준이 태그가 되므로, 태그 정책이 곧 배포 정책이 된다.
- 조회에 API 권한이 필요하다. Control Node가 클라우드 자격 증명을 갖게 되므로, 그 자격 증명의 권한 범위가 곧 Ansible의 영향 범위다.
- 캐시를 설정하지 않으면 실행마다 API를 호출한다.

## 참고 자료

- [Ansible 공식 문서 - How to build your inventory](https://docs.ansible.com/ansible/latest/inventory_guide/intro_inventory.html)
- [Ansible 공식 문서 - Using Variables](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html)
- [Ansible 공식 문서 - Variable precedence](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
- [Ansible 공식 문서 - Working with dynamic inventory](https://docs.ansible.com/ansible/latest/inventory_guide/intro_dynamic_inventory.html)
