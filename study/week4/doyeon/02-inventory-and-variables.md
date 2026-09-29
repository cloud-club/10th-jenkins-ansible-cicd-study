# Week 4 — Inventory & Variables

## Inventory란

Inventory는 Ansible이 관리할 호스트와 그룹, 접속 정보, 변수를 정의한 목록이다. 파일 하나를 사용할 수도 있고 디렉터리, 외부 API, 클라우드 Inventory Plugin 등 여러 source를 함께 사용할 수도 있다.

```text
Inventory
├── 어떤 호스트가 있는가
├── 호스트를 어떤 그룹으로 묶는가
├── 어떻게 연결하는가
└── 각 호스트에 어떤 변수를 적용하는가
```

---

## Static Inventory

### INI 형식

```ini
[web]
web01 ansible_host=203.0.113.10
web02 ansible_host=203.0.113.11

[db]
db01 ansible_host=203.0.113.20

[production:children]
web
db

[all:vars]
ansible_user=ubuntu
```

### YAML 형식

```yaml
---
all:
  vars:
    ansible_user: ubuntu
  children:
    production:
      children:
        web:
          hosts:
            web01:
              ansible_host: 203.0.113.10
            web02:
              ansible_host: 203.0.113.11
        db:
          hosts:
            db01:
              ansible_host: 203.0.113.20
```

`all`은 모든 호스트를 포함하는 기본 그룹이고 `ungrouped`는 별도 그룹에 속하지 않은 호스트를 포함한다.

### INI와 YAML 비교

두 형식은 표현 방식만 다를 뿐 Ansible이 구성하는 Host와 Group의 결과는 같다.

| 기준 | INI | YAML |
|---|---|---|
| 장점 | 짧고 직관적이며 소규모 Inventory 작성이 빠름 | 계층 구조와 복잡한 변수를 명확하게 표현할 수 있음 |
| 단점 | Group 계층이나 중첩 변수가 많아지면 구조 파악이 어려움 | 들여쓰기 오류에 민감하고 단순 구성도 길어짐 |
| 적합한 환경 | 학습, 서버 수가 적은 Static Inventory | 환경·역할별 Group이 많거나 구조화된 변수가 필요한 프로젝트 |
| 변수 표현 | 한 줄 표현이 간단하지만 자료형 해석이 직관적이지 않을 수 있음 | List와 Dictionary 같은 자료형을 자연스럽게 표현 가능 |

서버 한두 대로 연결을 실습할 때는 INI가 간결하다.

```ini
[web]
web01 ansible_host=203.0.113.10
web02 ansible_host=203.0.113.11
```

Group의 부모·자식 관계와 구조화된 변수가 많아지면 YAML이 읽기 쉽다.

```yaml
---
all:
  children:
    production:
      children:
        web:
          hosts:
            web01:
              ansible_host: 203.0.113.10
            web02:
              ansible_host: 203.0.113.11
          vars:
            app_ports:
              - 8080
              - 8081
```

Playbook이 YAML이라는 이유만으로 Inventory도 반드시 YAML을 사용할 필요는 없다. 작은 실습에서는 INI로 시작하고, Group 계층과 변수가 복잡해질 때 YAML로 전환할 수 있다. 팀에서는 구성원이 익숙한 형식 하나를 정해 일관되게 사용하는 것이 중요하다.

형식을 바꾸거나 Inventory를 수정한 뒤에는 Ansible이 해석한 최종 구조를 확인한다.

```bash
ansible-inventory -i inventory.ini --graph
ansible-inventory -i inventory.yml --graph
```

---

## Host와 Group 설계

그룹은 서버의 역할과 환경을 표현한다.

```text
기능: web, api, db
환경: development, staging, production
위치: seoul, tokyo
```

한 호스트는 여러 그룹에 속할 수 있다. 예를 들어 `web01`은 `web`, `production`, `seoul` 그룹에 동시에 속할 수 있다.

운영과 개발 환경을 실수로 함께 변경하지 않도록 Inventory 자체를 환경별로 분리하는 방법도 있다.

```text
inventories/
├── development/
│   └── hosts.yml
└── production/
    └── hosts.yml
```

---

## `group_vars`와 `host_vars`

Inventory 한 줄에 모든 변수를 적으면 관리하기 어렵다. 공통 값은 `group_vars`, 개별 호스트 값은 `host_vars`로 분리한다.

```text
inventories/production/
├── hosts.yml
├── group_vars/
│   ├── all.yml
│   └── web.yml
└── host_vars/
    └── web01.yml
```

```yaml
# group_vars/all.yml
---
ansible_user: ubuntu
timezone: Asia/Seoul
```

```yaml
# group_vars/web.yml
---
http_port: 80
app_environment: production
```

```yaml
# host_vars/web01.yml
---
http_port: 8080
```

`web01`에서는 더 구체적인 `host_vars/web01.yml`의 `http_port: 8080`이 그룹 값보다 우선한다.

비밀번호나 Secret Key는 평문 변수 파일에 넣지 않는다. 필요하면 Ansible Vault를 사용한다.

---

## Inventory 관련 Magic Variable

Magic Variable은 Ansible이 자동으로 제공하는 예약 변수이므로 같은 이름으로 직접 만들지 않는다.

### `inventory_hostname`

현재 실행 중인 호스트의 Inventory 이름이다. Facts 수집 여부와 관계없이 사용할 수 있다.

```yaml
- name: Show inventory name
  ansible.builtin.debug:
    msg: "current host={{ inventory_hostname }}"
```

### `groups`

그룹 이름을 key, 해당 그룹의 호스트 목록을 value로 제공한다.

```yaml
- name: Show all web hosts
  ansible.builtin.debug:
    var: groups['web']
```

### `hostvars`

다른 호스트에 연결된 변수를 조회한다.

```yaml
- name: Show web01 address
  ansible.builtin.debug:
    msg: "{{ hostvars['web01']['ansible_host'] }}"
```

다른 호스트의 Facts를 참조하려면 해당 호스트의 Facts가 먼저 수집되었거나 Fact Cache에 있어야 한다.

### `group_names`

현재 호스트가 속한 그룹 목록이다.

```yaml
- name: Show groups for current host
  ansible.builtin.debug:
    var: group_names
```

---

## Variable을 정의하는 위치

변수는 Inventory, `group_vars`, `host_vars`, Play, Task, Role, 실행 명령 등 여러 위치에 정의할 수 있다.

```yaml
- name: Configure Nginx
  hosts: web
  vars:
    http_port: 80
```

같은 이름을 여러 곳에 정의하면 Variable Precedence에 따라 한 값이 선택된다.

```text
낮음                                            높음
Role defaults → Group vars → Host vars → Play/Task vars → Extra vars
```

`--extra-vars`, `-e`로 전달한 변수는 항상 높은 우선순위를 가진다. 다만 우선순위에 의존해 같은 변수를 여러 곳에서 재정의하면 실제 값을 추적하기 어렵다.

```bash
ansible-playbook site.yml -e "http_port=8080"
```

### 실습: 같은 변수의 최종값 확인

하나의 `app_port` 변수를 범위별로 다르게 정의했다.

```yaml
# group_vars/all.yml
app_port: 8000
```

```yaml
# group_vars/production.yml
app_port: 8080
```

```yaml
# group_vars/web.yml
app_port: 8081
```

```yaml
# host_vars/vm01.yml
app_port: 9090
```

`vm01`은 `all → production → web` 순서의 Group에 속하고 Host 변수도 가진다. Inventory 범위 안에서는 더 구체적인 값이 앞의 값을 덮어쓴다.

```text
group_vars/all.yml         8000
          ↓
group_vars/production.yml  8080
          ↓
group_vars/web.yml         8081
          ↓
host_vars/vm01.yml         9090  ← 최종값
```

Ansible이 `vm01`에 적용할 최종 변수를 확인했다.

```bash
ansible-inventory -i inventory.local.yml --host vm01
```

결과에서 `app_port: 9090`을 확인했다. 실행 시 `--extra-vars`로 값을 전달하면 Host 변수보다도 우선한다.

```bash
ansible-playbook \
  -i inventory.local.yml \
  show-inventory-vars.yml \
  --extra-vars '{"app_port": 10000}'
```

해당 실행에서는 `app_port`가 `10000`으로 출력되고, `--extra-vars` 없이 다시 실행하면 파일을 수정한 것이 아니므로 `9090`으로 돌아온다.

```text
Group vars < Host vars < Extra vars
```

### 변수 관리 전략

- 공통 기본값은 `group_vars/all.yml`에 둔다.
- 역할이나 환경별 값은 해당 `group_vars`에 둔다.
- 예외적인 호스트 값만 `host_vars`에 둔다.
- Role의 변경 가능한 기본값은 `roles/<role>/defaults/main.yml`에 둔다.
- 실행 때 반드시 정해야 하는 값만 `--extra-vars`로 전달한다.
- 같은 의미의 변수는 가능한 한 한 곳에서 정의한다.
- 민감한 값은 Vault 또는 외부 Secret 저장소로 관리한다.

최종 값은 다음 명령으로 확인할 수 있다.

```bash
ansible-inventory -i inventories/production --host web01
```

---

## Dynamic Inventory

Static Inventory는 서버가 자주 생성되고 사라지는 클라우드 환경에서 쉽게 오래된 정보가 된다. Dynamic Inventory Plugin은 AWS 같은 외부 시스템에서 현재 서버 목록을 조회해 Inventory를 구성한다.

```text
AWS EC2 API
    ↓ 인스턴스와 태그 조회
amazon.aws.aws_ec2 Inventory Plugin
    ↓ 그룹과 변수 구성
Ansible Inventory
```

개념적인 Inventory source는 다음과 같다.

```yaml
# inventory.aws_ec2.yml
---
plugin: amazon.aws.aws_ec2
regions:
  - ap-northeast-2
filters:
  instance-state-name: running
keyed_groups:
  - key: ec2_tags.Role
    prefix: role
```

```bash
ansible-inventory -i inventory.aws_ec2.yml --graph
```

AWS 자격 증명을 저장소에 직접 작성하지 않고 AWS CLI profile, 환경 변수, IAM Role 등 표준 인증 방식을 사용한다. 

---

## 참고 자료

- [How to build your inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html)
- [Using variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)
- [Facts and magic variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_vars_facts.html)
- [Working with dynamic inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_dynamic_inventory.html)
- [amazon.aws.aws_ec2 Inventory Plugin](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/aws_ec2_inventory.html)
