# jenkins-ansible-cicd (minjun)

클클 10기 Jenkins & Ansible 스터디 실습 레포.

| 주차 | 내용 |
|---|---|
| 1주차 | Build → Test → Package → Deploy → Verify 기본 파이프라인 |
| **2주차** | **Rolling 배포** (drain/undrain + handler) · 무중단 측정 · 보안 변형(이미지 무결성 게이트, 감사 로그) |

## 할당 자원

| 항목 | 값 |
|---|---|
| Nginx 포트 | 18006 |
| App 포트 | 20006 (Rolling은 이것만 사용) / 21006 (예비) |
| 컨테이너 | `minjun-app-blue` (서버당 1개, 제자리 교체) |
| Nginx 설정 | `/etc/nginx/conf.d/minjun.conf`, `upstream minjun_backend` |
| Jenkins | Folder `minjun`, Job `deploy-pipeline`, Agent 라벨 `ansible-control` |

## 파이프라인

`Checkout → Build → Test → Package → (Demo: Plant Tampered Image) → Rolling Deploy → Verify`

| 파라미터 (choice만) | 값 | 의미 |
|---|---|---|
| `STRATEGY` | `drain` (기본) / `no-drain` | A: 한 대씩 Nginx에서 빼고 교체 / C: 빼지 않고 교체 (비교 실험) |
| `DEMO_TAMPER` | `none` (기본) / `app2` | 시연용. 배포 직전 app2에 같은 태그의 변조 이미지를 심는다 |

자유 입력(string) 파라미터는 쓰지 않는다. 3주차에 다른 사람이 실행하므로 명령 주입 경로가 되지 않게.
`site.yml`은 1주차 최초 배포용으로 그대로 둔다.

---

## 2주차: Rolling 배포

### 흐름 (`ansible/rolling.yml`)

```
[0] 사전 확인 (lb1)
    서비스 중인 서버가 아프면 시작하지 않음 (한 대 더 빼면 1대만 남는다)
    이전 배포에서 fail-safe로 빠진(down) 서버는 허용 — 아픈 서버면 가장 먼저 교체

[1~3] serial: 1, max_fail_percentage: 0          app1 → app2 → app3
    drain    upstream에서 이 서버만 down → handler(락 → nginx -t → reload) → flush_handlers로 즉시
    대기     3초 → Nginx 경유 6회 요청에 이 서버가 안 나오는지 확인
    교체     app Role: CI 이미지 로드 → 무결성 게이트 → 컨테이너 교체 → 서버 직접 /health, /version
    undrain  down 해제 → handler → reload
    확인     Nginx 경유로 이 서버가 새 버전으로 다시 응답하는지

    실패하면 그 서버는 down인 채로 멈추고 다음 서버로 안 넘어감. 나머지는 이전 버전으로 서비스 유지

[4] 전부 성공했을 때만 /opt/minjun/last_good_tag 갱신 (이전 값 → prev_good_tag) — 3주차 롤백용
```

같은 이미지 태그로 다시 실행하면 drain·reload를 하지 않는다.

### Handler

nginx 반영(락 → 백업 → 교체 → `nginx -t` → reload, 실패 시 원복)을 `roles/nginx/handlers/main.yml`로 옮겼다.
1주차에 handler를 못 쓴 이유("락 밖에서 돈다")는 락 처리 스크립트 자체를 handler 안에 넣어서 해결했다.

실서버에서 확인한 것:

| 확인한 것 | 결과 | 그래서 |
|---|---|---|
| notify한 태스크가 `delegate_to: lb1`이면 handler도 lb1에서 도나? | **아니다.** `fatal: [app1]` … `nginx: command not found` | handler에 `delegate_to`를 직접 적음 |
| handler는 언제 도나? | play 끝에서 한 번 | `meta: flush_handlers`로 drain/undrain 직후 즉시 실행 |
| 적용 여부를 무엇으로 판단하나? | staging 파일이 아니라 **실제 conf**와 비교 | 실패 직후 재배포에서 staging은 "안 바뀜"이었지만 실제 conf와 달라서 drain이 적용됨 (안 그랬으면 트래픽 받는 중에 교체) |
| `serial` 배치에서 태스크 이름의 `{{ inventory_hostname }}` | 첫 서버 기준으로 한 번만 해석 → app2 차례에 "app1"로 찍힘 | 이름에서 변수 제거, handler가 실제 conf에서 down 서버를 읽어 `NGINX_RELOADED down=[app2]`로 출력 |

### 무중단 측정 (A vs C)

Mac에서 0.2초 간격으로 `http://1.201.116.156:18006/version` 호출 → `results/*.csv`

```bash
python3 tools/measure.py --label A-drain        # 빌드 전에 켜고, 끝나면 Ctrl+C
python3 tools/analyze.py results/*A-drain.csv results/*C-nodrain.csv
```

| 방식 | 배포 | 요청 | 실패 | Nginx 재시도 | 최대 응답 | reload |
|---|---|---|---|---|---|---|
| **A drain** | v1 → v2 | 589 | **0** | 0 | 58ms | 6 |
| **C no-drain** | v2 → v3 | 487 | **0** | **4** | 95ms | 0 |

A 타임라인 (1칸 = 1초, `·` = 그 서버로 간 요청 없음):
```
app1   1111111111111111111111111111111111············22222222222222222222222…
app2   111111111111111111111111111111111111111111111111111············2222222…
app3   111111111111111111111111111111111111111111111111111111111111111111············2…
fail   (없음)
```
- 서버마다 약 13초씩 빠졌다가 새 버전으로 복귀. v1·v2가 동시에 응답한 구간 18.6초 — Rolling의 정상 동작
- **C도 실패 0.** 컨테이너가 내려간 순간의 요청은 `proxy_next_upstream error`로 다른 서버에 재시도되어 성공(`X-Upstream`에 주소 2개). 그 대신 지연이 늘고, 실패한 서버는 `fail_timeout=5s` 동안 Nginx가 스스로 뺐다(app3 6.8초 공백)
- **결론**: 짧은 GET에서는 Nginx 재시도가 drain을 대신했다. 차이는 "실패를 안 만드느냐(drain), 실패한 뒤 다시 보내느냐(no-drain)"다. 처리 중이던 긴 요청이나, Nginx가 기본으로 재시도하지 않는 POST였다면 C에서는 실패로 드러났을 것이다

---

## 2주차 보안 변형

### A. 이미지 무결성 게이트 (`roles/app/tasks/main.yml`)

1주차 app Role은 **"서버에 같은 태그가 있으면 로드 생략"**이었다. 누군가 배포될 태그(`minjun-app:v5-7b53b5d`)로 다른 이미지를 먼저 심어 두면 그대로 실행된다. **태그는 이름표일 뿐 내용을 보증하지 않는다.**

이제는 매번 CI 아카이브를 로드하고, 로드 **전**에 태그가 가리키던 이미지 ID를 판정한다.

| 로드 전 태그의 ID | 판정 |
|---|---|
| 없음 | 통과 (처음) |
| 이 파이프라인이 전에 로드하며 기록한 ID (`/opt/minjun/image-ids/<tag>`) | 통과 |
| 이번 CI 산출물 ID | 통과 |
| 그 외 | **TAMPER** → 감사 로그 기록, 컨테이너를 띄우지 않고 중단 |

**시연** (`DEMO_TAMPER=app2`, `demo-tamper.yml`): 정상 앱과 내용은 같고 라벨(`demo.tampered=true`)만 다른 이미지를 배포 태그로 app2에 심는다.

| 빌드 | 결과 |
|---|---|
| v5 변조 시연 | app1 정상 교체 → app2 `TAMPER … pointed to sha256:c610bd9c…` → 중단, app2 down 유지, app3 v4로 서비스 |
| 측정 | 461 요청 / **실패 0**. app2는 감지 시점부터 끝까지 트래픽 0 |
| v6 변조 → 같은 커밋 재실행 | 감지(`recorded=none`) → 다음 빌드에서 app2 `loaded by this pipeline before` → 복구, 3대 v6 |

ID는 빌드 로그와 이어진다: 정상 빌드의 `exporting manifest list sha256:47f48b05…` = 서버의 "CI 산출물" ID, 변조 빌드의 `sha256:c610bd9c…` = app2에서 발견된 ID.

**오탐을 겪고 고친 것**: 처음엔 "로드 전 ID == 이번 빌드 ID"만 통과시켰다. 그런데 Agent의 BuildKit이 빌드마다 attestation(빌드 기록)을 붙여서 **같은 커밋을 다시 빌드해도 최상위 ID가 바뀐다** (빌드 #10/#12: config `f0335529…` 같음, manifest list `47f48b05…`/`ea3901d2…` 다름). 재빌드가 전부 TAMPER로 막혔다. 그래서 기준을 "이번 빌드와 같은가"에서 **"이 파이프라인이 붙인 태그인가"**로 바꿨다.

### B. 배포 감사 로그 (`ansible/tasks/audit.yml`)

LB의 `/var/log/minjun-deploy.jsonl`에 JSON 한 줄씩. 빌드마다 마지막 15줄을 Console에 출력한다.

```json
{"ts": "2026-10-09 01:08:14", "build": "13", "tag": "v6-8b99f2a", "host": "app2", "event": "TAMPER_DETECTED",
 "found": "sha256:2ef7afae…", "recorded": "none", "ci_artifact": "sha256:7794700b…"}
{"ts": "2026-10-09 01:08:39", "build": "14", "tag": "v6-8b99f2a", "host": "lb1", "event": "DEPLOY_START", "already_down": ["app2"]}
{"ts": "2026-10-09 01:09:09", "build": "14", "tag": "v6-8b99f2a", "host": "app2", "event": "SERVER_UPDATED"}
```

이벤트: `DEPLOY_START`, `SERVER_DRAINED`, `SERVER_UPDATED`, `TAMPER_DETECTED`, `DEPLOY_DONE`.
측정 CSV의 시각과 맞춰 "언제 어느 서버가 빠졌고 그동안 실패가 있었나"를 대조할 수 있다.

---

## 겪은 것 (실패 기록)

| 상황 | 원인 | 조치 |
|---|---|---|
| Rolling 첫 실행 FAILURE | handler가 delegate를 상속하지 않아 app1에서 실행 | handler에 `delegate_to` |
| 빌드를 교체 도중 중단 | (조작 실수) | app1만 새 버전, 나머지 구버전으로 서비스 유지 — 한 대씩 교체라 중단 지점까지만 반영 |
| 측정 중 Verify 거짓 실패 (로컬 재현) | 측정 요청과 라운드로빈 순번을 나눠 가져 한 서버가 0회 | Verify 12 → 30회 |
| 같은 커밋 재빌드가 TAMPER | BuildKit attestation으로 ID가 빌드마다 다름 | 파이프라인 기록 ID 기준으로 판정 |

## 남은 한계 / 3주차로

- **같은 태그 재빌드 시 컨테이너 재생성**: 교체 대상이 아닌 서버(`update=False`)도 아카이브를 로드하는데, 재빌드라 ID가 바뀌어서 docker가 컨테이너를 **drain 없이** 다시 만든다(빌드 #14 app1). 교체 대상이 아니면 로드하지 않고 무결성만 확인하도록 바꿀 것
- **ID 기록 파일도 서버에 있다**: 서버 root 권한을 가진 공격자는 기록까지 바꿀 수 있다. 신뢰 기준은 CI 쪽(서명/레지스트리 digest)에 두는 게 맞다
- **헬스체크 기준**: `/health` 200 + `/version` 일치만 본다. 기능이 고장 났는데 `/health`는 200인 버전은 통과한다 (3주차 S2 시나리오)
- **롤백**: `last_good_tag`, `prev_good_tag`를 기록해 두었고 이전 이미지는 서버에 남아 있다 → 3주차에 "이전 태그로 rolling.yml 재실행"

## 공용 환경에서 지킨 것

- 모든 이름에 `minjun` 접두사. 남의 컨테이너·conf는 읽지도 수정하지도 않음
- nginx 변경은 공용 `flock` 락 안에서 `백업 → 교체 → nginx -t → reload`. 실패 시 내 변경만 원복
- 실제 적용된 설정과 같으면 reload 하지 않음
- 이미지 아카이브·테스트·시연 이미지는 빌드 후 정리 (서버의 이전 이미지는 롤백용으로 남김)

## 파일

```
Jenkinsfile                       STRATEGY / DEMO_TAMPER 파라미터, Rolling Deploy, 감사 로그 출력
ansible/rolling.yml               2주차 Rolling (serial 1, drain/undrain, fail-safe, last_good_tag)
ansible/demo-tamper.yml           변조 시연 (파라미터로만 실행)
ansible/tasks/audit.yml           감사 로그 한 줄 기록
ansible/roles/app/tasks/main.yml  CI 이미지 로드 + 무결성 게이트 + 컨테이너 교체
ansible/roles/nginx/tasks/render.yml    staging 렌더링 + 실제 conf 비교 → notify
ansible/roles/nginx/handlers/main.yml   락 안에서 적용·검사·reload (delegate_to LB)
tools/measure.py, tools/analyze.py      무중단 측정 / 타임라인 분석 (표준 라이브러리만)
results/*.csv                     A-drain, C-nodrain, tamper 측정 원본
```
