# Idempotency & no_log

## Idempotency (멱등성)

- 같은 작업을 여러 번 실행해도 결과 상태가 동일한 성질이다.
- Ansible 모듈은 대부분 **현재 상태를 먼저 확인하고, 원하는 상태와 다를 때만 변경**한다.
- 셸 스크립트와의 근본적인 차이다. `apt install nginx`를 두 번 실행하는 스크립트는 두 번 설치를 시도하지만, Ansible의 `apt` 모듈은 이미 설치되어 있으면 아무것도 하지 않는다.

### 실행 결과 표시

- `ok` — 확인했고 변경할 것이 없었다
- `changed` — 실제로 변경했다
- `failed` — 실패
- `skipped` — 조건에 맞지 않아 건너뜀

### 실습: 동일 Playbook 반복 실행

첫 실행 이후, 같은 Playbook을 한 번 더 실행했다.

```
TASK [패키지 목록 갱신]        ok: [node1] ok: [node2]
TASK [nginx 설치]              ok: [node1] ok: [node2]
TASK [애플리케이션 디렉터리 생성] ok: [node1] ok: [node2]
TASK [인덱스 파일 배포]        ok: [node1] ok: [node2]
TASK [멱등하지 않은 예]        changed: [node1] changed: [node2]

PLAY RECAP
node1 : ok=6  changed=1  unreachable=0  failed=0
node2 : ok=6  changed=1  unreachable=0  failed=0
```

### 해석

- `apt`, `file`, `copy` 태스크는 모두 `ok`로 끝났다. 이미 원하는 상태이므로 아무 작업도 수행하지 않았다.
- `command` 모듈만 `changed`로 표시됐다. **Ansible은 임의 명령이 시스템에 어떤 영향을 주는지 알 수 없으므로, 실행했다는 사실만으로 항상 `changed`로 간주한다.**
- 즉 멱등성은 Ansible 자체의 성질이 아니라 **모듈이 제공하는 성질**이다. `command`나 `shell`을 쓰는 순간 그 보장은 사라진다.

### 실무적 함의

- `changed` 개수는 배포 후 확인 지표로 쓸 수 있다. 아무것도 바뀌지 않아야 할 상황에서 `changed`가 나오면 설정 드리프트가 있다는 신호다.
- `--check` 모드로 실제 변경 없이 무엇이 바뀔지 미리 확인할 수 있다.
- `command`/`shell`을 꼭 써야 한다면 `creates:`, `removes:`, `changed_when:` 옵션으로 멱등성을 직접 부여할 수 있다.

---

## no_log — 변수 노출 차단의 경계

Ansible은 태스크 결과를 로그에 출력한다. 변수에 비밀번호가 들어 있으면 그대로 노출된다. 이를 억제하는 옵션이 `no_log: true`다.

**이 보호가 어디까지 유효한지** 직접 확인했다.

### 테스트 Playbook

```yaml
- name: no_log 동작 확인
  hosts: webservers
  gather_facts: no
  vars:
    db_password: "SuperSecret123"

  tasks:
    - name: 1. 그냥 출력
      debug:
        msg: "password is {{ db_password }}"

    - name: 2. no_log 적용
      debug:
        msg: "password is {{ db_password }}"
      no_log: true

    - name: 3. no_log 인데 태스크가 실패
      command: /bin/false
      environment:
        SECRET: "{{ db_password }}"
      no_log: true
      ignore_errors: true

    - name: 4. no_log 없이 변수를 파일에 기록
      copy:
        content: "db_password={{ db_password }}\n"
        dest: /tmp/app.conf
        mode: '0644'
```

### 결과

| 상황 | 출력 | 노출 여부 |
|---|---|---|
| 1. 그냥 `debug` | `password is SuperSecret123` | 노출 |
| 2. `no_log: true` | 출력 없음 (`ok:` 만 표시) | 차단 |
| 3. `no_log` + 실패 | `"censored": "the output has been hidden..."` | 차단 |
| 4. 파일로 기록 | `changed:` 만 표시 | 로그는 깨끗, **파일에 평문** |
| `-vvv` 실행 | `grep -c` 결과 **4건** | 노출 |
| `ANSIBLE_DEBUG=1` 실행 | `grep -c` 결과 **4건** | 노출 |

### 3번이 예상과 달랐던 점

- 태스크가 실패하면 `no_log`가 무력화된다는 설명이 널리 돌지만, 실제로는 `censored` 메시지로 정상 차단됐다.
- 실패 시 노출 문제는 과거 버전의 이슈였고 현재는 수정된 것으로 보인다.
- 지난주 Jenkins Secret Masking 실습에서도 같은 일이 있었다. 공식 블로그(2019)에는 base64 인코딩으로 마스킹이 뚫린다고 되어 있었으나 실제로는 대부분 차단됐다. **알려진 취약점이 현재도 유효한지는 직접 확인해야 한다**는 것이 두 주 연속 확인된 부분이다.

### 실제로 새는 지점

**첫째, verbose 및 디버그 모드**

`-vvv`와 `ANSIBLE_DEBUG=1` 양쪽에서 각각 4건씩 평문이 검출됐다. `no_log`는 **태스크 결과 출력**을 억제하는 기능이지, Ansible 내부 처리 과정 전체를 가리는 것이 아니다.

실무에서 문제가 되는 구조는 다음과 같다. CI에서 배포가 실패해 원인을 보려고 `-vvv`를 켜면, 그 출력이 빌드 로그로 저장되고 아티팩트로 남는다. 로그 접근 권한은 대개 배포 권한보다 넓다.

**둘째, 파일 시스템**

4번 태스크는 로그에 아무것도 남기지 않았지만, 대상 서버를 확인하면 값이 그대로 있다.

```
$ ansible webservers -i inventory.ini -m command -a "cat /tmp/app.conf"
node1 | CHANGED | rc=0 >>
db_password=SuperSecret123
```

`no_log`는 로그 출력에만 관여하며, 파일에 무엇이 쓰이는지는 애초에 관할 밖이다. 설정 파일을 배포하는 실제 작업에서 정확히 이 구조가 나온다.

### 결론

- `no_log`는 **우발적 노출을 줄이는 장치**이지 접근 통제가 아니다.
- 지난주 Jenkins Secret Masking과 정확히 같은 성질이다.
  * Jenkins 마스킹: 알려진 문자열 패턴을 치환 → 변형(`rev` 등)으로 우회 가능
  * Ansible `no_log`: 태스크 결과 출력을 억제 → verbose/디버그로 우회, 파일 기록은 범위 밖
- 두 도구 모두 **"로그에 보이지 않게 하는 것"과 "접근을 막는 것"을 혼동하면 안 된다.**

### 실제 통제 지점

- **변수 파일 암호화** — Ansible Vault (4주차 주제)
- **배포된 파일의 권한** — `mode: '0600'`, 소유자 제한
- **Playbook 저장소의 쓰기 권한** — Playbook을 수정할 수 있는 사람은 `no_log`를 제거하고 값을 출력할 수 있다. 지난주 Jenkins의 `Job/Configure` 권한과 동일한 구조다.
- **verbose 로그의 보관 정책** — CI 로그 접근 권한과 보존 기간

---

## 3주차 정리

멱등성과 `no_log`는 별개 주제처럼 보이지만 공통점이 있다. 둘 다 **Ansible이 보장하는 범위가 어디까지인지**에 대한 문제다.

- 멱등성은 Ansible이 아니라 **모듈**이 보장한다. `command`를 쓰면 사라진다.
- `no_log`는 **태스크 결과 출력**만 보장한다. verbose와 파일 기록은 범위 밖이다.

도구가 무엇을 보장하고 무엇을 보장하지 않는지 경계를 아는 것이, 도구 사용법을 아는 것보다 운영에서 중요하다고 느꼈다.

## 참고 자료

- [Ansible 공식 문서 - Desired state and idempotency](https://docs.ansible.com/ansible/latest/getting_started/basic_concepts.html)
- [Ansible 공식 문서 - Protecting sensitive data with no_log](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_advanced_syntax.html)
- [Ansible 공식 문서 - Validating tasks: check mode](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_checkmode.html)
- [Ansible 공식 문서 - Encrypting content with Ansible Vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html)
