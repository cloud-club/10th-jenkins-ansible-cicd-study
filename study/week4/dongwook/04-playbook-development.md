# Playbook Development

## 1. Playbook 구조

| 단위 | 의미 |
| --- | --- |
| Playbook | 하나 이상의 Play를 순서대로 담은 YAML 파일 |
| Play | 어떤 호스트에 어떤 작업을 적용할지 정의 |
| Task | 이름과 모듈 호출, 실행 조건 등으로 구성된 작업 |
| Module | 패키지·파일·서비스 등을 실제로 처리하는 기능 |

```yaml
# site.yml
- name: Prepare web servers
  hosts: web
  become: true
  tasks:
    - name: Ensure nginx is installed
      ansible.builtin.package:
        name: nginx
        state: present
```

Playbook 최상위는 Play의 목록이다. `hosts`로 대상을 선택하고 `tasks`에 작업을 나열한다. `name`을 구체적으로 작성하면 실행 로그에서 진행 상황을 파악하기 쉽다.

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml
```

기본 실행 전략에서는 한 Task를 대상 호스트들에 수행한 뒤 다음 Task로 진행한다. 호스트별로 Playbook 전체를 실행하는 방식이 아니라 Task 단위로 진행된다.

공식문서: [Ansible playbooks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_intro.html), [Controlling playbook execution](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)

## 2. 변수와 실행 조건

`vars`는 사용할 값을 정의하고, `register`는 실행 결과를 호스트별 변수에 저장한다. `when`은 그 값이나 Facts를 기준으로 실행 여부를 판단한다.

```yaml
- name: Inspect the selected service
  hosts: web
  vars:
    service_name: nginx
  tasks:
    - name: Read service activity
      ansible.builtin.command:
        argv:
          - systemctl
          - is-active
          - "{{ service_name }}"
      register: service_status
      changed_when: false
      failed_when: service_status.rc not in [0, 3]

    - name: Report an inactive service
      ansible.builtin.debug:
        msg: "{{ service_name }} is inactive on {{ inventory_hostname }}"
      when: service_status.rc == 3
```

이 예제는 systemd와 Nginx가 준비된 서버를 가정한다. `register`에는 문자열 하나가 아니라 `rc`, `stdout` 등을 포함한 결과가 저장된다. `when`은 호스트마다 평가되며, 조건식에는 `{{ }}`를 넣지 않는다.

Facts를 사용한 조건은 `when: ansible_facts['os_family'] == 'Debian'`처럼 쓴다. `when`에 조건 목록을 작성하면 모두 참일 때 실행한다.

공식문서: [Conditionals](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_conditionals.html), [Using variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)

### `loop`로 같은 작업 반복

```yaml
- name: Ensure application directories exist
  become: true
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    mode: '0755'
  loop:
    - /opt/ansible-study
    - /opt/ansible-study/logs
```

`loop`는 목록의 각 요소를 `item`으로 전달한다. `when`과 함께 쓰면 각 요소에 조건을 평가한다. 반복 Task에 `register`를 사용하면 개별 결과는 `변수명.results` 목록에 저장된다.

공식문서: [Loops](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_loops.html)

## 3. 변경이 있을 때만 Handler 실행

설정 파일이 바뀌면 서비스를 재시작해야 할 수 있다. 이때 Task의 `notify`로 Handler를 알린다.

```yaml
# Play 안에 작성하는 일부 구성. 파일은 Control Node에 준비한다.
tasks:
  - name: Deploy nginx configuration
    ansible.builtin.copy:
      src: files/nginx.conf
      dest: /etc/nginx/nginx.conf
      owner: root
      group: root
      mode: '0644'
      validate: '/usr/sbin/nginx -t -c %s'
    notify: Restart nginx

handlers:
  - name: Restart nginx
    ansible.builtin.service:
      name: nginx
      state: restarted
```

이 예제는 Nginx 설치와 `become: true`를 전제로 한다. `files/nginx.conf`에는 완전한 Nginx 설정 파일이 필요하다. 변수를 넣어 배포하는 예제는 [Jinja2 & Safe Execution](05-jinja2-and-safe-execution.md)을 참고한다.

`notify`는 Task가 `changed`일 때만 발생한다. 같은 호스트에서 여러 Task가 같은 Handler를 알려도 한 번의 Handler 실행 시점에는 한 번만 실행한다. Handler가 여러 개라면 알림 순서가 아니라 `handlers`에 정의된 순서로 실행된다.

공식문서: [Handlers: running operations on change](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html), [copy module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/copy_module.html)

## 4. `pre_tasks`, `tasks`, `post_tasks` 실행 순서

기본 실행에서의 주요 순서는 다음과 같다. 각 Handler 단계에서는 알림을 받은 Handler만 실행한다.

```text
Facts 수집(활성화한 경우)
  → pre_tasks → 알림받은 Handlers
  → roles / tasks → 알림받은 Handlers
  → post_tasks → 알림받은 Handlers
```

`pre_tasks`는 사전 준비, `tasks`는 본 작업, `post_tasks`는 적용 후 확인에 사용할 수 있다. Handler는 항상 Play 맨 마지막에만 실행되는 것이 아니다.

Ubuntu 서버에 Nginx를 설치하는 `prepare.yml` 예제다. [Inventory & Variables](02-Inventory-and-variables.md)의 Inventory를 사용한다.

```yaml
- name: Prepare nginx for the study
  hosts: web
  become: true
  vars:
    study_directories:
      - /opt/ansible-study
      - /opt/ansible-study/logs

  pre_tasks:
    - name: Refresh apt metadata on Debian family hosts
      ansible.builtin.apt:
        update_cache: true
        cache_valid_time: 3600
      when: ansible_facts['os_family'] == 'Debian'

  tasks:
    - name: Ensure nginx is installed
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Create study directories
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        mode: '0755'
      loop: "{{ study_directories }}"

    - name: Ensure nginx is running
      ansible.builtin.service:
        name: nginx
        state: started
        enabled: true

  post_tasks:
    - name: Validate installed nginx configuration
      ansible.builtin.command:
        cmd: /usr/sbin/nginx -t
      changed_when: false
```

```bash
ansible-playbook -i inventories/dev/hosts.yml prepare.yml --limit web01
```

`post_tasks`는 앞 단계에서 실패한 호스트에서도 반드시 실행되는 정리 구문은 아니다. Task 도중 Handler를 먼저 실행해야 한다면 `ansible.builtin.meta: flush_handlers`를 사용할 수 있다. 이후 새 알림이 발생하면 같은 Handler가 다시 실행될 수 있다.

공식문서: [Controlling when handlers run](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html#controlling-when-handlers-run), [apt module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/apt_module.html)

## 5. `block`, `rescue`, `always`로 실패 처리

| 구문 | 역할 |
| --- | --- |
| `block` | 관련 Task를 묶고 공통 `become`, `when` 등을 적용 |
| `rescue` | `block`의 Task가 실패했을 때 복구·대응 작업 수행 |
| `always` | 정상 실행 또는 실패 처리 뒤 공통 정리 작업 수행 |

`deploy.sh`가 실패하면 `rollback.sh`를 실행하고 임시 디렉토리를 정리하는 예제다. 두 스크립트는 대상 서버에 별도로 준비되어 있어야 한다.

```yaml
- name: Deploy with explicit recovery
  become: true
  block:
    - name: Deploy the application
      ansible.builtin.command:
        cmd: /opt/study/deploy.sh
  rescue:
    - name: Restore the previous release
      ansible.builtin.command:
        cmd: /opt/study/rollback.sh

    - name: Report deployment failure after recovery
      ansible.builtin.fail:
        msg: Deployment failed; the previous release was restored.
  always:
    - name: Remove the deployment temporary directory
      ansible.builtin.file:
        path: /opt/study/deploy-tmp
        state: absent
```

Ansible이 변경을 자동으로 롤백하지는 않는다. 복구 Task를 직접 작성해야 한다. `rescue`가 성공하면 실행이 계속될 수 있으므로, 위 예제는 복구 후에도 배포 실패를 전달하려고 `fail`을 사용한다.

잘못된 Task 정의나 `unreachable`이 발생하면 `rescue`와 `always`도 실행되지 않는다.

공식문서: [Blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html)

또한 설정 변경 후 다른 Task가 실패하면 해당 호스트의 알림받은 Handler가 기본적으로 실행되지 않을 수 있다. 이 경우 설정 파일만 바뀌고 서비스에는 반영되지 않은 상태로 남을 수 있다.

공식문서: [Handlers and failure](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html#handlers-and-failure)

## 6. `tags`와 `--limit`: 작업과 호스트 선택

`tags`는 실행할 작업을, `--limit`은 대상 호스트를 좁힌다. 아래 Task에 `packages` 태그를 붙일 수 있다.

```yaml
- name: Ensure nginx is installed
  ansible.builtin.package:
    name: nginx
    state: present
  tags:
    - packages
```

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml --list-tags
ansible-playbook -i inventories/dev/hosts.yml site.yml --tags packages --list-tasks
ansible-playbook -i inventories/dev/hosts.yml site.yml --tags packages --limit web01
ansible-playbook -i inventories/dev/hosts.yml site.yml --skip-tags packages
```

태그로 일부 작업만 실행하면 패키지 설치나 디렉토리 생성 같은 선행 작업이 빠질 수 있다. Handler는 태그로 직접 선택하는 방식이 아니라 실행된 Task의 변경 알림에 따라 동작한다.

공식문서: [Tags](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_tags.html)

`--limit web01`은 Play의 `hosts`와 교집합을 만든다. Play가 `hosts: web`이면 `--limit db01`로 DB 서버를 추가할 수 없다. 단축 옵션은 `-l`이다.

공식문서: [Patterns: targeting hosts and groups](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_patterns.html)

이전: [Modules & Idempotency](03-modules-and-idempotency.md) · 다음: [Jinja2 & Safe Execution](05-jinja2-and-safe-execution.md)
