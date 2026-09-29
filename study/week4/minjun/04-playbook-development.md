# Playbook Development

## 구조

Playbook은 Play → Task → Module 계층으로 구성된다.

- **Play**: 어떤 호스트 그룹에 무엇을 할지 정의하는 단위
- **Task**: Play 안의 개별 작업. 모듈 하나를 호출한다
- **Module**: 실제 실행되는 코드

## 실행 순서

한 Play 안에서 섹션이 실행되는 순서는 다음과 같다.

```
Gathering Facts
  ↓
pre_tasks
  ↓  (pre_tasks가 notify한 handler 실행)
roles
  ↓
tasks
  ↓
handlers        ← tasks가 notify한 handler
  ↓
post_tasks
```

## 실습 Playbook

이번 주 주제를 한 파일에 모아 실행했다.

```yaml
- name: Playbook Development 실습
  hosts: webservers
  vars:
    packages: [ curl, vim ]

  pre_tasks:
    - name: pre_tasks는 가장 먼저
      ansible.builtin.debug: { msg: "PRE" }

  tasks:
    - name: loop으로 패키지 설치
      ansible.builtin.apt:
        name: "{{ item }}"
        state: present
      loop: "{{ packages }}"

    - name: register로 명령 결과 저장
      ansible.builtin.command: uname -r
      register: kernel_result
      changed_when: false

    - name: register 결과 사용
      ansible.builtin.debug:
        msg: "커널: {{ kernel_result.stdout }}"

    - name: 설정 파일 배포 (변경 시 handler 호출)
      ansible.builtin.copy:
        content: "config version 1\n"
        dest: /etc/myapp.conf
        mode: '0644'
      notify: restart myapp

    - name: block / rescue / always
      block:
        - name: 실패하는 태스크
          ansible.builtin.command: /bin/false
      rescue:
        - name: 복구 태스크
          ansible.builtin.debug: { msg: "rescue 블록 실행됨" }
      always:
        - name: 항상 실행
          ansible.builtin.debug: { msg: "always 블록 실행됨" }

    - name: 태그가 붙은 태스크
      ansible.builtin.debug: { msg: "이건 태그로만 실행됩니다" }
      tags: [ manual ]

  post_tasks:
    - name: post_tasks는 마지막
      ansible.builtin.debug: { msg: "POST" }

  handlers:
    - name: restart myapp
      ansible.builtin.debug: { msg: "handler 실행 — 설정이 바뀌었을 때만" }
```

---

## 1. `loop` — 반복

```
TASK [loop으로 패키지 설치]
changed: [node1] => (item=curl)
changed: [node2] => (item=curl)
changed: [node1] => (item=vim)
changed: [node2] => (item=vim)
```

`item` 변수로 각 요소에 접근한다. 리스트뿐 아니라 딕셔너리 목록도 순회할 수 있다.

```yaml
loop:
  - { name: app1, port: 8080 }
  - { name: app2, port: 8081 }
```

`loop_control`로 `item` 대신 다른 변수명을 쓰거나(`loop_var`), 출력에 표시될 라벨을 지정할 수 있다(`label`). 비밀번호가 포함된 항목을 순회할 때 `label`로 표시 내용을 제한하는 용도로도 쓴다.

## 2. `register` — 결과 저장

```yaml
- ansible.builtin.command: uname -r
  register: kernel_result
  changed_when: false

- ansible.builtin.debug:
    msg: "커널: {{ kernel_result.stdout }}"
```

```
ok: [node1] => { "msg": "커널: 7.0.12-linuxkit" }
```

`register`로 저장한 객체에는 `stdout`, `stderr`, `rc`, `changed`, `failed` 등이 들어 있다. 이후 태스크의 `when` 조건이나 출력에 활용한다.

```yaml
when: kernel_result.stdout is search('linuxkit')
```

`loop`과 함께 쓰면 `results` 배열에 각 회차의 결과가 담긴다.

## 3. `notify` / `handlers` — 변경 기반 실행 ★

이번 실습의 핵심이다. **첫 실행과 두 번째 실행을 비교하면 동작이 명확히 드러난다.**

### 첫 실행

```
TASK [설정 파일 배포 (변경 시 handler 호출)]
changed: [node1]
changed: [node2]
...
RUNNING HANDLER [restart myapp]
ok: [node1] => { "msg": "handler 실행 — 설정이 바뀌었을 때만" }
ok: [node2] => { "msg": "handler 실행 — 설정이 바뀌었을 때만" }

TASK [post_tasks는 마지막]
```

### 두 번째 실행

```
TASK [설정 파일 배포 (변경 시 handler 호출)]
ok: [node1]
ok: [node2]
...
TASK [태그가 붙은 태스크]
...
TASK [post_tasks는 마지막]
```

**`RUNNING HANDLER` 줄이 아예 없다.**

### 해석

- 파일 내용이 이미 원하는 상태라 태스크가 `ok`로 끝났고, `changed`가 아니므로 `notify`가 발동하지 않았다.
- handler는 **호출되지 않은 것이 아니라 실행 목록에 아예 오르지 않았다.**
- 실행 위치도 확인됐다. handler는 모든 `tasks`가 끝난 뒤, **`post_tasks`보다 먼저** 실행된다.

### 실무 패턴

```yaml
- name: nginx 설정 배포
  ansible.builtin.template:
    src: nginx.conf.j2
    dest: /etc/nginx/nginx.conf
  notify: reload nginx

handlers:
  - name: reload nginx
    ansible.builtin.systemd:
      name: nginx
      state: reloaded
```

설정이 바뀔 때만 nginx를 reload한다. 매번 reload하면 불필요한 서비스 중단이 생기므로, 변경 여부를 판단 근거로 삼는 것이다.

여러 태스크가 같은 handler를 notify해도 **handler는 한 번만 실행된다.** 중복 재시작을 막는다.

Playbook이 중간에 실패하면 예약된 handler가 실행되지 않을 수 있다. `--force-handlers` 옵션으로 강제할 수 있다.

## 4. `block` / `rescue` / `always` — 예외 처리

```
TASK [실패하는 태스크]
fatal: [node1]: FAILED! => {"changed": true, "cmd": ["/bin/false"], "rc": 1, ...}

TASK [복구 태스크]
ok: [node1] => { "msg": "rescue 블록 실행됨" }

TASK [항상 실행]
ok: [node1] => { "msg": "always 블록 실행됨" }

PLAY RECAP
node1 : ok=11  changed=2  failed=0  rescued=1  ignored=0
```

### 해석

`fatal: FAILED!`가 찍혔는데 최종 집계는 **`failed=0`, `rescued=1`**이다. `rescue`가 처리했으므로 Playbook 전체는 실패로 보지 않는다.

| 블록 | 실행 조건 |
|---|---|
| `block` | 항상 시도 |
| `rescue` | `block` 안에서 실패가 발생했을 때만 |
| `always` | 결과와 무관하게 항상 |

`rescue` 안에서는 `ansible_failed_task`, `ansible_failed_result` 변수로 실패 정보에 접근할 수 있다.

### Jenkins와의 비교

3주차에 확인한 `catchError`와 목적이 같다. 실패를 잡아서 흐름을 이어가는 장치다.

| | Jenkins `catchError` | Ansible `block/rescue` |
|---|---|---|
| 실패 처리 | 빌드 결과만 낮추고 진행 | `rescue` 블록으로 분기 |
| 집계 | `UNSTABLE` 상태 | `rescued` 카운터 |
| 복구 로직 | 별도 작성 필요 | `rescue` 안에 직접 |

Ansible 쪽이 **복구 절차를 구조적으로 표현**한다는 점이 다르다. 배포 실패 시 롤백 같은 흐름을 그대로 담을 수 있다.

### `ignore_errors`와의 차이

01번 문서의 `become` 실습에서는 `ignore_errors: yes`를 썼고 집계가 `ignored=1`이었다.

| 방식 | 집계 | 동작 |
|---|---|---|
| `ignore_errors: yes` | `ignored` | 실패를 무시하고 다음 태스크로 |
| `block/rescue` | `rescued` | 실패를 받아서 복구 로직 실행 |

`ignore_errors`는 실패를 그냥 넘기는 것이고, `rescue`는 실패에 대응하는 것이다. 카운터를 분리해두면 Playbook 실행 결과만 보고도 어떤 종류의 예외가 있었는지 구분할 수 있다.

## 5. `pre_tasks` / `post_tasks`

```
TASK [pre_tasks는 가장 먼저]   → PRE
...
TASK [post_tasks는 마지막]     → POST
```

주로 쓰는 용도는 다음과 같다.

- `pre_tasks`: 배포 전 로드밸런서에서 해당 서버 제외, 사전 조건 검증
- `post_tasks`: 배포 후 헬스체크, 로드밸런서에 재등록

`roles`와 함께 쓸 때 실행 순서를 보장하기 위한 장치다. 단순 Playbook에서는 `tasks`만으로 충분하다.

## 6. `tags` — 선택적 실행

```bash
ansible-playbook -i inventory.ini week4-playbook.yml --tags manual
```

```
TASK [Gathering Facts]      ok: [node1] ok: [node2]
TASK [태그가 붙은 태스크]    ok: [node1] ok: [node2]

PLAY RECAP
node1 : ok=2  changed=0
```

전체 10개 태스크 중 `manual` 태그가 붙은 1개만 실행됐다(`Gathering Facts` 포함 `ok=2`).

| 옵션 | 동작 |
|---|---|
| `--tags <태그>` | 해당 태그만 실행 |
| `--skip-tags <태그>` | 해당 태그만 제외 |
| `--list-tags` | 정의된 태그 목록 확인 |
| `always` (예약 태그) | 태그 지정과 무관하게 항상 실행 |
| `never` (예약 태그) | 명시적으로 지정해야만 실행 |

긴 Playbook에서 특정 부분만 재실행할 때 쓴다. 예를 들어 설정 배포만 다시 하고 패키지 설치는 건너뛰는 경우다.

## 7. `--limit` — 대상 제한

```bash
ansible-playbook -i inventory.ini week4-playbook.yml --limit node1
```

```
PLAY RECAP
node1 : ok=10  changed=0  failed=0  rescued=1
```

node2가 아예 나타나지 않았다. Playbook의 `hosts: webservers`를 명령줄에서 더 좁힌 것이다.

### 주의

`--limit`과 Playbook의 `hosts:`는 다른 층위다.

- `hosts: webservers` → Play 대상이 node1, node2 (node3은 애초에 제외)
- `--limit node1` → 그중에서 다시 node1만

이번 실습에서 node3이 한 번도 나타나지 않은 것은 `--limit` 때문이 아니라 `hosts: webservers` 때문이다. 두 가지를 혼동하면 "왜 이 서버에 안 적용됐지"를 잘못 진단하게 된다.

### 운영 활용

```bash
# 1. 한 대만 먼저 적용해 확인
ansible-playbook -i inventory.ini deploy.yml --limit node1

# 2. 문제없으면 전체
ansible-playbook -i inventory.ini deploy.yml
```

카나리 방식이다. `--check`와 조합하면 한 대에 대해 변경 예정 내용만 미리 볼 수도 있다(05번 문서).

## 정리

| 기능 | 로그에서 확인한 것 |
|---|---|
| `loop` | `(item=curl)`, `(item=vim)`로 회차별 표시 |
| `register` | 명령 출력을 후속 태스크에서 사용 |
| `handlers` | 변경 없으면 `RUNNING HANDLER` 줄 자체가 없음 |
| `block/rescue` | `fatal` 표시되지만 `failed=0, rescued=1` |
| `pre/post_tasks` | PRE → tasks → handlers → POST |
| `tags` | 10개 중 1개만 실행 |
| `--limit` | node2가 집계에서 제외 |

## 참고 자료

- [Ansible 공식 문서 - Intro to playbooks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_intro.html)
- [Ansible 공식 문서 - Handlers: running operations on change](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_handlers.html)
- [Ansible 공식 문서 - Blocks](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_blocks.html)
- [Ansible 공식 문서 - Tags](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_tags.html)
- [Ansible 공식 문서 - Loops](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_loops.html)
