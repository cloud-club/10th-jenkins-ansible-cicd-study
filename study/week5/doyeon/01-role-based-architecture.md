# Ansible Role이란? 배포 Playbook을 역할별로 나누는 방법

> 한 줄 요약: **Role은 관련 작업을 이름 붙여 묶어 둔 폴더 구조다.**

처음에는 Nginx 설치, 파일 배포, 서비스 재시작을 한 Playbook에 모두 적어도 괜찮다. 하지만 배포 작업이 늘어나면 같은 코드를 여러 파일에 복사하게 되고, 수정할 위치도 찾기 어려워진다.

Role은 이 작업을 역할별로 나눈다.

```text
common     → 모든 서버에 공통으로 필요한 준비
app_deploy → 애플리케이션 파일 배포와 상태 확인
```

---

## 1. Playbook과 Role의 관계

Playbook은 **누구에게 어떤 Role을 실행할지** 적는다.

Role은 **그 Role이 실제로 할 일**을 담는다.

```yaml
# playbooks/site.yml
---
- name: Prepare web servers
  hosts: webservers
  become: true

  roles:
    - common
```

> `webservers`에 속한 서버에서 root 권한으로 `common` 작업 묶음을 실행한다.

---

## 2. Role 폴더 구조

```text
roles/
└── common/
    ├── tasks/main.yml
    ├── handlers/main.yml
    ├── templates/
    ├── files/
    ├── defaults/main.yml
    ├── vars/main.yml
    └── meta/main.yml
```

Ansible은 이 구조를 알고 있어서 `common`이라는 이름만 보면 필요한 `main.yml` 파일을 자동으로 찾는다.

| 위치 | 하는 일 | 예시 |
|---|---|---|
| `tasks/main.yml` | 서버에서 실행할 실제 작업 | 패키지 설치, 파일 생성 |
| `defaults/main.yml` | 쉽게 바꿀 기본값 | 포트, 설치 경로 |
| `vars/main.yml` | Role 내부에서 강하게 고정할 값 | OS별 내부 경로 |
| `handlers/main.yml` | 변경됐을 때만 실행할 후속 작업 | 서비스 reload |
| `templates/` | 변수값을 채워 생성할 파일 | 설정 파일, 상태 페이지 |
| `files/` | 내용 변경 없이 그대로 복사할 파일 | 정적 HTML, 스크립트 |
| `meta/main.yml` | Role 간 선행 관계 | 다른 Role 의존성 |

`main.yml`은 각 디렉터리의 기본 진입 파일이다. 예를 들어 `roles: - common`이라고 쓰면 Ansible은 기본적으로 `roles/common/tasks/main.yml`을 실행하고, 같은 Role의 `defaults/main.yml`, `handlers/main.yml` 등도 역할에 맞게 불러온다.

### `tasks`와 `handlers`

`tasks/main.yml`은 Role을 실행할 때 위에서 아래 순서로 실행하는 일반 작업 목록이다. 단, `when` 조건이나 Tag 설정에 따라 특정 작업은 건너뛸 수 있다. 반면 `handlers/main.yml`은 Task가 `notify`로 호출했을 때만 실행한다.

예를 들어 Nginx 설정 파일이 바뀐 경우에만 Nginx를 reload하고 싶다면 일반 Task가 Handler를 알린다.

```yaml
- name: Deploy Nginx configuration
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/conf.d/app.conf
  notify: Reload Nginx
```

```yaml
# handlers/main.yml
- name: Reload Nginx
  ansible.builtin.service:
    name: nginx
    state: reloaded
```

### `files`와 `templates`

`files/`는 파일을 그대로 복사할 때 사용한다. `templates/`는 `{{ 변수 }}`처럼 서버별 값이 들어가야 할 때 사용한다.

```text
files/logo.png              → 모든 서버에 같은 파일을 복사
templates/nginx.conf.j2     → 포트·도메인 같은 변수값을 넣어 생성
```

### `meta`

`meta/main.yml`에는 Role 의존성을 선언할 수 있다. 예를 들어 앱 배포 Role이 공통 웹 서버 준비 Role을 먼저 요구한다면 다음처럼 표현한다.

```yaml
dependencies:
  - role: common
```

이는 “`app_deploy`를 실행하기 전에 `common`을 먼저 실행하라”는 의미다.

### `defaults`와 `vars`의 차이

두 디렉터리는 모두 변수를 정의하지만, 값을 바꾸기 쉬운 정도가 다르다.

```text
defaults = Role 사용자가 환경에 맞게 바꿔도 되는 기본값
vars     = Role 구현을 위해 쉽게 바꾸면 안 되는 내부 값
```

예를 들어 서비스 포트나 배포 경로는 환경마다 달라질 수 있으므로 보통 `defaults`에 둔다. 반대로 Role 안에서만 사용하는 내부 파일명처럼 외부에서 바꿀 이유가 없는 값은 `vars`에 둘 수 있다.

다만 `vars`는 우선순위가 높아 덮어쓰기 어렵다. 재사용 가능한 Role을 만들려면 환경 설정 대부분을 `defaults`와 `group_vars`에 두고, `vars` 사용은 최소화하는 편이 좋다.

---

## 3. 예시: `common` Role

### 기본값: `defaults/main.yml`

```yaml
---
common_nginx_package: nginx
common_nginx_service: nginx
common_app_root: /var/www/rolling-demo
```

`defaults`는 “일단 이 값으로 쓰되, 환경에 맞게 바꿔도 되는 값”이다.

예를 들어 배포 디렉터리를 바꾸고 싶다면 다음처럼 실행 시점에 덮어쓸 수 있다.

```bash
ansible-playbook playbooks/site.yml \
  -e 'common_app_root=/srv/rolling-demo'
```

### 실제 작업: `tasks/main.yml`

```yaml
---
- name: Install Nginx
  ansible.builtin.apt:
    name: "{{ common_nginx_package }}"
    state: present
    update_cache: true
    cache_valid_time: 3600

- name: Create common application directory
  ansible.builtin.file:
    path: "{{ common_app_root }}"
    state: directory
    owner: root
    group: root
    mode: "0755"

- name: Enable and start Nginx
  ansible.builtin.service:
    name: "{{ common_nginx_service }}"
    state: started
    enabled: true
```

이 예시 Role은 아래 상태를 보장한다.

1. Nginx가 설치되어 있다.
2. `/var/www/rolling-demo` 디렉터리가 존재한다.
3. Nginx가 실행 중이고, 재부팅 후에도 자동 시작한다.

같은 Playbook을 두 번 실행해도 목표 상태가 이미 맞으면 대부분 변경하지 않는다. 이를 **멱등성(idempotency)** 이라고 한다.

---

## 4. OS가 하나라면 Task를 한 파일에 둔다

대상 서버가 모두 Ubuntu라면 Ubuntu의 패키지 관리자인 `apt`를 `tasks/main.yml`에 바로 적으면 된다.

```yaml
- name: Install Nginx
  ansible.builtin.apt:
    name: nginx
    state: present
```

서버 OS가 섞일 때만 파일을 나눈다.

```text
Ubuntu / Debian → apt
RHEL / Rocky    → dnf
```

```text
tasks/
├── main.yml
├── debian.yml
└── redhat.yml
```

서버 OS가 하나라면 파일을 과도하게 나누지 않는 편이 더 읽기 쉽다.

---

## 5. Jinja2 템플릿이란?

Jinja2는 **변수 자리에 실제 값을 넣어 최종 파일을 만드는 템플릿 엔진**이다.

원본 템플릿:

```html
<h1>{{ inventory_hostname }} 서버</h1>
<p>배포 버전: {{ deploy_version }}</p>
```

`web-01`에 `deploy_version=1.0.0`을 적용한 결과:

```html
<h1>web-01 서버</h1>
<p>배포 버전: 1.0.0</p>
```

`{{ ... }}` 안의 값을 실제 값으로 바꾸는 문법이 Jinja2다.

---

## 6. Role을 실행하는 방법

처음에는 아래 한 가지면 충분하다.

```yaml
roles:
  - common
  - app_deploy
```

위에서 아래 순서대로 실행한다.

```text
common
→ app_deploy
```

| 방식 | 쉽게 말하면 | 나중에 쓸 상황 |
|---|---|---|
| `include_role` | 조건이 맞을 때만 Role 실행 | LB를 사용할 수 있을 때만 LB 작업 |
| `import_role` | Task 중간에 Role을 미리 포함 | Tag 동작 비교 |
| `meta`의 `dependencies` | 이 Role 전에 저 Role을 먼저 실행 | `app_deploy` 전에 `common` 강제 |

예를 들어 LB를 쓸 수 있을 때만 Role을 실행하는 코드는 다음과 같다.

```yaml
- name: Include load balancer role only when enabled
  ansible.builtin.include_role:
    name: load_balancer
  when: use_load_balancer | bool
```

뜻은 단순하다.

> `use_load_balancer`가 참일 때만 `load_balancer` 작업 묶음을 실행한다.

---

## 7. Ansible Galaxy와 `requirements.yml`

Ansible Galaxy는 다른 사람이 만든 Ansible 콘텐츠를 찾아 설치하는 공개 저장소다. 역할은 npm 레지스트리나 Maven Central과 비슷하다.

Galaxy에서 설치할 수 있는 콘텐츠는 크게 두 종류다.

| 종류 | 구성 | 예시 |
|---|---|---|
| Role | 특정 목적의 Task 묶음 | Nginx 설치 Role |
| Collection | Role, 모듈, Plugin, 문서를 함께 묶은 패키지 | `community.general` |

Collection은 Role보다 큰 배포 단위다. 예를 들어 기본 Ansible에 없는 모듈을 사용하려면 해당 모듈이 들어 있는 Collection을 설치해야 한다.

### `requirements.yml`의 역할

`requirements.yml`은 프로젝트가 실행 전에 설치해야 하는 외부 Role과 Collection, 그리고 사용할 버전을 기록하는 파일이다.

```yaml
---
roles:
  - name: geerlingguy.java
    version: "1.9.6"

collections:
  - name: community.general
    version: ">=10.0.0,<11.0.0"
```

이 파일을 Git에 포함하면 Jenkins, 개발자 PC, 다른 관리 서버가 같은 의존성을 설치할 수 있다. 버전을 기록하지 않으면 설치 시점에 최신 버전이 받아져 환경마다 동작이 달라질 수 있다.

```bash
# Role과 Collection을 함께 설치
ansible-galaxy install -r requirements.yml

# Role만 설치
ansible-galaxy role install -r requirements.yml

# Collection만 설치
ansible-galaxy collection install -r requirements.yml
```

### `requirements.yml`과 `meta/main.yml`은 다르다

둘 다 의존성을 다루지만 시점과 목적이 다르다.

| 파일 | 질문에 대한 답 | 예시 |
|---|---|---|
| `requirements.yml` | 실행 전에 무엇을 **설치**해야 하는가? | `community.general` Collection 다운로드 |
| `meta/main.yml` | 이 Role 실행 전에 무엇을 **실행**해야 하는가? | `app_deploy` 전에 `common` 실행 |

즉, `requirements.yml`은 외부 패키지를 준비하는 목록이고, `meta/main.yml`은 Role 사이의 실행 순서를 선언하는 파일이다.

> `requirements.yml`은 Python 패키지의 의존성을 관리하지 않는다. Python 라이브러리는 별도의 `requirements.txt` 또는 Execution Environment 설정으로 관리한다.

---

## 참고 문서

- [Ansible Roles 공식 문서](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_reuse_roles.html)
- [Ansible 변수 사용과 우선순위](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)
- [apt 모듈](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/apt_module.html)
- [service 모듈](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/service_module.html)
- [Ansible Galaxy와 requirements 파일](https://docs.ansible.com/projects/ansible/latest/collections_guide/collections_installing.html)
