# 01-Role-Based-Architecture

## 1. Role이 필요한 이유

---

> 
> 
> 
> Role은 **Playbook의 Task, Handler, Variable, Template, File 등을 기능 단위로 묶어 재사용할 수 있게 만든 구조**
> 

Playbook이 커지면 하나의 YAML 파일에 설치, 설정, 배포, 재시작 로직이 모두 섞이기 쉽다. Role을 사용하면 책임별로 분리해 여러 환경과 프로젝트에서 다시 사용할 수 있다.

- **Playbook = 어떤 Role을 어떤 Host에 어떤 순서로 적용할지 정의**

```
- hosts: web
  become: true

  roles:
    - common
    - nginx
    - app
```

- **Role = 특정 기능을 수행하는 재사용 가능한 자동화 단위**

```
site.yml - playbook 파일 이름
  │
  ├── common Role
  ├── nginx Role
  └── app Role
        │
        ├── tasks
        ├── handlers
        ├── templates
        └── variables
```

### 1-1. Role 기본 디렉터리 구조

---

```
roles/
└── app/
    ├── tasks/
    │   └── main.yml
    ├── handlers/
    │   └── main.yml
    ├── templates/
    │   └── application.yml.j2
    ├── defaults/
    │   └── main.yml
    ├── vars/
    │   └── main.yml
    ├── files/
    │   └── app.service
    └── meta/
        └── main.yml
  
  -----------------------------------------------------------------
  
java Role
→ JDK 설치
→ JAVA_HOME 설정

nginx Role
→ nginx 설치
→ nginx.conf 배포
→ nginx 실행

mysql Role
→ MySQL 설치
→ 설정 파일 배포
→ MySQL 실행

-----------------------------------------------------------------

# roles/nginx/tasks/main.yml

- name: nginx 설치
  ansible.builtin.apt:
    name: nginx
    state: present
    update_cache: true

- name: nginx 설정 파일 배포
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  notify: restart nginx

- name: nginx 실행
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: true
```

- **tasks/**: Role이 실제로 수행할 Task
- **handlers/**: `notify`로 호출되는 후속 Task
- **templates/**: Jinja2 Template
- **defaults/**: 외부에서 쉽게 Override할 기본값
- **vars/**: Role 내부에서 강하게 유지할 Variable
- **files/**: 변환 없이 복사할 정적 파일
- **meta/**: Role 메타데이터와 의존성

모든 디렉터리가 반드시 필요한 것은 아니다. 필요한 기능만 만들어 사용하면 된다.

### 1-2. defaults/main.yml vs vars/main.yml

---

둘 다 Role Variable을 정의하지만 **Override 우선순위가 다르다.**

- `defaults/main.yml`은 Role Variable 중 우선순위가 가장 낮아 Inventory, Play Variable, Extra Vars 등으로 쉽게 덮어쓸 수 있다.

```yaml
# roles/app/defaults/main.yml
app_port: 8080
app_log_level: INFO
```

- `vars/main.yml`은 우선순위가 높아 일반적인 Inventory Variable보다 덮어쓰기 어렵다.

```yaml
# roles/app/vars/main.yml
app_install_dir: /opt/myapp
```

- 실무에서는 `vars/main.yml`을 무조건 많이 사용하는 것보다, 재사용성을 위해 `defaults`와 Inventory Variable을 적극적으로 사용하는 편이 관리하기 쉽다.

정리 :  

- default, vars 둘 다 role 변수를 관리한다
- 우선순위 ( vars > default)
- 실무에서 재활용을 위해 default와 inventory를 적극적으로 사용하는 것이 관리하기 쉽다
    - role에 변수가 하드로 박혀있으면 환경에 따라 role 자체를 수정해야 하기 떄문에

### 1-3. Role을 Playbook에서 사용하는 방법

---

가장 기본적인 방식은 `roles:`에서 호출하는 것이다.

```yaml
- name: Configure application servers
  hosts: app
  become: true

  roles:
    - common
    - nginx
    - app
```

Role마다 Variable을 전달할 수도 있다. → role에 변수를 다르게해서 재활용

```yaml
roles:
  - role: app
    vars:
      app_port: 8081
```

### 1-4. include_role vs import_role

---

- 둘 다 Playbook 이나 Task 실행 중 Role을 실행할 떄 사용하는 방법이지만, 시점이 다르다

| 구분 | include_role | import_role |
| --- | --- | --- |
| 방식 | 동적 Include | 정적 Import |
| 처리 시점 | 실행 시점 | Playbook Parse 시점 |
| 주요 용도 | 조건에 따라 Role을 선택적으로 실행 | 구조가 고정된 Role을 미리 포함 |
- import_role(static import)

```yaml
tasks:
  - name: nginx role 실행
    ansible.builtin.import_role:
      name: nginx
```

```
site.yml 읽음 -> playbook을 읽음
   ↓
import_role: nginx 발견
   ↓
roles/nginx/tasks/main.yml 내용을 미리 가져옴
   ↓
전체 실행 계획 생성
   ↓
실행
```

- include_role(dynamic include)

```yaml
tasks:
  - name: nginx role 실행
    ansible.builtin.include_role:
      name: nginx
```

```yaml
Playbook 실행
   ↓
Task 1 실행
   ↓
Task 2 실행
   ↓
include_role: nginx 도달
   ↓
그때 nginx Role 로딩
   ↓
nginx Role 실행
```

둘의 가장 큰 차이는

- import : playbook을 해석할 때 role의 task를 미리 펼쳐놓는 것
- include : playbook을 실행하고 해당 role task에 도달했을 때 불러옴

### 1-5. Ansible Galaxy와 requirements.yml

---

> Ansible Galaxy는 Role과 Collection을 배포하고 설치할 수 있는 생태계다.
> 
- **Ansible Galaxy = 다른 사람이 만든 Role/Collection을 공유하고 가져오는 저장소**
- **requirements.yml = 우리 프로젝트가 어떤 Role/Collection을 어떤 버전으로 필요로 하는지 적는 의존성 파일**

프로젝트가 사용하는 외부 의존성을 `requirements.yml`에 선언하면 Jenkins나 다른 Control Node에서도 동일한 의존성을 설치할 수 있다.

```yaml
---
roles:
  - name: geerlingguy.java
    version: "2.0.0"

collections:
  - name: amazon.aws
  - name: community.general
```

설치 방법

```bash
ansible-galaxy install -r requirements.yml
```

- Collection만 별도로 설치할 수도 있다.

```bash
ansible-galaxy collection install -r requirements.yml
```

- requirements.yml
    - 우리 프로젝트에 필요한 의존성을 선언해 두는 곳

```yaml
roles:
  - name: geerlingguy.nginx
    version: 3.1.4

collections:
  - name: amazon.aws
    version: 10.1.2
```

collection : 

- role 보다 더 큰 배포 단위

```
Collection
├── roles
├── modules
├── plugins
├── filters
└── 기타 Ansible 기능
```

### 1-6. 예제 프로젝트 구조

---

```
ansible/
├── ansible.cfg
├── requirements.yml
├── inventories/
│   ├── dev/
│   │   ├── hosts.yml
│   │   └── group_vars/
│   └── prod/
│       ├── hosts.yml
│       └── group_vars/
├── playbooks/
│   └── deploy.yml
└── roles/
    ├── common/
    ├── nginx/
    └── app/
```

### 1-7.  여기서 생각해볼 질문

---

1. Playbook과 Role의 책임은 어떻게 다른가?
    
    <aside>
    
    playbook은 어떤 role/task를 어떤 순서로 실행할지 정의하는 시나리오
    role을 너무 잘게 나누면 구조가 복잡해지고, 재사용성과 가독성이 떨어질 수 있다. 따라서 role을 책임 단위로 묶어 사용한다.
    
    </aside>
    
2. 환경별로 달라지는 값을 `vars/main.yml`보다 `defaults/main.yml`에 두는 이유는?
3. `include_role`과 `import_role`은 어떤 상황에서 구분해 사용할까?
    
    <aside>
    
    실행 전에 role이 확정 됐냐 안됐냐에 따라 갈린다.
    
    - import_role은 playbook을 해석하는 시점에 task를 미리 포함하므로 정적인 서버 구성에 적합
    - include_role은 `server_type == "web"`일 때만 nginx Role을 실행하거나, loop로 여러 Role을 동적으로 호출할 때 적합
    </aside>
    
4. 외부 Role/Collection 버전을 `requirements.yml`로 관리해야 하는 이유는?
    
    <aside>
    
    환경마다 같은 의존성 버전을 사용해서 실행 결과를 재현 가능하게 만들기 위해서
    
    </aside>
    
5. Role을 너무 잘게 나누면 어떤 문제가 생길 수 있을까?

### 1-8. 참고 자료

---

- [Ansible 공식 문서 - Roles](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html)
- [Ansible 공식 문서 - Variable Precedence](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)
- [Ansible 공식 문서 - import_role](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/import_role_module.html)
- [Ansible 공식 문서 - include_role](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/include_role_module.html)
- [Ansible 공식 문서 - Galaxy](https://docs.ansible.com/projects/ansible/latest/galaxy/user_guide.html)