# Week 4 — Playbook Development

## Playbook 구조

Playbook은 YAML로 작성하며 하나 이상의 Play를 포함한다. Play는 대상 호스트와 실행할 Task를 연결하고, 각 Task는 Module을 호출한다.

```text
Playbook
└── Play
    ├── hosts
    ├── vars
    ├── pre_tasks
    ├── roles
    ├── tasks
    │   └── Module
    ├── post_tasks
    └── handlers
```

```yaml
---
- name: Configure web servers
  hosts: web
  become: true

  tasks:
    - name: Ensure Nginx is installed
      ansible.builtin.package:
        name: nginx
        state: present
```

- Playbook: YAML 파일 전체
- Play: `hosts`와 작업 목록을 연결하는 실행 단위
- Task: 수행할 작업 하나
- Module: Task의 실제 작업을 수행하는 기능

Play와 Task는 위에서 아래 순서로 실행된다. 각 Task는 대상 호스트들에 적용된 뒤 다음 Task로 넘어간다.

---

## 변수와 `register`

### `vars`

Play 안에서 사용할 변수를 정의한다.

```yaml
- name: Configure web servers
  hosts: web
  vars:
    app_name: myapp
    app_port: 8080

  tasks:
    - name: Show application information
      ansible.builtin.debug:
        msg: "{{ app_name }} listens on {{ app_port }}"
```

### `register`

Task 실행 결과를 변수로 저장한다. 일반적으로 `stdout`, `stderr`, `rc`, `changed`, `failed` 등의 필드를 확인할 수 있다.

```yaml
- name: Check Nginx version
  ansible.builtin.command:
    cmd: nginx -v
  register: nginx_version
  changed_when: false

- name: Show Nginx version
  ansible.builtin.debug:
    var: nginx_version.stderr
```

`register`로 만든 변수는 이후 Task의 조건이나 출력에 사용할 수 있다.

실습에서는 `lab_root`, 디렉터리 목록, 확인할 파일 경로를 `vars`로 정의했다. `stat` 모듈의 실행 결과는 `managed_file_status`에, 파일을 읽은 결과는 `managed_file_content`에 등록해 이후 Task에서 사용했다.

---

## `when`

`when`은 조건이 참일 때만 Task를 실행한다. Jinja2 표현식을 사용하지만 `{{ }}`로 감싸지 않는다.

```yaml
- name: Install Nginx on Debian family
  ansible.builtin.apt:
    name: nginx
    state: present
    update_cache: true
  when: ansible_facts['os_family'] == 'Debian'
```

등록한 결과를 조건으로 사용할 수도 있다.

```yaml
- name: Check whether configuration exists
  ansible.builtin.stat:
    path: /etc/myapp/app.yml
  register: app_config

- name: Show message when configuration exists
  ansible.builtin.debug:
    msg: configuration exists
  when: app_config.stat.exists
```

조건에 맞지 않아 실행하지 않은 Task는 `skipped`로 표시된다.

`/home/doyeon/ansible-lab/message.txt`가 존재했기 때문에 파일 읽기와 내용 출력 Task는 실행됐고, 파일이 없을 때 출력할 Task는 `skipped`가 되었다.

---

## `loop`

같은 형태의 작업을 여러 값에 반복 적용한다.

```yaml
- name: Install required packages
  ansible.builtin.package:
    name: "{{ item }}"
    state: present
  loop:
    - nginx
    - curl
    - git
```

Dictionary 목록을 사용할 수도 있다.

```yaml
- name: Create application users
  ansible.builtin.user:
    name: "{{ item.name }}"
    groups: "{{ item.groups }}"
    state: present
  loop:
    - name: deploy
      groups: www-data
    - name: monitor
      groups: adm
```

Module이 목록 입력을 지원한다면 loop보다 목록을 한 번에 전달하는 것이 효율적일 수 있다.

실습에서는 `releases`, `logs`, `backup` 목록을 순회해 `/home/doyeon/ansible-playbook-lab` 아래에 세 디렉터리를 만들었다. 첫 실행에서는 세 항목이 모두 `changed`였지만 Play Recap은 반복 횟수가 아닌 Task 단위로 집계되어 `changed=1`로 표시됐다. 다시 실행했을 때는 모든 디렉터리가 이미 존재해 `changed=0`이 되었다.

---

## Handler와 `notify`

Handler는 Task가 `changed`가 되어 알림을 보냈을 때만 실행되는 특별한 Task다.

```yaml
tasks:
  - name: Render Nginx configuration
    ansible.builtin.template:
      src: templates/app.conf.j2
      dest: /etc/nginx/conf.d/app.conf
      mode: "0644"
    notify: Reload Nginx

handlers:
  - name: Reload Nginx
    ansible.builtin.service:
      name: nginx
      state: reloaded
```

설정 파일이 기존과 같으면 `ok`이므로 Handler가 실행되지 않는다. 여러 Task가 같은 Handler를 호출해도 기본적으로 Play의 Handler 실행 시점에 한 번만 실행된다.

Handler는 보통 다음 시점에 실행된다.

```text
pre_tasks → notified handlers
roles/tasks → notified handlers
post_tasks → notified handlers
```

즉시 실행해야 한다면 `meta: flush_handlers`를 사용할 수 있지만, 일반적인 경우에는 기본 실행 시점을 유지한다.

실습에서는 `/etc/nginx/conf.d/ansible-lab.conf`를 `copy`로 관리하고 변경 시 `Reload Nginx` Handler에 알리도록 구성했다. 첫 실행에서는 설정 파일 생성과 reload가 발생해 `changed=2`였고, 두 번째 실행에서는 파일 내용이 같아 `notify`가 발생하지 않았다. 따라서 Handler 자체가 출력되지 않았고 결과는 `changed=0`이었다.

---

## `pre_tasks`, `tasks`, `post_tasks`

```yaml
---
- name: Deploy application
  hosts: web
  become: true

  pre_tasks:
    - name: Check available disk space
      ansible.builtin.command:
        cmd: df -P /opt
      changed_when: false

  tasks:
    - name: Deploy application configuration
      ansible.builtin.template:
        src: templates/app.yml.j2
        dest: /opt/myapp/app.yml

  post_tasks:
    - name: Verify application health
      ansible.builtin.uri:
        url: http://localhost:8080/health
        status_code: 200
```

- `pre_tasks`: 주요 배포 전 사전 점검이나 준비
- `tasks`: 핵심 구성과 배포 작업
- `post_tasks`: 배포 후 Health Check나 정리

항상 이 세 구역을 모두 사용할 필요는 없다. 실행 단계의 의미를 분리할 필요가 있을 때 사용한다.

실습 결과는 다음 순서로 출력됐다.

```text
pre_tasks: 디스크 공간 확인과 출력
    ↓
tasks: Nginx 설정 변경
    ↓
handler: Nginx reload
    ↓
post_tasks: reload 이후 HTTP 200 응답 검증
```

설정 변경과 reload로 `changed=2`가 발생했고, `post_tasks`의 HTTP 검사는 Handler가 끝난 다음 실행됐다.

---

## `block`, `rescue`, `always`

여러 Task를 하나의 논리 단위로 묶고 예외 처리 흐름을 정의한다.

```yaml
- name: Deploy application safely
  block:
    - name: Deploy new application
      ansible.builtin.copy:
        src: files/myapp.jar
        dest: /opt/myapp/myapp.jar
        mode: "0644"

    - name: Verify application health
      ansible.builtin.uri:
        url: http://localhost:8080/health
        status_code: 200

  rescue:
    - name: Restore previous application
      ansible.builtin.command:
        cmd: /opt/myapp/rollback.sh

  always:
    - name: Record deployment completion
      ansible.builtin.debug:
        msg: deployment flow finished
```

- `block`: 정상 실행할 Task
- `rescue`: `block`의 Task가 실패했을 때 실행
- `always`: 성공과 실패 여부와 관계없이 실행

`rescue`는 실패를 무조건 숨기는 용도가 아니다. 복구 후에도 배포 실패를 알려야 한다면 `ansible.builtin.fail`로 명시적으로 실패 처리한다.

```yaml
rescue:
  - name: Restore previous application
    ansible.builtin.command:
      cmd: /opt/myapp/rollback.sh

  - name: Report deployment failure
    ansible.builtin.fail:
      msg: Deployment failed and rollback was executed
```

실습에서는 `simulate_failure` 변수로 정상 배포와 실패 후 복구 흐름을 모두 확인했다. 기본값 `false`에서는 `block`이 끝까지 실행되고 상태 파일에 `deployment succeeded`가 기록됐다. Extra Variable로 값을 바꾸자 검증 Task가 실패하고 남은 `block` 작업 대신 `rescue`가 실행됐다.

```bash
ansible-playbook \
  -i ../02-inventory/inventory.local.yml \
  error-handling.yml \
  --extra-vars '{"simulate_failure": true}'
```

복구 후 상태는 `rollback completed`였으며 결과는 `failed=0 rescued=1`이었다. `rescue`가 실패를 처리했기 때문에 Play 전체는 성공으로 끝났다. CI/CD에서 롤백 후에도 배포 실패를 Jenkins에 전달해야 한다면 `rescue` 마지막에 `ansible.builtin.fail`을 실행해야 한다.

---

## Tags

Tags는 Playbook의 일부 Task만 선택적으로 실행하거나 제외할 때 사용한다.

```yaml
- name: Install Nginx
  ansible.builtin.package:
    name: nginx
    state: present
  tags:
    - install

- name: Deploy Nginx configuration
  ansible.builtin.template:
    src: templates/app.conf.j2
    dest: /etc/nginx/conf.d/app.conf
  tags:
    - config
```

```bash
ansible-playbook site.yml --list-tags
ansible-playbook site.yml --tags config
ansible-playbook site.yml --skip-tags install
```

Tag가 없는 Task까지 실행되는 것으로 오해하지 않도록 실행 전에 `--list-tasks`와 함께 확인한다.

실습에서 `--list-tags`는 `always`, `config`, `deploy`, `verify`를 표시했다. `--tags deploy`로 실행하자 `always` Task와 `deploy` Task만 실행됐고, `--skip-tags deploy`에서는 `deploy`만 제외되고 나머지 세 Task가 실행됐다. 특별한 `always` Tag가 붙은 Task는 다른 Tag를 선택해도 기본적으로 함께 실행된다.

---

## `--limit`

`--limit` 또는 `-l`은 Inventory 중 일부 Host나 Group만 대상으로 제한한다.

```bash
ansible-playbook -i inventory.ini site.yml --limit web01
ansible-playbook -i inventory.ini site.yml --limit web
ansible-playbook -i inventory.ini site.yml --limit 'web:&production'
```

Playbook의 `hosts` 범위를 넓게 작성했더라도 `--limit` 밖의 호스트에는 실행되지 않는다. 운영 환경에서는 한 대에 먼저 적용하고 확인한 뒤 전체로 넓히는 데 사용할 수 있다.

```text
web01 한 대 → 일부 그룹 → 전체 그룹
```

실습에서는 `--tags verify --limit vm01`을 사용해 실행할 작업과 호스트를 동시에 제한했다. `always`와 `verify` Task만 `vm01`에서 실행됐다. Inventory에 없는 `vm99`를 지정했을 때는 대상 패턴을 찾지 못했다는 경고와 함께 실행 가능한 호스트가 없다는 오류가 발생했다.

---

## 전체 예제

```yaml
---
- name: Configure Nginx servers
  hosts: web
  become: true
  vars:
    nginx_package: nginx

  pre_tasks:
    - name: Verify target host
      ansible.builtin.debug:
        msg: "target={{ inventory_hostname }}"

  tasks:
    - name: Ensure Nginx is installed
      ansible.builtin.package:
        name: "{{ nginx_package }}"
        state: present

    - name: Deploy virtual host configuration
      ansible.builtin.template:
        src: templates/app.conf.j2
        dest: /etc/nginx/conf.d/app.conf
        mode: "0644"
      notify: Reload Nginx

  post_tasks:
    - name: Verify Nginx response
      ansible.builtin.uri:
        url: http://localhost
        status_code: 200

  handlers:
    - name: Reload Nginx
      ansible.builtin.service:
        name: nginx
        state: reloaded
```

---

## 참고 자료

- [Ansible playbooks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_intro.html)
- [Conditionals](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_conditionals.html)
- [Loops](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_loops.html)
- [Handlers](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html)
- [Blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html)
- [Tags](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_tags.html)
