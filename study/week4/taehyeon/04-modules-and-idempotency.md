# Modules & Idempotency

## 3. Module이란?

---

Module은 **Ansible이 Managed Node에서 실제 작업을 수행하는 기능 단위**다.

> Task는 무엇을 할지 선언하고, Module은 그 작업을 실제로 수행한다.
> 

```
Playbook
  ↓
Task
  ↓
Module
  ↓
패키지 설치 / 파일 복사 / 서비스 제어
```

### 3-1. Ad-hoc Command

---

- Ad-hoc Command는 **Playbook 없이 단일 작업을 즉시 실행하는 방식**이다.
- 터미널에서 Ansible 명령어 한 줄로 바로 Task를 실행하는 방식
- 점검이나 일회성 작업에 유용하고, 반복할 작업은 Playbook으로 남기는 것이 좋다.

```bash
ansible <대상> -m <모듈> -a "<모듈 옵션>"
ansible web -m ansible.builtin.shell -a "uptime"

ansible all -i inventory.yml -m ansible.builtin.ping
ansible web -i inventory.yml -m ansible.builtin.command -a "uname -a"
```

<aside>

Playbook
↓
여러 Task
↓
각 Task가 Module 실행
↓
Managed Node의 상태 변경

</aside>

### 3-2. FQCN

---

- FQCN(Fully Qualified Collection Name)은 **Module이나 Plugin의 소속 Collection까지 포함한 전체 이름**이다.
- 이 모듈이 정확히 어느 Collection에 들어있는지 모듈 전체 경로를 적는 이름

예:

```
ansible.builtin.copy
ansible.builtin.file
amazon.aws.ec2_instance
```

짧은 이름보다 출처가 명확하고 이름 충돌을 줄일 수 있다.

### 3-3. 주요 Builtin Module

---

#### command

- Shell을 거치지 않고 명령을 직접 실행한다.

```yaml
- name: Check Java version
  ansible.builtin.command:
    cmd: java -version
  changed_when: false
```

#### shell

- Pipe, Redirect, `&&` 등 Shell 기능이 필요할 때 사용한다.
- Shell 기능이 필요하지 않으면 `shell`보다 `command`를 우선한다.

```yaml
- name: Find errors
  ansible.builtin.shell:
    cmd: "grep ERROR /var/log/app.log | tail -n 20"
  changed_when: false
```

#### copy

- 완성된 정적 파일을 Managed Node에 복사한다.

```yaml
ansible.builtin.copy:
  src: files/app.conf
  dest: /etc/app/app.conf
```

#### file

- 파일/디렉터리/심볼릭 링크의 존재 여부, 권한, 소유자 등을 관리한다.

```yaml
ansible.builtin.file:
  path: /opt/app
  state: directory
  mode: '0755'
```

#### template

- Jinja2 Template과 Variable을 이용해 동적인 설정 파일을 생성한다.

```yaml
ansible.builtin.template:
  src: nginx.conf.j2
  dest: /etc/nginx/nginx.conf
```

#### package

- OS별 Package Manager를 추상화해 패키지 설치 상태를 관리한다.

```yaml
ansible.builtin.package:
  name: curl
  state: present
```

#### service / systemd_service

- 서비스의 시작, 중지, 재시작, 자동 실행 여부를 관리한다.

```yaml
ansible.builtin.service:
  name: nginx
  state: started
  enabled: true
```

### 3-4. Idempotency

---

멱등성은 **같은 작업을 여러 번 실행해도 이미 원하는 상태라면 추가 변경이 발생하지 않는 성질**이다.

```yaml
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
```

첫 실행은 `changed`, 이미 설치된 상태에서 다시 실행하면 `ok`가 된다.

Ansible에서는 Shell 명령을 그대로 옮기기보다 **서버가 어떤 상태여야 하는지** Module로 표현하는 것이 중요하다.

### 3-5. ok / changed / failed / unreachable → 모듈의 응답

---

- **ok**: 성공, 변경 없음
- **changed**: 성공, 상태 변경 발생
- **failed**: Task 실행 실패
- **unreachable**: Host 연결 실패
- **skipped**: 조건 때문에 실행하지 않음

### 3-6. register / changed_when / failed_when

---

Task 결과를 저장하고 상태 판정을 조정할 때 사용한다.

- **register**: 실행 결과 저장
- **changed_when**: 변경 여부 기준 지정
- **failed_when**: 실패 여부 기준 지정

```yaml
- name: Check application
  ansible.builtin.command:
    cmd: systemctl is-active myapp
  register: app_status
  changed_when: false
  failed_when: app_status.stdout != 'active'
```

### 3-7. 멱등성 확인 실습

---

같은 Playbook을 연속 두 번 실행한다.

```bash
ansible-playbook -i inventory.yml setup.yml
ansible-playbook -i inventory.yml setup.yml
```

두 번째 실행에서도 불필요한 `changed`가 발생하면 다음을 확인한다.

### 3-8. 여기서 생각해볼 질문

---

1. Task와 Module의 차이는?
2. `command`와 `shell`은 언제 구분해 사용하는가?
3. 멱등성이 중요한 이유는?
    - 모듈이 태스크를 실행하는데 멱등성이 지켜지지 않으면 같은 작업이 중복적으로 이루어질 수 있기 때문에
4. 두 번째 실행에서도 `changed`가 발생한다면 무엇을 확인할까?
5. `changed_when`과 `failed_when`은 왜 필요한가?

### 3-9. 참고 자료

---

- [Ansible Builtin Collection](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/)
- [Ansible command Module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/command_module.html)
- [Ansible shell Module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/shell_module.html)
- [Ansible Error Handling](https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_error_handling.html)