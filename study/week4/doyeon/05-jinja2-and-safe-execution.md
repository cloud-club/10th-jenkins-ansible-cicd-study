# Week 4 — Jinja2 & Safe Execution

## Jinja2 Template

서버마다 포트, 도메인, 환경 이름이 다르면 정적 파일을 각각 관리하기 어렵다. `ansible.builtin.template`은 Jinja2 문법으로 작성한 원본에 변수를 적용해 호스트별 설정 파일을 만든다.

```text
Template + Inventory Variable
              ↓
       Host별 설정 파일
```

프로젝트 구조는 다음과 같이 구성할 수 있다.

```text
ansible/
├── inventory.ini
├── site.yml
├── group_vars/
│   └── web.yml
└── templates/
    └── app.conf.j2
```

```yaml
# group_vars/web.yml
---
server_name: example.com
app_port: 8080
```

```jinja2
# templates/app.conf.j2
server {
    listen 80;
    server_name {{ server_name }};

    location / {
        proxy_pass http://127.0.0.1:{{ app_port }};
    }
}
```

```yaml
# site.yml
---
- name: Configure Nginx
  hosts: web
  become: true

  tasks:
    - name: Render Nginx configuration
      ansible.builtin.template:
        src: templates/app.conf.j2
        dest: /etc/nginx/conf.d/app.conf
        owner: root
        group: root
        mode: "0644"
        backup: true
      notify: Reload Nginx

  handlers:
    - name: Reload Nginx
      ansible.builtin.service:
        name: nginx
        state: reloaded
```

Template 결과가 기존 파일과 다를 때만 Task가 `changed`가 되고 Handler가 실행된다.

실습에서는 `templates/status.html.j2`에 Playbook 변수, Inventory 변수와 Ansible 기본 변수를 함께 적용해 VM의 `/var/www/html/ansible-status.html`을 생성했다.

```text
status.html.j2
+ Playbook vars: app_name, maintenance_mode, enabled_features
+ group_vars: app_environment, server_role
+ host_vars: app_port
+ Ansible 변수: inventory_hostname
        ↓
/var/www/html/ansible-status.html
```

첫 실제 실행에서는 파일이 생성되어 `changed=1`이었고, `uri` 모듈이 HTTP 200과 응답 본문의 `ANSIBLE TEMPLATE LAB` 문자열을 확인했다. 같은 Playbook을 다시 실행했을 때는 결과 파일이 동일해 `ok=2 changed=0`이 되었다.

---

## 변수 치환과 기본 문법

### 변수 출력

```jinja2
server_name {{ server_name }};
```

### 조건문

```jinja2
{% if enable_access_log %}
access_log /var/log/nginx/access.log;
{% endif %}
```

### 반복문

```jinja2
upstream backend {
{% for host in groups['app'] %}
    server {{ hostvars[host]['ansible_host'] }}:{{ app_port }};
{% endfor %}
}
```

`{{ }}`는 값을 출력하고 `{% %}`는 조건이나 반복 같은 제어 구문에 사용한다.

실습 Template에서는 `maintenance_mode`에 따라 정상 운영 또는 점검 메시지를 선택하고, `enabled_features` 목록을 반복해 여러 `<li>` 요소를 생성했다.

---

## 자주 사용하는 Filter

Filter는 `|` 뒤에 작성해 변수 값을 변환하거나 기본값을 제공한다.

### `default`

변수가 정의되지 않았을 때 기본값을 사용한다.

```jinja2
worker_processes {{ nginx_workers | default(2) }};
```

false, 빈 문자열 등도 기본값으로 바꾸려면 두 번째 인자에 `true`를 지정한다.

```jinja2
{{ value | default('fallback', true) }}
```

### `mandatory`

반드시 필요한 변수가 없다면 실행을 실패시킨다.

```jinja2
server_name {{ server_name | mandatory }};
```

### 자료형 변환

```yaml
when: feature_enabled | bool
```

```jinja2
worker_connections {{ max_connections | int }};
```

### 문자열과 목록

```jinja2
{{ allowed_ips | join(' ') }}
{{ app_name | upper }}
{{ environment | lower }}
```

복잡한 가공을 Template 안에 모두 넣기보다 변수 구조를 단순하게 설계하고, Template은 설정 파일의 형태를 읽기 쉽게 유지한다.

실습에서는 `app_name | upper`로 제목을 대문자로 바꾸고, 일부 Inventory 변수가 없을 경우를 대비해 `default`를 사용했다. `maintenance_mode | bool`은 전달된 값을 조건에서 Boolean으로 해석하도록 했다.

---

## 설정 파일 검증 후 반영

문법이 잘못된 설정 파일을 바로 덮어쓰면 서비스가 재시작되지 않을 수 있다. `template`의 `validate`를 사용하면 임시 파일을 검사한 뒤 성공한 경우에만 대상 경로에 반영한다.

```yaml
- name: Render and validate Nginx configuration
  ansible.builtin.template:
    src: templates/nginx.conf.j2
    dest: /etc/nginx/nginx.conf
    mode: "0644"
    validate: nginx -t -c %s
  notify: Reload Nginx
```

`%s`에는 Ansible이 만든 임시 파일 경로가 들어간다. 검증 명령이 실패하면 실제 설정 파일을 교체하지 않는다.

서비스별 검증 명령을 사용할 수 없는 경우 별도 Task에서 검증하고 `failed_when`으로 성공 조건을 정의한다.

---

## Check Mode

Check Mode는 실제 변경을 적용하지 않고 무엇이 바뀔지 예측한다.

```bash
ansible-playbook -i inventory.ini site.yml --check
```

짧은 옵션은 `-C`다.

```bash
ansible-playbook -i inventory.ini site.yml -C
```

모든 Module이 Check Mode를 완전히 지원하는 것은 아니다. 외부 명령, API 호출, 실행 시점에만 알 수 있는 값은 정확히 예측하지 못하거나 Task가 건너뛰어질 수 있다. Check Mode 성공이 실제 실행 성공을 보장하지는 않는다.

실습 Playbook의 HTTP 검증 Task에는 `when: not ansible_check_mode`를 적용했다. Check Mode에서는 Template 결과를 실제 경로에 배치하지 않으므로, 아직 반영되지 않은 페이지를 검사해 잘못 실패하는 일을 막기 위해서다.

---

## Diff Mode

Diff Mode는 Template이나 파일이 어떻게 변경되는지 전후 차이를 보여준다.

```bash
ansible-playbook -i inventory.ini site.yml --check --diff
```

Diff 출력에 비밀번호, 인증서, Secret 등이 노출될 수 있다. 민감한 값을 다루는 Task에는 `no_log: true`를 적용하거나 Diff 사용 범위를 제한한다.

```yaml
- name: Render secret configuration
  ansible.builtin.template:
    src: templates/secret.conf.j2
    dest: /etc/myapp/secret.conf
    mode: "0600"
  no_log: true
```

`no_log`는 로그 노출을 줄이지만 비밀 관리 자체를 대신하지 않는다.

첫 `--check --diff` 실행에서는 기존 파일이 없어 완성될 HTML 25줄 전체가 추가 내용으로 표시됐다. 실제 반영 후 `maintenance_mode`만 Extra Variable로 바꾸자 다음 한 줄의 차이만 표시됐다.

```diff
-  <p>서비스가 정상 운영 중입니다.</p>
+  <p>현재 점검 중입니다.</p>
```

Check Mode이므로 결과는 `changed=1`로 예측됐지만 실제 서버 파일은 변경되지 않았고, HTTP 검증 Task는 `skipped`였다.

---

## 특정 Host에서 먼저 검증하기

`--limit` 또는 `-l`을 사용해 한 대에 먼저 적용한 뒤 범위를 넓힌다.

```bash
ansible-playbook -i inventory.ini site.yml --limit web01 --check --diff
ansible-playbook -i inventory.ini site.yml --limit web01
ansible-playbook -i inventory.ini site.yml --limit web
```

```text
한 Host에서 변경 예상 확인
          ↓
한 Host에 실제 적용 및 검증
          ↓
일부 Group으로 확대
          ↓
전체 대상에 적용
```

첫 번째 Host가 정상이라고 모든 Host가 정상이라는 뜻은 아니다. 운영체제 버전, 기존 설정, 가용 용량 등 차이가 있을 수 있으므로 대표성을 고려해 대상을 고른다.

실습에서는 모든 사전 검토와 실제 적용에 `--limit vm01`을 지정했다. 현재 Inventory에 한 대만 있더라도, 여러 서버로 확장할 때 동일한 명령으로 첫 적용 대상을 제한할 수 있다.

---

## 실행 전 확인 명령

```bash
# YAML과 Playbook 문법 확인
ansible-playbook -i inventory.ini site.yml --syntax-check

# 실제 대상 Host 확인
ansible-playbook -i inventory.ini site.yml --list-hosts

# 실행할 Task와 Tag 확인
ansible-playbook -i inventory.ini site.yml --list-tasks
ansible-playbook -i inventory.ini site.yml --list-tags

# Inventory 구조와 최종 Host 변수 확인
ansible-inventory -i inventory.ini --graph
ansible-inventory -i inventory.ini --host web01
```

`--syntax-check`는 문법만 검사하며 변수 값, 접속, 권한, 실제 Module 실행 성공까지 확인하지 않는다.

---

## 안전한 실행 순서

```text
1. Git diff로 Playbook과 변수 변경 확인
2. --syntax-check로 문법 검사
3. --list-hosts로 대상 확인
4. --limit과 --check --diff로 한 Host의 변경 예상 확인
5. 한 Host에 실제 적용
6. 서비스 상태와 실제 요청 검증
7. 실행 범위를 Group 전체로 확대
8. Playbook 재실행으로 불필요한 changed가 없는지 확인
```

```bash
git diff
ansible-playbook -i inventory.ini site.yml --syntax-check
ansible-playbook -i inventory.ini site.yml --list-hosts
ansible-playbook -i inventory.ini site.yml --limit web01 --check --diff
ansible-playbook -i inventory.ini site.yml --limit web01
curl --fail http://203.0.113.10/health
ansible-playbook -i inventory.ini site.yml --limit web
ansible-playbook -i inventory.ini site.yml --limit web
```

옵션 표기는 다음과 같다.

```text
--limit 또는 -l
--check 또는 -C
--diff
```

`-limit`, `-check`, `-diff`처럼 하이픈 하나로 작성하지 않는다.

---

## 참고 자료

- [Templating with Jinja2](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_templating.html)
- [Using filters](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_filters.html)
- [Check and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)
- [Ansible playbooks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_intro.html)
- [Patterns: targeting hosts and groups](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_patterns.html)
