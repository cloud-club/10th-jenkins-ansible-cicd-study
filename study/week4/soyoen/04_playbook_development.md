# Playbook Development

Playbook은 여러 Task를 순서와 조건에 따라 실행하도록 YAML로 정의한 자동화 절차다.

## 1. Play / Task / Module

기본 구조:

```text
Playbook
└─ Play
   ├─ hosts
   ├─ vars
   ├─ tasks
   │  └─ Module
   └─ handlers
```

예:

```yaml
- name: Configure web servers
  hosts: web
  become: true

  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present
```

- **Play** : 어떤 Host에 작업할지 정의
- **Task** : 하나의 작업 단계
- **Module** : Task에서 실제 실행하는 기능

공식문서: [Ansible playbooks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_intro.html)

---

## 2. vars / register / when / loop

값을 변수로 정의:

```yaml
vars:
  app_port: 8080
```

Task 결과 저장:

```yaml
- name: Check nginx
  ansible.builtin.command: systemctl is-active nginx
  register: nginx_status
  changed_when: false
```

조건부 실행:

```yaml
- name: Show result
  ansible.builtin.debug:
    msg: "nginx is active"
  when: nginx_status.rc == 0
```

반복 실행:

```yaml
- name: Install packages
  ansible.builtin.package:
    name: "{{ item }}"
    state: present
  loop:
    - nginx
    - curl
    - git
```

즉 Playbook은 단순 명령 나열이 아니라 **변수·결과·조건·반복을 조합해 흐름을 만든다.**

공식문서: [Using variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html), [Loops](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_loops.html)

---

## 3. notify / handlers

설정 파일이 실제로 변경됐을 때만 서비스를 재시작하려면 Handler를 사용한다.

```yaml
tasks:
  - name: Deploy nginx config
    ansible.builtin.template:
      src: nginx.conf.j2
      dest: /etc/nginx/nginx.conf
    notify: Restart nginx

handlers:
  - name: Restart nginx
    ansible.builtin.service:
      name: nginx
      state: restarted
```

```text
template → ok
          └→ Restart 없음

template → changed
          └→ notify → Handler 실행
```

불필요한 서비스 재시작을 줄일 수 있다.

공식문서: [Handlers](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html)

---

## 4. 실행 흐름과 선택적 실행

작업 단계를 다음처럼 분리할 수 있다.

```text
pre_tasks
    ↓
tasks
    ↓
post_tasks
```

예:

```text
pre_tasks  : Load Balancer에서 서버 제외
tasks      : Application 배포
post_tasks : 검증 후 서버 복귀
```

예외 처리는 `block`, `rescue`, `always`를 사용한다.

```yaml
- name: Deploy
  block:
    - name: Deploy application
      ansible.builtin.command: /opt/deploy.sh

  rescue:
    - name: Rollback
      ansible.builtin.command: /opt/rollback.sh

  always:
    - name: Finish
      ansible.builtin.debug:
        msg: "finished"
```

```text
block 성공 → always
block 실패 → rescue → always
```

실행 범위 선택:

```bash
ansible-playbook site.yml --tags config
```

→ **어떤 Task를 실행할지**

```bash
ansible-playbook site.yml --limit web01
```

→ **어떤 Host에 실행할지**

공식문서: [Blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html), [ansible-playbook CLI](https://docs.ansible.com/projects/ansible/latest/cli/ansible-playbook.html)

> **핵심:** Playbook은 **어떤 서버에서 어떤 Task를 어떤 순서·조건으로 실행할지 정의하는 자동화 흐름**이다.
