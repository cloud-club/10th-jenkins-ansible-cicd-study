# Role-Based Architecture

## 1. 왜 Role로 나눌까?

웹 서버를 준비하려면 패키지를 설치하고, 설정 파일을 만들고, 서비스를 시작해야 한다. 서버가 몇 대 없을 때는 이 작업을 하나의 Playbook에 적어도 충분하다. 하지만 dev와 prod에서 같은 작업을 반복하기 시작하면 복사한 Playbook들을 함께 수정해야 한다.

**Role은 함께 쓰이는 작업과 파일을 하나로 묶어 재사용하는 단위다.** 웹 서버 설치 작업을 `study_web` Role에 모아 두면, Playbook에서는 “어느 서버에 이 Role을 적용할지”만 정할 수 있다. 환경마다 다른 포트나 배포 버전은 변수로 전달한다.

이번 주차에서는 이 구조를 출발점으로 배포 자동화를 확장한다.

```text
01 작업을 Role로 묶기 → 02 Secret을 안전하게 전달하기
                     → 03 여러 서버의 실행 순서 정하기
                     → 04 한 대씩 배포하고 실패 시 복구하기
                     → 05 Jenkins에서 실행하기
```

01 → 05 순서로 읽으면 앞에서 배운 개념이 이어진다. 다만 모든 코드 블록을 차례대로 실행하는 구성은 아니다. **01은 기본 서비스 실습, 02·03은 기능별 예제, 04·05는 앞의 내용을 연결한 배포 예제**다. 선택해서 사용하는 코드에는 별도로 설명을 붙였다.

공식문서: [Roles](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html)

## 2. Role 안에는 무엇을 넣을까?

Role의 디렉토리 이름은 각 파일의 용도를 나타낸다. 먼저 `tasks`에서 실행할 작업을 읽고, 그 작업이 사용하는 변수와 파일을 나머지 디렉토리에서 찾는다고 생각하면 된다.

```text
ansible-study/
├── ansible.cfg
├── site.yml
├── requirements.yml
├── inventories/dev/
│   ├── hosts.yml
│   └── group_vars/web.yml
└── roles/study_web/
    ├── tasks/main.yml
    ├── handlers/main.yml
    ├── templates/nginx.conf.j2
    ├── defaults/main.yml
    ├── vars/main.yml
    ├── files/
    └── meta/main.yml
```

| 디렉토리 | 담는 내용 | 웹 서버 예시 |
| --- | --- | --- |
| `tasks/` | 실행할 작업 | Nginx 설치, 설정 파일 배치 |
| `handlers/` | 변경 알림을 받았을 때 실행할 작업 | 설정 변경 후 Nginx reload |
| `templates/` | 변수를 채워 넣을 Jinja2 파일 | 포트가 변수인 Nginx 설정 |
| `defaults/` | 사용자가 바꿀 수 있는 기본값 | 기본 포트 `8080` |
| `vars/` | 높은 우선순위로 적용할 변수 | 환경 설정으로 덮어쓰지 않을 내부 값 |
| `files/` | 그대로 복사할 정적 파일 | 고정된 안내 페이지 |
| `meta/` | Role 정보와 의존성 | 먼저 실행할 다른 Role |

`tasks/main.yml`은 기본 작업 진입점이다. Role 안에서 `template`의 `src`를 `nginx.conf.j2`로 쓰면 `templates/`에서 해당 파일을 찾는다. 필요한 디렉토리만 만들어도 되며, 이번 예제에서는 `vars/`와 `files/`를 사용하지 않는다.

기본 골격을 직접 만들기 번거롭다면 다음 명령으로 생성할 수 있다.

```bash
# 새로운 Role의 기본 골격 생성
ansible-galaxy role init study_web --init-path roles
```

공식문서: [Role directory structure](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html#role-directory-structure), [ansible-galaxy CLI](https://docs.ansible.com/projects/ansible/latest/cli/ansible-galaxy.html)

## 3. `defaults`와 `vars`: Override 전략

### 3.1 기본값은 두고, 환경마다 필요한 값만 바꾸기

Role의 기본 포트는 `8080`이지만 prod에서는 `80`을 사용하고 싶을 수 있다. 이런 값은 `defaults/main.yml`에 둔다. 그러면 Role 코드는 그대로 두고 Inventory에서 포트만 바꿀 수 있다. 같은 이름의 변수를 더 높은 우선순위에 정의해 값을 바꾸는 것을 Override라고 한다.

이번 실습의 기본값은 다음과 같다.

```yaml
# roles/study_web/defaults/main.yml
study_web_port: 8080
study_web_root: /var/www/ansible-study
study_web_release: v1
```

환경별 설정은 Inventory에 둔다. 아래는 dev에서도 기본 포트와 버전을 사용하는 예다. 이 파일의 `study_web_port`를 `8081`로 바꾸면 Role은 `8081`을 사용한다.

```yaml
# inventories/dev/group_vars/web.yml
study_web_port: 8080
study_web_release: v1
```

특정 실행에서만 버전을 바꾸고 싶다면 Extra vars로 전달한다.

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml \
  -e '{"study_web_release":"v2"}'
```

이 명령은 파일을 수정하지 않고 이번 실행에 `v2`를 적용한다. **재사용할 설정은 `defaults`, 환경별 설정은 Inventory, 실행할 때 정하는 값은 Extra vars**로 나누면 값이 어디서 오는지 추적하기 쉽다.

### 3.2 같은 변수에 여러 값이 있으면 무엇이 이길까?

다음 표는 이번 문서에 등장하는 변수만 **낮은 우선순위 → 높은 우선순위**로 정리한 것이다.

| 순서 | 변수 종류 | 정의 위치 | 앞의 값과의 관계 |
| --- | --- | --- | --- |
| 1 | Role defaults | `roles/study_web/defaults/main.yml` | 가장 먼저 제공하는 기본값 |
| 2 | Inventory 변수 | `group_vars/`, `host_vars/` 등 | Role defaults를 덮어씀 |
| 3 | Play vars | Play 바로 아래의 `vars` | Inventory 변수를 덮어씀 |
| 4 | Role vars | `roles/study_web/vars/main.yml` | Play vars보다 우선 |
| 5 | Role 호출 변수 | `roles` 목록의 특정 Role 아래 `vars` | Role vars보다 우선 |
| 6 | Extra vars | `--extra-vars` 또는 `-e` | 변수 우선순위에서 가장 높음 |

따라서 사용자가 Inventory에서 바꾸어야 할 포트를 `vars/main.yml`에 넣으면 의도대로 바뀌지 않는다. `vars`는 높은 우선순위가 필요할 때만 사용한다. Extra vars 등으로는 덮어쓸 수 있으므로 변경 불가능한 상수는 아니다.

특히 **Play의 `vars`와 Role 호출 아래의 `vars`는 이름이 같아도 우선순위가 다르다.** 다음 예제는 작성 위치를 비교하기 위한 코드다.

```yaml
# 작성 위치 비교용 예제
- name: Compare play variables and role call variables
  hosts: web
  become: true
  vars:
    study_web_port: 8081       # Play vars
  roles:
    - role: study_web
      vars:
        study_web_port: 9090   # Role 호출 변수
```

여기서 Role은 `9090`을 사용한다. 실행 명령에 `-e study_web_port=8080`을 추가하면 가장 높은 우선순위인 `8080`이 적용된다.

> 더 알아보기: 위 표는 전체 우선순위 목록이 아니다. Facts, Task 변수, `set_fact` 등은 생략했으며 Inventory 내부에도 그룹·호스트 간 우선순위가 있다. 또한 `-e key=value`는 값을 문자열로 전달한다. 숫자·Boolean 타입이 필요하면 JSON이나 `-e @파일.yml`을 사용한다.

공식문서: [Variable precedence](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#understanding-variable-precedence), [Passing variables on the command line](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html#passing-variables-on-the-command-line)

## 4. 실습: Nginx Role 만들기

이제 파일들이 어떻게 연결되는지 확인해 보자. 목표는 `/health`에 요청하면 배포 버전인 `v1`을 응답하는 작은 웹 서버를 만드는 것이다. 이후 04번 문서에서는 이 응답을 `v2`로 바꾸며 배포 흐름을 살펴본다.

SSH·Python 3·sudo가 준비된 Ubuntu 실습 서버를 사용한다. 아래 경로는 별도로 만들 `ansible-study/` 프로젝트 기준이며, 코드 블록을 해당 파일에 저장한다. **예제가 `/etc/nginx/nginx.conf` 전체를 교체하므로 기존 서비스가 없는 실습 서버에서 진행한다.**

### 4.1 Inventory는 대상, Playbook은 적용할 Role을 정한다

```yaml
# inventories/dev/hosts.yml
all:
  vars:
    ansible_user: ubuntu
  children:
    web:
      hosts:
        web01:
          ansible_host: 192.0.2.11
        web02:
          ansible_host: 192.0.2.12
```

주소와 사용자는 실제 환경에 맞게 바꾼다. `192.0.2.x`는 문서용 예시 주소다. SSH 인증은 로컬의 `ssh-agent`나 실행 명령의 Key 옵션으로 준비한다.

```yaml
# site.yml
- name: Prepare the study web service
  hosts: web
  become: true
  roles:
    - role: study_web
      tags:
        - web
```

`hosts: web`으로 대상을 선택하고 `roles`에 `study_web`을 적으면 된다. 설치와 설정의 세부 작업은 Role 안에서 처리한다. 3절의 `defaults/main.yml`도 함께 작성한다.

### 4.2 Task는 설치 → 파일 준비 → 설정 → 시작 순서로 작성한다

아래 코드는 Nginx를 설치하고, `/health` 파일과 설정 파일을 만든 뒤 서비스를 시작한다. `template`에는 `validate`를 지정해 새 설정의 문법을 검사한 후 교체하도록 했다.

```yaml
# roles/study_web/tasks/main.yml
- name: Install nginx
  ansible.builtin.apt:
    name: nginx
    state: present
    update_cache: true
    cache_valid_time: 3600

- name: Create the document root
  ansible.builtin.file:
    path: "{{ study_web_root }}"
    state: directory
    owner: root
    group: root
    mode: '0755'

- name: Publish the release marker
  ansible.builtin.copy:
    content: "{{ study_web_release }}\n"
    dest: "{{ study_web_root }}/health"
    owner: root
    group: root
    mode: '0644'

- name: Configure nginx
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    owner: root
    group: root
    mode: '0644'
    validate: '/usr/sbin/nginx -t -c %s'
  notify: Study web reload nginx

- name: Ensure nginx is running
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: true
```

### 4.3 Template에는 환경마다 달라지는 값을 넣는다

`study_web_port`와 `study_web_root`가 실제 Nginx 설정으로 들어가는 부분을 살펴보자. 같은 Template을 쓰더라도 Inventory의 값에 따라 결과 파일은 달라진다.

```jinja2
{# roles/study_web/templates/nginx.conf.j2 #}
user www-data;
worker_processes auto;
pid /run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    default_type text/plain;
    server {
        listen {{ study_web_port | int }};
        root {{ study_web_root }};
        location = /health {
            try_files $uri =404;
        }
    }
}
```

### 4.4 Handler는 설정이 바뀌었을 때 실행한다

앞의 설정 Task는 파일이 변경되면 `notify`로 아래 Handler에 알린다. Handler는 기본적으로 정해진 실행 시점에 모아서 처리하므로, 여러 Task가 같은 Handler를 알림해도 반복 실행을 줄일 수 있다.

```yaml
# roles/study_web/handlers/main.yml
- name: Study web reload nginx
  ansible.builtin.service:
    name: nginx
    state: reloaded
```

`health`는 정적 파일이므로 그 내용만 바꿀 때는 reload가 필요 없다. 이 실습의 `/health`는 웹 응답과 버전을 확인하는 용도이며, DB 연결 같은 애플리케이션 내부 상태까지 검사하지는 않는다.

공식문서: [template module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/template_module.html), [copy module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/copy_module.html), [Handlers](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html), [Nginx request processing](https://nginx.org/en/docs/http/request_processing.html)

### 4.5 한 대에 적용하고 결과 확인하기

먼저 구문과 대상 목록을 확인하고, 한 대에 적용한 뒤 다시 변경 예상 결과를 확인한다.

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml --syntax-check
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01 --list-hosts
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01 --check --diff
```

적용한 서버에서 `curl http://127.0.0.1:8080/health`를 실행하면 `v1`이 반환된다. 같은 설정으로 재실행했을 때 변경이 줄어드는지도 확인해 보자. 최초 실행의 `--check`는 패키지나 디렉토리를 실제로 만들지 않으므로 전체 동작을 검증할 수 없다.

공식문서: [Check mode and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)

## 5. Role을 어느 시점에 실행할까?

지금까지는 Play의 `roles`에 Role을 나열했다. 하지만 배포할 때는 “LB에서 서버 제외 → Role 실행 → Health Check”처럼 일반 Task 사이에 Role을 넣어야 할 수 있다. 이때 `import_role`과 `include_role`을 사용한다.

| 방식 | Role을 불러오는 시점 | 주로 사용하는 상황 |
| --- | --- | --- |
| `roles` | Play를 정적으로 구성할 때 | Play의 기본 Role을 나열 |
| `import_role` | Playbook을 해석할 때 작업을 펼침 | Task 사이에 고정된 Role 배치 |
| `include_role` | 실행 중 해당 Task에 도달했을 때 | 조건이나 반복에 따라 Role 호출 |

Play의 `roles`는 `pre_tasks` 뒤, 일반 `tasks` 앞에서 실행된다. 아래 코드는 그 대신 `tasks`의 원하는 위치에서 Role을 실행하는 예다.

```yaml
# Play의 tasks 아래에 넣는 예제
- name: Apply the web role at this point
  ansible.builtin.import_role:
    name: study_web
  tags:
    - web
```

`import_role`에 붙인 `web` 태그는 내부 Task에도 적용된다. 반면 `include_role`은 호출 자체와 내부 Task를 구분한다. 태그로 실행할 때 내부 작업도 선택되게 하려면 다음처럼 `apply`를 함께 사용한다.

```yaml
- name: Include the web role when enabled
  ansible.builtin.include_role:
    name: study_web
    apply:
      tags:
        - web
  when: study_web_enabled | default(true) | bool
  tags:
    - web
```

> 더 알아보기: `include_role`은 `loop`로 반복 호출할 수 있다. 동적으로 불러오는 내부 작업은 실행 전 `--list-tasks`에 모두 나오지 않는다. Role 변수 공개 범위는 `public` 옵션과 Ansible 버전의 영향을 받으며, `include_role`의 기본값은 `public: false`다.

공식문서: [include_role](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/include_role_module.html), [import_role](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/import_role_module.html), [Comparing includes and imports](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse.html#comparing-includes-and-imports-dynamic-and-static-reuse)

## 6. 외부 Role과 Collection은 어떻게 함께 관리할까?

팀원이 같은 Playbook을 실행하려면 필요한 외부 기능도 함께 설치해야 한다. **Role은 작업을 재사용하는 단위이고, Collection은 Role·모듈·Plugin 등을 묶어 배포하는 패키지다.** Ansible Galaxy에서 제공하는 콘텐츠를 `ansible-galaxy` 명령으로 설치할 수 있다.

설치 목록은 `requirements.yml`로 관리한다. 아래는 형식 예시이며, `company_baseline`의 URL은 실제 저장소로 바꾸어야 한다. 이번 실습의 로컬 Role인 `study_web`은 다운로드할 필요가 없다.

```yaml
# requirements.yml: 의존성을 선언하는 형식 예제
roles:
  - name: company_baseline
    src: https://git.example.com/platform/ansible-role-baseline.git
    scm: git
    version: v1.0.0
collections:
  - name: community.general
    version: '13.4.0'
```

04번 실습에 필요한 것은 `community.general`이다. 사내 Role이 없다면 위 파일에서 `roles: []`로 바꾼다. 버전은 예시이므로 사용하는 ansible-core와의 호환성을 확인하고 팀에서 검증한 버전으로 고정한다.

```bash
ansible-galaxy role install -r requirements.yml -p roles
ansible-galaxy collection install -r requirements.yml
ansible-galaxy role list
ansible-galaxy collection list
```

Role과 Collection은 각각의 설치 명령으로 처리한다. Collection이 사용하는 `hvac`, `boto3` 같은 Python 라이브러리는 별도로 설치해야 한다.

`requirements.yml`이 **무엇을 설치할지** 정한다면, Role의 `meta/main.yml`은 **어떤 Role을 먼저 실행할지** 표현한다. 이번 Role에는 선행 Role이 없다.

```yaml
# roles/study_web/meta/main.yml: 이 실습에는 다른 Role 의존성이 없음
dependencies: []
```

공식문서: [Galaxy User Guide](https://docs.ansible.com/projects/ansible/latest/galaxy/user_guide.html), [Installing collections](https://docs.ansible.com/projects/ansible/latest/collections_guide/collections_installing.html), [Role dependencies](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html#role-dependencies)

## 7. 스터디에서 확인할 질문

- dev와 prod의 포트가 다르면 Role을 복사하지 않고 어디에서 바꿀 수 있을까?
- Inventory에 값을 적었는데 적용되지 않으면 어떤 변수 정의를 먼저 찾아볼까?
- LB 제외 작업 다음에 Role을 실행하려면 어떤 호출 방식을 사용할까?

다음 문서에서는 이렇게 분리한 설정 중 비밀번호와 Key를 어떻게 관리할지 살펴본다.

다음: [Security & Secret Management](02-security-and-secret-management.md)
