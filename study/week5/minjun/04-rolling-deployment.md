# Rolling Deployment & Failure Handling

## web 서버 4대 확장

web 서버가 2대면 canary(1대 먼저)와 일반 롤링(`serial: 1`)을 구별할 수 없고 `max_fail_percentage`도 50% 한 경우만 볼 수 있다. node4, node5를 추가해 web 4대로 늘렸다. haproxy 템플릿이 `groups['web']`에서 backend 목록을 만들므로 인벤토리에 두 줄만 추가해도 LB에 서버가 자동으로 들어간다.

## 롤링 배포 흐름

한 번에 한 대씩(`serial: 1`) 진행한다. 흐름은 LB에서 제외 → 배포 → 헬스체크 → LB 복귀다.

```yaml
serial: 1
max_fail_percentage: 0
pre_tasks:
  - name: Disable in LB
    community.general.haproxy:
      state: disabled
      host: "{{ inventory_hostname }}"
      backend: "{{ lb_backend }}"
      socket: "{{ lb_socket }}"
    delegate_to: "{{ lb_host }}"
roles:
  - webapp
post_tasks:
  - name: Health check from LB
    ansible.builtin.uri:
      url: "http://{{ inventory_hostname }}/health"
      return_content: true
    register: health
    until: health.content is defined and health.content.strip() == 'ok ' ~ app_version
    retries: 5
    delay: 2
    delegate_to: "{{ lb_host }}"
  - name: Enable in LB
    community.general.haproxy:
      state: enabled
      wait: true
      ...
    delegate_to: "{{ lb_host }}"
```

- 헬스체크는 "살아 있나"가 아니라 "새 버전이 떴나"를 확인한다(`ok {{ app_version }}` 비교). `/health`가 버전을 돌려주게 만든 이유다.
- `wait: true`는 LB에 다시 넣은 뒤 haproxy 자체 헬스체크가 UP으로 판정할 때까지 기다린다.
- `max_fail_percentage: 0`은 한 대라도 실패하면 남은 배치를 진행하지 않는다.

## 무중단 확인 — 대조 실험

배포 중에 별도 터미널에서 계속 요청을 보내 응답을 기록했다.

v2.0 배포에서는 요청 실패(`FAIL`)가 0건이었다. 그러나 이 배포는 정적 파일만 바꿔 nginx가 재시작되지 않았으므로, LB에서 빼지 않았어도 에러가 0이었을 것이다. "무중단이었다"는 사실이지 "LB에서 빼서 무중단이었다"는 증거가 아니다.

실제 앱 배포는 대부분 프로세스 재시작을 동반한다. nginx를 멈추고 4초 뒤 다시 켜는 동작을 넣고, LB 제외를 켰을 때와 껐을 때를 비교했다. 감시 도구도 HTTP 상태 코드를 기록하게 바꿨다(이전 curl은 503 에러 페이지도 성공으로 봤다).

| | 조건 | 요청 수 | 에러 |
|---|---|---|---|
| B | 재시작 O, LB 제외 X | 117 | 10 |
| C | 재시작 O, LB 제외 O | 144 | 0 |

같은 재시작인데 LB 제외 단계 하나로 에러가 10건에서 0건이 됐다.

B에서 두 가지를 더 확인했다.

- 에러 코드가 503이 아니라 `000`이었다. curl이 1초 안에 응답을 못 받아 포기한 것이다. haproxy가 연결이 거부된 서버에 재시도하며 시간을 쓰는 것으로 보인다(원인 추정). 사용자 입장에서는 멈춘 것처럼 보이는 장애다.
- B의 playbook은 `failed=0`으로 성공했다. 재시작이 4초 만에 끝나 헬스체크 시점에는 정상이었기 때문이다. 배포 도구는 성공이라 보고했는데 사용자는 10번 실패를 겪었다. 이 차이는 바깥에서 사용자처럼 요청을 보내는 감시 로그로만 보인다.

### `| bool` 함정

스위치 변수를 `-e skip_lb=false`로 넘기면 불리언이 아니라 문자열 `"false"`가 들어온다. 빈 문자열이 아니면 참으로 취급되므로 `| bool` 없이 쓰면 false를 넘겨도 참으로 동작한다. `when: not (skip_lb | bool)`처럼 `| bool`을 붙였다.

## Batch 크기와 Canary

`serial`을 명령줄에서 바꿀 수 있게 했다(`serial: "{{ batch | default(1) }}"`).

| | batch | 요청 수 | 에러 |
|---|---|---|---|
| D | `[1, "100%"]` (canary) | 86 | 0 |
| E | `100%` (전부 한꺼번에) | 52 | 38 (73%) |

- **D**: 1대를 먼저 배포하고 문제없으면 나머지 전부. 에러는 0이지만, 두 번째 배치 동안 node1 한 대만 응답한 구간이 있었다(단독 최장 연속 36회, 0.3초 간격이므로 약 11초간 용량 25%). 트래픽이 많은 서비스였다면 node1이 과부하로 쓰러질 수 있다.
- **E**: 네 대가 동시에 LB에서 빠져 요청의 73%가 실패했다. 그런데 playbook은 `failed=0`으로 성공을 보고했다. 무중단을 위한 LB 제외 절차도 batch 크기를 잘못 정하면 전면 장애의 원인이 된다.

## 실패 주입

버전이 `bad`면 `/health`가 `error`를 돌려주는 불량 버전을 만들었다. canary로 배포했다.

- node1이 헬스체크에서 5번 재시도한 뒤 실패했다.
- `max_fail_percentage: 0`이라 두 번째 배치(node2, node4, node5)는 시작도 하지 않았다(`NO MORE HOSTS LEFT`). 세 대는 이전 버전 그대로 남았다.
- node1은 `Enable in LB`까지 가지 못해 LB에서 빠진 채로 남았다(`MAINT`). 불량 버전이 사용자에게 한 번도 노출되지 않았다(감시 로그 에러 0, 응답 목록에 `bad` 없음). 대신 LB 용량은 3/4로 줄어든 채 남았다.

실패한 헬스체크 응답에서 확인한 점:

```
"content": "error\n", ... "status": 200, "url": "http://node1/health"
```

불량 버전이 HTTP 200으로 `error` 본문을 돌려줬다. 우리 헬스체크는 본문 내용까지 확인해 잡았지만, haproxy 자체 헬스체크(`option httpchk GET /health`)는 상태 코드만 본다. Ansible이 이 서버를 LB에 다시 넣었다면 haproxy는 node1을 정상으로 판정하고 불량 버전에 트래픽을 보냈을 것이다. 같은 `/health`를 보는 검사 두 개의 엄격도가 다르다.

## 자동 복구 (block/rescue)

헬스체크가 실패하면 이전 버전으로 되돌리고 LB에 다시 넣는 흐름을 만들었다. 여기서 두 함정을 실제로 겪었다.

1. **`-e`가 롤백까지 덮어쓴다.** 새 버전을 `-e app_version=bad`로 넘기면, 롤백에서 `app_version`을 이전 버전으로 지정해도 `-e`가 이겨 다시 bad를 배포한다. 이를 피하려고 새 버전은 `app_version`이 아니라 `target_version`으로 받게 했다.
2. **rescue는 실패 신호를 삼킨다.** rescue로 복구되면 그 호스트는 `failed`가 아니라 `rescued`로 기록된다. `max_fail_percentage`가 실패로 세지 않아 다음 배치로 계속 진행한다.

네 조건으로 실행했다.

| | 조건 | 불량 노출 | 최종 LB 용량 | 불량 배포 횟수 | RECAP |
|---|---|---|---|---|---|
| F | rescue 없음 | 0 | 3/4 | 1 | failed=1 |
| G | `-e app_version=bad` 함정 | 0 | 3/4, 복구 실패 | 2 | failed=1, rescued=1 |
| H | rescue만 (중단 없음) | 0 | 4/4 | 4 | failed=0, rescued=1 |
| I | rescue + 중단 | 0 | 4/4 | 1 | failed=1, rescued=1 |

**G**의 증거: 새 버전 헬스체크와 롤백 헬스체크의 응답 etag가 완전히 같았다.

```
"etag": "6ab8e84b-6", "last_modified": "Sun, 27 Sep 2026 09:56:27 GMT"   (배포 후)
"etag": "6ab8e84b-6", "last_modified": "Sun, 27 Sep 2026 09:56:27 GMT"   (롤백 후)
```

롤백이 파일을 한 글자도 바꾸지 않았다는 뜻이다. `-e app_version=bad`가 롤백의 `app_version` 지정을 이겨 롤백 template이 bad를 다시 렌더링했고, 내용이 같으니 파일을 건드리지 않았다. 롤백 절차는 실행됐는데 실제로는 아무 일도 하지 않았다.

**H**는 네 대 모두 `failed=0`이라 파이프라인이라면 초록불이 켜진다. 그런데 불량 버전을 네 번 배포하고 네 번 되돌렸다. 첫 서버에서 이미 알 수 있었던 실패를 전체에 반복했다.

**I**는 `failed=1, rescued=1`이다. 롤백은 성공했지만 배포 자체는 실패로 보고한다. 서비스는 원상태로 돌아가고(네 대 `UP`, `ok 6.0`) 파이프라인은 빨간불이 켜진다. 복구와 실패 보고를 둘 다 하는 구성이다.

## Blue-Green

서버를 두 묶음(blue: node1·node2 / green: node4·node5)으로 나누고, 쉬고 있는 쪽에 새 버전을 다 배포한 뒤 LB의 트래픽 방향만 한 번에 바꾼다. 활성 색은 LB의 실제 설정 파일에서 읽는다(기록이 아니라 실제 상태 기준). 대기 쪽 배포 play에 `any_errors_fatal: true`를 걸어 한 대라도 실패하면 전환이 실행되지 않게 했다.

| | 조건 | 결과 |
|---|---|---|
| J | 정상 배포 (v7.0 → green) | 에러 0, `default_backend green` |
| K | 롤백 (green → blue) | 4.4초, `default_backend blue` |
| L | 불량 버전 (bad → green) | green 헬스체크 실패, 전환 미실행, `default_backend blue` 유지, 에러 0 |

- **J**: v6.0의 마지막 응답과 v7.0의 첫 응답이 같은 초(19:04:34)였다. 롤링 v2.0에서는 두 버전이 20초 넘게 섞였는데, 여기서는 사실상 0이다. (감시를 전환 직후 멈춰 전환 이후 샘플은 짧다.)
- **K**: 4.4초. 롤링 롤백은 서버마다 다시 배포해 한 대에 15초 안팎 걸렸다. Blue-Green은 방향만 바꾼다. blue 서버들이 v6.0 상태로 대기하고 있었기 때문이다.
- **L**: green 배포 단계에서 헬스체크가 실패하고 전환 play는 실행되지 않았다(`default_backend`는 blue 그대로). 롤링 F는 사용자 쪽 용량이 3/4로 줄었지만, L은 실패가 대기 쪽에서만 일어나 사용자 쪽 용량에 변화가 없다.

L이 남긴 상태에서 확인한 점: K 직후 green은 v7.0으로 대기 중인 롤백 예비였다. L의 실패한 배포가 그 예비를 bad로 덮어썼다(`node4: error`, `node5: error`). Blue-Green에서 대기 쪽은 다음 배포 대상이면서 동시에 롤백 보험인데, 배포가 실패하면 보험도 함께 사라진다.

### 롤링과 Blue-Green 비교

| | 롤링 | Blue-Green |
|---|---|---|
| 버전 혼재 구간 | 20초 이상 (v2) | 사실상 0 (J) |
| 롤백 | 서버마다 재배포, 1대당 약 15초 | 방향 전환, 4.4초 (K) |
| 불량 배포 시 사용자 쪽 용량 | 3/4로 감소 (F) | 변화 없음 (L) |
| 필요한 서버 | N | 2N |
| 약점 | batch 크기를 잘못 정하면 전면 장애 (E) | 실패한 배포가 롤백 예비를 덮어씀 (L) |

## 설정과 실제 상태의 충돌

haproxy Role의 defaults에 `haproxy_active_color: blue`가 있었다. green이 활성인 상태에서 평소처럼 `site.yml`을 돌렸을 때를 확인했다.

| | site.yml 실행 전 | site.yml 결과 | 실행 후 트래픽 |
|---|---|---|---|
| M (수정 전) | green (v7.0) | `changed=2` | blue (v6.0)로 되돌아감 |
| M2 (수정 후) | green (v7.0) | `changed=0` | green 유지 |

M은 아무도 롤백을 결정하지 않았는데 일상적인 설정 적용이 트래픽을 이전 버전으로 되돌렸다. `changed=2`, `failed=0`으로 끝나 실행한 사람 입장에서는 평범한 성공이었다. 소켓 디렉터리 문제(01)와 같은 구조다. 그때는 패키지와 Ansible이 같은 디렉터리를, 여기서는 Role의 defaults와 배포 절차가 같은 설정 줄을 관리했다.

색을 명시했을 때만 바꾸고 명시하지 않으면 LB의 현재 설정을 유지하도록 고쳤다.

```yaml
- name: Detect current active color
  ansible.builtin.command: awk '/default_backend/{print $2}' /etc/haproxy/haproxy.cfg
  register: haproxy_cur
  changed_when: false
  failed_when: false
- name: Decide active color
  ansible.builtin.set_fact:
    haproxy_active: >-
      {{ haproxy_active_color if haproxy_active_color
         else (haproxy_cur.stdout | regex_replace('_backend$', '')
               if haproxy_cur.stdout in ['blue_backend', 'green_backend'] else 'blue') }}
```

M2에서 `site.yml`은 `changed=0`으로 끝나 green을 유지했고, 색을 명시하는 `bg_switch`는 blue로 정상 전환됐다.

`lbstate`에서 가끔 보인 `UP 1/3`은 reload 직후에만 나타나는 과도 상태다. haproxy가 reload하면 헬스체크 성공 횟수를 새로 세기 시작한다. `changed=0`이라 reload가 없던 실행에서는 전부 `UP`이었다.

## 정리

04에서 반복해 나온 것은 배포 도구의 성공 보고와 서비스의 실제 상태가 별개라는 점이다.

- B: 재시작 중 요청 10건 실패 → `failed=0`
- E: 요청 73% 실패 → `failed=0`
- H: 불량 버전 4회 배포 → `failed=0`
- M: 의도하지 않은 롤백 → `failed=0`

네 번 모두 playbook은 성공을 보고했고, 실제 영향은 바깥에서 사용자처럼 요청을 보낸 감시 로그나 LB의 실제 상태로만 보였다.

## 참고 자료

- [Ansible - Delegation, rolling updates, and local actions](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_delegation.html)
- [Ansible - Error handling in playbooks (block/rescue)](https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_error_handling.html)
- [community.general.haproxy module](https://docs.ansible.com/ansible/latest/collections/community/general/haproxy_module.html)
