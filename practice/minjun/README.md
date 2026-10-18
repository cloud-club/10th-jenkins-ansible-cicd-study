# jenkins-ansible-cicd (minjun)

클클 10기 Jenkins & Ansible 스터디 실습 레포.

| 주차 | 내용 |
|---|---|
| 1주차 | Build → Test → Package → Deploy → Verify 기본 파이프라인 |
| 2주차 | Rolling 배포 (drain/undrain + handler) · 무중단 측정 · 보안 변형(이미지 무결성 게이트, 감사 로그) |
| **3주차** | **Rolling 롤백** · 서명된 배포 기록(ledger) · 승인 게이트 · 증거 보존 · 격리 |

## 할당 자원

| 항목 | 값 |
|---|---|
| Nginx 포트 | 18006 |
| App 포트 | 20006 (Rolling은 이것만 사용) / 21006 (예비) |
| 컨테이너 | `minjun-app-blue` (서버당 1개, 제자리 교체) |
| Nginx 설정 | `/etc/nginx/conf.d/minjun.conf`, `upstream minjun_backend` |
| Jenkins | Folder `minjun`, Job `deploy-pipeline`, Agent 라벨 `ansible-control` |

## 파이프라인

```
ACTION=deploy    Checkout → Ledger: Verify(격리 태그 거부) → Build → Test → Package → Rolling Deploy → Verify → Ledger: Record
ACTION=rollback  Checkout → Ledger: Verify(롤백 대상 결정) → Approve Rollback → Rolling Deploy(로드 없음, 증거 수집) → Verify → Ledger: Record
```

| 파라미터 (choice만) | 값 | 의미 |
|---|---|---|
| `ACTION` | `deploy` (기본) / `rollback` | 현재 커밋 배포 / 서명된 기록의 직전 정상 버전으로 되돌림 (빌드 없음, 승인 필요) |
| `STRATEGY` | `drain` (기본) / `no-drain` | A: 한 대씩 Nginx에서 빼고 교체 / C: 빼지 않고 교체 (2주차 비교 실험) |
| `DEMO_TAMPER` | `none` (기본) / `app2` / `ledger` / `restore-ledger` | 시연용. 변조 이미지 심기 / LB 배포 기록 한 줄 변조 / 변조 되돌리기 |

자유 입력(string) 파라미터는 쓰지 않는다. 다른 사람이 실행해도 명령 주입 경로가 되지 않게.
`site.yml`은 1주차 최초 배포용으로 그대로 둔다.

---

## 3주차: Rolling 롤백

> 과제 가정: 서비스를 완전히 배포하고 약 12시간 뒤 치명적인 에러가 발생해 **이전 버전으로 완전히 롤백**해야 한다.
> 배포 정보는 Jenkins Archive Artifacts, 파일 등에 저장할 수 있다.

### 왜 "서명된" 기록인가

롤백은 결국 **"직전 정상 버전이 무엇이었나"라는 기록을 믿고 실행**된다.
그 기록이 서버(LB)에만 평문으로 있으면, 서버 root 권한을 가진 사람이 기록을 바꿔 두는 것만으로
장애가 나서 급하게 롤백하는 순간 **원하는 이미지를 3대 전체에 배포하게 만들 수 있다.** 롤백이 공격 경로가 된다.

그래서 이번 주는 롤백을 이렇게 설계했다.

| 원칙 | 구현 |
|---|---|
| 롤백 대상은 사람이 입력하지 않는다 | 서명이 검증된 기록에서 "격리되지 않은 직전 배포"를 자동 선택 (`tools/ledger.py rollback-target`) |
| 기록이 한 줄이라도 틀리면 롤백하지 않는다 | 각 줄 HMAC-SHA256 서명 + 앞 줄 서명을 포함한 해시 체인 |
| 서버를 장악해도 서명은 위조할 수 없다 | 키는 Jenkins Credential(`minjun-ledger-hmac`, Secret text)에만. `ledger.py`가 환경변수로만 읽고 ansible 프로세스에는 넘기지 않음 |
| 롤백은 다시 빌드하지 않는다 | 다시 빌드하면 BuildKit attestation 때문에 다른 이미지가 된다(2주차 확인). 서버에 남아 있는 이전 이미지를 로드 없이 쓰고, ID가 **서명된 기록의 ID와 같아야** 실행 |
| 롤백도 무중단 | 2주차 `rolling.yml` 그대로 — 한 대씩 drain → 교체 → undrain |
| 누가 왜 롤백했는지 남긴다 | `input` 승인 게이트 (`submitter: minjun`, 사유는 choice) → 기록·감사 로그에 approver, reason |
| 교체 전에 증거를 남긴다 | 불량 컨테이너를 지우기 전에 `docker inspect`, 이미지 정보, 최근 로그 300줄 + `SHA256SUMS` → Archive Artifacts |
| 같은 실수를 반복하지 않는다 | 롤백된 태그를 기록에 `QUARANTINE`으로 올림 → 같은 태그 배포는 빌드 시작 전에 거부 |

### 배포 기록 (`tools/ledger.py`)

LB `/var/lib/minjun/ledger.jsonl` (원본) + 매 빌드 Jenkins Archive Artifacts (`ledger.jsonl`, `ledger-head.txt`) 두 곳.

```
#1 DEPLOY     v7-516c930  build=15
#2 DEPLOY     v8-fd47ebb  build=16
#3 ROLLBACK   v7-516c930  build=17 from=v8-fd47ebb approver=minjun reason=functional-failure
#4 QUARANTINE v8-fd47ebb  build=17 approver=minjun reason=functional-failure
#5 DEPLOY     v9-6b885ec  build=20
```

각 줄에는 태그, 서버별 이미지 ID, 빌드 번호, 커밋, 시각, `prev_mac`, `mac`이 들어 있다.

| 변조 | 검출 |
|---|---|
| 한 줄의 내용 변경 | 그 줄의 `mac` 불일치 |
| 중간 줄 삭제·순서 변경 | 다음 줄의 `prev_mac` 불일치 |
| 키 없이 새 줄 추가 | `mac` 불일치 |
| 뒤쪽 줄을 통째로 잘라냄 | **체인만으로는 못 잡는다** → Jenkins에 남은 빌드별 `ledger-head.txt`(seq, mac)와 대조 |

### 시나리오와 결과 (실서버, 2026-10-18)

| # | 빌드 | 한 일 | 결과 |
|---|---|---|---|
| 1 | #15 | v7 정상 배포 | `LEDGER_APPEND #1`, 3대 같은 ID `sha256:91bde9ff…` |
| 2 | #16 | **v8 배포** — `/`만 500, `/health`·`/version`은 정상 | 헬스체크·Verify 통과, **`Finished: SUCCESS`**. 실제 서비스는 `{"error": "order service crashed"}` 500 |
| 3 | #17 | **`ACTION=rollback`** + 측정 | 아래 표 |
| 4 | #18 | 격리된 v8 재배포 시도 | `QUARANTINED: v8-fd47ebb was quarantined at ledger #4` → Build 전에 FAILURE, 서버 v7 유지 |
| 5 | #19 | LB 기록 변조(#2를 `v6-8b99f2a`로) → rollback | `LEDGER_REJECTED: line 2 (seq 2, DEPLOY v6-8b99f2a): signature mismatch` → 롤백 대상 계산 전에 FAILURE |
| 6 | #20 | 기록 복구 + v9(수정본) 배포 | `LEDGER_OK entries=4` → `#5 DEPLOY v9-6b885ec`, `/` 200 |

2번이 "12시간 뒤에 발견되는 장애"의 재현이다. 파이프라인 기준으로는 완벽한 배포였다.

**롤백(#17) 상세**

| 단계 | 로그 |
|---|---|
| 대상 결정 | `ROLLBACK_TARGET v7-516c930 (ledger #1) ← current v8-fd47ebb` |
| 재빌드 | Build · Test · Package **skipped** |
| 승인 | `Approved by 박민준`, `reason=functional-failure` |
| 증거 | 3대 모두 교체 전 수집 (`EVIDENCE_COLLECTED`, 서버별 4개 파일 Artifacts에 보관) |
| 무결성 | `integrity ok (no load, matches signed ledger)` × 3 — 빌드 #15 때 기록한 ID 그대로 |
| 기록 | `#3 ROLLBACK`, `#4 QUARANTINE v8-fd47ebb` |
| 소요 | 롤링 약 67초, reload 6번 |

Mac에서 0.2초 간격 측정 두 개를 동시에 돌렸다 (`results/1018-203648-rb-version.csv`, `results/1018-203652-rb-service.csv`).

| 측정 | 요청 | 실패 | 의미 |
|---|---|---|---|
| `/version` (가용성) | 2212 | **0** | 롤백 중 서비스가 끊긴 적 없음 |
| `/` (실제 기능) | 2185 | 628 (전부 HTTP 500) | 롤백 전 100% 실패 → 한 대씩 복구되며 0 |

- `/` 실패는 마지막 v8 서버(app3)가 **v7로 돌아온 시점(159s)이 아니라 drain된 시점(~145s)에 끝났다.** 롤링 롤백에서는 drain이 곧 장애 차단이고, 교체는 그 뒤의 일이다
- `/version` 기준 v8과 v7이 섞여 응답한 구간 **28.4초**. 그동안 고장 난 버전도 일부 요청을 받는다 → 롤링 롤백의 대가 (아래 한계)
- `/` 타임라인 앞부분의 `·`는 트래픽이 없던 게 아니라, 500 응답은 본문을 읽지 않아 서버 이름이 비어서다. `fail` 줄의 `X`가 실제 요청

### 12시간 뒤에 남는 것과 사라지는 것

| 저장 위치 | 무엇 | 12시간 뒤 | 롤백에서 쓰임 |
|---|---|---|---|
| Agent workspace | 이미지 아카이브(`build/minjun-app.tar.gz`) | **없음** (매 빌드 `post`에서 삭제) | 안 씀. 그래서 서버의 이미지를 쓴다 |
| Agent docker | 빌드한 이미지 | **없음** (빌드 후 삭제) | 다시 빌드해도 ID가 달라 무의미 |
| App 서버 docker | 이전 버전 이미지 | 남음 (지우지 않음) | **롤백에 실제로 쓰는 이미지** |
| App 서버 `/opt/minjun/image-ids/<tag>` | 이 파이프라인이 로드한 ID | 남음 | 2주차 게이트 기준. 서버 쪽이라 신뢰 기준으로는 부족 |
| LB `/var/lib/minjun/ledger.jsonl` | 서명된 배포 기록 원본 | 남음 | **롤백 대상과 기대 ID의 출처** |
| Jenkins Archive Artifacts | 기록 사본, head, 롤백 대상, `rolling.log`, 증거 | 남음 (최근 20개 빌드) | 원본 대조·복구, 사후 분석 |
| 불량 컨테이너의 로그·설정 | | 교체하는 순간 **사라짐** | 그래서 교체 직전에 증거로 보관 |

### 추가로 고친 것 (2주차 한계)

- **같은 태그 재빌드 시 컨테이너 재생성**: 교체 대상이 아닌 서버(`update=False`)는 이제 아카이브를 로드하지 않고 무결성만 확인한다 (`app_skip_load`). 롤백 경로와 같은 "로드 없음" 모드를 공유한다. *로컬 시뮬레이션에서만 확인 — 이번 주 실서버 빌드에는 같은 태그 재배포가 없었다*

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
| 3주차 첫 빌드 대기 (10/17) | 공용 ansible-agent 기동 실패 — 컨트롤러→Agent SSH가 인증 전에 `Connection reset` | 스터디장님께 로그와 함께 공유, 복구 후 진행 |

## 2주차 한계 → 3주차에서

| 2주차 한계 | 3주차 |
|---|---|
| 같은 태그 재빌드 시 교체 대상이 아닌 서버도 drain 없이 컨테이너 재생성 (빌드 #14 app1) | 교체 대상이 아니면 로드하지 않음 (로컬에서만 확인) |
| ID 기록 파일이 서버에 있어 root 권한이면 기록까지 바꿀 수 있음 | 롤백은 서버 기록이 아니라 **서명된 기록의 ID**를 기준으로 판정 |
| 헬스체크가 `/health`·`/version`만 봄 | **그대로.** v8 시나리오가 바로 이 한계를 이용했다 (아래) |
| 롤백 미구현 (`last_good_tag`만 기록) | 서명된 기록 기반 롤백으로 대체. `last_good_tag`는 참고용으로 남아 있음 |

## 남은 한계 (3주차)

- **장애 감지는 사람 몫이다.** 헬스체크가 실제 기능을 보지 않아서 v8은 배포에 성공했다. 롤백은 누군가 장애를 발견하고 `ACTION=rollback`을 눌러야 시작된다. 실제 경로(`/`)를 확인하는 smoke test나 에러율 모니터링이 있어야 "12시간"이 줄어든다
- **롤링 롤백은 느리게 끊는다.** 측정상 v8·v7이 28.4초 동안 섞여 응답했다. 장애가 치명적이면 모든 서버를 한 번에 빼거나(Blue-Green 전환) 문제 서버부터 먼저 drain하는 편이 낫다
- **격리 거부가 감사 로그에 안 남는다.** 빌드 #18의 `QUARANTINED` 거부는 Jenkins 빌드 기록(FAILURE)에만 있고 LB의 `minjun-deploy.jsonl`에는 없다
- **기록 끝부분 잘라내기(truncation)는 체인만으로 못 잡는다.** Jenkins Artifacts의 `ledger-head.txt`와 대조해야 하는데, 이 대조는 자동화하지 않았다
- **변조 복구는 시연용이다.** `restore-ledger`는 LB의 `.pre-tamper` 백업을 쓴다. 실제라면 LB의 백업도 믿을 수 없으니 Jenkins Artifacts에 남은 마지막 정상 사본으로 복구하고, 그 사본의 head가 빌드 기록과 일치하는지 확인해야 한다
- **Artifacts 보존은 최근 20개 빌드**(`buildDiscarder`). 빌드가 많은 환경에서는 기록 사본을 별도 저장소로 옮겨야 한다
- **서명 키 하나에 모든 신뢰가 걸려 있다.** `Job/Configure` 권한이 있으면 Jenkinsfile을 바꿔 키를 쓸 수 있다(2주차 스터디에서 확인한 "Job 권한 = Credential 접근"). 키 교체 절차도 없다
- **이전 이미지가 서버에서 지워지면 롤백 불가.** 지금은 지우지 않지만, 디스크 정리 정책이 생기면 "직전 정상 버전"만큼은 남기는 규칙이 필요하다

## 공용 환경에서 지킨 것

- 모든 이름에 `minjun` 접두사. 남의 컨테이너·conf는 읽지도 수정하지도 않음
- nginx 변경은 공용 `flock` 락 안에서 `백업 → 교체 → nginx -t → reload`. 실패 시 내 변경만 원복
- 실제 적용된 설정과 같으면 reload 하지 않음
- 이미지 아카이브·테스트·시연 이미지는 빌드 후 정리 (서버의 이전 이미지는 롤백용으로 남김)

## 파일

```
Jenkinsfile                       ACTION / STRATEGY / DEMO_TAMPER, Ledger 검증·기록, 롤백 승인, Archive Artifacts
tools/ledger.py                   3주차 서명된 배포 기록 (verify / check-deployable / rollback-target / append / head)
ansible/ledger.yml                3주차 기록을 LB ↔ workspace로 옮김, 서버별 이미지 ID 수집 (서명은 하지 않음)
ansible/demo-tamper-ledger.yml    3주차 기록 변조·복구 시연 (파라미터로만 실행)
ansible/rolling.yml               Rolling (serial 1, drain/undrain, fail-safe) + 3주차 롤백 모드·증거 수집
ansible/demo-tamper.yml           2주차 이미지 변조 시연 (파라미터로만 실행)
ansible/tasks/audit.yml           감사 로그 한 줄 기록
ansible/roles/app/tasks/main.yml  CI 이미지 로드 + 무결성 게이트 + 컨테이너 교체 / 로드 없음 모드(롤백, 교체 대상 아님)
ansible/roles/nginx/tasks/render.yml    staging 렌더링 + 실제 conf 비교 → notify
ansible/roles/nginx/handlers/main.yml   락 안에서 적용·검사·reload (delegate_to LB)
tools/measure.py, tools/analyze.py      무중단 측정 / 타임라인 분석 (표준 라이브러리만)
results/*.csv                     2주차 A-drain, C-nodrain, tamper / 3주차 rb-version, rb-service 측정 원본
```
