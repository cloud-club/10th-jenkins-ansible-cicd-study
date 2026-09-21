# Inventory & Variables

Inventory는 단순한 서버 IP 목록이 아니라 **어떤 서버를 관리할지와 서버별 설정값을 구조화하는 기준**이다.

## 1. Host와 Group

여러 서버를 역할별 Group으로 묶을 수 있다.

```yaml
all:
  children:
    web:
      hosts:
        web01:
          ansible_host: 10.0.1.10
        web02:
          ansible_host: 10.0.1.11

    db:
      hosts:
        db01:
          ansible_host: 10.0.2.10
```

```text
all
├─ web
│  ├─ web01
│  └─ web02
└─ db
   └─ db01
```

Playbook에서 다음처럼 Group 단위로 실행할 수 있다.

```yaml
- name: Configure web servers
  hosts: web
```

Inventory 구조 확인:

```bash
ansible-inventory -i inventory.yml --graph
```

공식문서: [Building an inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html)

---

## 2. group_vars와 host_vars

서버가 많아지면 변수를 Inventory 파일에 모두 작성하지 않고 별도 파일로 분리한다.

```text
inventory/
├─ hosts.yml
├─ group_vars/
│  └─ web.yml
└─ host_vars/
   └─ web01.yml
```

`group_vars/web.yml`

```yaml
app_port: 8080
app_env: production
```

`host_vars/web01.yml`

```yaml
app_port: 9090
```

- `group_vars` : Group 전체가 공유하는 값
- `host_vars` : 특정 Host만 사용하는 값

같은 변수가 여러 위치에 있으면 Ansible의 **Variable Precedence**에 따라 최종 값이 결정된다. 실무에서는 우선순위를 이용해 계속 덮어쓰기보다 변수의 위치를 명확하게 정하는 것이 중요하다.

공식문서: [Using variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)

---

## 3. Inventory 관련 주요 변수

Ansible은 Inventory 정보를 Playbook과 Template에서 사용할 수 있게 제공한다.

| 변수 | 의미 |
|---|---|
| `inventory_hostname` | 현재 실행 중인 Host 이름 |
| `groups` | Group별 Host 목록 |
| `hostvars` | 각 Host의 변수 |

예:

```yaml
- name: Show current host
  ansible.builtin.debug:
    msg: "{{ inventory_hostname }}"
```

```jinja2
{{ groups['web'] }}
```

다른 Host의 값도 확인할 수 있다.

```jinja2
{{ hostvars['db01']['ansible_host'] }}
```

예를 들어 Web 서버 설정에 DB 서버의 IP를 자동으로 넣을 때 활용할 수 있다.

---

## 4. Dynamic Inventory

Cloud 환경에서는 서버가 계속 생성·삭제되므로 Static Inventory를 사람이 직접 수정하기 어렵다.

```text
Static Inventory
사람이 IP 추가/삭제

Dynamic Inventory
AWS API → 현재 EC2 조회 → Inventory 생성
```

AWS EC2 예:

```yaml
plugin: amazon.aws.aws_ec2

regions:
  - ap-northeast-2

filters:
  instance-state-name: running

keyed_groups:
  - key: tags.Role
    prefix: role
```

`Role=web` 같은 EC2 Tag를 기준으로 Group을 자동 구성할 수도 있다.

확인:

```bash
ansible-inventory -i inventory.aws_ec2.yml --graph
```

공식문서: [Dynamic Inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_dynamic_inventory.html), [AWS EC2 Inventory Plugin](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/aws_ec2_inventory.html)

> **핵심:** Inventory는 **어떤 서버에 실행할지**, Variables는 **각 서버에서 어떤 값을 사용할지** 결정한다.
