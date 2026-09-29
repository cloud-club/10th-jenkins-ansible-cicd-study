# 04-Rolling-Deployment-&-Failure-Handling

## 4. Rolling Deployment란?

---

> 여러 서버에 애플리케이션을 한 번에 전부 배포하지 않고, 일부 서버씩 순차적으로 배포하는 방식
> 

```
                 Load Balancer
                      ↓
        ┌─────────────┼─────────────┐
       web1          web2          web3

1. LB에서 web1 트래픽 제외
          ↓
2. web1에 새 버전 배포
          ↓
3. web1 애플리케이션 재시작
          ↓
4. Health Check
          ↓
5. 정상이라면 LB에 web1 다시 등록
          ↓
6. 다음 서버 web2 배포
```

### 4-1. serial을 이용한 Rolling Deployment

---

가장 단순한 형태는 `serial: 1`이다.

```yaml
- name: Rolling deploy application
  hosts: app
  serial: 1
  any_errors_fatal: true

  roles:
    - app
```

한 서버의 전체 Play가 완료된 뒤 다음 서버로 넘어간다.

서버가 많다면 Batch 크기를 늘릴 수 있다.

```yaml
serial: 2
```

Batch를 단계적으로 키울 수도 있다.

```yaml
serial:
  - 1
  - 2
  - "25%"
```

첫 Batch를 Canary처럼 작게 검증하고 이후 범위를 확대하는 전략으로 사용할 수 있다.

### 4-2. Load Balancer Drain → Deploy → Health Check → 복귀

---

```
app01
  ↓
LB에서 제외
  ↓
새 app.jar 배포
  ↓
Application 재시작
  ↓
Health Check
  ↓
정상
  ↓
LB에 다시 등록
  ↓
app02로 이동
```

예시:

```yaml
---
- name: Rolling deployment
  hosts: app
  serial: 1
  any_errors_fatal: true

  pre_tasks:
    # 1. 현재 배포 대상 서버를 Load Balancer에서 제외
    - name: Disable current host from load balancer
      ansible.builtin.command:
        cmd: "/usr/local/bin/lb-disable {{ inventory_hostname }}"
      delegate_to: localhost

    # 2. 기존 Artifact 백업
    - name: Backup current artifact
      ansible.builtin.copy:
        src: /opt/myapp/app.jar
        dest: /opt/myapp/app.jar.bak
        remote_src: true

  tasks:
    # 3. 신규 Artifact 배포
    - name: Deploy new application
      ansible.builtin.copy:
        src: app.jar
        dest: /opt/myapp/app.jar
        owner: app
        group: app
        mode: "0644"
      notify: Restart application

    # 4. notify된 Restart Handler를 지금 실행
    - name: Flush handlers before health check
      ansible.builtin.meta: flush_handlers

    # 5. Application Health Check
    - name: Wait for application health
      ansible.builtin.uri:
        url: "http://127.0.0.1:8080/actuator/health"
        method: GET
        status_code: 200
      register: health_result
      retries: 10
      delay: 3
      until: health_result.status == 200

  post_tasks:
    # 6. 정상이라면 Load Balancer에 다시 등록
    - name: Enable current host in load balancer
      ansible.builtin.command:
        cmd: "/usr/local/bin/lb-enable {{ inventory_hostname }}"
      delegate_to: localhost

  handlers:
    - name: Restart application
      ansible.builtin.service:
        name: myapp
        state: restarted
```

```
app01
 ├─ LB 제외
 ├─ 기존 app.jar 백업
 ├─ 신규 app.jar 배포
 ├─ Application 재시작
 ├─ Health Check
 └─ LB 복귀
       ↓
app02
 ├─ LB 제외
 ├─ 백업
 ├─ 배포
 ├─ 재시작
 ├─ Health Check
 └─ LB 복귀
       ↓
app03
 └─ 동일
```

### 4-3. Health Check는 무엇을 확인해야 할까?

---

단순히 Process가 떠 있는 것만 확인하면 부족할 수 있다.

가능하면 다음을 단계적으로 확인한다.

- Process / Service가 실행 중인가?
- Application Port가 열렸는가?
- Health Endpoint가 200을 반환하는가?
- DB/Redis 같은 핵심 Dependency 연결이 정상인가?
- 실제 핵심 API가 최소 기능을 수행하는가?

### 4-4. 실패 시 배포 중단

---

Health Check가 실패했다면 다음 Batch로 계속 진행하면 장애 범위가 커질 수 있다.

```yaml
any_errors_fatal: true
```

또는 허용 가능한 실패 비율을 정할 수 있다.

```yaml
max_fail_percentage: 0
```

운영에서는 Batch 크기, 최소 가용 서버 수, 실패 허용 범위를 함께 결정한다.

### 4-5. block / rescue를 이용한 복구

---

배포 실패 시 이전 Artifact로 복구할 수 있다.

```yaml
- name: Deploy with rollback

  # block 내부 Task를 순서대로 실행한다.
  # block 안에서 Task 하나라도 실패하면
  # 나머지 block Task는 중단되고 rescue로 이동한다.
  block:

    # 1. 현재 운영 중인 Artifact를 백업
    # 신규 버전 배포에 실패했을 때 되돌리기 위해
    # 현재 app.jar를 app.jar.bak으로 복사한다.
    - name: Backup current artifact
      ansible.builtin.copy:
        src: /opt/myapp/app.jar
        dest: /opt/myapp/app.jar.bak

        # src 파일이 Ansible Control Node가 아니라
        # 현재 Managed Node에 존재한다는 의미
        remote_src: true

    # 2. 신규 Artifact 배포
    # Control Node에 있는 app.jar를
    # 현재 배포 대상 서버의 /opt/myapp/app.jar로 복사한다.
    - name: Deploy new artifact
      ansible.builtin.copy:
        src: app.jar
        dest: /opt/myapp/app.jar

    # 3. 신규 Artifact를 반영하기 위해 Application 재시작
    - name: Restart application
      ansible.builtin.service:
        name: myapp
        state: restarted

    # 4. 신규 버전이 정상적으로 올라왔는지 Health Check
    - name: Health check
      ansible.builtin.uri:
        url: "http://127.0.0.1:8080/actuator/health"
        status_code: 200

      # uri 실행 결과를 health 변수에 저장
      register: health

      # Health Check가 실패하면 최대 10번 재시도
      retries: 10

      # 재시도 사이에 3초 대기
      delay: 3

      # HTTP Status가 200이 될 때까지 재시도
      until: health.status == 200

  # block 내부 Task 중 하나라도 실패하면 rescue 실행
  rescue:

    # 5. 백업해 두었던 이전 Artifact를 복원
    - name: Restore previous artifact
      ansible.builtin.copy:
        src: /opt/myapp/app.jar.bak
        dest: /opt/myapp/app.jar

        # app.jar.bak 역시 현재 Managed Node에 존재
        remote_src: true

    # 6. 이전 버전 Artifact로 다시 Application 재시작
    - name: Restart previous version
      ansible.builtin.service:
        name: myapp
        state: restarted
```

```
기존 app.jar
    ↓
Backup
    ↓
app.jar.bak 생성
    ↓
신규 app.jar 배포
    ↓
Application Restart
    ↓
Health Check
    ↓
200 OK
    ↓
배포 성공
```

- 자바의 try-catch라고 생각하면 될 듯

### 4-6. Canary Deployment

---

> 새 버전을 전체 사용자에게 바로 배포하지 않고, 일부나 서버나 일부 사용자에게 먼저 노출한뒤 문제가 없으면 점진적으로 확대하는 방식
> 

```yaml
serial:
  - 1
  - 2
  - "50%"
```

또는 별도의 Inventory Group을 둘 수도 있다.

```yaml
all:
  children:

    canary:
      hosts:
        app01:

    stable:
      hosts:
        app02:
        app03:
        app04:

    app:
      children:
        canary:
        stable:
```

```bash
ansible-playbook deploy.yml -i inventory.yml --limit canary
```

```
사용자 요청
   ↓
Load Balancer
   ├─ 90% → v1 서버들
   └─ 10% → v2 Canary 서버
```

### 4-7. Blue-Green Deployment

---

Blue-Green은 같은 애플리케이션의 두 환경을 유지한 뒤 Traffic을 전환하는 방식이다.

```
             ┌── blue  ← 현재 Traffic
Load Balancer
             └── green ← 신규 버전 배포/검증
```

Inventory Group을 환경 단위로 나눌 수 있다.

```yaml
all:
  children:
    blue:
      hosts:
        blue01:
        blue02:
    green:
      hosts:
        green01:
        green02:
```

흐름:

```
Green 배포
   ↓
Green Health Check
   ↓
Smoke Test
   ↓
LB Traffic Green으로 전환
   ↓
문제 발생 시 Blue로 복귀
```

Rolling Deployment보다 추가 서버 자원이 필요하지만 전환과 원복 경계가 명확하다.

### 4-8. 실습

---

- [ ]  Application Host 3대 이상 구성
- [ ]  `serial: 1` Rolling 실행
- [ ]  LB 제외/복귀 Task를 `delegate_to`로 구현
- [ ]  Application Restart 후 Health Check 수행
- [ ]  Health Check 실패 시 다음 Batch가 중단되는지 확인
- [ ]  `block/rescue`로 Artifact Rollback 구현
- [ ]  `serial` Batch 크기를 1 → 2로 변경해 비교
- [ ]  Canary Group 또는 `--limit`으로 선배포
- [ ]  Blue/Green Inventory Group 설계

### 4-9. 운영 배포 체크리스트

---

- [ ]  최소 가용 서버 수가 정의되어 있는가?
- [ ]  LB Drain이 완료된 뒤 배포가 시작되는가?
- [ ]  배포 전 이전 Artifact를 복구할 수 있는가?
- [ ]  Health Check 성공 기준이 명확한가?
- [ ]  실패 시 다음 Batch로 진행하지 않는가?
- [ ]  Rollback 이후 Health Check를 다시 수행하는가?
- [ ]  Canary 범위와 확대 기준이 정의되어 있는가?
- [ ]  Blue-Green 전환 시 되돌릴 방법이 있는가?

### 4-10. 여기서 생각해볼 질문

---

1. Rolling Deployment에서 `serial: 1`이 항상 좋은 선택은 아닌 이유는?
2. LB에서 서버를 제외하지 않고 재시작하면 어떤 문제가 생길 수 있는가?
3. Health Check를 Process 상태만으로 판단하면 부족한 이유는?
4. Canary와 Rolling Deployment는 어떤 관계가 있는가?
5. Blue-Green이 Rolling보다 많은 인프라 자원을 요구하는 이유는?

### 4-11. 참고 자료

---

- [Ansible 공식 문서 - Rolling Upgrade Example](https://docs.ansible.com/projects/ansible/latest/playbook_guide/guide_rolling_upgrade.html)
- [Ansible 공식 문서 - Delegation](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_delegation.html)
- [Ansible 공식 문서 - Strategies and serial](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)
- [Ansible 공식 문서 - Error Handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)