# 03-Multi-Host-Execution-&-Orchestration

## 3. Multi-Host Orchestration이란?

---

> 서버에 작업을 어떤 순서와 방식으로 배포할지 제어하는 것
> 

Ansible은 하나의 Host만 관리하는 도구가 아니라 여러 서버를 대상으로 **실행 순서, 병렬성, Batch 크기, 실패 정책까지 제어**할 수 있다.

```
app01 ─┐
app02 ─┼── Ansible Playbook
app03 ─┤      │
app04 ─┘      ├── 몇 대씩 실행할지
              ├── 어느 Task만 제한할지
              └── 몇 대 실패하면 중단할지
```

왜 필요한 가?

→ 서비스 중단 위험을 줄이기 위해서

- 웹서버 10대를 전부 재시작하면 가용가능한 서버는 0대
- 이 처럼 전체를 하는 것이 아니라 몇 대씩 순차적으로 하지 이런걸 컨트롤 하는 것

### 3-1. linear Strategy

---

> 같은 Batch에 속한 모든 서버가 현재 Task를 끝낸 뒤, 다음 Task로 넘어가는 방식
default Strategy는 `linear`다.
> 

```yaml
- hosts: web
  strategy: linear

  tasks:
    - name: 패키지 설치
      ansible.builtin.apt:
        name: nginx
        state: present

    - name: 설정 파일 배포
      ansible.builtin.template:
        src: nginx.conf.j2
        dest: /etc/nginx/nginx.conf

    - name: nginx 시작
      ansible.builtin.service:
        name: nginx
        state: started
```

```
Task 1: nginx 설치
 ├─ web1 ─ 완료
 ├─ web2 ─ 완료
 └─ web3 ─ 완료
        ↓
모든 서버 완료
        ↓
Task 2: 설정 파일 배포
 ├─ web1 ─ 완료
 ├─ web2 ─ 완료
 └─ web3 ─ 완료
        ↓
모든 서버 완료
        ↓
Task 3: nginx 시작
 ├─ web1 ─ 완료
 ├─ web2 ─ 완료
 └─ web3 ─ 완료
```

### 3-2. strategy: free

---

> 각 Host가 다른 Host의 진행 상황을 기다리지 않고, 자기 Task가 끝나는 즉시 다음 Task로 넘어가는 방식
> 

→ Host별로 독립적으로 진행되는 것

```yaml
- hosts: web
  strategy: free

  tasks:
    - name: 패키지 설치
      ansible.builtin.apt:
        name: nginx
        state: present

    - name: 설정 파일 배포
      ansible.builtin.template:
        src: nginx.conf.j2
        dest: /etc/nginx/nginx.conf

    - name: nginx 시작
      ansible.builtin.service:
        name: nginx
        state: started
```

```
web1  Task1 → Task2 → Task3 → 완료

web2  Task1 ─────────→ Task2 → Task3 → 완료

web3  Task1 ────→ Task2 ─────→ Task3 → 완료
```

### 3-3. forks

---

> Ansible이 동시에 몇 개의 Host에 작업을 실행할지 정하는 병렬 처리 개수
즉, 동시에 작업할 수 있는 서버 수
> 

```
forks = 5
```

```
서버 10대

1차
web1
web2
web3
web4
web5
   ↓ 완료

2차
web6
web7
web8
web9
web10
```

`forks`를 무조건 크게 하면 좋은 것은 아니다.

- Control Node CPU/Memory
- SSH Connection 수
- Managed Node 부하
- Load Balancer / API Rate Limit
- Network 대역폭

을 함께 고려해야 한다.

### 3-4. serial

---

> 전체 Host를 몇 대씩 Batch로 나누어 Play를 실행할지 지정
즉, 배치 크기이다
> 

```yaml
- hosts: web
  serial: 2
```

```
Batch 1
web1
web2
  ↓ 완료

Batch 2
web3
web4
  ↓ 완료

Batch 3
web5
web6

...
```

- 10대를 돌려야한다면 serial크기가 2개니깐 5번 돈다

Percentage도 사용할 수 있다.

```yaml
serial: "25%"
```

### 3-5. run_once

---

> Task를 현재 Batch에서 한 Host에서만 실행하도록 하는 옵션
`run_once: true`는 해당 Task를 Host마다 반복하지 않고 한 번만 실행하도록 한다.
> 

예를 들어 DB Migration처럼 배포 대상 서버 수만큼 반복하면 안 되는 작업에 사용할 수 있다.

```yaml
- hosts: web
  tasks:
    - name: DB migration
      ansible.builtin.command: /app/migrate.sh
      run_once: true
```

```
web1 → DB migration 실행
web2 → 실행 안 함
web3 → 실행 안 함
```

언제 사용하는지?

- 여러 서버에서 중복 실행하면 안되는 작업
    - DB Migration
    - 공통 초기화 작업
    - 공유 파일 생성
    - 외부 API 한 번 호출
    - 배포 완료 알림 한 번 전송

### 3-6. delegate_to

---

> Task를 원래 대상 Host가 아닌 다른 Host에서 실행하도록 하는 것
> 

```yaml
- hosts: web
  tasks:
    - name: Load Balancer에서 현재 서버 제거
      ansible.builtin.command: /usr/local/bin/remove_from_lb {{ inventory_hostname }}
      delegate_to: lb01
```

```
Play 대상
web1
web2
web3

Task 실행 위치
   ↓
  lb01
```

### 3-7. throttle

---

> Task를 동시에 몇 개의 Host에서 실행할 수 있는지 제한하는 옵션
> 

```yaml
- name: 서비스 재시작
  ansible.builtin.service:
    name: myapp
    state: restarted
  throttle: 2
```

```
web1 ─┐
web2 ─┘ 실행
      ↓
web3 ─┐
web4 ─┘ 실행
      ↓
...
```

이 Task는 한 번에 최대 2대에서만 실행

> `forks` = Ansible 전체 병렬 실행 한도
`serial` = 한 Batch에 포함할 Host 수
`throttle` = 특정 Task/Block의 동시 실행 한도
> 

### 3-8. any_errors_fatal

---

> Host 하나에서도 처리되지 않는 Task 실패가 발생하면, 전체 Play 실행 중단
> 

```yaml
- hosts: web
  any_errors_fatal: true

  tasks:
    - name: 애플리케이션 배포
      ansible.builtin.command: /app/deploy.sh

    - name: 서비스 재시작
      ansible.builtin.service:
        name: myapp
        state: restarted
```

```
Task 1: Deploy

web1 → 성공
web2 → 실패 ❌
web3 → 성공

        ↓

전체 Play 중단
```

왜 사용하는지?

- 한 서버라도 실패하면 다음 단계로 진행하면 안 되는 작업

### 3-9. max_fail_percentage

---

> 실행 중인 Host 들 중 몇 %까지 실패를 허용할지 정하는 옵션
> 

```yaml
- hosts: web
  max_fail_percentage: 30

  tasks:
    - name: Deploy
      ansible.builtin.command: /app/deploy.sh
```

```
실패 1대 → 10% → 계속
실패 2대 → 20% → 계속
실패 3대 → 30% → 계속
실패 4대 → 40% → 중단
```

- 정해놓은 실패율을 초과하면 중단

### 3-10. 여기서 생각해볼 질문

---

1. `forks`와 `serial`은 무엇이 다른가?
2. `linear`보다 `free`가 적합한 작업은 어떤 것인가?
3. DB Migration에 `run_once`를 사용할 때 `serial`을 왜 같이 확인해야 하는가?
    
    <aside>
    
    play 기준 전체 1회가 아니라 serial batch 기준 1회로 실행될 수 있기 때문에 
    serial이 2대로 묶이면 1회로 두 대 기준으로 1회로 되기 때문에
    
    </aside>
    
4. Load Balancer 제어에 `delegate_to`가 필요한 이유는?
5. `max_fail_percentage`는 Batch 크기와 어떤 관계가 있는가?

### 3-11. 참고 자료

---

- [Ansible 공식 문서 - Controlling playbook execution](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_strategies.html)
- [Ansible 공식 문서 - Delegation](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_delegation.html)
- [Ansible 공식 문서 - Error Handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)