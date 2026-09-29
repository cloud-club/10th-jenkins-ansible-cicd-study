# Multi-Host Execution & Orchestration

## 1. 서버가 여러 대면 무엇을 결정해야 할까?

한 대에 적용하던 Playbook을 웹 서버 20대에 실행한다고 생각해 보자. 한꺼번에 변경하면 빠르지만, 배포 중 서비스를 제공할 서버가 부족해질 수 있다. 반대로 한 대씩 실행하면 영향은 줄어도 시간이 오래 걸린다.

Ansible에서는 **작업 순서, 동시에 처리할 수, 한 번에 배포할 서버 수를 따로 정한다.** 이름이 비슷해 보여도 제어하는 대상이 다르다.

| 알고 싶은 것 | 관련 설정 |
| --- | --- |
| 어떤 서버에 적용할까? | `hosts`, `--limit` |
| 다른 서버가 작업을 마칠 때까지 기다릴까? | `strategy` |
| 몇 개의 작업 프로세스를 사용할까? | `forks` |
| 몇 대씩 Play 전체를 완료할까? | `serial` |
| 특정 Task만 동시에 적게 실행할까? | `throttle` |
| 이 Task를 다른 서버에서 실행할까? | `delegate_to` |
| 공통 작업을 배치에서 한 번만 실행할까? | `run_once` |

이 문서의 코드는 설정별 동작을 비교하는 예제다. 모두를 하나의 Playbook에 순서대로 추가하는 방식으로 읽지 않아도 된다.

공식문서: [Strategies and execution controls](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)

## 2. `linear`와 `free`: 다음 Task로 언제 넘어갈까?

웹 서버 두 대에 Task A, B, C를 실행한다고 해 보자. 기본 방식인 **`linear`는 현재 배치의 서버들이 Task A를 처리한 다음 B로 넘어간다.** 한 서버가 빠르게 끝나도 다른 서버를 기다린다.

반면 `free`는 각 서버가 자기 작업을 마치면 다음 Task로 진행한다. 빠른 서버는 다른 서버가 A를 수행하는 동안 B, C까지 진행할 수 있다.

```text
linear
web01: Task A ────────┐ → Task B
web02: Task A ──대기──┘ → Task B

free
web01: Task A ──────────→ Task B
web02: Task A → Task B → Task C
```

서버별로 독립적인 정보를 수집한다면 서로 기다릴 필요가 적다. 다음처럼 `strategy: free`를 지정할 수 있다.

```yaml
- name: Collect independent host information
  hosts: web
  gather_facts: false
  strategy: free
  tasks:
    - name: Read operating system details
      ansible.builtin.command:
        argv:
          - cat
          - /etc/os-release
      changed_when: false
```

배포처럼 서버 간 진행 순서와 전체 중단 시점이 중요하면 `linear`부터 사용하는 편이 이해하기 쉽다. `free`도 `forks`나 `serial`의 제한을 받으므로 모든 서버의 모든 작업을 무제한으로 실행하는 것은 아니다.

공식문서: [linear strategy](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/linear_strategy.html), [free strategy](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/free_strategy.html)

## 3. `forks`와 `serial`: 병렬 처리와 배포 묶음 구분하기

### 3.1 `forks`는 작업 프로세스 수다

Ansible은 기본적으로 작업 프로세스 5개를 사용한다. 이 수를 정하는 옵션이 `forks`다. 대상이 20대라면 각 Task의 원격 작업을 이 프로세스들로 나누어 처리한다.

설정 파일이나 CLI에서 값을 바꿀 수 있다. Playbook에 `forks: 10`이라는 Play 키를 추가하는 방식은 아니다.

```ini
# ansible.cfg
[defaults]
forks = 10
```

```bash
ansible-playbook -i inventories/dev/hosts.yml site.yml --forks 10
```

`forks`를 높이면 병렬 처리 여지가 커지지만 Control Node와 네트워크 부하도 증가한다. 실제 작업 시간을 측정하며 조정한다.

공식문서: [Setting the number of forks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html#setting-the-number-of-forks), [ansible-playbook CLI](https://docs.ansible.com/projects/ansible/latest/cli/ansible-playbook.html)

### 3.2 `serial`은 Play를 끝낼 서버 묶음이다

“두 대의 배포를 끝낸 다음 다음 두 대를 시작하자”는 요구에는 `serial: 2`를 사용한다. 한 묶음의 서버가 Role·Task·Handler 등 Play의 작업을 마쳐야 다음 묶음으로 넘어간다.

```text
forks=5, serial 없음
  각 Task를 최대 5개의 작업 프로세스로 처리
  → 대상 20대 전체가 Play에 참여

forks=5, serial=2
  [서버 2대: Play 전체 완료] → [다음 2대: Play 전체 완료] → ...
  → 현재 배치는 2대이므로 forks를 늘려도 배치가 커지지 않음
```

따라서 `forks`만 낮춘다고 배포 중 서비스에서 빠질 서버 수까지 제한되는 것은 아니다. 배포 묶음은 `serial`로 정하고, LB 제외와 복귀는 별도 Task로 작성한다.

### 3.3 작은 배치로 시작해 점차 늘리기

`serial`에 목록을 주면 처음에는 작게 시작하고 이후 배치를 키울 수 있다.

```yaml
- name: Update web hosts in batches
  hosts: web
  become: true
  strategy: linear
  serial:
    - 1
    - 2
    - '25%'
  roles:
    - study_web
```

대상이 20대라면 첫 배치는 1대, 다음은 2대, 그다음부터는 전체의 25%인 5대씩 진행한다. 남은 서버가 5대보다 적으면 남은 수만 처리한다. 목록의 마지막 값은 이후 배치에도 반복되며, 비율로 계산한 배치도 최소 1대는 포함한다.

공식문서: [Setting the batch size with serial](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html#setting-the-batch-size-with-serial)

## 4. `delegate_to`: 웹 서버 작업 중 LB에서 실행하기

Play의 대상이 `web`이어도 모든 Task를 웹 서버에서 실행할 필요는 없다. 예를 들어 배포한 웹 서버가 LB에서도 접근 가능한지 확인하려면 **HTTP 요청을 보내는 위치를 LB로 옮기면 된다.**

다음 Task는 `lb01`이 Inventory에 있고 SSH 인증이 준비되어 있다고 가정한다.

```yaml
# lb01이 Inventory에 있으며 SSH 인증이 준비되어 있다고 가정
- name: Verify the web endpoint from the load balancer
  ansible.builtin.uri:
    url: "http://{{ hostvars[inventory_hostname]['ansible_host'] }}:8080/health"
    status_code: 200
  delegate_to: lb01
  become: false
  changed_when: false
```

현재 배포 대상이 `web01`이면 `inventory_hostname`은 계속 `web01`이다. `delegate_to: lb01`은 이 Task의 실행 위치만 LB로 바꾼다. 그래서 URL에는 `hostvars[inventory_hostname]`을 사용해 원래 웹 서버의 주소를 넣었다.

연결 계정, Python, 권한 전환 설정은 위임된 호스트의 영향을 받는다. 또한 `--limit web`으로 대상을 좁혀도 LB로 위임한 Task는 실행될 수 있다. `--limit`은 위임 작업의 실행 위치까지 제한하는 옵션이 아니다.

공식문서: [Delegation and local actions](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_delegation.html)

## 5. `throttle`: 특정 Task만 적게 실행하기

여러 웹 서버가 동시에 LB에 작업을 요청하면 공통 자원에 부담을 주거나 같은 설정을 충돌해서 바꿀 수 있다. **같은 서버로 위임했다고 자동으로 한 번에 하나씩 실행되지는 않는다.** 특정 Task의 동시 실행 수를 줄일 때 `throttle`을 사용한다.

아래는 앞의 요청을 한 번에 하나만 실행하도록 바꾼 예다.

```yaml
# 위 Health Check Task를 한 번에 하나씩 실행하는 예제
- name: Probe web endpoints without overloading the checker
  ansible.builtin.uri:
    url: "http://{{ hostvars[inventory_hostname]['ansible_host'] }}:8080/health"
    status_code: 200
  delegate_to: lb01
  become: false
  throttle: 1
  changed_when: false
```

다음 세 값을 함께 보면 차이가 분명해진다.

| 설정 | 일반적인 동기 Task에서의 의미 |
| --- | --- |
| CLI의 `--forks 10` | 작업 프로세스는 최대 10개 |
| `serial: 4` | 현재 배포 묶음은 4대 |
| 해당 Task의 `throttle: 1` | 이 Task는 동시에 최대 1대씩 처리 |

`throttle`은 기존 동시 실행 한도를 더 낮추는 옵션이다. 다른 Ansible 실행이나 다른 Jenkins Job까지 잠그지는 않으므로 여러 Job이 같은 LB를 바꾼다면 별도의 공유 잠금이 필요하다.

공식문서: [Restricting execution with throttle](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html#restricting-execution-with-throttle)

## 6. `run_once`: 어디까지가 ‘한 번’일까?

현재 배치의 서버 목록 같은 공통 메시지를 서버마다 출력할 필요는 없다. 이때 Task에 `run_once: true`를 붙인다.

```yaml
- name: Print the current batch once
  ansible.builtin.debug:
    msg: "Batch: {{ ansible_play_batch }}"
  run_once: true
```

`linear`에서 이 Task는 현재 배치의 첫 호스트를 기준으로 실행되고 결과는 같은 배치에 적용된다. **`serial`을 사용하면 전체 Playbook에서 한 번이 아니라 배치마다 한 번이다.** 예를 들어 서버 6대에 `serial: 2`라면 배치가 3개이므로 세 번 실행된다.

DB Migration처럼 배포 전체에서 한 번만 실행해야 하는 작업은 한 호스트만 포함한 별도 Play로 분리하면 흐름이 명확하다.

<details>
<summary>별도 Play로 Migration을 실행하는 구조 예제</summary>

```yaml
# 전체 Playbook의 첫 Play: migration_runner 그룹에는 한 호스트만 등록
- name: Run the schema migration before web deployment
  hosts: migration_runner
  gather_facts: false
  any_errors_fatal: true
  tasks:
    - name: Apply the application migration
      ansible.builtin.command:
        argv:
          - /opt/study/bin/migrate
      register: migration_result
      changed_when: migration_result.rc == 2
      failed_when: migration_result.rc not in [0, 2]
```

`migration_runner` 그룹에는 한 호스트만 등록한다. `/opt/study/bin/migrate`는 미리 준비한 애플리케이션 도구를 가정한 예시다. 종료 코드도 `0=변경 없음`, `2=변경 완료`라는 예제 규약이므로 실제 도구에 맞게 바꾼다.

별도 Play 역시 `--limit`의 영향을 받는다. 웹 서버만 허용한 실행에서 Migration 호스트가 제외되지 않도록 실행 명령을 함께 설계한다.

</details>

`free`에서는 `run_once`가 한 번 실행된다고 기대할 수 없다. 공통 작업을 정확히 한 번 실행해야 한다면 실행 전략과 배치 경계를 함께 확인한다.

공식문서: [Running on a single machine](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html#running-on-a-single-machine-with-run-once), [Ansible Lint — run-once](https://docs.ansible.com/projects/lint/rules/run-once/)

## 7. 실패하면 나머지 서버도 멈출까?

기본적으로 Task에 실패한 서버는 후속 작업에서 빠지고, 정상 서버는 계속 진행할 수 있다. 배포에서는 새 버전에 문제가 발견됐을 때 나머지 서버로 확대하지 않는 정책이 필요하다.

| 원하는 정책 | 설정 | 동작 |
| --- | --- | --- |
| 한 대라도 실패하면 전체 중단 | `any_errors_fatal: true` | 현재 배치에서 실패한 Task의 처리를 마친 뒤 진행 중단 |
| 일부 실패는 허용하되 한도를 넘으면 중단 | `max_fail_percentage` | 실패 비율이 지정값을 **초과**하면 중단 |

예를 들어 4대 배치에서 2대가 실패하면 멈추고 싶다면 다음처럼 설정한다.

```yaml
# 두 정책 중 목적에 맞는 하나를 선택하는 예제
- name: Deploy with a failure threshold
  hosts: web
  become: true
  serial: 4
  max_fail_percentage: 49
  roles:
    - study_web
```

2대 실패는 50%다. `49`를 초과하므로 멈춘다. `50`으로 설정하면 같은 비율에 도달한 것이므로 아직 중단 기준을 넘지 않는다. `serial`과 함께 쓸 때는 현재 배치를 기준으로 계산한다.

중단 설정이 이미 적용한 변경까지 되돌려 주지는 않는다. 복구는 별도의 Task로 작성해야 한다. 또한 `rescue`가 성공하면 원래 실패가 복구된 것으로 처리될 수 있다. 복구 후에도 나머지 배포를 멈추려면 실패를 다시 전달해야 하며, 이 구조를 04번 문서에서 다룬다.

공식문서: [Aborting a play and failure percentage](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html#aborting-a-play-on-all-hosts), [Handling errors with blocks](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html#handling-errors-with-blocks)

## 8. 스터디에서 확인할 질문

- `forks=10`, `serial=2`이면 한 배치에 몇 대가 참여할까?
- 웹 서버의 Task를 모두 `lb01`로 위임하면 자동으로 순서대로 실행될까?
- `serial: 2`인 배포에서 `run_once`로 DB Migration을 실행하면 어떤 문제가 생길까?

이전: [Security & Secret Management](02-security-and-secret-management.md) · 다음: [Rolling Deployment & Failure Handling](04-rolling-deployment-and-failure-handling.md)
