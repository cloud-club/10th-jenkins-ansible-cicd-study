# Inventory & Variables

## 2. Inventory란?

---

Inventory는 **Ansible이 관리할 Host, Group, 연결 정보를 정의하는 대상 목록**이다.

> 쉽게 말해 **"어느 서버에 실행할 것인가?"**를 정의하는 곳이다.
> 

```
Inventory
├── web
│   ├── web01
│   └── web02
├── app
│   └── app01
└── db
    └── db01
```

### 2-1. Static Inventory

---

Static Inventory는 **Host와 Group 정보를 INI 또는 YAML 파일에 직접 작성해 관리하는 방식**이다.

서버 수가 적거나 대상이 자주 바뀌지 않는 환경에 적합하다.

#### INI 형식

```
[web]
web01 ansible_host=10.0.1.11
web02 ansible_host=10.0.1.12

[app]
app01 ansible_host=10.0.2.11

[all:vars]
ansible_user=deploy
```

#### YAML 형식

```yaml
all:
  children:
    web:
      hosts:
        web01:
          ansible_host: 10.0.1.11
        web02:
          ansible_host: 10.0.1.12
```

구조 확인:

```bash
ansible-inventory -i inventory.yml --graph
```

### 2-2. group_vars / host_vars

---

`group_vars`와 `host_vars`는 **Inventory 변수를 적용 범위에 따라 분리하는 디렉터리 규칙**이다.

- **group_vars**: Group 공통 변수
- **host_vars**: 특정 Host 전용 변수

```
inventories/prod/
├── hosts.yml
├── group_vars/
│   ├── all.yml
│   └── web.yml
└── host_vars/
    └── web01.yml
```

예:

```yaml
# group_vars/web.yml
http_port: 8080
worker_count: 4
```

```yaml
# host_vars/web01.yml
worker_count: 8
```

<aside>
🤔

**고민할 점:** `host_vars` 예외가 너무 많아진다면 Group 설계가 적절한지 다시 확인할 필요가 있다.

</aside>

### 2-3. Inventory Magic Variables

---

Magic Variable은 **Ansible이 실행 중 자동으로 제공하는 내부 정보 변수**다.

#### inventory_hostname

현재 실행 중인 Inventory Host 이름:

```yaml
msg: "{{ inventory_hostname }}"
```

#### groups

특정 Group의 Host 목록:

```yaml
var: groups['web']
```

#### hostvars

특정 Host의 변수 조회:

```yaml
msg: "{{ hostvars['db01']['ansible_host'] }}"
```

### 2-4. Variable Precedence

---

Variable Precedence는 **같은 변수가 여러 위치에 정의됐을 때 최종 값을 결정하는 우선순위 규칙**이다.

실무에서 우선 기억할 흐름:

```
공통 값
  ↓
Group Variable
  ↓
Host Variable
  ↓
Play / Task 근처 Variable
  ↓
--extra-vars
```

전체 규칙은 더 세분화되어 있으므로, 같은 변수를 여러 위치에서 반복해서 덮어쓰지 않는 것이 중요하다.

#### 변수 관리 원칙

- 공통 값과 Host 예외를 분리
- 동일 변수를 여러 계층에서 중복 정의하지 않기
- Secret을 평문 Variable 파일에 저장하지 않기
- 변수 이름에 의미 드러내기

### 2-5. Dynamic Inventory

---

- Dynamic Inventory는 **Ansible이 관리할 서버 목록을 파일에 직접 적어두지 않고, AWS 같은 외부 시스템에서 실시간으로 조회해서 Inventory를 구성하는 방식**입니다.
- AWS API로 현재 실행 중인 EC2 같은 리소스 정보를 조회하고, 그 결과를 Ansible의 Host/Group/Host Variable 형태로 동적으로 구성한다.
- Auto Scaling처럼 Instance가 계속 생성/삭제되는 환경에서 유용하다.

```
Static Inventory  → 파일에 서버 목록 저장
Dynamic Inventory → AWS API 등에서 현재 목록 조회
```

AWS EC2 예시:

```yaml
plugin: amazon.aws.aws_ec2
regions:
  - ap-northeast-2

filters:
  instance-state-name: running
  "tag:Environment": prod

keyed_groups:
  - key: tags.Role
    prefix: role
```

```bash
ansible-inventory -i aws_ec2.yml --graph
```

### 2-7. 여기서 생각해볼 질문

---

1. Host와 Group을 나누는 이유는?
2. `group_vars`와 `host_vars`는 언제 각각 사용하는가?
3. `groups`와 `hostvars`의 차이는?
4. 같은 변수를 여러 위치에서 덮어쓰면 어떤 문제가 생길까?
5. Auto Scaling 환경에서 Dynamic Inventory가 유리한 이유는?

### 2-8. 참고 자료

---

- [Ansible 공식 문서 - Using Variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)
- [Ansible 공식 문서 - Magic Variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_vars_facts.html)
- [Ansible 공식 문서 - Dynamic Inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_dynamic_inventory.html)
- [Ansible 공식 문서 - AWS EC2 Dynamic Inventory](https://docs.ansible.com/projects/ansible/latest/collections/amazon/aws/docsite/aws_ec2_guide.html)