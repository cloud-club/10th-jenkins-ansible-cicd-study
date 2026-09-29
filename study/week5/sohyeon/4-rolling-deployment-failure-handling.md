## **4. Rolling Deployment & Failure Handling**

---

### 4-1) Load Balancer에서 대상 서버 제외 → 배포 → Health Check → 복귀 흐름 구성

```
[ Control Node (Ansible) ]
          │
          ├── (1) LB 제외 / (4) LB 복귀 명령 실행 (Control Node에서 직접 API 호출)
          ▼
   [ Load Balancer ]
          │
          ├── Traffic 차단 / 재개
          ▼
   [ Managed Node ]
    (2) 애플리케이션 배포 및 업데이트
    (3) Health Check 완료 확인
```

**Delegation(작업 위임) 사용**

- **기본 동작 방식의 한계**
    
    Ansible은 플레이북에 지정된 target host(Managed Node)에 접속해 모든 태스크를 직접 수행하는 것이 기본 동작 모드이다.
    
- **무중단 배포 시 문제 발생**
    
    배포 중 웹 서버(Managed Node)를 Load Balancer에서 잠시 제외해야 하는데, 이 제외 명령(LB API 호출, 스크립트 실행 등)은 배포 대상인 웹 서버 내부에서 실행할 수 없고 Ansible이 동작 중인 Control Node나 별도의 LB 관리 서버에서 수행되어야 한다.
    
- **Delegation의 필요성**
    
    이처럼 "작업 대상은 Managed Node이지만, 특정 태스크만 Control Node 등 제3의 위치에서 실행해야 할 때"를 해결하기 위해 Delegation(작업 위임) 개념이 사용된다.
    

**롤링 배포 핵심 제어 요소**

- **`delegate_to` / `local_action`**
    - 특정 태스크를 지정한 호스트(예: `127.0.0.1` 또는 `localhost`)로 위임하여 실행하게 만드는 키워드이다.
    - Load Balancer API 호출이나 상태 변경 스크립트처럼 Control Node에서 실행해야 하는 명령에 사용한다.
- **`serial` 키워드**
    - 전체 서버를 한 번에 배포하지 않고, 지정한 개수(예: `serial: 1`)만큼 그룹을 나누어 순차적으로 작업을 진행하도록 제어한다.
    - 롤링 업데이트 시 서비스 중단 없이 일부 서버씩 나눠서 작업할 수 있게 해준다.

**배포 워크플로우 단계별 구현 예시**

1. **Load Balancer 풀에서 대상 서버 제외 (`delegate_to`)**
    - Control Node(`127.0.0.1`)로 태스크를 위임하여 현재 배포 순번에 해당하는 Managed Node를 LB 풀에서 제외하고 트래픽을 차단한다.
    - 예시: `delegate_to: 127.0.0.1`을 이용해 LB 스크립트/모듈 실행
2. **애플리케이션 배포 및 설정 업데이트**
    - 실제 Managed Node에 연결하여 패키지 설치, 파일 복사, 서비스 재시작 등 본 배포 작업을 수행한다.
3. **Health Check (상태 검증)**
    - Managed Node에서 배포된 애플리케이션이 정상적으로 동작하고 헬스체크 응답을 반환하는지 검증한다.
4. **Load Balancer 풀에 대상 서버 복귀 (`delegate_to`)**
    - Health Check 통과 후, 다시 Control Node로 태스크를 위임하여 해당 서버를 LB 풀에 재등록하고 트래픽 수용을 재개한다.
    - 예시: `delegate_to: 127.0.0.1`을 이용해 LB 복귀 스크립트/모듈 실행

**주요 주의사항**

- **변수 컨텍스트 유지**
    - 태스크를 Control Node로 위임하더라도, 실행에 사용되는 파라미터나 대상 정보는 원본 대상 호스트(`inventory_hostname`)의 변수를 참조한다.
- **동시성 관리 (`serial` / `throttle`)**
    - 여러 Managed Node가 동시에 Control Node로 태스크를 위임해 동일한 파일이나 로컬 자원에 접근하면 덮어쓰기 등 충돌이 발생할 수 있다.
    - `serial: 1` 설정이나 `throttle: 1`을 적용하여 Control Node에서의 실행을 순차적으로 제어해야 한다.

---

### 4-2) `serial`을 활용한 Rolling Deployment 구현

```
[ Control Node ]
       │
       ├─ (Batch 1: Managed Node 1) ──► Traffic OUT ──► Update ──► Traffic IN
       ├─ (Batch 2: Managed Node 2) ──► Traffic OUT ──► Update ──► Traffic IN
       └─ (Batch 3: Managed Node 3) ──► Traffic OUT ──► Update ──► Traffic IN
```

**Serial 키워드의 개념**

- 플레이북 실행 시 한 번에 작업(Operation)을 수행할 호스트의 개수 또는 비율을 지정한다.
- `serial`을 지정하지 않으면 Ansible은 기본 설정(forks) 범위 내에서 지정된 모든 호스트를 동시에 병렬 처리한다.
- 전체 서버를 일괄 업데이트하지 않고 지정한 수량만큼 나누어 배치(Batch) 단위로 순차 진행하므로 무중단 롤링 배포(Zero-downtime Rolling Upgrade)를 구현할 수 있다.

**Rolling Deployment 프로세스 흐름**

- **작업 노드 제외 (Pre Tasks)**
    - 업데이트를 진행할 대상 노드를 로드 밸런서(HAProxy 등)의 트래픽 배분 대상에서 제외한다.
    - 대상 노드의 모니터링 알림(Nagios 등)을 일시 중지하여 정상적인 배포 과정 중의 중단을 알람 오류로 감지하지 않도록 처리한다.
- **애플리케이션 배포 및 업데이트 (Roles / Tasks)**
    - 트래픽이 차단된 노드에 최신 애플리케이션 코드 및 시스템 구성을 적용한다.
- **작업 노드 재투입 (Post Tasks)**
    - 업데이트가 완료된 노드의 모니터링 알림을 다시 활성화한다.
    - 해당 노드를 로드 밸런서 풀에 다시 등록하여 정상 트래픽을 수신하도록 복구한다.

**Ansible Rolling Update의 특징 및 유의사항**

- **배치(Batch) 단위 실행**
    - `serial` 키워드는 플레이 전체를 지정한 크기의 호스트 그룹 단위로 끊어서 실행한다.
- **실패 격리 및 안정성**
    - 특정 배치에 속한 모든 호스트가 실패할 경우, 플레이북 전체가 작업을 중단하여 서비스 전체로 오류가 전파되는 것을 막는다.
- **위임(Delegation) 활용**
    - 타겟 관리 노드를 트래픽에서 제어하기 위해 `delegate_to` 옵션을 활용하여 로드 밸런서나 모니터링 서버에 제어 명령을 보낸다.

**Ansible 롤링 업데이트 구성 예시 (`rolling_update.yml`)**

```
- hosts: webservers
  user: root
  serial: 1

  pre_tasks:
    - name: Disable nagios alerts for this host
      nagios:
        action: disable_alerts
        host: "{{ inventory_hostname }}"
        services: webserver
      delegate_to: "{{ item }}"
      loop: "{{ groups.monitoring }}"

    - name: Disable the server in haproxy
      shell: echo "disable server myapplb/{{ inventory_hostname }}" | socat stdio /var/lib/haproxy/stats
      delegate_to: "{{ item }}"
      loop: "{{ groups.lbservers }}"

  roles:
    - common
    - base-apache
    - web

  post_tasks:
    - name: Enable the server in haproxy
      shell: echo "enable server myapplb/{{ inventory_hostname }}" | socat stdio /var/lib/haproxy/stats
      delegate_to: "{{ item }}"
      loop: "{{ groups.lbservers }}"

    - name: Re-enable nagios alerts
      nagios:
        action: enable_alerts
        host: "{{ inventory_hostname }}"
        services: webserver
      delegate_to: "{{ item }}"
      loop: "{{ groups.monitoring }}"
```

---

### 4-3) Canary Deployment 및 Batch 크기 조절 전략

```
Control Node
    │
    │ serial: [1, 5, "20%"]
    ▼
[Batch 1: Host 1] ────────► (Pre-tasks ➔ Rollout ➔ Post-tasks / 카나리 검증)
    │
    ▼ (성공 시 다음 단계 진행)
[Batch 2: Host 2~6] ──────► (확장 배포 및 검증)
    │
    ▼
[Batch 3: Remainder 20%] ─► (전체 무중단 롤링 배포 완료)
```

**Canary / Rolling Deployment**

- 전체 서버에 동시에 변경 사항을 적용하지 않고, 일부 호스트 그룹(Batch) 단위로 순차 배포를 진행하여 서비스 중단(Zero-downtime) 없이 시스템을 업데이트한다.
    - 처음에는 작은 batch로 검증하고 이후 범위를 확대하는 방식
- 장애 발생 시 전체 시스템으로 영향이 퍼지는 결함 격리(Failure Isolation)를 실현하며, 소수 Node에서 문제가 감지되면 배포를 즉시 중단할 수 있다.

**Batch 크기 제어 (`serial` 키워드)**

- Ansible Playbook에서 한 번에 실행할 Managed Node의 개수 또는 비율을 지정한다.
- `serial` 키워드가 지정되면 지정된 Batch 단위마다 전체 Play 과정(Task 목록)을 독립된 실행 주기로 나누어 끝까지 완료한 후 다음 Batch로 이동한다.

**Batch Size 설정 방식**

- **정수형 지정:** `serial: 1` 또는 `serial: 3`과 같이 구체적인 호스트 개수를 지정하여 실행한다.
- **백분율 지정:** `serial: "20%"` 또는 `serial: "30%"`와 같이 전체 대상 호스트에 대한 비율로 배치 크기를 산출한다.
- **단계별 가중 배포 (List 형태):** `serial: [1, 5, "20%"]` 형태로 리스트를 구성하여 초반에는 1대의 호스트로 안전하게 카나리 검증을 수행하고, 점진적으로 대상을 늘려나가는 패턴을 구현한다.

**단계별 배포 절차 (Pre / Post Tasks 활용)**

- **Pre-tasks (트래픽 차단 및 모니터링 일시 중지)**
    - 해당 Batch 호스트의 모니터링 알람(Nagios 등)을 일시 중지한다.
    - 로드밸런서(HAProxy, F5 등)에서 해당 호스트를 제거하여 사용자 트래픽 유입을 차단한다.
- **Core Deployment (변경 사항 적용)**
    - 최신 애플리케이션 코드 배포, 설정 파일 변경 및 서비스 재시작(Roles 적용)을 수행한다.
- **Post-tasks (검증 및 트래픽 재연결)**
    - 헬스체크를 통해 서비스 정상 동작을 확인한 후, 로드밸런서에 호스트를 다시 등록한다.
    - 일시 중지했던 모니터링 알람을 다시 활성화하여 정상 운영 상태로 복구한다.

**실행 제어 및 보조 키워드**

- **작업 위임 (`delegate_to`) 및 반복 (`loop`)**
    - Batch 내 호스트 작업 중 로드밸런서나 모니터링 서버 등 외부 제어 시스템에 명령을 보낼 때 `delegate_to`를 사용해 특정 노드로 실행을 위임한다.
- **실행 수 제한 (`throttle`)**
    - Task나 Block 단위에서 동시에 실행할 Worker 수를 제한하여 CPU 부하나 API 호출 제한(Rate Limit)을 방지한다.
- **단일 실행 (`run_once`)**
    - 각 Batch의 첫 번째 호스트에서만 단 한 번 실행되도록 지정하여 데이터베이스 마이그레이션 등 중복 실행을 방지한다.

---

### 4-4) Health Check 실패 시 배포 중단 및 복구 처리

```
Ansible Control Node
    │
    │ Playbook Execution
    ▼
[Task Execution / Health Check]
    │
    ├── (성공) ──► 계속해서 다음 작업 또는 다음 호스트 배포 진행
    └── (실패) ──► 배포 중단 (Aborting) 및 복구 처리 (Rescue / Handlers)
```

**기본 동작 방식 (Default Error Behavior)**

- Ansible은 플레이북 실행 중 특정 호스트에서 명령어 오류나 모듈 실패가 발생하면, 해당 호스트에 대한 작업만 즉시 중단하고 성공한 다른 호스트에 대한 작업은 계속 진행한다.

**배포 중단 제어 (Aborting Play Execution)**

- `any_errors_fatal` **(즉시 전체 배포 중단)**
    - 특정 태스크나 플레이 수준에서 설정하며, 하나의 호스트에서라도 실패(Health Check 실패 등)가 발생하면 실행 중인 배치 작업을 마친 뒤 전체 호스트에 대한 플레이북 실행을 즉시 중단한다.
    - 서비스 영향도를 최소화하기 위해 모든 노드가 정상 상태여야만 다음 단계로 넘어가는 안전한 배포 환경에 적합하다.
- `max_fail_percentage` **(임계치 기반 중단)**
    - 롤링 업데이트(Rolling Update) 진행 시 허용 가능한 최대 실패 비율을 지정한다.
    - 지정한 비율 초과로 호스트 실패가 발생하면 남은 배치 및 전체 배포 작업을 중단한다.

**실패 조건 정의 (Defining Failure)**

- `failed_when`
    - Health Check 명령어의 리턴 코드뿐만 아니라 응답 본문(stdout/stderr)에 특정 에러 문자열이 포함되었는지 여부 등을 조합하여 실패 조건으로 정의한다.
    - 단순 프로세스 종료 코드 외에 애플리케이션의 세부 상태 정보에 따른 배포 실패 판정을 가능하게 한다.

**복구 및 예외 처리 (Recovery & Rollback)**

- `block` / `rescue` / `always` **(예외 처리 구문)**
    - Programming의 `try-catch`와 유사한 구조를 제공한다.
    - `block` 영역의 Health Check나 배포 작업이 실패할 경우, `rescue` 영역이 실행되어 이전 버전으로 롤백하거나 트래픽을 재연결하는 복구 작업을 수행한다.
- `force_handlers` **(강제 상태 회복)**
    - 작업 중 오류가 발생하더라도 이전에 트리거된 Handler(예: 서비스 재시작, 설정 원복 등)를 강제로 실행하도록 설정하여 시스템을 안정적인 상태로 돌려놓는다.

---

### 4-5) Blue-Green Deployment 구조 및 Inventory Group 활용 방식 이해

```
               [ Load Balancers / Gateways ]
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [ Blue Group (Active) ]           [ Green Group (Idle) ]
     Managed Node 1                    Managed Node 3
     Managed Node 2                    Managed Node 4
```

**Inventory Group을 통한 배포 타겟 분리**

- Inventory 파일 내에 호스트들을 `webservers_blue`, `webservers_green` 또는 기능별 그룹(`dbservers`, `lbservers`, `monitoring`)으로 세분화하여 그룹핑한다.
- Playbook 실행 시 특정 그룹만 타겟으로 지정하거나, `group_vars`를 통해 그룹별 환경 변수(포트, 설정 파일)를 유연하게 적용한다.

**Blue-Green Deployment 동작 원리**

- **구버전(Blue)과 신버전(Green) 환경 공존**: 실제 운영 중인 Blue 그룹과 새로 배포할 Green 그룹을 인벤토리상에서 독립된 그룹으로 관리한다.
- **무중단 스위칭 (Zero-Downtime Traffic Shift)**: Green 그룹에 대한 배포 및 검증이 완료되면, 상단 Load Balancer(HAProxy 등)의 트래픽 라우팅 대상을 Blue에서 Green으로 전환한다.
- **신속한 롤백 지원**: 배포 후 문제가 발생하더라도 Load Balancer의 라우팅 대상만 다시 Blue 그룹으로 원복(Revert)하면 즉시 이전 상태로 복구할 수 있다.

**Ansible의 Dynamic Traffic Control & Orchestration**

- **`delegate_to` 기반의 외부 시스템 제어**
    - Managed Node를 업데이트하기 전/후에, Load Balancer나 Monitoring 서버에 명령을 위임(`delegate_to`)하여 실행한다.
    - 배포 대상 호스트의 모니터링 알람을 일시 중지(Disable)하고, Load Balancer 인프라 세션에서 제외(Disable/Drain)시키는 작업을 자동화한다.
- **`serial` 키워드를 활용한 순차적 배포**
    - 배포 플레이북 내에서 `serial` 구문을 사용하여 한 번에 처리할 호스트 개수나 비율을 제어한다.
    - 전체 서버를 한 번에 중단시키지 않고 그룹 단위/단계별로 안전하게 업데이트를 수행한다.

**Ansible 기반 Blue-Green / Rolling 배포의 특징 및 장점**

- **무중단 지속적 배포 (Zero-Downtime Continuous Delivery)**
    - 서비스 중단 없이 신규 버전 코드를 상시 배포할 수 있는 파이프라인을 구축한다.
- **자동화된 헬스체크 및 안전장치**
    - Pre-task와 Post-task 구간을 두어 트래픽 투입 전 애플리케이션의 정상 동작 여부를 확인한 후 세션을 다시 연결한다.
- **재사용성 높은 Playbook 구조 (Roles)**
    - Common, Web, DB, Load Balancer 등의 역할을 Role 단위로 모듈화하여, Blue/Green 어느 환경에든 동일한 상태를 재현할 수 있다.

---

### 4-6) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_delegation.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/guide_rolling_upgrade.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/guide_rolling_upgrade.html