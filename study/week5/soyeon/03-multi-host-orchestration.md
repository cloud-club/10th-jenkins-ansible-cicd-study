# 3. Multi-Host Execution & Orchestration

## 1. strategy: linear와 free

기본 전략인 `linear`는 모든 호스트가 현재 task를 끝낸 뒤 다음 task로 넘어간다.

```yaml
- hosts: web
  strategy: linear
```

```text
Task 1: web1 ─────┐
        web2 ─────────┐
Task 2:              web1, web2 함께 시작
```

`free`는 각 호스트가 준비되는 즉시 다음 task를 진행한다.

```yaml
- hosts: web
  strategy: free
```

```text
web1: Task 1 → Task 2 → Task 3
web2: Task 1 ───────→ Task 2 → Task 3
```

| 전략 | 장점 | 주의점 |
|---|---|---|
| `linear` | 순서를 이해하기 쉽고 배포 통제가 쉬움 | 느린 호스트를 기다림 |
| `free` | 호스트별 작업을 빠르게 완료 | 전체가 같은 단계에 있다는 보장이 없음 |

롤링 배포처럼 단계 간 순서가 중요한 작업에는 보통 `linear`가 안전하다.

## 2. forks: 전체 병렬 실행 수

`forks`는 Control Node가 동시에 처리할 호스트 수다.

```ini
# ansible.cfg
[defaults]
forks = 20
```

값을 키우면 무조건 빨라지는 것은 아니다. Control Node의 CPU·메모리, SSH 연결 수, 대상 서버와 네트워크의 수용량을 함께 고려해야 한다.

## 3. serial: 배치 단위 제어

```yaml
- hosts: web
  serial: 2
```

웹 서버가 10대라면 2대씩 5개 배치로 진행한다.

Canary 형태도 만들 수 있다.

```yaml
serial:
  - 1
  - 25%
  - 100%
```

첫 1대를 검증한 뒤 25%, 이후 나머지를 배포한다. 단, `100%` 배치가 모든 서버를 동시에 서비스에서 제외하지 않도록 가용 용량을 계산해야 한다.

## 4. run_once

모든 호스트를 대상으로 하는 play에서 한 번만 실행할 작업에 사용한다.

```yaml
- name: Run database migration once
  ansible.builtin.command: /opt/app/migrate
  run_once: true
```

`serial`과 함께 사용하면 배치마다 한 번 실행될 수 있다는 점에 주의한다. 전체 배포에서 정확히 한 번이어야 한다면 별도의 play로 분리하거나 특정 호스트에 명시적으로 위임하는 편이 명확하다.

## 5. delegate_to

현재 대상 호스트가 아닌 다른 곳에서 task를 실행한다.

```yaml
- name: Check service from load balancer
  ansible.builtin.uri:
    url: "http://{{ inventory_hostname }}/health"
  delegate_to: "{{ groups['lb'][0] }}"
```

Health Check를 Control Node가 아니라 Load Balancer에서 실행하면 실제 사용자 트래픽과 가까운 네트워크 경로를 검증할 수 있다.

## 6. throttle

특정 task의 동시 실행 수만 제한한다.

```yaml
- name: Restart expensive service
  ansible.builtin.service:
    name: myapp
    state: restarted
  throttle: 1
```

전체 play는 병렬로 처리하되 DB 작업이나 고비용 재시작만 직렬화할 때 유용하다.

## 7. 실패 정책

### any_errors_fatal

```yaml
any_errors_fatal: true
```

호스트 하나에서 실패하면 현재 배치의 작업을 정리한 뒤 전체 play를 중단한다. 일부 서버만 새 버전이 되는 상황을 줄일 수 있다.

### max_fail_percentage

```yaml
serial: 4
max_fail_percentage: 25
```

실패 비율이 설정값을 초과하면 다음 배치를 중단한다. 기준이 전체 서버가 아니라 현재 배치와 결합되어 해석된다는 점, 그리고 ‘초과’ 조건이라는 점을 고려해 값을 정한다. 한 대의 실패도 허용하지 않으려면 `0`이 명확하다.

## 8. 선택 기준

```text
빠른 독립 작업인가? ── 예 ─→ free + 적절한 forks
        │
        아니오
        ↓
순서가 중요한 배포인가? ── 예 ─→ linear + serial
        │
        └─ 특수 작업만 제한 → throttle
           한 번만 실행 → run_once
           다른 위치에서 실행 → delegate_to
```

