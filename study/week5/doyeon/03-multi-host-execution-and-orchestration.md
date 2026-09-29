# Ansible 멀티 호스트 실행과 오케스트레이션

> 한 줄 요약: `strategy`는 **작업 순서**, `forks`는 **컨트롤 노드의 전체 동시 작업자 수**, `serial`은 **배포 배치 크기**, `throttle`은 **특정 작업의 동시 실행 수**를 제어한다.

여러 서버에 같은 Playbook을 적용할 때 중요한 것은 단순히 “병렬로 실행한다”가 아니다. 서비스 중단을 피하려면 어느 서버가 어떤 순서로 배포되고, 한 번에 몇 대를 변경하며, 실패했을 때 어디까지 중단할지 설계해야 한다.

이 문서는 여러 웹 서버(`webservers`)에 새 버전을 무중단으로 배포할 때, 모든 서버를 한꺼번에 업데이트하지 않고 일부 서버씩 순서대로 배포하는 상황을 예시로 설명한다.

---

## 1. 먼저 보는 전체 그림

```text
대상 호스트 10대

strategy  ── 작업 진행 방식 결정 (호스트들이 같은 Task에서 보조를 맞출지)
forks     ── 컨트롤 노드가 동시에 처리할 최대 호스트 수
serial    ── 이번 배포 차례에 포함할 호스트 수 (배치)
throttle  ── 특정 Task 또는 block에만 적용하는 더 좁은 동시성 제한

실제 특정 Task의 동시 실행 수
  = min(forks, 현재 serial 배치 크기, 해당 Task의 throttle)
```

예를 들어 `forks: 10`, `serial: 4`, 특정 API 호출 Task에 `throttle: 2`를 설정하면 다음과 같다.

| 범위 | 동시 실행 상한 | 의미 |
|---|---:|---|
| Playbook 전체 | 10 | 컨트롤 노드가 만들 수 있는 worker(fork) 최대 수 |
| 현재 배포 배치 | 4 | 동시에 배포 대상으로 삼는 서버 수 |
| API 호출 Task | 2 | 그 Task만 한 번에 2대씩 실행 |

따라서 API 호출 Task는 최대 2대, 그 밖의 Task는 최대 4대에서 병렬 실행된다. `throttle`은 이미 `forks`나 `serial`이 정한 동시성을 **늘릴 수 없고 줄이기만** 한다.

---

## 2. 기본 `linear`과 `strategy: free`

### `linear`: 모든 호스트가 현재 Task를 끝낸 뒤 다음 Task로 이동한다

`linear`는 Ansible의 기본 전략이다. 현재 배치의 모든 호스트가 현재 Task를 끝내야 다음 Task가 시작된다.

```yaml
- name: Linear strategy example
  hosts: webservers
  strategy: linear # 생략해도 기본값으로 적용됨
  tasks:
    - name: Upload artifact
      ansible.builtin.copy:
        src: app.tar.gz
        dest: /tmp/app.tar.gz

    - name: Restart application
      ansible.builtin.service:
        name: myapp
        state: restarted
```

```text
시간 →
web-01  [artifact 업로드] [재시작]
web-02  [artifact 업로드] [재시작]
web-03  [artifact 업로드---------] [재시작]
                              ↑
                 가장 느린 web-03이 업로드를 마칠 때까지
                 web-01, web-02도 다음 Task로 가지 않는다.
```

- 장점: 단계 간 의존성이 명확하고, 로그·실패 분석이 비교적 쉽다.
- 적합한 경우: 배포, DB 마이그레이션 전후 처리, 모든 호스트가 특정 단계를 완료해야 다음 단계로 가도 되는 작업.
- 주의: 한 호스트가 느리면 다른 호스트도 기다리므로 전체 수행 시간이 길어질 수 있다.

### `free`: 호스트마다 가능한 만큼 다음 Task로 진행한다

`free` 전략은 느린 호스트가 다른 호스트의 진행을 막지 않게 한다. 각 호스트는 자신이 현재 Task를 끝내는 즉시 다음 Task를 실행한다.

```yaml
- name: Free strategy example
  hosts: webservers
  strategy: free
  tasks:
    - name: Upload artifact
      ansible.builtin.copy:
        src: app.tar.gz
        dest: /tmp/app.tar.gz

    - name: Restart application
      ansible.builtin.service:
        name: myapp
        state: restarted
```

```text
시간 →
web-01  [artifact 업로드] [재시작]
web-02  [artifact 업로드] [재시작]
web-03  [artifact 업로드---------] [재시작]
                        ↑
      web-01, web-02는 web-03을 기다리지 않고 다음 Task로 진행한다.
```

- 장점: 호스트별 작업 시간이 크게 다를 때 worker를 더 효율적으로 사용한다.
- 적합한 경우: 호스트 간 단계 동기화가 중요하지 않은 점검, 수집, 독립적인 설정 작업.
- 주의: 호스트마다 서로 다른 단계에 있게 되므로, “모두 로드밸런서에서 제외된 뒤 배포 시작” 같은 전역 순서 보장이 필요한 배포에는 신중히 사용한다.
- 주의: `free`와 `run_once` 조합은 실행 시점과 대상 호스트를 예측하기 어려울 수 있다. 자세한 이유는 아래를 참고한다.

#### 왜 `free`와 `run_once`를 함께 쓰면 위험한가?

`run_once: true`는 Task를 한 호스트에서만 실행한다. `free`에서는 먼저 이전 Task를 끝낸 호스트가 다음 Task로 이동하므로, 어떤 호스트가 `run_once` Task를 실행할지는 매 실행마다 달라질 수 있다.

```yaml
- hosts: webservers
  strategy: free
  tasks:
    - name: Upload artifact
      ansible.builtin.copy:
        src: app.tar.gz
        dest: /tmp/app.tar.gz

    - name: Run database migration once
      ansible.builtin.command: /opt/myapp/bin/migrate
      run_once: true
```

예를 들어 이번에는 `web-02`가, 다음 실행에는 `web-01`이 마이그레이션을 실행할 수 있다. 또 빠른 호스트는 다른 호스트가 업로드를 끝내기 전에도 다음 단계로 진행한다.

```text
strategy: free + run_once

web-01  [업로드----------------] [다음 Task]
web-02  [업로드] [마이그레이션 1회] [재시작]
web-03  [업로드------] [재시작]
```

DB 마이그레이션처럼 “어느 서버에서, 언제 한 번 실행할지”가 중요한 작업에는 이 순서가 위험할 수 있다. Ansible Lint도 `free`와 `run_once` 조합을 경고한다.

단일 실행이 중요하면 `linear`를 사용하고, 실행 호스트까지 고정해야 한다면 `delegate_to`를 함께 쓴다.

```yaml
# serial이 있어도 Play 전체에서 한 번만, 지정한 호스트에서 실행
- name: Run migration on the deployment runner
  ansible.builtin.command: /opt/myapp/bin/migrate
  delegate_to: deploy-runner-01
  run_once: true
  when: inventory_hostname == ansible_play_hosts_all[0]
```

### 선택 기준

| 요구사항 | 권장 설정 | 이유 |
|---|---|---|
| 단계별 전역 동기화가 필요함 | `linear` | 현재 Task가 배치 전체에서 끝난 후 다음 Task로 이동 |
| 독립적인 서버 점검·수집을 빠르게 수행 | `free` | 느린 호스트가 빠른 호스트를 막지 않음 |
| 무중단 롤링 배포 | `linear` + `serial` | 배치 내 절차를 읽기 쉽고 예측 가능하게 유지 |

---

## 3. `forks`: 컨트롤 노드의 병렬 작업자 수

`forks`는 Ansible 컨트롤 노드가 동시에 실행할 수 있는 최대 작업자 수다. 기본값은 5다. 대상이 20대여도 `forks`가 5이면 한 시점에는 최대 5대만 처리한다.

```ini
# ansible.cfg
[defaults]
forks = 20
```

또는 한 번의 실행에만 적용할 수 있다.

```bash
ansible-playbook -i inventory/hosts.yml playbooks/site.yml --forks 20
```

`forks`를 크게 잡는다고 항상 빨라지지는 않는다. 컨트롤 노드 CPU·메모리, SSH 연결 제한, 대상 서버의 부하, 호출 대상 API의 rate limit을 함께 고려해야 한다.

```text
forks를 높여도 serial: 2라면
→ 현재 배포 배치에는 2대만 있으므로 최대 2대까지만 작업한다.
```

운영 배포에서 `forks`는 인프라 전체의 처리 여력, `serial`은 서비스 위험 허용 범위를 표현하는 값으로 분리해 생각하면 좋다.

---

## 4. `serial`: Batch 기반 롤링 배포

`serial`은 대상 전체를 작은 배치로 나누고, **한 배치의 Play 전체를 완료한 뒤** 다음 배치로 넘어가게 한다. 무중단 배포에서 가장 자주 쓰는 키워드다.

```yaml
- name: Deploy in batches of two
  hosts: webservers
  strategy: linear
  serial: 2
  tasks:
    - name: Deploy application
      ansible.builtin.include_role:
        name: app_deploy

    - name: Verify application health
      ansible.builtin.uri:
        url: "http://127.0.0.1:8080/health"
        status_code: 200
```

대상이 7대이고 `serial: 2`라면 배치는 `2 → 2 → 2 → 1`이 된다. 각 배치에서 배포와 헬스 체크를 끝낸 후 다음 배치로 진행한다.

### 숫자, 백분율, 점진적 확대

```yaml
# 항상 3대씩
serial: 3

# 전체 대상의 20%씩 (최소 1대)
serial: "20%"

# Canary 1대 → 소규모 3대 → 이후 최대 20%씩
serial:
  - 1
  - 3
  - "20%"
```

마지막 예시는 첫 서버에서 배포를 검증한 뒤 점진적으로 범위를 키우는 Canary 배포 패턴이다. 단, `serial`의 퍼센트는 전체 대상 수를 기준으로 계산하며, 남은 호스트가 더 적으면 남은 호스트만 처리한다.

### 배치 순서도 명시하기

`serial`은 “누가 먼저 배포되는가”까지 보장하지 않는다. Canary 서버를 명확히 고르려면 inventory 그룹을 분리하거나 `order`를 함께 명시한다.

```yaml
- name: Roll out in a stable name order
  hosts: webservers
  order: sorted
  serial: 1
  tasks:
    - ansible.builtin.debug:
        msg: "Deploy {{ inventory_hostname }}"
```

`order: inventory`는 기본값이지만, 인벤토리 파일에 적힌 순서와 완전히 같다고 가정하면 안 된다. 실제로는 Ansible이 조합한 inventory 결과의 순서를 따른다.

---

## 5. `run_once`, `delegate_to`, `throttle`

### `run_once`: 현재 배치에서 한 번만 실행

예를 들어 스키마 마이그레이션은 서버마다 반복 실행하면 안 될 수 있다.

```yaml
- name: Run database migration once per batch
  ansible.builtin.command: /opt/myapp/bin/migrate
  run_once: true
```

중요한 규칙은 다음과 같다.

- `serial`이 없으면 Play의 첫 번째 활성 호스트에서 1회 실행한다.
- `serial`이 있으면 **각 배치의 첫 번째 활성 호스트에서 1회씩** 실행한다.
- 실행 결과와 facts는 기본적으로 같은 배치의 활성 호스트에 적용된다.

따라서 DB 마이그레이션처럼 Play 전체에서 정확히 한 번만 실행해야 하는 작업을 `serial`과 함께 쓸 때는 조건을 명시한다.

```yaml
- name: Run database migration exactly once for this play
  ansible.builtin.command: /opt/myapp/bin/migrate
  when: inventory_hostname == ansible_play_hosts_all[0]
```

이 방식도 첫 호스트가 실행 불가 상태가 되는 상황을 고려해야 한다. 더 확실하게 특정 실행 위치를 정하고 싶다면 `delegate_to`와 조합한다.

### `delegate_to`: 작업을 다른 호스트에서 실행

배포 대상은 `webservers`지만, 로드밸런서의 upstream 설정 변경은 보통 로드밸런서 또는 컨트롤 노드에서 실행해야 한다. 이때 Task에 `delegate_to`를 둔다.

```yaml
- name: Remove current web server from load balancer
  ansible.builtin.command: >
    /usr/local/bin/lbctl disable {{ inventory_hostname }}
  delegate_to: load-balancer-01

- name: Deploy application on current web server
  ansible.builtin.include_role:
    name: app_deploy

- name: Add current web server back to load balancer
  ansible.builtin.command: >
    /usr/local/bin/lbctl enable {{ inventory_hostname }}
  delegate_to: load-balancer-01
```

`delegate_to`는 “현재 호스트에 대한 작업의 실행 장소”만 바꾼다. 위 예에서 `inventory_hostname`은 계속 현재 배포 중인 웹 서버다.

주의할 점은 여러 웹 서버가 하나의 delegated 호스트의 같은 파일·API를 동시에 수정하면 경쟁 상태가 생길 수 있다는 것이다. 이때는 `serial: 1`, `throttle: 1`, 또는 `run_once` + loop 중 상황에 맞는 방법으로 동시성을 제한한다.

```yaml
- name: Call shared deployment API one at a time
  ansible.builtin.uri:
    url: "https://deploy-api.internal/v1/register/{{ inventory_hostname }}"
    method: POST
    status_code: 204
  delegate_to: localhost
  throttle: 1
```

### `throttle`: 특정 Task/block만 병렬도 낮추기

배포는 5대씩 해도 외부 API 호출은 2개만 동시에 허용해야 하는 경우가 있다.

```yaml
- name: Deploy a batch
  hosts: webservers
  serial: 5
  tasks:
    - name: Install application package
      ansible.builtin.package:
        name: myapp
        state: present

    - name: Notify rate-limited deployment API
      ansible.builtin.uri:
        url: "https://deploy-api.internal/v1/deployments"
        method: POST
        body_format: json
        body:
          host: "{{ inventory_hostname }}"
      throttle: 2
```

위 Play에서는 패키지 설치를 최대 5대에서 병렬로 진행하지만, API 호출만 최대 2대에서 진행한다. 여러 Task에 같은 제한을 반복해서 쓰고 싶으면 `block`에 `throttle`을 둘 수 있다. 아래에서는 `notify-start`와 `notify-finish` 각각이 한 번에 한 호스트에서만 실행된다.

```yaml
- name: Notify external system with limited concurrency
  block:
    - ansible.builtin.command: /usr/local/bin/notify-start
    - ansible.builtin.command: /usr/local/bin/notify-finish
  throttle: 1
```

`block`은 관련 Task를 묶어 공통 옵션을 적용하는 문법이다. `throttle: 1`이 두 Task 사이의 전체 흐름을 하나의 원자적 작업으로 만들지는 않는다. “app01에서 start와 finish를 모두 끝낸 뒤 app02를 처리”해야 한다면 `serial: 1`을 사용한다.

---

## 6. 실패 정책: `any_errors_fatal`과 `max_fail_percentage`

기본 동작에서는 한 호스트의 Task가 실패하면 그 호스트에서는 이후 Task를 중단하지만, 다른 호스트는 계속 진행한다. 배포에서는 이 기본 정책이 너무 느슨하거나 너무 엄격할 수 있으므로 허용 가능한 실패 범위를 정책으로 선언한다.

### `any_errors_fatal: true`: 하나라도 실패하면 전체 중단

```yaml
- name: Stop all deployment work on a critical failure
  hosts: webservers
  serial: 2
  any_errors_fatal: true
  tasks:
    - name: Deploy application
      ansible.builtin.include_role:
        name: app_deploy
```

현재 배치의 어떤 호스트에서든 fatal Task가 실패하면 Ansible은 그 Task를 현재 배치의 다른 호스트에서 마무리한 뒤, 이후 Task와 이후 배치의 실행을 중단한다.

- 적합한 경우: 보안 키 배포, 로드밸런서 전체 차단처럼 한 부분만 성공한 상태가 위험한 절차.
- 주의: “즉시 모든 작업을 강제 취소”가 아니라 현재 진행 중인 fatal Task가 배치에서 마무리된 뒤 중단되는 동작이다.
- 범위: Play 전체뿐 아니라 필요한 `block`에만 적용할 수도 있다.

### `max_fail_percentage`: 배치별 허용 실패율

```yaml
- name: Abort if more than 20 percent of a batch fails
  hosts: webservers
  serial: 10
  max_fail_percentage: 20
  tasks:
    - name: Deploy application
      ansible.builtin.include_role:
        name: app_deploy
```

`serial`과 함께 쓸 때 `max_fail_percentage`는 **전체 대상이 아니라 각 배치에 적용**된다. 위 예에서 10대 배치 중 3대가 실패하면 20%를 초과했으므로 이후 실행이 중단된다.

임계값은 “이상(≥)”이 아니라 “초과(>)”일 때 중단된다. 그래서 4대 배치에서 2대 실패 시 중단하려면 `50`이 아니라 `49`를 설정해야 한다.

| 정책 | 의미 | 사용 예 |
|---|---|---|
| `any_errors_fatal: true` | 1대라도 실패하면 중단 | 트래픽 제어·보안 변경 등 원자성이 중요한 작업 |
| `max_fail_percentage: 20` | 배치 실패율이 20%를 초과하면 중단 | 다수 서버에 점진 배포, 일시적 개별 실패를 일부 허용 |
| 둘 다 생략 | 실패한 호스트만 중단, 다른 호스트는 계속 | 비핵심 설정 변경·상태 수집 |

두 정책은 의도가 다르므로 일반적으로 하나를 선택해 사용한다. `any_errors_fatal: true`를 동시에 설정하면 단 한 대의 실패도 허용하지 않는 정책이 된다.

---

## 7. 실전형 롤링 배포 예시

다음 Playbook은 한 대씩 Canary 배포를 시작하고, 각 서버를 로드밸런서에서 제외한 뒤 배포·헬스 체크·복귀하는 흐름을 보여 준다.

```yaml
---
- name: Roll out application safely
  hosts: webservers
  become: true
  gather_facts: false
  strategy: linear
  serial:
    - 1      # Canary
    - "25%"  # 검증 후 점진 확대
    - "100%"
  max_fail_percentage: 0

  pre_tasks:
    - name: Run database migration once before rolling deployment
      ansible.builtin.command: /opt/myapp/bin/migrate
      delegate_to: deploy-runner-01
      become: false
      run_once: true
      when: inventory_hostname == ansible_play_hosts_all[0]

  tasks:
    - name: Remove this server from load balancer
      ansible.builtin.command: >
        /usr/local/bin/lbctl disable {{ inventory_hostname }}
      delegate_to: load-balancer-01
      throttle: 1

    - name: Deploy application to this server
      ansible.builtin.include_role:
        name: app_deploy

    - name: Verify local health endpoint
      ansible.builtin.uri:
        url: http://127.0.0.1:8080/health
        status_code: 200
      register: health
      retries: 12
      delay: 5
      until: health.status == 200

    - name: Add this server back to load balancer
      ansible.builtin.command: >
        /usr/local/bin/lbctl enable {{ inventory_hostname }}
      delegate_to: load-balancer-01
      throttle: 1
```

이 예시의 의도는 다음과 같다.

1. 첫 배치는 1대(Canary)만 배포한다.
2. `linear`로 배치 내 절차를 일관되게 진행한다.
3. 로드밸런서 작업은 지정된 호스트에서 실행하고, 공유 제어 지점의 동시 변경은 `throttle: 1`로 막는다.
4. 헬스 체크 실패는 Task 실패가 되며 `max_fail_percentage: 0` 때문에 다음 배포를 진행하지 않는다.
5. DB 마이그레이션은 배치마다 반복되지 않도록 전체 Play의 첫 호스트 조건과 특정 실행 호스트 위임을 함께 사용한다.

> 운영 환경에서는 배포 실패 시 로드밸런서에 재등록하는 `rescue`/`always` 처리와 애플리케이션 롤백 절차도 추가해야 한다. 현재 저장소의 [`rolling-deploy.yml`](playbooks/rolling-deploy.yml)도 `serial: 1`과 `any_errors_fatal: true`를 사용하는 기본 롤링 배포 예시다.

---

## 8. 이번 실습 요약

이번 실습에서는 app01, app02, app03을 대상으로 `sleep`, `debug`, 의도적 `fail`만 실행했다. Nginx 설정이나 배포 파일은 바꾸지 않았다.

### 실행 전략: `linear`과 `free`

[`strategy-lab.yml`](playbooks/strategy-lab.yml)은 서버별 대기 시간을 app01=1초, app02=3초, app03=5초로 다르게 설정한다.

```bash
ansible-playbook playbooks/strategy-lab.yml \
  -e 'lab_strategy=linear' -f 3 \
  --vault-id production@vault-password-production
```

`linear`에서는 app03의 대기가 끝난 뒤에야 세 서버 모두 Step 2를 시작했다. 같은 파일을 `-e 'lab_strategy=free'`로 실행하면 app01은 1초 후 바로 Step 2로 이동하고, app02·app03은 자기 대기를 마친 뒤 각각 이동했다.

### `forks`와 `throttle`

[`concurrency-lab.yml`](playbooks/concurrency-lab.yml)의 `forks` Task는 각 서버에서 3초 동안 독립 작업을 흉내 낸다.

```bash
time ansible-playbook playbooks/concurrency-lab.yml \
  --tags forks -f 1 \
  --vault-id production@vault-password-production

time ansible-playbook playbooks/concurrency-lab.yml \
  --tags forks -f 3 \
  --vault-id production@vault-password-production
```

`-f 1`은 약 13.8초, `-f 3`은 약 4.3초가 걸렸다. 대기 시간 외에 SSH 연결과 Ansible 초기화 시간이 포함되지만, worker 수를 늘리면 독립 작업이 병렬로 처리된다는 점을 확인할 수 있다.

같은 파일의 `throttle` Task에는 `throttle: 1`을 넣었다. `-f 3`으로 실행해도 app01 → app02 → app03 순으로 해당 Task가 하나씩 진행됐다.

### `run_once`와 `delegate_to`

```bash
ansible-playbook playbooks/concurrency-lab.yml \
  --tags run_once -f 3 \
  --vault-id production@vault-password-production
```

로그의 `app01 -> localhost`는 app01이 현재 배치의 대표 호스트이고, 명령은 관리 노드인 localhost에서 실행됐다는 뜻이다. `run_once` Task가 만든 marker 값은 현재 배치의 app01·app02·app03 모두가 참조했다.

### `serial` 배치와 실패 비율

[`batch-lab.yml`](playbooks/batch-lab.yml)에서 `serial: 2`는 `[app01, app02]` 배치를 끝낸 뒤 `[app03]` 배치로 진행했다. `serial: "50%"`는 대상 세 대의 50%가 1.5대이므로 최소 정수 배치인 한 대씩 app01 → app02 → app03으로 진행했다.

[`failure-threshold-lab.yml`](playbooks/failure-threshold-lab.yml)은 첫 배치(app01, app02)에서 app02만 의도적으로 실패시켰다.

| 설정 | 1/2 실패 시 결과 |
|---|---|
| `max_fail_percentage: 49` | 실패율 50%가 기준을 초과하므로 app03 배치를 시작하지 않음 |
| `max_fail_percentage: 50` | 실패율 50%가 기준과 같으므로 app01과 app03은 계속 진행 |

`max_fail_percentage`는 기준과 같을 때가 아니라 **기준을 초과할 때** 중단한다.

---

## 9. 학습·검증 순서

1. 인벤토리에 테스트 호스트 3대를 준비한다. 로컬 검증에는 `ansible_connection: local`도 사용할 수 있다.
2. 동일한 `debug` + `command: sleep` Playbook을 `linear`과 `free`로 각각 실행해 출력 순서를 비교한다.
3. `--forks 1`, `--forks 3`으로 바꿔 worker 수에 따른 차이를 확인한다.
4. `serial: 1`, `serial: 2`, `serial: [1, "100%"]`을 바꾸어 배치 이동을 확인한다.
5. `delegate_to: localhost` Task에 `throttle: 1`을 넣고, 공유 파일을 동시에 수정하지 않도록 동시성을 제어한다.
6. 테스트용 Task에 `ansible.builtin.fail`을 넣어 `any_errors_fatal`과 `max_fail_percentage`가 중단시키는 시점을 관찰한다.

안전한 사전 점검 명령은 다음과 같다.

```bash
# 문법 검사
ansible-playbook -i inventory/hosts.yml playbooks/rolling-deploy.yml --syntax-check

# 변경 없이 예상 변경 사항 확인
ansible-playbook -i inventory/hosts.yml playbooks/rolling-deploy.yml --check --diff

# 특정 그룹 또는 호스트에만 제한하여 실행
ansible-playbook -i inventory/hosts.yml playbooks/rolling-deploy.yml --limit webservers
```

`--check`은 모든 모듈의 실제 동작을 완전히 재현하지는 않으며, 특히 `command`·외부 API·상태 검증에는 별도 테스트 환경이 필요하다.

---

## 참고 문서

- [Controlling playbook execution: strategies and more](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)
- [linear strategy](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/linear_strategy.html)
- [free strategy](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/free_strategy.html)
- [Controlling where tasks run: delegation and local actions](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_delegation.html)
- [Error handling in playbooks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)
- [Continuous Delivery and Rolling Upgrades](https://docs.ansible.com/projects/ansible/latest/playbook_guide/guide_rolling_upgrade.html)
- [Ansible Lint run-once rule](https://docs.ansible.com/projects/lint/rules/run-once/)
