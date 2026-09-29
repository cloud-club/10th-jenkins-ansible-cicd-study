# Rolling Deployment & Failure Handling

## 1. 한 대씩 바꾸면서 서비스를 유지하려면?

웹 서버 두 대가 같은 서비스를 제공하고 있다고 생각해 보자. 두 대를 동시에 멈추면 요청을 처리할 서버가 없다. 한 대를 배포하는 동안 다른 한 대가 요청을 처리하도록 하면 서비스 영향을 줄일 수 있다.

이처럼 **일부 서버를 순서대로 갱신하는 방식이 Rolling Deployment**다. 03번에서 배운 `serial`로 배포할 서버 수를 정하고, 각 서버에서는 다음 순서로 작업한다.

```text
web01: LB에서 제외 → 배포 → Health Check → LB에 복귀
web02:                                             LB에서 제외 → 배포 → 확인 → 복귀
```

여기서 핵심은 “한 대씩 실행한다”보다 **정상 동작을 확인한 서버만 다시 요청을 받게 한다**는 점이다. `serial: 1`만 설정하면 LB 제어와 Health Check까지 자동으로 수행되지는 않는다.

이번 문서는 01번의 Nginx 예제를 이어서 사용한다. `/health`가 응답하는 버전을 `v1`에서 `v2`로 바꾸며 배포 순서와 실패 처리를 학습한다. 실제 애플리케이션에서는 파일 교체 부분을 산출물 설치·프로세스 재시작으로 바꾸고, 서비스의 실제 준비 상태를 검사해야 한다.

공식문서: [Delegation — rolling update example](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_delegation.html#delegating-tasks), [Serial batches](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html#setting-the-batch-size-with-serial)

## 2. 배포 한 사이클을 단계별로 보기

먼저 정상 경로를 이해한 뒤 실패 처리를 더해 보자. 전체 Playbook은 5절에서 펼쳐 볼 수 있다.

| 단계 | 하는 일 | 필요한 이유 |
| --- | --- | --- |
| 이전 버전 확보 | 기존 `/health` 파일 내용 저장 | 실패하면 원래 값으로 복원하기 위해 |
| LB에서 제외 | 새 요청을 막고 기존 연결 종료 대기 | 변경 중인 서버가 요청을 받지 않도록 |
| 새 버전 배포 | 버전 파일을 새 값으로 교체 | 실습에서 배포를 표현하는 작업 |
| Health Check | LB에서 웹 서버에 직접 요청 | 새 버전의 응답을 확인하기 위해 |
| LB에 복귀 | 확인된 서버를 다시 활성화 | 정상 서버만 요청을 받도록 |

### 2.1 LB 제외 작업은 LB에서 실행한다

Play의 대상은 웹 서버지만 HAProxy를 제어하는 Task는 `delegate_to: lb01`로 LB에서 실행한다. `inventory_hostname`에는 현재 배포 중인 웹 서버 이름이 들어간다.

```yaml
# 정상 배포 흐름 중 LB 제외 Task 발췌
- name: Remove the host from traffic and wait for connections
  community.general.haproxy:
    socket: /run/haproxy/admin.sock
    backend: study_web
    host: "{{ inventory_hostname }}"
    state: disabled
    drain: true
    wait: true
    wait_interval: 2
    wait_retries: 30
    fail_on_not_found: true
  delegate_to: lb01
  throttle: 1
```

`drain: true`는 기존 연결이 없어지기를 기다리게 한다. `wait: true`는 상태 변경을 확인한 뒤 다음 작업으로 넘어가게 한다. 서버 이름을 잘못 지정했을 때 조용히 진행하지 않도록 `fail_on_not_found`도 켰다.

공식문서: [community.general.haproxy](https://docs.ansible.com/projects/ansible/latest/collections/community/general/haproxy_module.html)

### 2.2 Health Check는 새 버전인지도 확인한다

서버가 HTTP 200을 반환하더라도 이전 버전이 계속 응답하고 있을 수 있다. 이번 실습에서는 상태 코드와 응답 본문을 함께 확인한다.

```yaml
# 새 버전을 배포한 뒤 실행하는 Task 발췌
- name: Check the new release from the load balancer
  ansible.builtin.uri:
    url: "http://{{ hostvars[inventory_hostname]['ansible_host'] }}:8080/health"
    status_code: 200
    return_content: true
    timeout: 5
  delegate_to: lb01
  become: false
  register: release_health
  until:
    - release_health.status | default(0) == 200
    - release_health.content | default('') | trim == study_web_release
  retries: 5
  delay: 2
  changed_when: false
```

`register`로 응답을 저장하고 `until`로 통과 조건을 정했다. 조건을 만족하지 않으면 잠시 기다린 뒤 다시 요청한다. 정해진 재시도 후에도 실패하면 복구 경로로 넘어간다.

LB의 공용 주소가 아닌 **현재 배포 중인 웹 서버의 주소**를 직접 확인하는 것도 중요하다. 다른 정상 서버의 응답을 새 서버의 응답으로 착각하지 않기 위해서다.

공식문서: [uri module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/uri_module.html), [Retrying a task until a condition is met](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_loops.html#retrying-a-task-until-a-condition-is-met)

## 3. 실패하면 복구하고, 다음 배치는 멈춘다

정상 경로를 `block`에 묶고, 실패했을 때 할 일을 `rescue`에 작성한다. `rescue`가 이전 상태를 자동으로 되돌려 주는 것은 아니다. 복원할 파일과 확인할 상태를 직접 정해야 한다.

```text
block:  LB 제외 → 새 버전 배포 → 검증 → LB 복귀
                     ↓ 실패
rescue: LB 제외 상태 확인 → 이전 버전 복원 → 복구 검증
                                         ├─ 성공: LB 복귀 → 배포 실패 전달
                                         └─ 실패: 추가 복귀 작업 중단 → 배포 실패 전달
```

**복구 성공과 배포 성공은 다르다.** 이전 버전으로 돌아왔다면 서비스는 복구됐지만 새 버전의 배포는 실패한 것이다. 그래서 예제의 `rescue` 마지막에는 `ansible.builtin.fail`을 실행한다. 이 실패를 `any_errors_fatal: true`와 연결해 다음 서버의 배포도 멈춘다.

실패 여부와 관계없이 실행하는 `always`에 LB 복귀를 넣으면 검증하지 못한 서버도 다시 요청을 받을 수 있다. 이번 예제에서는 새 버전 검증이나 복구 검증을 통과한 경로에서만 복귀한다.

| 실패 지점 | 예제의 동작 |
| --- | --- |
| 이전 버전 읽기 | LB를 건드리기 전에 중단 |
| LB 제외·배포·새 버전 검증·복귀 | 이전 버전 복구 시도 |
| 이전 버전 복구와 검증 성공 | LB에 복귀한 뒤 전체 배포 실패 처리 |
| 복구 또는 복구 검증 실패 | 추가 복귀 Task를 실행하지 않고 확인 요청 |

> 복구의 한계: 잘못된 Task 정의나 연결 불가(`UNREACHABLE`)는 일반적인 `rescue` 대상이 아니다. Ansible·Agent 프로세스가 종료돼도 복구가 끝나지 않을 수 있다. LB 제어 요청 자체가 실패했다면 실제 제외·복귀 상태도 직접 확인해야 한다.

공식문서: [Blocks and rescue](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_blocks.html), [Aborting on the first error](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html#aborting-on-the-first-error-any-errors-fatal)

## 4. 실습 환경 준비하기

구조를 이해했다면 실제 예제를 준비한다. 01번의 `site.yml`을 웹 서버 두 대에 먼저 적용하고, 포트는 `8080`, 문서 경로는 `/var/www/ansible-study`로 유지한다.

| 위치 | 준비할 내용 |
| --- | --- |
| Ansible Control Node | `community.general` Collection, 웹 서버·LB에 접속할 SSH 인증 |
| `web01`, `web02` | 01번 Nginx 서비스와 sudo 권한 |
| `lb01` | HAProxy, `nc`를 제공하는 패키지, sudo 권한 |
| 네트워크 | Control Node → 각 서버 SSH, LB → 웹 서버 8080 접근 |

Ubuntu LB에서는 `haproxy`, `netcat-openbsd` 패키지를 준비한다. 아래 Inventory와 HAProxy 설정의 주소는 실제 실습 서버 주소로 바꾼다.

<details>
<summary>Inventory와 HAProxy 설정 펼치기</summary>

```yaml
# inventories/dev/hosts.yml
all:
  vars:
    ansible_user: ubuntu
  children:
    web:
      hosts:
        web01:
          ansible_host: 192.0.2.11
        web02:
          ansible_host: 192.0.2.12
    load_balancers:
      hosts:
        lb01:
          ansible_host: 192.0.2.10
```

HAProxy의 서버 이름을 Inventory의 `web01`, `web02`와 맞춘다. 다음은 기존 서비스가 없는 실습 LB의 설정 예제다.

```text
# /etc/haproxy/haproxy.cfg on lb01
global
    stats socket /run/haproxy/admin.sock mode 600 level admin

defaults
    mode http
    timeout connect 5s
    timeout client 30s
    timeout server 30s

frontend study_frontend
    bind *:80
    default_backend study_web

backend study_web
    option httpchk GET /health
    http-check expect status 200
    server web01 192.0.2.11:8080 check
    server web02 192.0.2.12:8080 check
```

설정 파일을 작성한 뒤 LB에서 문법을 검사하고 적용한다.

```bash
# lb01에서 설정 검사 후 적용
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
sudo systemctl reload haproxy
```

Runtime Socket은 관리자 작업에 사용하므로 접근 권한을 제한한다. 예제의 Runtime 상태 변경은 설정 파일에 영구 저장되지 않는다. 배포 중 LB가 재시작되거나 reload될 때 상태를 유지하는 방법은 별도로 설계해야 한다.

</details>

공식문서: [HAProxy configuration manual](https://docs.haproxy.org/3.2/configuration.html), [HAProxy Runtime API](https://www.haproxy.com/documentation/haproxy-runtime-api/), [HAProxy module requirements](https://docs.ansible.com/projects/ansible/latest/collections/community/general/haproxy_module.html)

## 5. 전체 Playbook으로 연결하기

아래 예제는 `serial: 1`로 한 대씩 진행한다. `pre_tasks`에서 입력을 확인하고 이전 버전을 저장한 뒤, `tasks`에서 정상 배포와 복구를 수행한다. 먼저 큰 구조를 보고 앞에서 읽은 Task가 어디에 들어가는지 찾아보자.

<details>
<summary>rolling.yml 전체 코드 펼치기</summary>

```yaml
# rolling.yml
- name: Roll out the study web release
  hosts: web
  become: true
  gather_facts: false
  strategy: linear
  serial: 1
  any_errors_fatal: true
  tags:
    - deploy

  pre_tasks:
    - name: Require a real run and a valid release
      ansible.builtin.assert:
        that:
          - not ansible_check_mode
          - study_web_release is defined
          - study_web_release is match('^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
        fail_msg: Use a real run with a valid study_web_release after preflight checks.

    - name: Save the previous release marker
      ansible.builtin.slurp:
        src: /var/www/ansible-study/health
      register: previous_release

  tasks:
    - name: Deploy and recover the current host
      block:
        - name: Remove the host from traffic and wait for connections
          community.general.haproxy:
            socket: /run/haproxy/admin.sock
            backend: study_web
            host: "{{ inventory_hostname }}"
            state: disabled
            drain: true
            wait: true
            wait_interval: 2
            wait_retries: 30
            fail_on_not_found: true
          delegate_to: lb01
          throttle: 1

        - name: Publish the new release
          ansible.builtin.copy:
            content: "{{ study_web_release }}\n"
            dest: /var/www/ansible-study/health
            owner: root
            group: root
            mode: '0644'

        - name: Check the new release from the load balancer
          ansible.builtin.uri:
            url: "http://{{ hostvars[inventory_hostname]['ansible_host'] }}:8080/health"
            status_code: 200
            return_content: true
            timeout: 5
          delegate_to: lb01
          become: false
          register: release_health
          until:
            - release_health.status | default(0) == 200
            - release_health.content | default('') | trim == study_web_release
          retries: 5
          delay: 2
          changed_when: false

        - name: Return the healthy host to traffic
          community.general.haproxy:
            socket: /run/haproxy/admin.sock
            backend: study_web
            host: "{{ inventory_hostname }}"
            state: enabled
            wait: true
            fail_on_not_found: true
          delegate_to: lb01
          throttle: 1

      rescue:
        - name: Recover the previous release or leave the host isolated
          block:
            - name: Ensure the failed host is removed from traffic
              community.general.haproxy:
                socket: /run/haproxy/admin.sock
                backend: study_web
                host: "{{ inventory_hostname }}"
                state: disabled
                drain: true
                wait: true
                fail_on_not_found: true
              delegate_to: lb01
              throttle: 1

            - name: Restore the previous release marker
              ansible.builtin.copy:
                content: "{{ previous_release.content | b64decode }}"
                dest: /var/www/ansible-study/health
                owner: root
                group: root
                mode: '0644'

            - name: Verify the recovered release
              ansible.builtin.uri:
                url: "http://{{ hostvars[inventory_hostname]['ansible_host'] }}:8080/health"
                status_code: 200
                return_content: true
                timeout: 5
              delegate_to: lb01
              become: false
              register: recovery_health
              until:
                - recovery_health.status | default(0) == 200
                - >-
                  recovery_health.content | default('') | trim ==
                  previous_release.content | b64decode | trim
              retries: 5
              delay: 2
              changed_when: false

            - name: Return the recovered host to traffic
              community.general.haproxy:
                socket: /run/haproxy/admin.sock
                backend: study_web
                host: "{{ inventory_hostname }}"
                state: enabled
                wait: true
                fail_on_not_found: true
              delegate_to: lb01
              throttle: 1

          rescue:
            - name: Report that recovery needs operator attention
              ansible.builtin.debug:
                msg: "Recovery failed on {{ inventory_hostname }}; verify LB and host state."

        - name: Fail the deployment even if rollback succeeded
          ansible.builtin.fail:
            msg: "Deployment failed on {{ inventory_hostname }}; stop further batches."
```

</details>

이 예제는 작은 버전 파일을 `slurp`로 읽어 복구에 사용한다. 실제 산출물 전체를 변수로 읽기보다는 이전 릴리스 경로나 산출물 버전을 기록하는 방식으로 확장한다.

공식문서: [slurp module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/slurp_module.html)

### 5.1 한 대부터 실행하기

전체 코드를 `rolling.yml`로 저장한 뒤 구문과 대상을 확인하고 `web01`에 적용한다.

```bash
ansible-playbook -i inventories/dev/hosts.yml rolling.yml --syntax-check
ansible-playbook -i inventories/dev/hosts.yml rolling.yml --list-hosts --limit web
ansible-playbook -i inventories/dev/hosts.yml rolling.yml --limit web01 \
  -e study_web_release=v2
```

02번의 Vault 파일을 함께 사용한다면 각 명령에 `--vault-id dev@prompt` 등 복호화 수단도 전달한다. 정상 적용 후에는 `web01`이 `v2`를 응답하고 LB에서 활성화됐는지 확인한다.

HAProxy 모듈은 check mode를 지원하지 않는다. 따라서 이 Playbook은 `--check` 실행을 거절하도록 작성했다. 구문 검사 후 격리된 실습 환경에서 실제 동작을 확인한다.

### 5.2 실패 경로도 확인하기

정상 배포만 확인하면 복구 코드가 올바른지 알 수 없다. 실습용 Playbook 복사본에서 새 버전 Health Check의 기대값을 일부러 다르게 만들어 실패를 발생시켜 보자. 복구 검증의 기대값은 바꾸지 않는다.

실행 후에는 이전 버전이 돌아왔는지, LB에 복귀했는지, 전체 실행은 실패로 끝났는지 확인한다. 웹 서버 전체를 대상으로 실행했다면 다음 배치의 서버가 변경되지 않았는지도 살펴본다.

### 5.3 실제 애플리케이션 Role로 바꾸기

실제 배포 작업을 Role로 구현했다면 파일 교체 Task 대신 아래 구조를 사용할 수 있다. `application_release`는 별도로 작성해야 하는 Role이다.

```yaml
# 위 배포 Task를 실제 앱 Role로 교체할 때의 구조 예제
- name: Deploy the application role
  ansible.builtin.include_role:
    name: application_release

- name: Apply pending service changes before the health check
  ansible.builtin.meta: flush_handlers
```

설정 변경으로 서비스 reload가 필요하다면 Health Check 전에 Handler를 실행해야 한다. `flush_handlers`는 그때까지 알림받은 Handler들을 실행한다. 이전 버전 복원도 파일뿐 아니라 설정·프로세스 상태까지 되돌리도록 작성한다.

공식문서: [Controlling when handlers run](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_handlers.html#controlling-when-handlers-run)

## 6. Canary: 작은 범위에서 먼저 확인하기

Canary는 새 버전을 일부 대상에 먼저 배포하고 결과를 관찰한 뒤 범위를 넓히는 방식이다. `serial`을 `[1, 2, '50%']`로 설정하면 첫 배치를 작게 시작할 수 있다. 하지만 **작은 배치만 설정했다고 관찰과 승인 단계까지 생기지는 않는다.**

관찰 시간을 분리하고 싶다면 `web01`을 기존 `web` 그룹에 유지하면서 `web_canary` 그룹에도 넣는다. 같은 버전을 Canary와 나머지 서버에 나누어 배포한다.

```bash
# Canary 적용 후 지표를 확인
ansible-playbook -i inventories/dev/hosts.yml rolling.yml \
  --limit web_canary -e study_web_release=v2

# 검증 후 나머지 서버 적용
ansible-playbook -i inventories/dev/hosts.yml rolling.yml \
  --limit 'web:!web_canary' -e study_web_release=v2
```

두 명령 사이에서 오류율·응답 시간·주요 기능을 확인하고 다음 배포 여부를 결정한다. 서버 10%에 배포했다고 트래픽도 정확히 10%가 되는 것은 아니다. 트래픽 비율을 제어하려면 LB의 라우팅 설정도 필요하다.

공식문서: [Serial batches](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html#setting-the-batch-size-with-serial), [Inventory patterns](https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_patterns.html), [AWS deployment configurations](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-configurations.html)

## 7. Blue-Green: 새 환경을 준비한 뒤 전환하기

Blue-Green은 기존 환경과 새 환경을 따로 준비한다. 새 환경의 배포와 검증을 마친 다음 트래픽을 전환한다.

```text
전환 전: LB → web_blue(v1)     web_green(v2) 검증
전환 후:     web_blue(v1)     LB → web_green(v2)
```

Inventory에서는 두 환경을 별도 그룹으로 표현할 수 있다.

```yaml
# Blue-Green 구조 설명용 Inventory 조각
all:
  children:
    web_blue:
      hosts:
        blue01:
          ansible_host: 192.0.2.31
    web_green:
      hosts:
        green01:
          ansible_host: 192.0.2.41
```

예를 들어 `hosts: web_green`인 Play로 새 환경에 Role을 적용하고 검증한다. 이후 LB나 DNS에서 실제 트래픽을 전환한다. **Inventory 그룹은 작업 대상을 나누는 수단이므로 그룹만 바꿔서는 요청이 이동하지 않는다.** 위 Inventory는 구조 설명용이며 앞의 `hosts: web`인 Rolling 예제와는 별도 구성이다.

| 방식 | 무엇을 순서대로 바꿀까? | 문제가 생기면? |
| --- | --- | --- |
| Rolling | 기존 서버를 배치 단위로 변경 | 해당 서버의 이전 버전 복원 |
| Canary | 일부 대상부터 변경하고 관찰 | 확대 중단 후 Canary 복구 |
| Blue-Green | 준비한 새 환경으로 트래픽 전환 | 기존 환경으로 재전환 |

어떤 방식을 사용하든 DB Schema나 공유 데이터의 호환성은 따로 확인해야 한다. 트래픽을 되돌리는 것만으로 이미 변경된 데이터까지 복원되지는 않는다.

공식문서: [AWS Blue/Green Deployments](https://docs.aws.amazon.com/whitepapers/latest/blue-green-deployments/welcome.html)

## 8. 스터디에서 확인할 질문

- `serial: 1` 외에 서비스 영향을 줄이기 위해 어떤 Task가 필요할까?
- 이전 버전 복구에 성공했는데도 마지막에 `fail`을 실행하는 이유는 무엇일까?
- 첫 배치를 1대로 설정하는 것과 Canary 결과를 관찰하는 것은 어떻게 다를까?

이전: [Multi-Host Execution & Orchestration](03-multi-host-execution-and-orchestration.md) · 다음: [Jenkins CI/CD Integration & Operations](05-jenkins-cicd-integration-and-operations.md)
