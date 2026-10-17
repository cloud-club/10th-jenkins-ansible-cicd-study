# 2주차: Canary 배포

기존 서비스를 유지하면서 새 버전의 트래픽을 **10% → 50% → 100%**로 늘리는 실습이다.
Jenkins가 순서와 승인을 관리하고, Ansible이 컨테이너 배포와 Nginx 설정 변경을 맡는다.

| 바로 열기 | 용도 |
| --- | --- |
| [Demo App](http://1.201.116.156:18004/) | 현재 응답한 버전과 서버 확인 |
| [Jenkins Job](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/) | 파이프라인 실행 |
| [성공한 빌드 #7](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/7/) | 실제 전환 결과 확인 |
| [Jenkinsfile](Jenkinsfile) | 전체 배포 순서 확인 |

> 이 문서는 1번부터 순서대로 설명하고, 각 절의 **확인할 화면**을 열어보는 흐름으로 구성했다.
> 실습 서버와 Jenkins는 허용된 네트워크에서 접속해야 한다.

---

## 1. 1주차에서 무엇을 바꿨나

1주차에는 이미지를 빌드하고 서버 3대의 컨테이너를 교체하는 기본 배포를 만들었다.
2주차에는 기존 컨테이너를 바로 교체하지 않고, **추가 포트에서 새 컨테이너를 먼저 준비**하도록 바꿨다.

| 항목 | 1주차 | 2주차 |
| --- | --- | --- |
| 앱 | Python 기본 HTTP 서버 | FastAPI |
| 접속 화면 | JSON API | 기본 HTML 화면 + 기존 JSON API |
| 컨테이너 | 서버마다 하나 | 서버마다 기존·후보 두 개 |
| 전환 방법 | 기존 컨테이너 교체 | Nginx에서 후보 비율을 단계적으로 확대 |
| 확인 방법 | 배포 후 응답 확인 | 배포 중 연속 요청 + 단계별 비율 확인 |
| 진행 판단 | 순서대로 실행 | 10%, 50% 결과 확인 후 승인 |

Canary를 선택한 이유는 새 버전에 처음부터 모든 요청을 보내지 않고, 일부 요청부터 보내면서 상태를 확인하기 위해서다.
이번 실습에서는 기능 차이보다 **어느 버전이 요청을 처리하는지**를 확인하는 데 집중했다.

**확인할 화면:** [Demo App](http://1.201.116.156:18004/)

```text
Demo App

버전: v2
서버: app1
상태: 정상
```

화면은 요청을 처리한 서버의 값을 보여준다. 새로고침하면 `app1`, `app2`, `app3` 중 다른 서버가 응답할 수 있다.
전체 서버의 상태를 모아서 보여주는 화면은 아니다.

---

## 2. 서버와 포트는 어떻게 나눴나

공통 서버 6대 중 Controller와 Agent가 배포를 실행하고, Nginx와 App 서버 3대가 서비스를 제공한다.

```text
GitHub
  │ 코드 가져오기
  ▼
Jenkins Controller ── 작업 실행 ──▶ Jenkins Agent
                                     │ 빌드·테스트·Ansible 실행
                                     ▼
                              App 서버 3대에 이미지 전달

사용자 ──▶ Nginx :18004 ──┬──▶ app1  기존 / 후보
                         ├──▶ app2  기존 / 후보
                         └──▶ app3  기존 / 후보
```

각 App 서버에는 할당받은 `20004`, `21004` 포트를 사용한다. 컨테이너 내부 포트는 둘 다 `8080`이다.

**실제 v1 → v2 배포(#7) 당시 구성:**

| 서버 | 주소 | 기존 v1 | 후보 v2 |
| --- | --- | --- | --- |
| app1 | `1.201.118.202` | `21004` | `20004` |
| app2 | `1.201.118.10` | `21004` | `20004` |
| app3 | `1.201.118.90` | `21004` | `20004` |

포트가 특정 버전에 고정된 것은 아니다. 현재 활성 포트를 읽고 반대 포트에 다음 버전을 올린다.
#7이 끝난 뒤에는 `20004`가 활성 포트이고, 다음 배포의 후보 포트는 `21004`가 된다.

**확인할 코드:** [inventory.ini](ansible/inventory.ini), [discover.yml](ansible/discover.yml)

`discover.yml`에서는 다음 순서로 배포 기준을 만든다.

1. 개인 Nginx 설정에서 활성 포트를 읽는다.
2. 기존 서버 3대가 같은 릴리스로 정상 응답하는지 확인한다.
3. 반대 포트를 후보 포트로 선택한다.
4. 이전 설정과 릴리스 정보를 복구용으로 저장한다.

---

## 3. 같은 이미지를 어떻게 배포하나

이미지를 서버마다 따로 빌드하지 않는다. **Agent에서 한 번 빌드하고 테스트한 이미지**를 서버 3대에 전달한다.

```text
앱 테스트 → Docker 이미지 빌드 → 이미지 실행 검사
                                      │
                                      ▼
                              docker save + gzip
                                      │
                                      ▼
                        서버 3대에 전달 → load → 실행
```

별도 Registry를 추가하지 않고 1주차의 이미지 파일 전달 방식을 유지했다.
이미지 태그에는 버전, Git 커밋, Jenkins 빌드 번호를 넣는다.

```text
v2-448e9f3a89da-7
│  │            └─ Jenkins 빌드 번호
│  └────────────── Git 커밋 앞 12자리
└───────────────── VERSION 파라미터
```

이름이 같은 이미지를 전달했다는 것만으로 끝내지 않고, 각 서버에서 로드한 **이미지 ID가 Agent의 이미지 ID와 같은지** 확인한다.

**확인할 코드:** [Jenkinsfile](Jenkinsfile)의 `Build`, `Test`, `Package` → [app Role](ansible/roles/app/tasks/main.yml)

후보를 실행한 뒤에는 서버 내부에서 API를 검사하고, Nginx 서버에서도 후보 포트에 접근해 같은 릴리스가 응답하는지 확인한다.
이 과정까지는 기존 버전이 계속 사용자 요청을 처리한다.

---

## 4. Canary 비율은 어떻게 바꾸나

후보 서버 3대가 모두 준비되면 개인 Nginx upstream의 가중치를 바꾼다.

| 단계 | 기존 서버 각각 | 후보 서버 각각 | 전체 후보 비율 |
| --- | ---: | ---: | ---: |
| 배포 전 | 1 | 제외 | 0% |
| 10% | 9 | 1 | 10% |
| 50% | 1 | 1 | 50% |
| 100% | 제외 | 1 | 100% |

10% 단계에서 기존 가중치 합은 `9 × 3 = 27`, 후보 합은 `1 × 3 = 3`이다.
따라서 후보의 목표 비율은 `3 / (27 + 3) = 10%`가 된다.

50%에서는 양쪽을 모두 1로 맞춘다. 100%에서는 기존 서버의 항목을 upstream에서 제외한다.
기존 컨테이너 자체는 복구에 사용할 수 있도록 남겨둔다.

**확인할 코드:** [canary.conf.j2](ansible/roles/traffic/templates/canary.conf.j2)

설정은 다음 순서로 반영한다.

```text
개인 설정 준비 → 공유 잠금 획득 → 기존 설정 검사
             → 개인 설정 교체 → nginx -t → reload
```

**확인할 코드:** [traffic Tasks](ansible/roles/traffic/tasks/main.yml), [reload Handler](ansible/roles/traffic/handlers/main.yml)

Task가 Handler 실행을 예약하고, `flush_handlers`로 실제 반영을 마친 뒤 다음 측정으로 넘어간다.
설정 검사나 reload가 실패하면 교체 직전 설정을 되돌린다.

---

## 5. 다음 단계로 넘어가는 기준은 무엇인가

설정을 바꿨다고 바로 다음 비율로 넘어가지 않는다. **자동 측정이 통과한 뒤 사람이 승인**한다.

```text
기존 서비스 측정
  → 후보 준비
  → 10% 전환·측정 → 승인
  → 50% 전환·측정 → 승인
  → 100% 전환·측정 → 완료
```

| 검사 항목 | 통과 기준 |
| --- | --- |
| 관측 시간·요청 수 | 60초 이상이면서 최소 300건 |
| 오류 | HTTP 오류, 비정상 상태, 잘못된 릴리스 등 0건 |
| 후보 비율 | 10%, 50%는 목표의 ±5%p 이내 |
| 배포 전·최종 비율 | 각각 후보 0%, 100% |
| 응답 서버 | 배포 전에는 기존 서버 3대, 전환 단계에서는 후보 서버 3대 확인 |
| 릴리스 구분 | 버전·커밋·릴리스가 예상값과 일치 |

**확인할 코드:** [observe.py](scripts/observe.py)의 `classify`, `verdict`

단계별 측정과 별개로 후보 준비부터 최종 전환까지 계속 HTTP 요청을 보내는 관측도 실행한다.
승인 대기 중에도 관측은 계속된다. 한 번 발생한 오류를 뒤의 성공 응답으로 지우지 않는다.

후보 설정에서는 `proxy_next_upstream off`로 Nginx 재시도를 끈다. 실패한 요청이 다른 서버의 성공 응답으로 가려지는 것을 막기 위해서다.
두 관측 도구의 요청 순서가 고정되지 않도록 요청 간격은 0.1~0.2초 사이로 바꾼다.

> Nginx의 가중치는 목표 분배 비율이다. 제한된 표본에서 측정한 비율은 정확히 10%, 50%가 아닐 수 있다.

---

## 6. 실제 전환 결과는 어땠나

2026-10-12, [Jenkins #7](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/7/)에서 v1 → v2 전환을 확인했다.
검증한 코드 커밋은 `448e9f3`이다.

| 구간 | 요청 수 | 실패 수 | 실제 v2 비율 |
| --- | ---: | ---: | ---: |
| 배포 전 | 383 | 0 | 0% |
| 10% | 388 | 0 | 11.34% |
| 50% | 388 | 0 | 47.68% |
| 100% | 388 | 0 | 100% |

각 구간에서 필요한 서버 3대의 응답을 모두 확인했고, 빌드는 **SUCCESS**로 끝났다.
별도로 실행한 전체 배포 관측은 **1,867건 중 오류 0건**이었다.

**확인할 화면:** [#7 Console Output](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/7/console) → 빌드 페이지의 Artifacts

| 파일 | 확인할 내용 |
| --- | --- |
| `canary-10.json`, `canary-50.json`, `canary-100.json` | 요청 수, 오류 수, 후보 비율, 확인한 서버 |
| `continuous.json` | 전체 배포 관측 결과 |
| `*.jsonl` | 개별 요청의 시각, 버전, 릴리스, 서버, 응답 시간 |
| `deploy-vars.json` | 배포 이미지와 릴리스 정보 |
| `state.json`, `previous.conf` | 배포 전 포트·릴리스·Nginx 설정 |

전체 관측과 단계별 측정은 별도 요청이다. 요청 수를 서로 더해서 하나의 측정 결과처럼 사용하지 않는다.
이 결과는 **측정한 요청에서 오류가 없었다**는 뜻이며, 모든 사용자 요청과 모든 순간의 무중단을 보장하는 수치는 아니다.

---

## 7. 중간에 취소하면 어떻게 되나

후보 준비가 시작된 뒤 실패하거나 승인을 취소하면 후속 배포를 중단하고, 배포 전 개인 Nginx 설정으로 돌아간다.
승인 대기 시간이 10분을 넘는 경우에도 복구 대상이 된다.

```text
v1 90% / v2 10%
      │ 승인 취소
      ▼
후속 단계 중단 → 이전 Nginx 설정 복구 → v1 응답 확인
```

**확인할 화면:** [취소·복구 빌드 #6](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/6/)

| 확인 항목 | 실제 결과 |
| --- | --- |
| 취소 시점 | 10% 측정 통과 후, 50% 승인 단계 |
| 후속 배포 | 50%, 100% 실행 안 함 |
| 복구 응답 | 388건 중 오류 0건, 후보 비율 0% |
| 서버 확인 | 기존 v1 서버 3대 응답 확인 |
| 빌드 결과 | ABORTED |

복구에 성공했어도 취소된 배포를 SUCCESS로 표시하지 않는다.

**확인할 코드:** [Jenkinsfile](Jenkinsfile)의 `post → unsuccessful` → [traffic Role](ansible/roles/traffic/tasks/main.yml)

이번에 실제 확인한 것은 **승인 취소 후 복구**다. 장애 버전 주입, SSH 단절, Jenkins 자체 중단은 아직 검증하지 않았다.
특히 SSH 연결이 끊기면 설정을 되돌리는 명령도 실패할 수 있다.

---

## 8. 직접 시연할 때의 순서

현재 버전을 먼저 보고 시작한다. 이미 v2인 상태에서 다시 v2를 배포하면 릴리스는 달라져도 화면의 버전 이름은 그대로다.
**v1 → v2 시연이 필요하면 v1 배포를 미리 완료해 둔다.**

이번 v1과 v2는 VERSION 파라미터로 구분한 데모 버전이다. 서로 다른 기능을 추가한 두 코드 버전은 아니다.

| 순서 | 열거나 누를 곳 | 확인할 내용 |
| --- | --- | --- |
| 1 | [Demo App](http://1.201.116.156:18004/) | 시작 버전이 v1인지 확인 |
| 2 | [Jenkins Job](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/) → **Build with Parameters** | VERSION을 v2로 선택하고 Build |
| 3 | 새 빌드 → **Console Output** | 후보 서버 준비와 10% 측정 결과 |
| 4 | 승인 입력의 **Proceed** | 결과를 확인하고 50%로 확대 |
| 5 | 다음 승인 입력의 **Proceed** | 50% 결과 확인 후 100%로 전환 |
| 6 | 빌드 결과 → **Artifacts** | SUCCESS와 측정 파일 확인 |
| 7 | Demo App 새로고침 | v2와 응답 서버 확인 |

배포 중 화면을 몇 번 새로고침하는 것만으로 비율을 판단하지 않는다. 비율은 Jenkins 측정 결과로 설명한다.
첫 화면은 자동 갱신되지 않으므로 버전 전환을 보려면 직접 새로고침한다.

발표 시간이 짧으면 새 배포를 기다리는 대신 **#7의 실행 로그와 Artifacts**를 열어 같은 순서로 설명할 수 있다.

---

## 참고: 파일과 실행 환경

### 코드 위치

| 파일 | 역할 |
| --- | --- |
| [app/app.py](app/app.py) | FastAPI API와 Demo App HTML |
| [Jenkinsfile](Jenkinsfile) | 빌드, 단계 제어, 승인, 복구 |
| [discover.yml](ansible/discover.yml) | 활성 포트와 기존 릴리스 확인 |
| [prepare.yml](ansible/prepare.yml) | 후보 배포와 LB 접근 검사 |
| [app Role](ansible/roles/app/tasks/main.yml) | 이미지 전달, 소유권·이미지 ID 검사, 컨테이너 실행 |
| [traffic Role](ansible/roles/traffic/tasks/main.yml) | Nginx 설정 준비와 Handler 실행 |
| [observe.py](scripts/observe.py) | HTTP 관측과 판정 |

`deploy.yml`, `verify.yml`, `roles/nginx`, `app/VERSION`은 1주차 기록이다.
현재 파이프라인은 위 2주차 파일과 Jenkins VERSION 파라미터를 사용한다.
[1주차 코드 보기](https://github.com/cloud-club/10th-jenkins-ansible-cicd-study/tree/week6/taewook/practice/taewook)

### 개인 리소스와 공유 환경

| 항목 | 값 |
| --- | --- |
| Jenkins Job / Agent 라벨 | `taewook/deploy-pipeline` / `ansible-control` |
| 브랜치 / Script Path | `week7/taewook` / `practice/taewook/Jenkinsfile` |
| SSH Credential | `SSH_KeyPair-cc10-cicd.pem` |
| 컨테이너 | `taewook-app-20004`, `taewook-app-21004` |
| Nginx 주소 | `1.201.116.156:18004` |
| 개인 Nginx 설정 | `/etc/nginx/conf.d/taewook.conf` |

컨테이너는 `owner=taewook` 라벨로 소유권을 확인한다.
설정 교체·문법 검사·reload는 `/var/lock/nginx-cicd.lock` 안에서 진행한다. 다른 사용자도 같은 잠금을 써야 동시 변경을 막을 수 있다.
시스템 패키지 설치, Docker 재시작, 서버 재부팅은 하지 않는다. SSH 키는 Jenkins에서 주입하고 호스트 키 검증도 유지한다.

### 로컬 실행

```sh
cd practice/taewook
python3 -m venv .venv
.venv/bin/pip install -r app/requirements-test.txt
.venv/bin/python -m unittest discover -s app -v
python3 -m unittest discover -s scripts -v
APP_VERSION=v1 INSTANCE=local .venv/bin/uvicorn app:app --app-dir app --port 8080
```

### 검증 이력

- 로컬 앱·관측 테스트 8개, Ansible 및 Jenkins 문법 검사 통과.
- [#3](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/3/): 기본 HTTP 앱 → FastAPI v1 준비 성공. 전체 관측 2,237건, 오류 0건.
- #4, #5: 복구 변수 수정 반영 과정에서 트래픽 변경 전에 중단.
- [#6](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/6/): 승인 취소와 v1 복구 확인.
- [#7](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/7/): v1 → v2 정상 전환 성공.
