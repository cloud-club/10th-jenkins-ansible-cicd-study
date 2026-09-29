# Role-Based Architecture

## 실습 환경

Docker 컨테이너를 Managed Node로 구성했다. 4주차 환경을 이어받되 키 인증 전용으로 바꿨다.

| 그룹 | 호스트 | 역할 |
|---|---|---|
| web | node1, node2 (이후 node4, node5 추가) | nginx |
| lb | node3 | haproxy |

- 비밀번호 로그인을 막고(`PasswordAuthentication no`) 공개키를 이미지에 넣었다. 컨테이너에서 `ssh -o PubkeyAuthentication=no`로 접속을 시도하면 비밀번호를 묻지 않고 `Permission denied (publickey)`로 거부된다.
- 컨테이너를 같은 네트워크(`ansible-lab`)에 묶어 컨테이너 이름으로 서로를 찾게 했다. haproxy가 backend를 컨테이너 이름으로 참조하기 위해서다.
- `ansible.cfg`에 `profile_tasks` 콜백을 켜서 task별 소요 시간을 측정한다.

## Role 구조

`ansible-galaxy role init`으로 표준 구조를 생성했다.

```
$ ansible-galaxy role init --init-path roles webapp
roles/webapp
├── defaults/main.yml
├── files/
├── handlers/main.yml
├── meta/main.yml
├── README.md
├── tasks/main.yml
├── templates/
├── tests/
│   ├── inventory
│   └── test.yml
└── vars/main.yml
```

계획표에 나온 7개 디렉터리(`tasks`, `handlers`, `templates`, `defaults`, `vars`, `files`, `meta`) 외에 `tests/`와 `README.md`가 함께 생성된다. `tests/`는 Role을 단독으로 테스트할 때 쓰는 디렉터리다.

Role 세 개로 나눴다.

- **common**: apt 캐시 갱신. 모든 서버 공통 작업.
- **webapp**: nginx 설치, 정적 설정(`files/`), 버전이 찍히는 페이지(`templates/`).
- **haproxy**: 인벤토리의 web 그룹을 읽어 backend를 구성.

webapp과 haproxy는 `meta/main.yml`에 common을 의존성으로 걸었다.

```yaml
# roles/webapp/meta/main.yml
dependencies:
  - role: common
```

### meta 의존성 동작

`site.yml`에는 common을 직접 넣지 않았다.

```yaml
- name: Web servers
  hosts: web
  roles:
    - webapp
- name: Load balancer
  hosts: lb
  roles:
    - haproxy
```

실행 결과 두 play 모두에서 `common : Update apt cache`가 각 Role의 첫 task보다 먼저 실행됐다. `meta/`에 선언한 의존 Role이 자동으로 앞에 실행된다.

### template validate

haproxy 설정 배포 task에 `validate`를 걸었다.

```yaml
- name: Deploy haproxy config
  ansible.builtin.template:
    src: haproxy.cfg.j2
    dest: /etc/haproxy/haproxy.cfg
    mode: "0644"
    validate: haproxy -c -f %s
  notify: Reload haproxy
```

`validate`는 파일을 목적지에 배치하기 전에 문법 검사를 먼저 실행한다. 검사에 실패하면 파일이 교체되지 않는다.

## 실습 중 발생한 문제 — 소켓 디렉터리 멱등성

haproxy Role 초기 버전에 `/run/haproxy` 디렉터리를 만드는 task를 넣었다.

```yaml
- name: Ensure socket directory exists
  ansible.builtin.file:
    path: /run/haproxy
    state: directory
    mode: "0755"
```

playbook을 반복 실행하니 이 task만 간헐적으로 `changed`가 떴다. 설정을 바꾸지 않았는데도 바뀌는 것이라 원인을 확인했다.

`stat`으로 보니 소유자와 권한이 `haproxy:haproxy 2775`였다. Role에는 owner를 지정하지 않았으므로 다른 주체가 바꾼 것이다. haproxy 시작 스크립트를 확인했다.

```
$ grep -nE 'chmod|chown|mkdir' /etc/init.d/haproxy
45: [ -d "$RUNDIR" ] || mkdir "$RUNDIR"
46: chown haproxy:haproxy "$RUNDIR"
47: chmod 2775 "$RUNDIR"
```

haproxy가 시작될 때마다 시작 스크립트가 `/run/haproxy`를 `haproxy:haproxy 2775`로 맞춘다. Ansible task는 다음 실행 때 mode를 `0755`로 되돌린다. `--diff`로 확인했다.

```
--- before
+++ after
@@ -1,4 +1,4 @@
-    "mode": "02775",
+    "mode": "0755",
     "path": "/run/haproxy"
```

즉 **haproxy가 재시작될 때마다** 다음 실행이 `changed`가 된다. 단순 재실행에서는 재시작이 없어 `ok`로 끝났기 때문에 "매번" 깨지는 것이 아니라 "재시작할 때마다" 깨지는 것이었다.

이 task는 멱등성만 깬 것이 아니라 패키지가 의도한 setgid 비트(`2`)와 그룹 쓰기 권한도 지우고 있었다. 같은 리소스를 패키지와 Ansible이 함께 관리하면 결과가 흔들리고, 한쪽의 설정을 다른 쪽이 덮어쓴다.

디렉터리는 haproxy 패키지가 관리하는 자원이므로 task를 제거했다. 제거 후 재실행은 모두 `changed=0`이 됐다.

## 실험 A — 변수 우선순위

`app_version` 하나를 네 위치에 두고 curl로 실제 적용값을 확인했다. 각 단계에서 이전 위치의 값은 그대로 둔 채 상위 위치를 추가했다.

| 단계 | 위치 | curl 결과 |
|---|---|---|
| 1 | `roles/webapp/defaults/main.yml` (1.0) | v1.0 |
| 2 | `group_vars/web/vars.yml` (2.0) 추가 | v2.0 |
| 3 | `roles/webapp/vars/main.yml` (3.0) 추가 | v3.0 |
| 4 | `-e app_version=4.0` | v4.0 |
| 복구 | vars 비우고 group_vars 삭제 | v1.0 |

정리:

- `defaults/`의 값은 `group_vars`로 덮어쓸 수 있다. 사용자가 바꿔도 되는 기본값이다.
- `vars/`의 값은 `group_vars`로 덮어쓸 수 없다. 인벤토리를 관리하는 사람이 바꿀 수 없고, Role 코드를 고치거나 `-e`를 써야 한다.
- `-e`(extra vars)는 `vars/`까지 포함해 모든 위치를 이긴다.

3단계와 4단계는 이후 실습과 연결된다. Jenkins 파라미터를 `-e`로 넘기면 Role의 `vars/`에 고정한 값까지 덮어쓴다는 뜻이다.

정적 파일(index, health)은 nginx reload 없이 curl에 바로 반영됐다. nginx는 매 요청마다 디스크에서 정적 파일을 읽으므로 reload가 필요 없다. handler는 설정 파일(`default.conf`)에만 붙였다.

## 실험 B — import_role과 include_role

같은 Role을 `import_role`, `include_role`, `include_role` + `apply`로 불러 비교했다. 세 playbook 모두 `tags: deploy`를 붙였다.

### `--list-tasks`

```
# import_test.yml
play #1 (web): import_role test
    common : Update apt cache        TAGS: [deploy]
    webapp : Install nginx           TAGS: [deploy]
    webapp : Deploy site config      TAGS: [deploy]
    webapp : Deploy index page       TAGS: [deploy]
    webapp : Deploy health file      TAGS: [deploy]
    webapp : Ensure nginx is running TAGS: [deploy]

# include_test.yml
play #1 (web): include_role test
    Include webapp                   TAGS: [deploy]
```

import는 Role 내부 task 6개가 모두 나열되고 각 task에 `[deploy]` 태그가 붙는다. include는 `Include webapp` 한 줄만 나온다. import는 playbook을 읽는 시점(파싱)에 Role을 펼쳐 넣고, include는 실행 시점에 내용을 가져오기 때문이다.

### `--tags deploy` 실행

| 방식 | 결과 |
|---|---|
| import | 내부 task 6개 전부 실행 |
| include | `ok=1`, 내부 task 0개 실행 |
| include + apply | 내부 task 전부 실행 |

include는 `included: webapp for node1, node2`까지 로그에 찍히고 `failed=0`으로 끝나지만, 내부 task는 태그가 없어 하나도 실행되지 않는다. 에러 없이 성공한 것처럼 보이지만 실제로는 아무것도 배포하지 않는다.

`include_role`에 태그를 함께 쓸 때는 `apply`로 태그를 내부 task에 명시적으로 전달해야 한다.

```yaml
- name: Include webapp
  ansible.builtin.include_role:
    name: webapp
    apply:
      tags: deploy
  tags: deploy
```

이 문제는 5주차 Jenkins 파라미터(`--tags`)와 연결된다. 파라미터로 태그를 넘기는 파이프라인에서 이 구조가 생기면 빌드는 성공하는데 배포는 0건이 된다.

## Galaxy와 requirements.yml

haproxy 모듈을 쓰려면 `community.general` 컬렉션이 필요하다. brew로 설치한 ansible 패키지에는 이미 포함되어 있어, 이번에는 "설치"보다 "프로젝트가 어떤 버전을 쓸지 스스로 정하게 만들기"와 "설치된 코드의 변조 검증"에 초점을 뒀다.

```yaml
# requirements.yml
collections:
  - name: community.general
    version: ">=9.0.0"
roles:
  - name: geerlingguy.haproxy
```

### 버전 범위와 실제 설치본

처음 `-p ./collections`로 설치하니 `Nothing to do. All requested collections are already installed`가 나왔다. 범위 조건(`>=9.0.0`)을 brew가 설치한 13.4.0이 만족해 새로 받지 않은 것이다. 이 상태에서 `collection list`는 brew 경로 하나만 보여줬다.

버전 범위만 적어두면 실제로 실행될 버전은 프로젝트가 아니라 그 머신에 설치된 것으로 정해진다. 같은 playbook이 환경에 따라 다른 코드로 실행될 수 있다.

`--force`로 프로젝트 전용 경로에 다시 설치하니 두 경로가 모두 나오고, `collections_path`에 지정한 `./collections`가 먼저 나왔다. 경로 순서로 우선순위가 정해진다.

```
# /Users/shanks/ansible-week5/collections/ansible_collections
community.general 13.4.0
# /opt/homebrew/.../ansible_collections
community.general 13.4.0
```

의존성 하나(`community.library_inventory_filtering_v1`)는 `already installed, skipping`으로 brew 경로 것을 그대로 썼다. 본체는 프로젝트 것, 의존성은 시스템 것이 섞였다. 완전히 분리하려면 `--force-with-deps`가 필요하다.

### 변조 검증

외부 Role과 Collection은 모든 서버에서 root 권한으로 실행되므로 받은 코드가 원본 그대로인지 확인이 필요하다. `ansible-galaxy collection verify`로 검사했다.

- **brew 설치본**: 수백 개 파일이 "modified content"로 나왔다. `tests/`, `docs/`, `.github/` 같은 개발용 파일이 전부 목록에 있었다. brew가 쓰는 배포판이 컬렉션을 묶을 때 이런 파일을 제외하고 포장해서, Galaxy 원본과 비교하면 파일이 없어 "다르다"고 나오는 것으로 보인다(원인 추정).
- **Galaxy 원본**: `Successfully verified`로 통과했다.
- **변조 후**: `plugins/modules/haproxy.py`에 한 줄을 추가하니 그 파일 하나만 목록에 잡혔다.

```
Collection community.general contains modified content in the following files:
    plugins/modules/haproxy.py
```

- **재설치 후**: 다시 통과했다.

같은 13.4.0인데 brew 설치본은 경고 수백 줄, Galaxy 설치본은 통과였다. 버전 번호가 같아도 같은 파일 구성이 아니다. 검증 도구가 경고를 대량으로 내면 그 안에 진짜 변조가 섞여도 찾기 어렵다.

verify의 한계 두 가지:

- verify는 사람이 직접 실행해야 동작한다. `ansible-playbook`은 실행 전에 자동으로 검사하지 않는다. 변조된 모듈도 그대로 실행된다.
- 기준은 Galaxy 원본이다. Galaxy에 올라간 파일 자체가 오염됐다면 verify는 통과한다. 이를 막는 것이 서명 검증(`--keyring`)이다.

### 직접 만든 Role과 Galaxy Role 비교

`geerlingguy.haproxy`(1.3.2)를 받아 직접 만든 Role과 비교했다.

| 항목 | 직접 만든 Role | geerlingguy.haproxy |
|---|---|---|
| backend 서버 목록 | `groups['web']`에서 자동 생성 | `haproxy_backend_servers` 리스트를 호출부가 전달 |
| 헬스체크 | `GET /health` 고정 | `haproxy_backend_httpchk` 변수 |
| 템플릿 | 고정 | `haproxy_template` 변수로 교체 가능 |
| 타임아웃·소켓·chroot | 템플릿에 하드코딩 | 전부 defaults로 열어둠 |
| 변수 이름 | 일부만 `haproxy_` 접두사 | 전부 `haproxy_` 접두사 |

직접 만든 Role은 이 인벤토리 구조를 전제로 해서 편하지만 다른 환경에서는 쓰기 어렵다. Galaxy Role은 어떤 환경에서 쓰일지 모르므로 거의 모든 값을 defaults로 열어뒀다. 재사용을 전제로 하면 defaults가 두꺼워진다. 소켓 위치도 배포판마다 달라 변수로 빼두었다(`/var/lib/haproxy/stats`).

## 참고 자료

- [Ansible - Roles](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_reuse_roles.html)
- [Ansible - Using variables (precedence)](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_variables.html#variable-precedence-where-should-i-put-a-variable)
- [Ansible Galaxy - requirements.yml](https://docs.ansible.com/ansible/latest/galaxy/user_guide.html)
