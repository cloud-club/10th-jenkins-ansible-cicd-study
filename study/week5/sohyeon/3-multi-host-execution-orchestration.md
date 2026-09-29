## **3. Multi-Host Execution & Orchestration**

---

### 3-1) 기본 `linear` Strategy와 `strategy: free` 실행 방식 비교

**Linear Strategy (기본 방식)**

- **Ansible의 기본(Default) 실행 전략**: `strategy plugins`가 도입된 2.0 이전부터 존재해 온 `ansible.builtin.linear` 표준 플러그인 방식을 사용한다.
- **Lockstep 방식의 동기화 실행**: `serial`에 지정된 호스트 배치(Host batch) 단위로 작업을 발맞추어(`lockstep`) 실행한다.
- **Fork 제한과 동시 처리**: 지정된 `fork` 제한 수만큼의 호스트가 현재 작업(Task)을 동시에 실행하고, 해당 호스트 배치의 처리가 완전히 완료된 후에야 다음 작업으로 다 함께 이동한다.
- **제약 및 동기화**: 특정 호스트에서 작업이 지연되거나 실패하면 다음 호스트 시리즈 및 다음 작업 진행도 함께 동기화되어 제약을 받는다.
- **적용 대상**: 전체 서버 상태를 균일하게 유지해야 하거나 작업 간 순서 제어 및 동기화가 필요한 다중 서버 배치 작업에 적합하다.

**Free Strategy**

- **Ansible 비동기 실행 전략**: 다른 호스트의 작업 완료를 기다리지 않고 최선의 속도로 다음 작업을 실행하는 `ansible.builtin.free` 표준 플러그인 방식을 사용한다.
- **비동기(Asynchronous) 방식의 작업 실행**: `serial`에 지정된 호스트 배치(Host batch, 기본값: `all`) 단위 내에서 타 호스트의 진행 상태와 상관없이 작업을 독립적으로 진행한다.
- **대기열(Queue) 즉시 할당 및 속도 최적화**: 특정 호스트가 먼저 현재 작업을 마치면 다른 호스트를 기다리지 않고 대기열에 다음 작업을 즉시 올려 가장 빠르게 실행한다.
- **병목 방지 및 지연 완화**: 특정 호스트가 느리거나 특정 작업에서 멈춰(stuck) 있어도 전체 프로세스가 차단되지 않으며, 빠르게 완료된 호스트는 지속적으로 다음 작업을 수행한다.
- **적용 대상**: 서버 간 작업 순서나 동기화(의존성)가 중요하지 않고, 개별 서버 단위의 빠른 배포 및 전체 실행 시간 단축이 최우선일 때 적합하다.

**Strategy 설정 방법**

- **Playbook 내 설정**: 특정 Play 단위로 `strategy: free` 또는 `strategy: linear`를 지정하여 적용한다.
- **글로벌 설정 (`ansible.cfg`)**: `[defaults]` 항목 하위에 `strategy = free`와 같이 전역 실행 방식을 지정할 수 있다.

**실행 방식 제어 관련 주요 설정**

- **Forks**: 동시에 처리할 작업 스레드(작업 호스트) 수의 기본값은 5이며, `ansible.cfg`나 `f` 옵션으로 병렬성을 늘릴 수 있다.
- **Serial**: 전체 호스트를 한 번에 처리하지 않고 지정한 수나 비율(%) 단위의 그룹으로 나누어 순차 배포를 진행할 때 사용한다.
- **Throttle**: 특정 작업이나 블록 단위에서 동시에 실행할 작업자의 수를 제한하여 CPU 부하나 API 호출 제약을 관리한다.
- **Run Once**: 전체 Managed Node 중 첫 번째 호스트에서만 작업을 1회 실행하고 결과를 공유하도록 설정한다.

---

### 3-2) `forks`를 활용한 병렬 실행 제어

```
Control Node (ansible.cfg: forks = 30 또는 -f 30)
    │
    ├──────────┬──────────┬──────────┐ (병렬 동시 접속/제어)
    ▼          ▼          ▼          ▼
Managed    Managed    Managed    Managed ... (최대 Forks 수만큼 동시 처리)
Node 1     Node 2     Node 3     Node 4
```

**Forks (기본 병렬 처리 단위)**

- Ansible이 Managed Node에 동시 접속하여 작업을 수행할 때 사용하는 프로세스/워커(Worker)의 개수
- 기본값(Default)은 **5**로 설정되어 있어, 한 번에 최대 5개의 호스트에 명령을 동시 실행한다.
- Control Node의 CPU 및 네트워크 리소스 여유가 있다면 Forks 수를 늘려 전체 Playbook 실행 시간을 크게 단축할 수 있다.

**Forks 설정 방법**

- **설정 파일 (`ansible.cfg`)**: `defaults` 섹션 하위에 지정하여 전역 적용
    
    ```
    [defaults]
    forks = 30
    ```
    
- **명령줄 옵션 (CLI)**: 실행 시 `f` 또는 `-forks` 옵션 전달
    
    ```
    ansible-playbook -f 30 my_playbook.yml
    ```
    

**실행 방식 (Execution Strategy)**

- **Linear Strategy (기본값)**
    - 기본 실행 전략으로, 지정된 Forks 수만큼의 호스트에서 현재 Task 완료를 기다린 후 다음 Task로 다 함께 넘어간다.
    - 모든 호스트가 동일한 단계의 작업 상태를 유지해야 할 때 유용하다.
- **Free Strategy**
    - 호스트별로 다른 호스트의 작업 완료를 기다리지 않고, Playbook의 끝까지 가장 빠르게 독립적으로 작업을 실행한다.
    - Playbook 내에서 `strategy: free` 키워드로 설정 가능하다.

**세부 제어 옵션 (Execution Keywords)**

- **`serial` (배치 크기 제어)**
    - 전체 호스트를 한 번에 제어하지 않고, 지정된 수나 비율(%)로 그룹을 나누어 순차적으로 작업을 완료한다.
    - 무중단 롤링 업데이트(Rolling Update)를 구현할 때 필수적으로 활용된다.
- **`throttle` (특정 Task 워커 제한)**
    - 특정 Task나 Block 레벨에서 사용 가능한 최대 워커 수를 제한한다.
    - CPU 사용량이 높거나 API 호출 제한(Rate Limit)이 걸려있는 작업의 부하를 줄일 때 활용한다.
- **`run_once` (단일 실행)**
    - 배치 내 첫 번째 호스트에서만 단 한 번 실행하며, 결과 및 Fact를 동일 배치의 모든 호스트에 공유한다.
    - DB 마이그레이션 등 전체 호스트 중 한 곳에서만 수행해야 하는 작업에 적합하다.

---

### 3-3) `serial`을 활용한 Batch 기반 서버 배포

```
Control Node
    │
    ├─► Batch 1 (web1, web2, web3) ──► Task 1 ──► Task 2 ──► 완료
    │
    └─► Batch 2 (web4, web5, web6) ──► Task 1 ──► Task 2 ──► 완료
```

**Serial (Batch Size)**

- `hosts`에 지정된 전체 대상 중 한 번에 처리할 호스트의 수(배치 크기)를 정의하는 키워드 (Play의 대상 서버를 몇 대씩 batch로 처리할 것인가)
- 지정한 배치 단위로 플레이북의 모든 작업(Tasks)이 완료된 후 다음 배치 호스트 그룹으로 이동하여 배포를 진행한다.

**Batch 기반 배포의 특징**

- 무중단 롤링 업데이트(Rolling Update) 구현 가능
    - 전체 서버를 동시에 중지하지 않고, 일부 그룹씩 순차적으로 업데이트하여 서비스 연속성을 유지한다.
- 영향 범위(Failure Scope) 제한
    - 작업 실패 시 오류 영향 범위를 전체 시스템이 아닌 해당 배치 그룹으로 제한한다.
- 유연한 배치 크기 설정
    - 고정된 호스트 개수뿐만 아니라 비율(%) 및 가변 리스트 형식으로 지정할 수 있다.

**Serial 키워드 설정 방식**

- **고정 수치 지정 (`serial: 3`)**:
    - 한 번에 정확히 지정된 개수(예: 3대)의 호스트씩 나누어 순차 실행.
- **비율 지정 (`serial: "30%"`)**:
    - 전체 대상 호스트 수 대비 지정한 비율만큼 나누어 실행 (계산 결과가 1 미만이어도 최소 1대는 보장).
- **가변 리스트 지정 (`serial: [1, 5, 10]`)**:
    - 카나리 배포처럼 첫 배치에는 1대, 두 번째 배치에는 5대, 이후 남은 호스트는 10대씩 단계적으로 확대하여 실행.
- **혼합 지정 (`serial: [1, 5, "20%"]`)**:
    - 수치와 비율을 조합하여 점진적으로 배포 그룹의 크기를 늘려가는 방식 적용.

**Batch 배포 제어 추가 옵션**

- **`run_once: true`**:
    - 특정 작업을 배치 내 첫 번째 호스트에서만 단 1회 실행하고, 해당 결과를 동일 배치 내 모든 호스트에 적용한다. (예: 데이터베이스 마이그레이션 작업 등)
- **`throttle` 연동**:
    - `serial`로 나뉜 배치 내에서도 Worker 수를 제한하여 CPU 부하나 API 요청 제약을 제어한다.

---

### 3-4) `run_once`, `delegate_to`, `throttle` 활용

```
Control Node
    │
    ├─► Task Delegation (delegate_to) ──► Delegated Host (e.g. Load Balancer / DB)
    │
    └─► Parallel Execution (throttle) ──► Managed Nodes (Batch Processing)
```

**delegate_to (작업 위임)**

- 기본적으로 특정 대상 호스트를 향해 실행되는 태스크를 다른 지정된 머신(예: 로컬 컨트롤 노드, 로드 밸런서 등)에서 실행하도록 변경한다.
- 특징 및 활용
    - 특정 노드의 작업 전후로 외부 서비스(로드 밸런서 등)를 제어하거나 모니터링 등록/해제 작업에 유용하다.
    - 축약형인 `local_action`을 사용해 컨트롤 노드(localhost)에서 작업을 즉시 위임할 수도 있다.
    - 위임받은 호스트에서 사실(Fact) 수집 결과를 현재 대상 호스트에 귀속시키거나, `delegate_facts: true` 옵션으로 위임된 호스트에 직접 할당할 수 있다.
    - `include`, `add_host`, `debug`와 같은 일부 연결 비활성화 모듈은 위임할 수 없다.
- 보완 및 주의사항
    - **결과 및 Fact 공유**: `delegate_to`를 사용하더라도 실행 결과 및 기본 Fact 정보는 원래 대상 호스트(Original Host)의 데이터로 귀속됩니다.
    - **`delegate_facts` 연계**: 위임된 대상 호스트 자체의 Fact를 수집하고 저장하려면 `delegate_facts: true` 옵션을 명시해야 합니다.

**run_once (단일 실행)**

- 전체 대상 호스트 목록 중 첫 번째 호스트에 대해서만 태스크를 단 한 번만 실행한다.
- 특징 및 활용
    - 이메일 알림 발송, 데이터베이스 마이그레이션, 공유 리소스 초기화 등 중복 실행이 필요 없는 작업에 적합하다.
    - `delegate_to`와 함께 사용하거나 전체 호스트를 순회하는 `loop` 항목과 조합하여 동시성 충돌을 방지하면서 일괄 제어할 수 있다.
- 보완 및 주의사항 (중요)
    - **`serial`과 조합 시 동작 방식**: `serial` 옵션과 함께 사용할 경우, 전체 실행 중 '딱 1번만' 실행되는 것이 아니라 매 배치(batch)마다 1번씩 실행됩니다.
        - 전체 배치 통틀어 정말 1번만 실행해야 한다면 `when: inventory_hostname == ansible_play_hosts_all[0]` 조건문을 조합해야 합니다.
    - **조건문(`when`) 평가 기준**: `run_once` 태스크에 `when` 조건문을 적용하면, 조건의 참/거짓 여부는 배치 내 '첫 번째 호스트'의 변수/Fact를 기준으로만 평가됩니다.
    - **결과 공유**: 기본적으로 첫 번째 호스트에서 실행된 결과 및 생성된 Fact는 동일 배치의 모든 호스트에 적용됩니다.

**throttle (동시 실행 제한)**

- 플레이북의 기본 병렬 실행(Forks) 수를 해당 태스크 단위에서 원하는 개수로 제한한다.
- 특징 및 활용
    - 여러 호스트가 동시에 특정 단일 공유 리소스(파일 수정, API 서버 호출 등)를 업데이트할 때 발생하는 덮어쓰기 및 동시성 문제(Concurrency issues)를 방지한다.
    - `throttle: 1` 설정을 통해 동시 작업을 1개로 제한하여 순차적으로 안정적인 처리가 가능하게 한다.
- 보완 및 주의사항
    - **상한선 제약 (`forks` / `serial`)**: `throttle` 설정값은 이미 지정된 `forks` 수나 `serial` 설정값보다 클 수 없습니다. 즉, 동시 실행 수를 줄이는 제약 역할만 가능하며, 기존에 설정된 병렬성 상한을 늘려주지는 못합니다.

---

### 3-5) `any_errors_fatal`, `max_fail_percentage`를 활용한 배포 실패 정책 구성

```
                       [ Play 시작 ]
                             │
                             ▼
                  [ 배치(Batch) 단위 실행 ]
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
   [ any_errors_fatal ]            [ max_fail_percentage ]
            │                                 │
     단 1대의 호스트라도 실패             설정된 실패율 초과
            │                                 │
            └────────────────┬────────────────┘
                             ▼
                 [ 전체 Play 중단 (Abort) ]
```

**기본 동작 방식 (Default Behavior)**

- Ansible은 실행 중 특정 호스트에서 태스크 실패가 발생하더라도, 해당 호스트의 작업만 중단하고 다른 정상 호스트들에서는 남은 작업을 계속 진행한다.
- 하지만 전체 서비스의 일관성이나 안전한 배포를 위해 실패가 발생했을 때 플레이북 전체를 중단시키는 정책 설정이 필요하다.

**any_errors_fatal**

- **첫 번째 에러 발생 시 즉시 Play 중단**
    - 특정 호스트에서 태스크 실패가 발생하는 즉시, 현재 실행 중인 배치 내 나머지 작업까지만 마무리한 뒤 플레이북 전체 실행을 중단한다.
    - 후속 태스크나 이후 정의된 Play는 더 이상 실행되지 않는다.
- **적용 수준**
    - Play 수준 또는 Block 수준에 지정할 수 있다.
    - `block` 구조 내부에서 사용할 경우 `rescue` 섹션을 통해 에러를 복구하도록 구성할 수도 있다.
- **주요 사용 사례**
    - 100% 성공이 보장되어야 다음 단계로 진행할 수 있는 작업
    - 예: 로드 밸런서 제어 작업 중 일부라도 실패하면 백엔드 서비스 업데이트를 진행하지 않고 즉시 중단해야 하는 경우

**max_fail_percentage**

- **최대 허용 실패율 설정을 통한 배포 제어**
    - 허용 가능한 실패 호스트 비율(백분율)을 지정하여, 이 임계값을 초과하는 실패가 발생하면 Play를 중단한다.
    - `serial` 키워드와 함께 배치 단위 롤링 업데이트를 수행할 때 유용하다.
- **임계값 적용 기준**
    - 지정한 실패 비율을 '초과'할 때 동작한다 (동률일 때는 중단되지 않음).
    - 예: `serial: 4`인 상태에서 2대(50%) 실패 시 중단되도록 하려면 `max_fail_percentage: 50`이 아닌 `49`로 설정해야 한다.
- **주요 사용 사례**
    - 대규모 서버 군에 대한 무중단 롤링 업데이트
    - 일부 호스트의 장애는 수용 가능하지만, 전체 서비스 장애로 번지는 것을 막기 위해 일정 비율 이상의 실패 시 배포를 중단하고자 할 때

---

### 3-6) 참고 문헌

- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html
- https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/linear_strategy.html
- https://docs.ansible.com/projects/ansible-core/2.17/collections/ansible/builtin/free_strategy.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html
- https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html