# Modules & Idempotency

## Module

Ansible이 대상 서버로 전송해 실행하는 코드 단위다. 대부분의 모듈은 **원하는 상태(state)를 선언**하면 현재 상태와 비교해 필요한 경우에만 변경을 수행한다.

`apt`에 `state: present`라고 쓰는 것은 "설치해라"가 아니라 "설치된 상태여야 한다"는 뜻이다.

## Ad-hoc Command

Playbook 없이 모듈을 즉시 실행한다. 일회성 확인이나 긴급 조치에 쓴다.

```bash
ansible all -i inventory.ini -m ping
ansible webservers -i inventory.ini -m command -a "uptime"
ansible all -i inventory.ini -m setup            # 수집된 fact 전체 확인
```

```
node1 | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

## 주요 모듈

| 모듈 | 용도 |
|---|---|
| `ansible.builtin.command` | 명령 실행. 셸 해석 없음 |
| `ansible.builtin.shell` | 셸을 거쳐 실행. 파이프·리다이렉션 가능 |
| `ansible.builtin.copy` | 파일 배포. `content:`로 내용 직접 지정 가능 |
| `ansible.builtin.template` | Jinja2 렌더링 후 배포 (05번 문서) |
| `ansible.builtin.file` | 파일·디렉터리 생성, 권한·소유자 설정 |
| `ansible.builtin.package` | OS 무관 패키지 관리 |
| `ansible.builtin.apt` / `yum` | 배포판별 패키지 관리 |
| `ansible.builtin.service` / `systemd` | 서비스 제어 |
| `ansible.builtin.user` | 계정 관리 |
| `ansible.builtin.debug` | 변수·메시지 출력 |

`command`와 `shell`의 차이는 셸 해석 여부다. `command`는 `|`, `>`, `&&` 같은 셸 메타문자를 처리하지 못한다. 필요 없다면 `command`가 안전하다.

## FQCN (Fully Qualified Collection Name)

Ansible 2.10부터 모듈이 **Collection** 단위로 재편되면서, 모듈의 정식 이름은 `<네임스페이스>.<컬렉션>.<모듈>` 형태가 됐다.

| 짧은 이름 | FQCN |
|---|---|
| `copy` | `ansible.builtin.copy` |
| `apt` | `ansible.builtin.apt` |
| `ec2_instance` | `amazon.aws.ec2_instance` |
| `docker_container` | `community.docker.docker_container` |

짧은 이름도 여전히 동작하지만 FQCN을 쓰는 것이 권장된다.

- 서로 다른 컬렉션에 같은 이름의 모듈이 있을 때 **어느 것인지 명확해진다.**
- 커스텀 모듈이나 로컬 플러그인이 내장 모듈 이름을 가리는 사고를 막는다.
- `ansible-lint`가 FQCN 사용을 권고 규칙으로 검사한다.

이번 주 실습은 전부 FQCN으로 작성했다. 3주차 문서는 짧은 이름을 썼는데, 같은 모듈이라도 표기가 달라지면 검색이 어려워지므로 통일하는 편이 낫다.

---

## Idempotency (멱등성)

같은 작업을 여러 번 실행해도 결과 상태가 동일한 성질이다.

셸 스크립트와의 차이가 여기서 드러난다. `apt install nginx`를 두 번 실행하는 스크립트는 두 번 설치를 시도하지만, Ansible의 `apt` 모듈은 이미 설치되어 있으면 아무 작업도 하지 않는다.

### 실행 결과 상태

| 표시 | 의미 |
|---|---|
| `ok` | 확인했고 변경할 것이 없었다 |
| `changed` | 실제로 변경했다 |
| `failed` | 실패 |
| `skipped` | 조건에 맞지 않아 건너뜀 |
| `rescued` | 실패했으나 `rescue` 블록이 처리함 |
| `ignored` | 실패했으나 `ignore_errors`로 무시됨 |

`rescued`와 `ignored`는 `failed`와 별도로 집계된다. 둘 다 "실패가 있었지만 Playbook은 성공"인 상태를 구분해 기록한다.

### 실습: 동일 Playbook 반복 실행

```yaml
- name: 패키지 목록 갱신
  ansible.builtin.apt: { update_cache: yes }
- name: nginx 설치
  ansible.builtin.apt: { name: nginx, state: present }
- name: 디렉터리 생성
  ansible.builtin.file: { path: "{{ app_dir }}", state: directory, mode: '0755' }
- name: 파일 배포
  ansible.builtin.copy: { content: "...", dest: "{{ app_dir }}/index.html" }
- name: 멱등하지 않은 예
  ansible.builtin.command: echo "always changed"
```

두 번째 실행 결과:

```
TASK [패키지 목록 갱신]     ok: [node1] ok: [node2]
TASK [nginx 설치]           ok: [node1] ok: [node2]
TASK [디렉터리 생성]        ok: [node1] ok: [node2]
TASK [파일 배포]            ok: [node1] ok: [node2]
TASK [멱등하지 않은 예]     changed: [node1] changed: [node2]

PLAY RECAP
node1 : ok=6  changed=1  unreachable=0  failed=0
```

### 해석

- `apt`, `file`, `copy`는 모두 `ok`로 끝났다. 이미 원하는 상태이므로 아무 작업도 하지 않았다.
- `command`만 `changed`로 표시됐다. **Ansible은 임의 명령이 시스템에 어떤 영향을 주는지 알 수 없으므로, 실행했다는 사실만으로 변경으로 간주한다.**
- 즉 **멱등성은 Ansible 자체의 성질이 아니라 모듈이 제공하는 성질**이다. `command`나 `shell`을 쓰는 순간 그 보장은 사라진다.

---

## `changed_when` / `failed_when`

위 결론에는 단서가 붙는다. 모듈이 멱등성을 주지 못하면 **사람이 선언할 수 있다.**

| 지시어 | 역할 |
|---|---|
| `changed_when` | 어떤 조건일 때 `changed`로 볼지 직접 지정 |
| `failed_when` | 어떤 조건일 때 실패로 볼지 직접 지정 |

### 실습

```yaml
- name: register로 명령 결과 저장
  ansible.builtin.command: uname -r
  register: kernel_result
  changed_when: false
```

결과:

```
TASK [register로 명령 결과 저장]
ok: [node1]
ok: [node2]
```

`command` 모듈인데 `changed`가 아니라 **`ok`로 표시됐다.**

`uname -r`은 조회만 하는 명령이므로 상태를 바꾸지 않는다. 그런데 Ansible은 `command`를 항상 변경으로 간주하기 때문에, `changed_when: false`로 "이 태스크는 변경이 아니다"라고 선언한 것이다.

### 응용

출력 내용으로 판단하게 할 수도 있다.

```yaml
- name: 배포 스크립트 실행
  ansible.builtin.command: ./deploy.sh
  register: result
  changed_when: "'Updated' in result.stdout"
  failed_when: result.rc != 0 and 'already exists' not in result.stderr
```

- `changed_when`: 출력에 `Updated`가 있을 때만 변경으로 집계
- `failed_when`: 종료 코드가 0이 아니어도 특정 메시지면 실패로 보지 않음

### 정리

3주차에 "`command`는 항상 `changed`로 잡힌다"고 정리했는데, 정확히는 **기본값이 그렇다**는 것이다. `changed_when`으로 제어할 수 있다.

따라서 멱등성은 세 층으로 나뉜다.

| 층 | 예 |
|---|---|
| 모듈이 보장 | `apt`, `file`, `copy` |
| 사람이 선언 | `command` + `changed_when` |
| 보장 없음 | `command`, `shell` 그대로 |

`command`/`shell`을 꼭 써야 한다면 `creates:`(해당 파일이 있으면 실행 안 함), `removes:`(없으면 실행 안 함) 옵션으로도 멱등성을 부여할 수 있다.

```yaml
- name: 압축 해제 (이미 풀려 있으면 건너뜀)
  ansible.builtin.command: tar xzf /tmp/app.tar.gz -C /opt
  args:
    creates: /opt/app/bin/start.sh
```

## 실무적 함의

- `changed` 개수는 배포 후 확인 지표가 된다. 아무것도 바뀌지 않아야 할 상황에서 `changed`가 나오면 설정 드리프트가 있다는 신호다.
- 반대로 `changed`가 항상 나오는 태스크는 이 지표를 무의미하게 만든다. `command`에 `changed_when`을 붙이는 이유가 여기에 있다.
- `--check` 모드로 실제 변경 없이 무엇이 바뀔지 미리 확인할 수 있다(05번 문서).

## 참고 자료

- [Ansible 공식 문서 - Desired state and idempotency](https://docs.ansible.com/ansible/latest/getting_started/basic_concepts.html)
- [Ansible 공식 문서 - Module Index](https://docs.ansible.com/ansible/latest/collections/index_module.html)
- [Ansible 공식 문서 - Using collections](https://docs.ansible.com/ansible/latest/collections_guide/collections_using_playbooks.html)
- [Ansible 공식 문서 - Defining failure](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_error_handling.html)
