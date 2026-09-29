# Jinja2 & Safe Execution

## 5. Jinja2 Template이 필요한 이유

---

- Jinja2는 **변수, 조건문, 반복문 등을 이용해 텍스트를 동적으로 생성하는 Template Engine**이다.
- Ansible에서는 설정 파일 구조는 하나로 유지하고, 환경별로 달라지는 값만 Variable로 분리할 때 사용한다.

> **Template = 공통 구조 + 환경별 Variable
문자열이나 설정 파일 안에 변수를 넣어서, 실행 시점에 실제 값으로 치환해주는 템플릿 엔진**
> 

```
DEV  → port 8080
STG  → port 8080
PROD → port 80
```

### 5-1. template Module

---

`copy`는 완성된 파일을 그대로 복사하고, `template`은 **Jinja2와 Variable을 조합해 최종 파일을 생성**한다.

Template:

```
server.port={{ app_port }}
log.level={{ log_level | default('INFO') }}
```

Variable:

```yaml
app_port: 8080
```

Playbook:

```yaml
- name: Render application config
  ansible.builtin.template:
    src: app.conf.j2
    dest: /etc/myapp/app.conf
```

### 5-2. 기본 Jinja2 표현

---

#### 변수 치환

```
{{ app_port }}
```

#### 조건문

```
{% if enable_tls %}
listen 443 ssl;
{% else %}
listen 80;
{% endif %}
```

#### 반복문

```yaml
{% for server in upstream_servers %}
server {{ server }};
{% endfor %}
```

#### 자주 사용하는 Filter

```
{{ log_level | default('INFO') }}
{{ app_name | lower }}
{{ allowed_hosts | join(',') }}
{{ upstream_servers | length }}
```

### 5-3. 변경 전 검증: --check

---

Check Mode는 **실제 변경 없이 어떤 변경이 발생할지 미리 확인하는 Dry Run 기능**이다.

```bash
ansible-playbook site.yml -i inventory.yml --check
```

주의:

- 모든 Module이 Check Mode를 동일하게 지원하지는 않는다.
- Check Mode 결과가 실제 실행을 완전히 보장하지는 않는다.

<aside>
🤔

`--check`는 예측이므로 실제 적용 전 소수 Host 검증과 Health Check가 필요하다.

</aside>

### 5-4. 변경 내용 확인: --diff

---

Diff Mode는 **파일이나 Template의 변경 전/후 차이를 보여주는 기능**이다.

- `--check`: 변경 여부 예측
- `--diff`: 정확히 무엇이 달라지는지 확인

```bash
ansible-playbook site.yml -i inventory.yml --check --diff
```

Secret이 포함된 파일은 Diff 노출을 막을 수 있다.

```yaml
- name: Render secret config
  ansible.builtin.template:
    src: secret.conf.j2
    dest: /etc/myapp/secret.conf
  diff: false
```

### 5-5. 특정 Host만 안전하게 검증

---

잘못된 자동화도 대량으로 적용될 수 있으므로 **한 대 또는 소수 Host에 먼저 적용한 뒤 전체로 확대**하는 것이 안전하다.

```bash
# 변경 예정 확인
ansible-playbook site.yml   -i inventories/prod/hosts.yml   --check --diff --limit web01

# 한 대 실제 적용
ansible-playbook site.yml   -i inventories/prod/hosts.yml   --limit web01

# 전체 Web Group 적용
ansible-playbook site.yml   -i inventories/prod/hosts.yml   --limit web
```

### 5-6. 추가 Safe Execution 명령

---

Safe Execution은 **실제 변경 전에 문법, 대상, Task, 변경 내용을 확인해 영향 범위를 줄이는 실행 전략**이다.

```bash
# 문법 검사
ansible-playbook site.yml --syntax-check

# 대상 Host 확인
ansible-playbook site.yml -i inventory.yml --list-hosts

# Task 확인
ansible-playbook site.yml --list-tasks

# Tag 확인
ansible-playbook site.yml --list-tags
```

<aside>
🛡️

운영에서는 **Syntax Check → 대상 확인 → Check/Diff → 소수 Host → Health Check → 전체 적용** 순서로 진행하면 안전하다.

</aside>

### 5-7. 안전한 실행 흐름

---

```
Syntax Check
    ↓
대상 Host 확인
    ↓
--check / --diff
    ↓
--limit으로 1대 적용
    ↓
Health Check
    ↓
전체 적용
```

### 5-8. 실습

---

- [ ]  `nginx.conf.j2` 작성
- [ ]  DEV/PROD Variable 분리
- [ ]  조건문 또는 반복문 사용
- [ ]  `--syntax-check` 실행
- [ ]  `--list-hosts` 확인
- [ ]  `--check --diff --limit <host>` 실행
- [ ]  한 서버 실제 적용
- [ ]  재실행 후 멱등성 확인
- [ ]  Secret Template에 `diff: false` 적용

### 5-9. 운영 적용 체크리스트

---

- [ ]  Inventory 환경이 분리되어 있는가?
- [ ]  대상 Host를 확인했는가?
- [ ]  Syntax Check를 통과했는가?
- [ ]  Check/Diff를 확인했는가?
- [ ]  Secret이 Log/Diff에 노출되지 않는가?
- [ ]  소수 Host부터 적용하는가?
- [ ]  적용 후 Health Check를 수행하는가?
- [ ]  실패 시 원복 절차가 있는가?

### 5-10. 여기서 생각해볼 질문

---

1. `copy`와 `template`은 언제 각각 사용하는가?
2. Jinja2 Variable을 분리하는 이유는?
3. `--check`가 실제 실행을 완전히 대체할 수 없는 이유는?
4. `--diff` 사용 시 보안상 무엇을 주의해야 하는가?
5. 운영 전체 적용 전에 어떤 순서로 검증해야 하는가?

### 5-11. 참고 자료

---

- [Ansible 공식 문서 - Check Mode & Diff Mode](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_checkmode.html)
- [Ansible Builtin default Filter](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/default_filter.html)
- [Ansible Builtin Collection](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/)