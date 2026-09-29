# Rolling Deployment & Failure Handling

> **한 줄 요약**  
> 서버를 한 번에 모두 바꾸지 않고, 일부씩 트래픽에서 제외한 뒤 배포·검증·복귀시키는 방식

## 1. 왜 Rolling Deployment가 필요할까?

웹 서버 4대를 동시에 배포한다고 가정해 보자.

```text
동시 배포

[web1 배포 중] [web2 배포 중] [web3 배포 중] [web4 배포 중]
                              ↓
                      요청을 처리할 서버 없음
```

동시 배포는 빠르지만 다음 위험이 있다.

- 애플리케이션 재시작 동안 요청이 실패할 수 있다.
- 잘못된 버전이면 모든 서버가 동시에 영향을 받는다.
- 문제가 생겨도 정상 서버로 트래픽을 돌릴 수 없다.

Rolling Deployment는 **한 번에 변경되는 서버 수를 제한**해 장애 범위를 줄인다.

---

## 2. 배포 흐름

```text
① 대상 서버를 Load Balancer에서 제외
                    ↓
② 새 버전 배포 및 애플리케이션 재시작
                    ↓
③ Health Check로 새 버전 검증
                    ↓
④ 정상인 경우에만 Load Balancer에 복귀
                    ↓
⑤ 다음 서버에서 같은 과정 반복
```

```text
사용자 요청 ──→ Load Balancer ──┬──→ web1  ← 현재 배포 중: 제외
                                ├──→ web2  ← 요청 처리
                                ├──→ web3  ← 요청 처리
                                └──→ web4  ← 요청 처리
```

핵심은 단순히 서버를 순서대로 업데이트하는 것이 아니다.

> **LB 제외 → 배포 → 검증 → LB 복귀** 순서를 서버마다 보장해야 한다.

---

## 3. Ansible에서는 어떻게 구현할까?

```yaml
---
- name: Rolling deploy web application
  hosts: web
  serial: 1
  max_fail_percentage: 0

  pre_tasks:
    - name: Remove host from load balancer
      ansible.builtin.command:
        cmd: "/usr/local/bin/lb-disable {{ inventory_hostname }}"
      delegate_to: "{{ groups['lb'][0] }}"

  roles:
    - role: webapp

  post_tasks:
    - name: Verify the deployed version
      ansible.builtin.uri:
        url: "http://{{ inventory_hostname }}/health"
        return_content: true
      register: health
      until:
        - health.status == 200
        - health.content | trim == target_version
      retries: 10
      delay: 3
      delegate_to: "{{ groups['lb'][0] }}"
```

### 사용된 핵심 기능

| 기능 | 역할 |
|---|---|
| `serial: 1` | 서버를 한 대씩 배포 |
| `delegate_to` | LB 조작과 Health Check를 LB 서버에서 실행 |
| `until`, `retries`, `delay` | 서비스가 정상화될 때까지 재시도 |
| `max_fail_percentage: 0` | 한 대라도 실패하면 다음 배치 중단 |

실제 환경에서는 사용하는 Load Balancer의 전용 Ansible 모듈이나 API를 이용하는 것이 좋다.

---

## 4. HTTP 200만 확인하면 충분할까?

```text
프로세스 실행 중              ✅
HTTP 상태 코드 200            ✅
새 버전이 실제로 실행 중       ❓
DB·Cache 연결 정상            ❓
사용자 경로에서 접근 가능      ❓
```

프로세스가 살아 있는 것과 정상적으로 서비스를 제공하는 것은 다르다.

```yaml
until:
  - health.status == 200
  - health.content | trim == target_version
```

좋은 Health Check는 다음을 확인해야 한다.

- 정상 HTTP 상태 코드를 반환하는가?
- 배포한 버전이 실제로 응답하는가?
- 필수 의존성과 통신할 수 있는가?
- 실제 트래픽과 가까운 경로에서도 접근 가능한가?

따라서 위 예제는 Control Node가 아니라 **Load Balancer에서 Health Check를 실행**한다.

---

## 5. Canary로 먼저 확인하기

```yaml
serial:
  - 1
  - 25%
  - 50%
```

```text
1단계  [●] [○] [○] [○]   첫 서버만 배포
2단계  [●] [●] [○] [○]   일부 서버로 확대
3단계  [●] [●] [●] [●]   나머지 서버 배포

● 새 버전  ○ 기존 버전
```

첫 서버에 문제가 생기면 전체 서버에 배포되기 전에 중단할 수 있다.

다만 배치 크기를 정할 때는 배포 속도뿐 아니라 **남은 서버가 전체 트래픽을 감당할 수 있는지**도 확인해야 한다.

---

## 6. Health Check가 실패하면?

```text
새 버전 배포
     ↓
Health Check 실패
     ↓
이전 안정 버전으로 Rollback
     ↓
Rollback Health Check
     ├── 성공 → LB 복귀 후 전체 배포 중단
     └── 실패 → 서버 격리 후 운영자 확인
```

```yaml
- name: Deploy with rollback
  block:
    - name: Deploy target version
      ansible.builtin.include_role:
        name: webapp
      vars:
        app_version: "{{ target_version }}"

    - name: Check target version
      ansible.builtin.uri:
        url: "http://{{ inventory_hostname }}/health"
        return_content: true
      register: health
      failed_when: health.content | trim != target_version

  rescue:
    - name: Restore stable version
      ansible.builtin.include_role:
        name: webapp
      vars:
        app_version: "{{ stable_version }}"

    - name: Stop the remaining deployment
      ansible.builtin.fail:
        msg: "Deployment failed and rollback completed"
```

### 주의할 점

1. `rescue`가 성공하면 원래 오류가 복구된 것으로 처리될 수 있다.  
   남은 배포를 멈추려면 실패 상태를 다시 명시해야 한다.

2. `-e app_version=...`은 우선순위가 매우 높다.  
   롤백 값까지 덮어쓰지 않도록 `target_version`과 `stable_version`을 분리한다.

---

## 7. Rolling과 Blue-Green 비교

| 구분 | Rolling | Blue-Green |
|---|---|---|
| 배포 방법 | 기존 서버를 일부씩 교체 | 새 환경 전체를 만든 뒤 트래픽 전환 |
| 추가 인프라 | 적음 | 거의 2배 필요할 수 있음 |
| 배포 중 버전 혼재 | 있음 | 전환 전에는 없음 |
| 롤백 | 서버를 다시 배포 | LB를 이전 환경으로 전환 |
| 적합한 상황 | 일반적인 점진 배포 | 빠른 전환과 복구가 중요한 서비스 |

---

## 8. 정리

```text
serial          → 한 번에 변경되는 서버 수 제한
delegate_to     → 실제 서비스 경로에서 LB 조작·검증
Health Check    → 새 버전의 서비스 가능 상태 확인
Canary          → 문제를 작은 범위에서 먼저 발견
block / rescue  → 실패 시 안정 버전 복구
```

> **Ansible의 배포 성공과 실제 서비스 정상은 같은 의미가 아니다.**  
> 배포 결과뿐 아니라 사용자 관점의 모니터링까지 확인해야 한다.

## 참고 자료

- [Ansible — Delegating tasks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_delegation.html)
- [Ansible — Controlling playbook execution](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_strategies.html)
- [Ansible — Blocks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_blocks.html)

