# Rolling Deployment와 실패 처리

> 한 줄 요약: 서버를 로드밸런서에서 잠시 제외하고, 배포와 헬스 체크가 성공한 서버만 다시 트래픽에 넣는다. `serial`은 이 절차를 몇 대씩 반복할지 정한다.

## 1. 롤링 배포란?

롤링 배포(Rolling Deployment)는 전체 서버를 한꺼번에 업데이트하지 않고, 일부 서버씩 순서대로 배포하는 방식이다.

```text
웹 서버 4대

일괄 배포:  [app01][app02][app03][app04] 모두 배포 중 → 서비스 전체 영향 가능
롤링 배포:  [app01] 배포·검증 → [app02] 배포·검증 → [app03] ...
```

트래픽을 받는 서버를 업데이트하는 기본 흐름은 다음과 같다.

```text
1. Load Balancer에서 현재 서버 제외
2. 현재 서버에 새 버전 배포
3. 애플리케이션 Health Check
4. 성공: Load Balancer에 서버 복귀
   실패: 복구 후 배포 중단
```

서버를 제외하는 이유는 배포·재시작 중인 서버로 사용자의 요청이 가지 않게 하기 위해서다. 반대로 헬스 체크가 성공하기 전에는 서버를 다시 등록하면 안 된다.

---

## 2. `serial`로 배포 단위 정하기

`serial`은 한 번에 배포할 서버 수, 즉 배치 크기를 정한다.

```yaml
- name: Roll out application
  hosts: webservers
  serial: 1
```

`webservers`가 4대라면 `serial: 1`은 아래 흐름으로 동작한다.

```text
app01: 제외 → 배포 → 점검 → 복귀
app02: 제외 → 배포 → 점검 → 복귀
app03: 제외 → 배포 → 점검 → 복귀
app04: 제외 → 배포 → 점검 → 복귀
```

| 설정 | 예: 서버 10대 | 특징 |
|---|---|---|
| `serial: 1` | 1대씩 10회 | 영향 범위 최소, 가장 느림 |
| `serial: 2` | 2대씩 5회 | 안전성과 속도의 절충 |
| `serial: "20%"` | 2대씩 5회 | 서버 수가 달라도 비율 유지 |
| `serial: [1, "20%", "100%"]` | 1대 Canary → 2대씩 → 나머지 | 처음에는 조심스럽게, 검증 뒤 확대 |

`serial`이 1보다 크면 같은 배치의 서버들이 동시에 제외될 수 있다. 로드밸런서에 남은 서버가 트래픽을 감당할 수 있는지 먼저 계산해야 한다.

---

## 3. Canary와 Batch 크기 전략

Canary Deployment는 새 버전을 소수 서버에 먼저 적용해 실제 환경에서 확인하는 방식이다. 문제없음을 확인한 뒤 배포 범위를 넓힌다.

```yaml
serial:
  - 1      # Canary 서버 1대
  - "25%"  # 이후 전체의 25%씩
  - "100%" # 남은 서버 전체
```

```text
서버 8대일 때

1차: 1대 배포 → 오류율·로그·핵심 기능 확인
2차: 2대 배포 → 같은 지표 확인
3차: 나머지 5대 배포
```

Canary를 선택할 때는 다음을 결정해야 한다.

- **대상**: 중요도가 낮고 관찰하기 쉬운 서버를 별도 그룹으로 관리하면 더 명확하다.
- **관찰 시간**: 헬스 체크 한 번만 통과했다고 충분하지 않을 수 있다. 오류율·지연 시간·로그를 확인할 시간을 둔다.
- **확대 기준**: 헬스 체크, 모니터링 지표, 기능 테스트가 모두 통과해야 다음 배치로 진행한다.
- **배치 크기**: 남은 서버 수와 용량을 기준으로 정한다. 예를 들어 4대 중 2대를 제외하면 남은 2대가 평소 트래픽을 처리할 수 있어야 한다.

`serial: [1, "25%", "100%"]`만으로는 Canary 관찰 시간이 생기지 않는다. 첫 서버의 Task와 Health Check가 성공하면 Ansible은 곧바로 다음 배치로 진행한다. 실제 운영에서는 Canary 배포와 전체 배포를 별도 Stage 또는 별도 Playbook 실행으로 나누고, 그 사이에 관찰·승인 단계를 둔다.

```text
Canary 1대 배포
  → 10~30분 동안 오류율·응답 시간·핵심 기능 확인
  → 기준 통과 및 배포 승인
  → 나머지 서버를 Rolling 방식으로 배포
```

관찰 시간은 정답이 있는 값이 아니다. 장애가 몇 분 안에 드러나는지, 트래픽 양이 충분한지, 배포 변경 범위가 큰지를 기준으로 정한다. Jenkins를 사용한다면 Canary Stage 뒤에 `input` 승인 Step을 두거나, 모니터링 지표를 조회하는 Stage가 기준을 통과할 때만 다음 Rolling Stage를 실행하게 만들 수 있다.

---

## 4. Health Check의 역할

배포가 성공했다는 것은 파일 복사나 서비스 재시작이 성공했다는 뜻만은 아니다. 사용자가 실제로 요청할 수 있는 상태인지 확인해야 한다.

```yaml
- name: Wait until the local health endpoint is healthy
  ansible.builtin.uri:
    url: http://127.0.0.1:8080/health
    status_code: 200
  register: health
  retries: 12
  delay: 5
  until: health.status == 200
```

위 Task는 `/health`가 HTTP 200을 반환할 때까지 5초 간격으로 최대 12번 확인한다. 끝까지 성공하지 못하면 Task가 실패한다.

좋은 Health Check는 단순히 프로세스가 떠 있는지보다, 서비스가 요청을 처리할 준비가 되었는지 확인한다. 예를 들면 DB 연결, 필수 설정 로드, 의존 서비스 연결 여부를 포함할 수 있다. 단, 너무 많은 외부 의존성을 검사하면 일시적 외부 장애 때문에 정상 서버까지 계속 제외될 수 있으므로 범위를 정해야 한다.

---

## 5. 실패하면 복구하고 배포를 멈추기

배포 중 헬스 체크에 실패했다면 다음 배치로 진행하면 안 된다. 또한 실패한 서버를 그대로 로드밸런서에 다시 넣는 것도 위험하다.

안전한 실패 흐름은 다음과 같다.

```text
배포 또는 Health Check 실패
  → 이전 버전으로 롤백 시도
  → 롤백 후 Health Check
  → 정상일 때만 Load Balancer에 재등록
  → Play를 실패 처리하여 다음 배치 중단
```

아래 예시의 `lbctl`과 `rollback-myapp`은 환경에 맞게 구현해야 하는 명령이다. HAProxy, Nginx, 클라우드 Load Balancer API 등 실제 장비·서비스의 관리 방식으로 바꾼다.

```yaml
---
- name: Roll out application safely
  hosts: webservers
  become: true
  gather_facts: false
  strategy: linear
  serial: 1
  any_errors_fatal: true

  tasks:
    - name: Deploy one server and verify it
      block:
        - name: Remove current server from the load balancer
          ansible.builtin.command: >
            /usr/local/bin/lbctl disable {{ inventory_hostname }}
          delegate_to: load-balancer-01

        - name: Deploy the new version
          ansible.builtin.include_role:
            name: app_deploy

        - name: Verify the deployed application
          ansible.builtin.uri:
            url: http://127.0.0.1:8080/health
            status_code: 200
          register: health
          retries: 12
          delay: 5
          until: health.status == 200

        - name: Return healthy server to the load balancer
          ansible.builtin.command: >
            /usr/local/bin/lbctl enable {{ inventory_hostname }}
          delegate_to: load-balancer-01

      rescue:
        - name: Roll back the application
          ansible.builtin.command: /usr/local/bin/rollback-myapp

        - name: Verify the rolled back application
          ansible.builtin.uri:
            url: http://127.0.0.1:8080/health
            status_code: 200
          register: rollback_health
          retries: 12
          delay: 5
          until: rollback_health.status == 200

        - name: Return recovered server to the load balancer
          ansible.builtin.command: >
            /usr/local/bin/lbctl enable {{ inventory_hostname }}
          delegate_to: load-balancer-01

        - name: Stop the rolling deployment
          ansible.builtin.fail:
            msg: "Deployment failed and was rolled back on {{ inventory_hostname }}."

      always:
        - name: Record result for this server
          ansible.builtin.debug:
            msg: "Finished deployment batch for {{ inventory_hostname }}."
```

| 요소 | 역할 |
|---|---|
| `block` | 정상 배포 흐름을 묶음 |
| `rescue` | `block` 안의 Task가 실패했을 때 롤백·복구 |
| `always` | 성공·실패와 관계없이 로그·정리 작업 수행 |
| `any_errors_fatal: true` | 현재 서버 실패 후 이후 배포를 중단 |
| `serial: 1` | 한 서버가 정상 복귀한 뒤 다음 서버를 배포 |

`rescue`에서 롤백까지 실패했다면 해당 서버는 로드밸런서에 복귀시키지 않는 편이 안전하다. 이 경우 운영자 알림, 장애 티켓 생성, 수동 복구 절차가 필요하다.

---

## 6. Blue-Green Deployment

Blue-Green Deployment는 같은 서비스를 제공하는 두 환경을 준비하고, 트래픽을 한쪽에서 다른 쪽으로 전환하는 방식이다.

```text
배포 전
사용자 → Load Balancer → Blue(현재 운영 버전)
                         Green(새 버전 배포 준비)

검증 후 트래픽 전환
사용자 → Load Balancer → Green(새 운영 버전)
                         Blue(이전 버전, 즉시 롤백용)
```

롤링 배포와 비교하면 다음과 같다.

| 구분 | Rolling | Blue-Green |
|---|---|---|
| 배포 대상 | 현재 운영 서버 일부씩 | 트래픽을 받지 않는 반대 환경 전체 |
| 트래픽 전환 | 서버별로 점진적 | Load Balancer에서 환경 단위로 전환 |
| 롤백 | 배포된 서버를 개별 롤백 | Load Balancer를 이전 환경으로 되돌림 |
| 필요한 자원 | 기존 서버군 활용 가능 | 동일 환경 두 벌이 필요 |
| 주요 위험 | 버전이 섞인 상태가 잠시 생김 | DB 스키마·세션 호환성, 두 환경 운영 비용 |

### Canary 뒤에 Rolling할 때와 Blue-Green으로 전환할 때

Canary는 새 버전을 실제 트래픽에 먼저 노출해 확인하는 **검증 단계**다. 검증이 끝난 뒤 어떤 방식으로 전체에 적용하느냐가 다르다.

```text
Canary 후 Rolling
기존 서버 9대 + 새 버전 Canary 1대
  → Canary 정상 확인
  → 기존 서버를 2대씩 새 버전으로 교체
  → 한동안 기존·새 버전 서버가 함께 트래픽 처리

Canary 후 Blue-Green 전환
Blue: 기존 버전 전체 / Green: 새 버전 전체 준비
  → Green 일부에만 소량의 트래픽을 보내 Canary 검증
  → 정상 확인 후 트래픽을 Green 전체로 전환
  → 문제 발생 시 트래픽을 Blue 전체로 되돌림
```

| 구분 | Canary 후 Rolling | Canary 후 Blue-Green 전환 |
|---|---|---|
| 검증 뒤 확대 | 기존 운영 서버를 배치별로 계속 배포 | 새 환경(Green)으로 트래픽을 한 번에 전환 |
| 새·기존 버전 공존 | 롤링이 끝날 때까지 운영 서버 안에서 공존 | Blue와 Green 두 환경이 공존 |
| 롤백 | Canary와 이미 배포된 서버를 개별 롤백 또는 트래픽 제외 | Load Balancer를 Blue로 다시 전환 |
| 필요한 조건 | 추가 환경 없이 가능 | 두 환경과 트래픽 비율 조절 기능 필요 |

### Inventory Group으로 환경 나누기

Blue와 Green을 별도 인벤토리 그룹으로 표현하면 배포 대상과 트래픽 대상이 명확해진다.

```yaml
all:
  children:
    blue:
      hosts:
        app01:
        app02:
    green:
      hosts:
        app03:
        app04:
    load_balancers:
      hosts:
        load-balancer-01:
```

새 버전을 Green에 배포하는 Play는 다음처럼 작성할 수 있다.

```yaml
- name: Deploy candidate version to Green
  hosts: green
  serial: "100%"
  roles:
    - app_deploy

- name: Switch traffic to Green after verification
  hosts: load_balancers
  tasks:
    - name: Point production traffic to Green
      ansible.builtin.command: /usr/local/bin/lbctl switch-to green
```

트래픽 전환 전에는 Green의 각 서버 헬스 체크와 핵심 기능 테스트를 통과시켜야 한다. 전환 후 문제가 발견되면 Load Balancer를 Blue로 되돌리는 방식으로 빠르게 롤백한다.

```yaml
- name: Roll back traffic to Blue
  hosts: load_balancers
  tasks:
    - ansible.builtin.command: /usr/local/bin/lbctl switch-to blue
```

> Blue-Green의 빠른 롤백은 애플리케이션 버전에 대한 이야기다. 새 버전이 DB 스키마를 이전 버전과 호환되지 않게 바꾸었다면 트래픽만 Blue로 되돌려도 문제가 해결되지 않을 수 있다. DB 변경은 이전 버전도 읽을 수 있는 방식으로 단계적으로 설계한다.

---

## 7. 어떤 방식을 선택할까?

| 상황 | 권장 방식 |
|---|---|
| 서버 수가 많고, 일부씩 안전하게 새 버전으로 바꾸고 싶음 | Rolling + `serial` |
| 새 환경을 둘 비용이 있고, 빠른 전체 롤백이 중요함 | Blue-Green |
| 새 버전을 실제 트래픽으로 먼저 검증하고, 추가 환경은 없음 | Canary 후 Rolling |
| 새 버전을 실제 트래픽으로 먼저 검증하고, 빠른 전체 롤백도 중요함 | Canary 후 Blue-Green 전환 |
| DB 변경이 이전 버전과 호환되지 않음 | 배포 방식보다 DB 마이그레이션 설계를 먼저 검토 |

## 8. 배포 전 점검 목록

- Load Balancer에서 서버를 제외·복귀시키는 명령 또는 API가 검증되어 있는가?
- 제외된 서버 수만큼 남은 서버가 트래픽을 감당할 수 있는가?
- Health Check가 실제 서비스 준비 상태를 확인하는가?
- 실패 시 이전 버전으로 되돌리는 명령이 테스트되었는가?
- 롤백 실패 시 서버를 LB에 넣지 않고 알릴 수 있는가?
- DB 변경이 이전 애플리케이션 버전과 호환되는가?
- Playbook을 운영 환경에 적용하기 전에 `--syntax-check`, `--check`, `--limit`으로 확인했는가?

## 참고 문서

- [Continuous Delivery and Rolling Upgrades](https://docs.ansible.com/projects/ansible/latest/playbook_guide/guide_rolling_upgrade.html)
- [Controlling playbook execution: strategies and more](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)
- [Error handling in playbooks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)
- [Blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html)
- [Controlling where tasks run: delegation and local actions](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_delegation.html)
- [How to build your inventory](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html)
