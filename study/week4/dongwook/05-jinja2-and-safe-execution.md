# Jinja2 & Safe Execution

## 1. Jinja2로 서버마다 다른 설정 생성

정적 파일을 배포할 때는 `copy`, 변수에 따라 내용이 달라지는 파일은 `template`을 사용한다. Jinja2 렌더링은 Control Node에서 수행하고, 완성된 파일을 Managed Node로 전달한다. 대상에 Jinja2를 따로 설치할 필요는 없다.

```text
Inventory의 변수 + templates/nginx.conf.j2
                 ↓ Control Node에서 렌더링
          호스트별 완성된 설정 파일
                 ↓ template 모듈로 배포
          /etc/nginx/nginx.conf
```

공식문서: [Templating (Jinja2)](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_templating.html)

| 문법 | 의미 |
| --- | --- |
| `{{ http_port }}` | 변수·표현식의 값을 출력 |
| `{% if ... %}` / `{% endif %}` | 조건에 따라 내용 포함 |
| `{% for ... %}` / `{% endfor %}` | 목록을 순회하며 내용 생성 |
| `{# ... #}` | 최종 파일에 포함되지 않는 주석 |

예를 들어 호스트 목록을 주석으로 출력하는 템플릿 조각은 다음과 같다.

```jinja2
{% for host in groups['web'] %}
# {{ host }} = {{ hostvars[host]['ansible_host'] }}
{% endfor %}
```

공식문서: [Jinja Template Designer Documentation](https://jinja.palletsprojects.com/en/stable/templates/)

## 2. 기본 Filter

Filter는 `변수 | Filter` 형태로 값을 변환하거나 기본값을 지정한다.

| 표현식 | 용도 |
| --- | --- |
| `http_port \| default(8080)` | 변수가 정의되지 않았으면 기본값 사용 |
| `http_port \| int` | 정수로 변환 |
| `enable_health \| bool` | Ansible에서 문자열 등의 값을 Boolean으로 변환 |
| `groups['web'] \| join(', ')` | 목록을 문자열로 연결 |
| `app_env \| upper` | 대문자로 변환 |

`default(8080)`은 기본적으로 미정의 값에 적용한다. 빈 문자열이나 `false`까지 기본값으로 대체하려면 `default(8080, true)`를 사용하지만, 유효한 `false` 값까지 바뀔 수 있으므로 목적을 구분한다. 필수 변수를 모두 기본값으로 감추기보다 환경별 변수 파일에 명시하는 것이 좋다.

YAML에서 값이 Jinja 표현식으로 시작하면 `dest: "{{ config_path }}"`처럼 전체 값을 따옴표로 감싼다. 반면 `when`은 이미 표현식으로 해석되므로 중괄호 없이 작성한다.

공식문서: [Using filters to manipulate data](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_filters.html), [Jinja filters](https://jinja.palletsprojects.com/en/stable/templates/#filters), [Using variables](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_variables.html)

## 3. Nginx 템플릿과 Playbook 연결

### 3.1 준비 조건

이 예제는 **Ubuntu 실습 전용 서버의 `/etc/nginx/nginx.conf` 전체를 교체**한다. [Inventory & Variables](02-Inventory-and-variables.md)의 dev Inventory와 변수 파일, [Playbook Development](04-playbook-development.md)의 `prepare.yml`로 Nginx가 설치·실행된 상태를 전제로 한다. `web01`에 `prepare.yml`을 먼저 실행한다.

`group_vars/web.yml`의 `http_port: 8080`, `server_name: study.local`과 `host_vars/web01.yml`의 `server_name`을 사용한다. 다음 두 파일을 Inventory 디렉토리와 같은 프로젝트 안에 작성한다.

```text
ansible-study/
├── inventories/dev/...
├── prepare.yml
├── site.yml
└── templates/nginx.conf.j2
```

### 3.2 템플릿

```jinja2
{# templates/nginx.conf.j2 #}
user www-data;
worker_processes auto;
pid /run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    default_type text/plain;

    server {
        listen {{ http_port | int }};
        server_name {{ server_name }};

        location / {
            return 200 "Ansible study: {{ inventory_hostname }}\n";
        }
{% if enable_health | default(true) | bool %}
        location = /health {
            return 200 "ok\n";
        }
{% endif %}
    }
}
```

`web01`에는 Inventory의 호스트별 `server_name`이 들어간다. 선택 변수 `enable_health`가 없으면 `/health` 응답을 포함한다. 실행 시각처럼 매번 달라지는 값을 넣으면 파일도 매번 달라지므로, 변경이 필요 없는 정보는 템플릿에 넣지 않는다.

예제의 Nginx 설정 구조와 `return`은 [Nginx Beginner’s Guide](https://nginx.org/en/docs/beginners_guide.html), [return directive](https://nginx.org/en/docs/http/ngx_http_rewrite_module.html#return)를 참고했다.

### 3.3 배포 Playbook

```yaml
# site.yml
- name: Apply the study nginx configuration
  hosts: web
  become: true
  tasks:
    - name: Render and validate nginx configuration
      ansible.builtin.template:
        src: templates/nginx.conf.j2
        dest: /etc/nginx/nginx.conf
        owner: root
        group: root
        mode: '0644'
        backup: true
        validate: '/usr/sbin/nginx -t -c %s'
      notify: Reload nginx
      tags:
        - config

  handlers:
    - name: Reload nginx
      ansible.builtin.service:
        name: nginx
        state: reloaded
```

`src`는 Control Node의 템플릿 경로이고 `dest`는 Managed Node의 배포 경로다. `backup: true`는 교체 전 파일의 백업을 남긴다. 렌더링 결과나 관리 속성이 바뀌면 Task가 `changed`를 보고하고 Handler에 알린다.

`validate`는 최종 경로를 교체하기 전에 임시 파일을 검증한다. `%s`가 임시 파일 경로로 치환되며, Shell 파이프나 리다이렉션은 사용할 수 없다. 여기서는 전체 Nginx 설정을 `nginx -t -c`로 검사하고 성공했을 때 배포한다. `backup`이 자동 복구까지 수행하는 것은 아니다.

공식문서: [template module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/template_module.html), [Nginx command-line parameters](https://nginx.org/en/docs/switches.html)

## 4. `--check`와 `--diff`의 차이

| 옵션 | 동작 |
| --- | --- |
| `--check` / `-C` | 지원하는 모듈이 실제 변경 없이 예상 결과 보고 |
| `--diff` / `-D` | 지원하는 모듈이 변경 전후 차이 표시. 단독 사용 시 실제 실행 |
| `--check --diff` | 예상 변경 내용과 파일 차이를 함께 확인 |

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml --check --diff --limit web01
```

Check mode는 전체 실행의 성공을 보장하지 않는다.

- 모듈마다 지원 범위가 다르고, 미지원 Task는 생략될 수 있다.
- 앞 Task가 실제 파일·패키지를 만들지 않으므로 후속 작업의 전제가 충족되지 않을 수 있다.
- 생략된 명령의 `register` 결과에 의존하면 실제 실행과 흐름이 달라질 수 있다.
- Task에 `check_mode: false`가 있으면 `--check`에서도 실제 실행된다.

Diff에는 파일 내용이 노출된다. 민감한 설정은 Task에 `diff: false`를 지정할 수 있다.

공식문서: [Validating tasks: check mode and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)

`command`는 `creates` / `removes`가 없으면 check mode에서 일반적으로 생략된다. 또한 `template`의 check mode 결과를 `validate` 명령이나 서비스 재적용까지 실제로 성공했다는 증거로 해석하지 않는다. 실제 적용 단계의 검증과 서비스 확인이 필요하다.

공식문서: [command — check mode](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/command_module.html#attributes), [template — attributes](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/template_module.html#attributes)

## 5. 한 대부터 검증하고 적용하기

`--limit web01`로 한 대에 먼저 적용한다. `--limit`은 Play의 `hosts` 범위를 추가로 좁히며, Inventory에 정의된 이름을 사용한다.

```bash
# 1. Playbook 구문 확인
ansible-playbook -i inventories/dev/hosts.yml site.yml --syntax-check

# 2. 선택된 호스트 확인
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01 --list-hosts

# 3. 한 대에서 예상 변경 확인
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01 --check --diff

# 4. 같은 대상에 실제 적용
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01 --diff

# 5. 재실행 시 추가 변경이 예상되는지 확인
ansible-playbook -i inventories/dev/hosts.yml site.yml --limit web01 --check --diff
```

`--syntax-check`는 SSH 연결, sudo, 서비스 정상 동작까지 검사하지 않는다. 실제 적용 후에는 `web01`에서 `curl http://127.0.0.1:8080/health`로 응답도 확인한다. Control Node에서 접근하려면 해당 포트의 네트워크 접근이 가능해야 한다.

같은 변수와 템플릿으로 다시 검사했을 때 `changed=0`이면 추가 변경이 없는 상태다. 다른 서버에 적용할 때도 `prepare.yml`로 Nginx를 먼저 준비한 뒤 검증과 배포를 진행한다.

공식문서: [Patterns and command-line options](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_patterns.html), [ansible-playbook CLI](https://docs.ansible.com/projects/ansible/latest/cli/ansible-playbook.html)

이전: [Playbook Development](04-playbook-development.md)
