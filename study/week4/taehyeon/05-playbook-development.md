# Playbook Development

## 4. Playbook의 기본 구조

---

- **Playbook**: 전체 자동화 시나리오
- **Play**: 특정 Host/Group을 대상으로 한 작업 묶음
- **Task**: 하나의 실행 단계
- **Module**: Task가 호출하는 실제 기능

> **Playbook = 어떤 서버에 어떤 작업을 어떤 순서로 수행할지 YAML로 정의한 파일**
> 

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

### 4-1. vars / register / when / loop

---

- Playbook 흐름을 제어하는 기본 기능이다.

#### vars

- 값을 정의한다.

```yaml
vars:
  app_name: sample-api
  app_port: 8080
```

#### register

- Task 결과를 변수에 저장한다.

```yaml
- name: Check Java
  ansible.builtin.command:
    cmd: java -version
  register: java_version
  changed_when: false
```

#### when

- 조건에 따라 Task 실행 여부를 결정한다.

```yaml
when: ansible_facts['os_family'] == 'Debian'
```

#### loop

- 같은 Task를 여러 값에 반복 실행한다.

```yaml
- name: Install packages
  ansible.builtin.package:
    name: "{{ item }}"
    state: present
  loop:
    - curl
    - unzip
    - jq
```

### 4-2. notify / handlers

---

Handler는 **Task가 `notify`했을 때 실행되는 후속 Task**다.

설정 파일이 실제로 변경됐을 때만 서비스 재시작이 필요한 경우에 자주 사용한다.

```yaml
tasks:
  - name: Render nginx config
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

<aside>
🤔

서비스 재시작처럼 영향이 있는 작업은 실제 변경이 있을 때만 수행하도록 구성하는 편이 좋다.

</aside>

### 4-3. pre_tasks / tasks / post_tasks

---

Play 내부 작업을 **사전 작업 → 핵심 작업 → 사후 작업**으로 나누는 구조다.

- **pre_tasks**: 사전 검증, Backup, Drain
- **tasks**: 실제 변경
- **post_tasks**: Health Check, 결과 검증

```
pre_tasks
   ↓
tasks
   ↓
post_tasks
```

### 4-4. block / rescue / always

---

여러 Task를 하나의 오류 처리 단위로 묶는다.

- **block**: 정상 작업
- **rescue**: 실패 시 복구
- **always**: 성공/실패와 관계없이 실행

Java의 `try / catch / finally`와 비슷하게 이해하면 쉽다.

```yaml
- name: Deploy with recovery
  block:
    - name: Deploy
      ansible.builtin.copy:
        src: app.jar
        dest: /opt/app/app.jar

  rescue:
    - name: Restore backup
      ansible.builtin.copy:
        src: app.jar.backup
        dest: /opt/app/app.jar

  always:
    - name: Check status
      ansible.builtin.command:
        cmd: systemctl status myapp
      changed_when: false
```

<aside>
⚠️

Host가 `unreachable`인 경우 등은 일반적인 `rescue` 흐름으로 처리되지 않을 수 있다.

</aside>

### 4-5. tags / --limit

---

둘 다 실행 범위를 줄이는 기능이다.

- **tags**: 실행할 Task 제한
    - 태그가 붙은 특정 Task만 골라서 진행한다는 뜻
- **--limit**: 실행할 Host/Group 제한
    - 어떤 서버에서 실행할지 고르는 것

#### tags

```yaml
- name: Render config
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  tags:
    - config
```

```bash
ansible-playbook site.yml --tags config
```

#### --limit

```bash
ansible-playbook site.yml -i inventory.yml --limit web01
```

짧은 옵션은 `-l`이다.

### 4-6. 종합 Playbook 예제

---

```yaml
- name: Configure nginx
  hosts: web
  become: true

  pre_tasks:
    - name: Show target
      ansible.builtin.debug:
        msg: "Target: {{ inventory_hostname }}"

  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Render config
      ansible.builtin.template:
        src: nginx.conf.j2
        dest: /etc/nginx/nginx.conf
      notify: Restart nginx

    - name: Ensure nginx is running
      ansible.builtin.service:
        name: nginx
        state: started
        enabled: true

  post_tasks:
    - name: Check nginx
      ansible.builtin.command:
        cmd: systemctl is-active nginx
      register: nginx_status
      changed_when: false
      failed_when: nginx_status.stdout != 'active'

  handlers:
    - name: Restart nginx
      ansible.builtin.service:
        name: nginx
        state: restarted
```

### 4-8. 여기서 생각해볼 질문

---

1. Play, Task, Module의 관계는?
2. `register`와 `when`을 함께 쓰는 경우는?
3. Handler를 사용하는 이유는?
4. `rescue`와 `always`의 차이는?
5. 운영 전체 적용 전 `--limit`이 필요한 이유는?

### 4-9. 참고 자료

---

- [Ansible 공식 문서 - Playbook Keywords](https://docs.ansible.com/projects/ansible/latest/reference_appendices/playbooks_keywords.html)
- [Ansible 공식 문서 - Handlers](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html)
- [Ansible 공식 문서 - Blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html)
- [Ansible 공식 문서 - Error Handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)