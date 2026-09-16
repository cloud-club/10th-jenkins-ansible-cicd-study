# Jinja2 & Safe Execution

## `template` 모듈

`copy`가 파일을 그대로 옮긴다면, `template`은 **Jinja2로 렌더링한 결과**를 배포한다. 렌더링은 Control Node에서 일어나고, 결과물만 대상 서버로 전송된다.

관례적으로 템플릿 파일은 `templates/` 디렉터리에 두고 `.j2` 확장자를 붙인다.

## 실습: 호스트별 설정 파일 생성

`templates/app.conf.j2`

```jinja
# {{ inventory_hostname }} 설정
# 생성: Ansible

server_name = {{ inventory_hostname }}
environment  = {{ env_name | default('unknown') }}
port         = {{ app_port | default(8080) }}

# 같은 그룹의 다른 서버들
{% for host in groups['webservers'] %}
peer = {{ host }} ({{ hostvars[host]['ansible_host'] }}:{{ hostvars[host]['ansible_port'] }})
{% endfor %}

# 전체 호스트 수: {{ groups['all'] | length }}
```

```yaml
- name: 설정 파일 생성
  ansible.builtin.template:
    src: templates/app.conf.j2
    dest: /etc/app.conf
    mode: '0644'
  become: yes
```

### 생성 결과

node1:
```
# node1 설정
# 생성: Ansible

server_name = node1
environment  = study
port         = 8080

# 같은 그룹의 다른 서버들
peer = node1 (127.0.0.1:2221)
peer = node2 (127.0.0.1:2222)

# 전체 호스트 수: 2
```

node2에는 `server_name = node2`로, 나머지는 동일하게 생성됐다.

### 확인한 것

- **`inventory_hostname`** — 호스트마다 다른 내용의 파일이 만들어졌다. 하나의 템플릿으로 서버별 설정을 파생시킨다.
- **`groups` + `hostvars`** — 각 서버가 다른 서버의 주소와 포트를 알고 있다. 로드밸런서 백엔드 목록, 클러스터 peer 목록을 자동 생성하는 실무 패턴이 이것이다.
- **`default()` 필터** — 정의되지 않은 변수에 기본값을 준다. `app_port`가 없어 `8080`이 적용됐다.

Inventory 하나를 진실의 원천으로 두고 설정 파일을 파생시키는 구조다. 서버가 추가되면 Inventory만 고치면 모든 설정 파일이 따라 바뀐다.

## Jinja2 기본 문법

| 구문 | 용도 |
|---|---|
| `{{ 변수 }}` | 값 치환 |
| `{% for %}` / `{% endfor %}` | 반복 |
| `{% if %}` / `{% endif %}` | 조건 |
| `{# 주석 #}` | 렌더링되지 않는 주석 |

### 자주 쓰는 필터

| 필터 | 동작 |
|---|---|
| `default('값')` | 변수가 없을 때 기본값 |
| `length` | 길이 |
| `join(',')` | 리스트를 문자열로 |
| `upper` / `lower` | 대소문자 |
| `to_json` / `to_nice_yaml` | 직렬화 |
| `regex_replace()` | 정규식 치환 |
| `password_hash('sha512')` | 비밀번호 해시 |

`default()`에 `| default('값', true)`처럼 두 번째 인자를 주면 빈 문자열도 기본값으로 대체한다.

### 공백 제어

`{%- ... -%}`처럼 하이픈을 붙이면 앞뒤 공백과 줄바꿈을 제거한다. 설정 파일 형식이 공백에 민감할 때 쓴다.

---

## `--check` / `--diff` — 변경 사전 검증

### 개념

| 옵션 | 동작 |
|---|---|
| `--check` | 실제로 변경하지 않고 무엇이 바뀔지만 보고 (드라이런) |
| `--diff` | 파일 변경 내용을 diff 형식으로 출력 |
| `--limit` | 대상 호스트 제한 |

세 가지를 조합하면 "특정 서버 한 대에 대해, 실제 적용 없이, 어떤 내용이 바뀔지" 확인할 수 있다.

### 실습

템플릿의 공백을 수정한 뒤 `--check --diff`로 실행했다.

```bash
ansible-playbook -i inventory-deploy.ini template-test.yml --check --diff
```

```
TASK [설정 파일 생성]
--- before: /etc/app.conf
+++ after: /Users/shanks/.ansible/tmp/.../app.conf.j2
@@ -3,7 +3,7 @@
 
 server_name = node1
 environment  = study
-port         = 8080
+port = 8080
 
 # 같은 그룹의 다른 서버들
 peer = node1 (127.0.0.1:2221)

changed: [node1]

PLAY RECAP
node1 : ok=2  changed=1  unreachable=0  failed=0
```

### 실제 파일 확인

```bash
ansible webservers -i inventory-deploy.ini -m command -a "grep port /etc/app.conf" --become
```

```
node1 | CHANGED | rc=0 >>
port         = 8080
```

### 해석

- Playbook 출력은 `changed: [node1]`이었지만 **실제 파일은 바뀌지 않았다.**
- `--check` 모드에서 `changed`는 "바뀜"이 아니라 **"바뀔 예정"**을 뜻한다.
- `--diff`가 `before`/`after`를 보여주므로, 적용 전에 변경 내용을 눈으로 확인할 수 있다.

### 한계

`--check`가 모든 상황에서 정확하지는 않다.

- `command`/`shell` 모듈은 기본적으로 check 모드에서 건너뛴다. 실행해봐야 결과를 알 수 있기 때문이다.
- 앞 태스크의 결과에 의존하는 뒤 태스크는 부정확할 수 있다. 앞 태스크가 실제로 수행되지 않았기 때문이다.
- 모듈별로 check 모드 지원 수준이 다르다. `check_mode: no`로 특정 태스크는 check 모드에서도 실제 실행하게 할 수 있다.

### 운영 절차

```bash
# 1. 한 대에 대해 변경 예정 내용 확인
ansible-playbook -i inventory.ini deploy.yml --limit node1 --check --diff

# 2. 한 대에만 실제 적용
ansible-playbook -i inventory.ini deploy.yml --limit node1

# 3. 확인 후 전체 적용
ansible-playbook -i inventory.ini deploy.yml
```

---

## `no_log` — 변수 노출 차단과 그 경계

Playbook 변수에 비밀번호가 들어 있으면 `debug`로 출력하거나 태스크 결과에 포함될 때 로그에 그대로 남는다. 이를 억제하는 옵션이 `no_log: true`다.

**이 보호가 어디까지 유효한지** 확인했다.

### 테스트

```yaml
- name: no_log 동작 확인
  hosts: webservers
  gather_facts: no
  vars:
    db_password: "SuperSecret123"

  tasks:
    - name: 1. 그냥 출력
      ansible.builtin.debug:
        msg: "password is {{ db_password }}"

    - name: 2. no_log 적용
      ansible.builtin.debug:
        msg: "password is {{ db_password }}"
      no_log: true

    - name: 3. no_log 인데 태스크가 실패
      ansible.builtin.command: /bin/false
      environment:
        SECRET: "{{ db_password }}"
      no_log: true
      ignore_errors: yes

    - name: 4. 변수를 파일에 기록
      ansible.builtin.copy:
        content: "db_password={{ db_password }}\n"
        dest: /tmp/app.conf
        mode: '0644'
```

### 결과

| 상황 | 출력 | 노출 |
|---|---|---|
| 1. 그냥 `debug` | `password is SuperSecret123` | 노출 |
| 2. `no_log: true` | 출력 없음 (`ok:`만 표시) | 차단 |
| 3. `no_log` + 실패 | `"censored": "the output has been hidden due to the fact that 'no_log: true' was specified for this result"` | 차단 |
| 4. 파일로 기록 | `changed:`만 표시 | **로그는 깨끗, 파일에 평문** |
| `-vvv` 실행 | `grep -c` 결과 **4건** | 노출 |
| `ANSIBLE_DEBUG=1` 실행 | `grep -c` 결과 **4건** | 노출 |

### 3번이 예상과 달랐던 점

태스크가 실패하면 `no_log`가 무력화된다는 설명이 널리 돌지만, 실제로는 `censored` 메시지로 정상 차단됐다. 과거 버전의 이슈였고 현재는 수정된 것으로 보인다.

3주차 Jenkins Secret Masking 실습에서도 같은 일이 있었다. 공식 블로그(2019)에는 base64 인코딩으로 마스킹이 뚫린다고 되어 있었으나 실제로는 대부분 차단됐다. **알려진 취약점이 현재도 유효한지는 직접 확인해야 한다.**

### 실제로 새는 지점

**첫째, verbose 및 디버그 모드**

`-vvv`와 `ANSIBLE_DEBUG=1` 양쪽에서 각각 4건씩 평문이 검출됐다. `no_log`는 **태스크 결과 출력**을 억제하는 기능이지, Ansible 내부 처리 과정 전체를 가리는 것이 아니다.

실무에서 문제가 되는 구조는 이렇다. CI에서 배포가 실패해 원인을 보려고 `-vvv`를 켜면, 그 출력이 빌드 로그로 저장되고 아티팩트로 남는다. **로그 접근 권한은 대개 배포 권한보다 넓다.**

**둘째, 파일 시스템**

4번 태스크는 로그에 아무것도 남기지 않았지만, 대상 서버를 확인하면 값이 그대로 있다.

```
$ ansible webservers -i inventory.ini -m command -a "cat /tmp/app.conf"
node1 | CHANGED | rc=0 >>
db_password=SuperSecret123
```

`no_log`는 로그 출력에만 관여하며, 파일에 무엇이 쓰이는지는 관할 밖이다. 설정 파일을 배포하는 실제 작업에서 정확히 이 구조가 나온다.

### 정리

`no_log`는 **우발적 노출을 줄이는 장치**이지 접근 통제가 아니다.

| | Jenkins Secret Masking | Ansible `no_log` |
|---|---|---|
| 방식 | 알려진 문자열 패턴 치환 | 태스크 결과 출력 억제 |
| 우회 | `rev`, `cut` 등 변형 | `-vvv`, `ANSIBLE_DEBUG` |
| 범위 밖 | 파일 기록, 외부 전송 | 파일 기록, 외부 전송 |

두 도구 모두 **"로그에 보이지 않게 하는 것"과 "접근을 막는 것"을 혼동하면 안 된다.**

### 실제 통제 지점

- **변수 파일 암호화** — Ansible Vault. 다음 주차 주제다.
- **배포된 파일의 권한** — `mode: '0600'`, 소유자 제한. 이번 실습의 `0644`는 모든 사용자가 읽을 수 있다.
- **Playbook 저장소의 쓰기 권한** — Playbook을 수정할 수 있는 사람은 `no_log`를 제거하고 값을 출력할 수 있다.
- **verbose 로그의 보관 정책** — CI 로그 접근 권한과 보존 기간

마지막 항목이 지금까지 반복 확인된 구조다.

| 주차 | 실행 시점 방어 | 우회/해제 경로 | 실제 통제 지점 |
|---|---|---|---|
| Jenkins 2주차 | Secret Masking | `rev`, `cut` | `Job/Configure` 권한 |
| Jenkins 3주차 | Groovy Sandbox | Trusted로 등록 위치 변경 | 라이브러리 저장소 푸시 권한 |
| Ansible 4주차 | `no_log` | `-vvv`, 파일 기록 | Playbook 저장소 쓰기 권한 |

세 번 모두 실행 시점의 방어 장치는 우회 가능하거나 설정으로 해제됐고, 실제 통제는 **누가 코드를 넣을 수 있는가**에 있었다.

## 참고 자료

- [Ansible 공식 문서 - Templating (Jinja2)](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_templating.html)
- [Ansible 공식 문서 - Using filters to manipulate data](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_filters.html)
- [Ansible 공식 문서 - Validating tasks: check mode and diff mode](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_checkmode.html)
- [Ansible 공식 문서 - Protecting sensitive data with no_log](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_advanced_syntax.html)
- [Ansible 공식 문서 - Encrypting content with Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html)
