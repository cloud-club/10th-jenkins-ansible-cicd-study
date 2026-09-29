# 1. Role-Based Architecture

## 1. Role이 필요한 이유

Playbook 하나에 설치, 설정, 배포 작업을 모두 작성하면 처음에는 단순하지만 서버와 환경이 늘수록 중복이 많아진다. Role은 관련 작업과 파일을 하나의 재사용 가능한 단위로 묶는다.

```text
roles/webapp/
├── tasks/main.yml       # 실행할 작업
├── handlers/main.yml    # notify로 호출되는 후속 작업
├── templates/           # Jinja2 템플릿
├── files/               # 그대로 복사할 정적 파일
├── defaults/main.yml    # 쉽게 덮어쓸 기본값
├── vars/main.yml        # Role 내부의 강한 고정값
└── meta/main.yml        # Role 정보와 의존성
```

Role 기본 구조는 다음 명령으로 만들 수 있다.

```bash
ansible-galaxy role init roles/webapp
```

## 2. 디렉터리별 역할

| 디렉터리 | 용도 | 예시 |
|---|---|---|
| `tasks/` | Role의 실제 작업 | 패키지 설치, 파일 배포 |
| `handlers/` | 변경이 발생했을 때만 실행 | nginx reload |
| `templates/` | 변수를 반영할 설정 파일 | `nginx.conf.j2` |
| `files/` | 가공 없이 복사할 파일 | 인증서, 정적 파일 |
| `defaults/` | 사용자가 바꾸기 쉬운 기본값 | 포트, 패키지명 |
| `vars/` | Role 내부에서 강하게 유지할 값 | 내부 경로, 상수 |
| `meta/` | Role 의존성·메타데이터 | `common` Role 의존 |

## 3. defaults와 vars의 차이

두 파일 모두 변수를 정의하지만 우선순위가 다르다.

```yaml
# roles/webapp/defaults/main.yml
web_port: 8080
app_version: "1.0.0"
```

`defaults/main.yml`은 우선순위가 낮아 inventory, play 변수, `-e` 등으로 쉽게 덮어쓸 수 있다. Role 사용자에게 열어 둘 설정은 여기에 둔다.

```yaml
# roles/webapp/vars/main.yml
web_config_dir: /etc/webapp
```

`vars/main.yml`은 우선순위가 높다. 일반적인 환경별 설정은 여기에 두지 않는 편이 좋다. 지나치게 많이 사용하면 Role 재사용성이 떨어진다.

실무 기준은 간단하다.

- 사용자가 조정해야 하는 값 → `defaults/`
- 환경별 값 → `group_vars/`, `host_vars/`
- 정말 Role 내부에 고정해야 하는 값 → `vars/`
- 긴급하거나 실행 시점에만 정하는 값 → `--extra-vars` (`-e`)

`-e`는 매우 강한 우선순위를 가지므로 편리하지만, 잘못 사용하면 롤백 변수까지 덮어쓸 수 있다. 배포 대상은 `target_version`, 현재 안정 버전은 `stable_version`처럼 목적별로 이름을 나누는 것이 안전하다.

## 4. Role을 사용하는 Playbook

```yaml
---
- name: Configure web servers
  hosts: web
  become: true
  roles:
    - role: common
    - role: webapp
      vars:
        web_port: 80
```

Playbook에는 어떤 호스트에 어떤 Role을 적용할지만 남고, 구현 세부사항은 Role 안으로 이동한다.

## 5. import_role과 include_role

```yaml
tasks:
  - name: Statically load webapp role
    ansible.builtin.import_role:
      name: webapp

  - name: Dynamically load migration role
    ansible.builtin.include_role:
      name: migration
    when: run_migration | bool
```

| 구분 | `import_role` | `include_role` |
|---|---|---|
| 처리 시점 | Playbook 해석 시점 | 실제 실행 시점 |
| 성격 | 정적 | 동적 |
| task 목록 예측 | 쉬움 | 실행 조건에 따라 달라짐 |
| 적합한 상황 | 항상 포함되는 Role | 조건·반복에 따라 선택되는 Role |

기본적으로 구조가 고정되어 있으면 `roles:` 또는 `import_role`, 런타임 조건으로 선택해야 하면 `include_role`을 사용한다.

## 6. 의존성 관리

직접 만든 Role 사이의 의존성은 `meta/main.yml`에 선언할 수 있다.

```yaml
dependencies:
  - role: common
```

외부 Role과 Collection은 `requirements.yml`로 버전을 고정한다.

```yaml
---
roles:
  - name: geerlingguy.nginx
    version: "3.2.0"

collections:
  - name: community.general
    version: "10.4.0"
```

```bash
ansible-galaxy install -r requirements.yml
```

CI 환경에서 매번 최신 버전을 받으면 같은 코드가 어느 날 다르게 동작할 수 있다. 재현 가능한 배포를 위해 검증한 버전을 명시적으로 고정한다.

## 7. 정리

- Role은 Ansible 코드의 재사용·테스트·책임 분리를 돕는다.
- 변경 가능한 값은 `defaults`, 환경별 값은 inventory 계층에서 관리한다.
- 정적 구성은 `import_role`, 동적 선택은 `include_role`이 잘 맞는다.
- 외부 의존성은 `requirements.yml`에 버전을 고정한다.

