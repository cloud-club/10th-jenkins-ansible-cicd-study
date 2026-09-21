# Jinja2 & Safe Execution

Jinja2는 같은 설정 파일을 여러 Host와 환경에서 재사용하게 하고, Check/Diff/Limit은 실제 변경 전에 영향을 확인하도록 돕는다.

## 1. Jinja2와 template

서버별로 설정 파일을 따로 만들지 않고 변수를 이용해 하나의 Template을 재사용할 수 있다.

`nginx.conf.j2`

```jinja2
server {
    listen {{ app_port }};
    server_name {{ inventory_hostname }};
}
```

Playbook:

```yaml
- name: Deploy nginx config
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/conf.d/app.conf
```

```text
Jinja2 Template
      +
Inventory / Variables
      ↓
Control Node에서 렌더링
      ↓
Managed Node에 설정 파일 배포
```

공식문서: [Templating](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_templating.html)

---

## 2. 자주 쓰는 Jinja2 문법

변수 치환:

```jinja2
{{ app_port }}
```

조건:

```jinja2
{% if app_env == 'production' %}
log_level=warn
{% else %}
log_level=debug
{% endif %}
```

반복:

```jinja2
{% for host in groups['web'] %}
server {{ hostvars[host]['ansible_host'] }};
{% endfor %}
```

Filter:

```jinja2
{{ app_port | default(8080) }}
{{ app_port | int }}
{{ database_password | mandatory }}
```

| Filter | 용도 |
|---|---|
| `default` | 값이 없을 때 기본값 사용 |
| `int` | 정수형으로 변환 |
| `bool` | Boolean으로 변환 |
| `mandatory` | 값이 없으면 오류 발생 |

공식문서: [Filter plugins](https://docs.ansible.com/projects/ansible/latest/plugins/filter.html)

---

## 3. Check Mode와 Diff Mode

실제 반영 전에 Playbook이 어떤 변경을 만들지 확인할 수 있다.

문법 확인:

```bash
ansible-playbook site.yml --syntax-check
```

대상 Host 확인:

```bash
ansible-playbook -i inventory.yml site.yml --list-hosts
```

실제 변경 없이 실행 결과 예상:

```bash
ansible-playbook site.yml --check
```

파일의 변경 전후 확인:

```bash
ansible-playbook site.yml --diff
```

둘을 함께 사용할 수 있다.

```bash
ansible-playbook site.yml --check --diff
```

단, 모든 Module이 Check Mode와 Diff Mode를 완벽하게 지원하는 것은 아니다.

공식문서: [Check mode and diff mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)

---

## 4. 특정 Host에서 먼저 검증

운영 전체에 바로 적용하지 않고 한 대에서 먼저 확인할 수 있다.

```bash
ansible-playbook \
  -i inventory/prod \
  site.yml \
  --check \
  --diff \
  --limit web01
```

추천 흐름:

```text
1. --syntax-check
       ↓
2. --list-hosts
       ↓
3. --check --diff
       ↓
4. --limit web01 실제 적용
       ↓
5. 서비스 검증
       ↓
6. 전체 적용
```

`--diff`는 파일 내용을 출력할 수 있으므로 Secret이 포함된 Task는 주의한다.

```yaml
- name: Deploy secret config
  ansible.builtin.template:
    src: secret.conf.j2
    dest: /etc/app/secret.conf
  diff: false
```

필요한 경우 `no_log: true`도 활용할 수 있다.

> **핵심:** Jinja2는 **환경별 설정을 하나의 Template으로 재사용**하게 하고, Check/Diff/Limit은 **변경 내용을 작은 범위에서 먼저 검증**하게 한다.
