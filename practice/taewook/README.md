# 2주차 Canary 배포 실습

FastAPI 앱을 Jenkins에서 빌드하고 Ansible로 서버 3대에 배포한다.
기존 버전을 유지한 채 새 버전의 트래픽을 10% → 50% → 100%로 늘린다.
이미지는 1주차와 같이 `docker save`로 전달한다.

## 실행

1. Jenkins `taewook/deploy-pipeline`에서 **Build with Parameters**를 누른다.
2. `VERSION`을 선택한다. 처음에는 v1으로 FastAPI 앱을 준비하고, 그다음 v2로 전환한다.
3. 10% 단계가 통과하면 Console Output의 요청 수, 실패 수, 후보 비율을 확인하고 승인한다.
4. 50%에서도 같은 방식으로 확인하고 승인한다. 승인 대기는 각각 최대 10분이다.
5. 100% 검증이 끝나면 빌드 결과와 Artifacts를 확인한다.

[Demo App](http://1.201.116.156:18004/)은 버전, 응답 서버, 상태만 표시한다.
새로고침하면 다른 서버나 버전이 응답할 수 있다. 화면 자체에서 통계를 수집하지 않는다.

| 경로 | 응답 |
| --- | --- |
| `/` | Demo App HTML |
| `/health` | 상태와 릴리스 정보 JSON |
| `/version` | 버전·커밋·릴리스·서버 JSON |

## 배포 흐름

`Checkout → Preflight → Build → Test → Package → Discover → Baseline → Canary`

- 사전 점검에서 SSH, sudo, Docker, Nginx를 확인한다.
- 앱과 관측 코드 테스트 후 이미지를 빌드한다. 실행한 이미지의 API도 검사한다.
- 현재 개인 Nginx 설정에서 활성 포트를 읽고 반대 포트에 후보를 배포한다.
- 서버 3대에서 이미지 ID와 응답 내용을 확인한 뒤 LB에서도 후보 접근을 검사한다.
- 후보를 준비하는 동안 기존 컨테이너가 계속 요청을 처리한다.
- 10%, 50% 단계마다 측정 결과를 확인하고 사람이 승인한다.

| 단계 | 기존 서버 가중치 | 후보 서버 가중치 | 후보 비율 |
| --- | --- | --- | --- |
| 10% | 서버마다 9 | 서버마다 1 | 10% |
| 50% | 서버마다 1 | 서버마다 1 | 50% |
| 100% | upstream에서 제외 | 서버마다 1 | 100% |

20004와 21004는 특정 버전에 고정된 포트가 아니다. 배포가 끝나면 다음 실행에서 역할이 바뀐다.
기존 컨테이너는 다음 배포에서 비활성 포트를 재사용할 때까지 남겨둔다.

## 검증과 복구

각 단계는 60초 이상, 최소 300건을 측정한다. 오류가 없어야 하고 후보 비율은 목표의 ±5%p,
0%와 100%는 정확히 일치해야 한다. 후보 서버 세 대의 응답도 모두 확인한다.
기존·후보 구분에는 버전 이름만 쓰지 않고 릴리스와 커밋도 함께 비교한다.

전체 배포 중에는 별도 HTTP 관측을 계속한다. 오류가 나오면 후속 배포를 중단하고,
실패·취소·승인 시간 초과 시 배포 전 개인 Nginx 설정으로 복구한 뒤 기존 릴리스를 검사한다.
복구되더라도 실패하거나 취소된 배포를 성공으로 바꾸지는 않는다.

Nginx 재시도가 오류를 가리지 않도록 후보 배포 설정에서는 `proxy_next_upstream off`를 사용한다.
관측 도구끼리 요청 순서가 고정되지 않도록 요청 간격을 0.1~0.2초 사이로 바꾼다.
요청 표본에서 오류가 없었다는 결과가 모든 요청의 무중단을 보장하지는 않는다.

SSH 단절이나 Jenkins 자체 중단으로 복구가 실행되지 못할 수 있다. 이때는 이전 빌드의
`previous.conf`, `state.json`과 실제 Nginx 상태를 확인한 뒤 복구해야 한다.
혼합 포트 상태에서는 새로운 배포를 시작하지 않는다.

## 구성과 변경 범위

| 항목 | 값 |
| --- | --- |
| Jenkins Job | `taewook/deploy-pipeline` |
| Agent 라벨 | `ansible-control` |
| 브랜치 | `week7/taewook` |
| Script Path | `practice/taewook/Jenkinsfile` |
| SSH Credential | `SSH_KeyPair-cc10-cicd.pem` |
| App 서버 | `1.201.118.202`, `1.201.118.10`, `1.201.118.90` |
| 컨테이너 | `taewook-app-20004`, `taewook-app-21004` |
| App 호스트 포트 | `20004`, `21004` (컨테이너 내부 8080) |
| Nginx | `1.201.116.156:18004` |
| 개인 설정 | `/etc/nginx/conf.d/taewook.conf` |

컨테이너 소유권은 `owner=taewook` 라벨로 확인한다. 다른 사용자의 컨테이너는 건드리지 않는다.
Nginx 파일 교체·문법 검사·reload는 `/var/lock/nginx-cicd.lock` 안에서 진행한다.
다른 사용자도 같은 잠금을 사용해야 동시 변경을 막을 수 있다.
시스템 패키지 설치, Docker 재시작, 서버 재부팅은 하지 않는다.
SSH 키는 Jenkins가 주입하고, SSH 호스트 키 검증은 유지한다.

## 코드 위치

- `app/app.py`: FastAPI API와 기본 HTML
- `ansible/discover.yml`: 현재 포트와 기존 릴리스 확인
- `ansible/prepare.yml`: 후보 배포 및 LB 접근 검사
- `ansible/roles/app`: 이미지 전달, 소유권·이미지 ID 검사, 컨테이너 실행
- `ansible/roles/traffic`: 개인 Nginx 설정과 reload Handler
- `scripts/observe.py`: 요청 기록과 단계별 판정

`deploy.yml`, `verify.yml`, `roles/nginx`, `app/VERSION`은 1주차 기록이다.
현재 파이프라인은 위 2주차 파일과 Jenkins VERSION 파라미터를 사용한다.
[1주차 코드](https://github.com/cloud-club/10th-jenkins-ansible-cicd-study/tree/week6/taewook/practice/taewook)

## 로컬 확인

```sh
cd practice/taewook
python3 -m venv .venv
.venv/bin/pip install -r app/requirements-test.txt
.venv/bin/python -m unittest discover -s app -v
python3 -m unittest discover -s scripts -v
APP_VERSION=v1 INSTANCE=local .venv/bin/uvicorn app:app --app-dir app --port 8080
```

## 실행 결과

2026-10-12 실서버에서 확인했다.

| 빌드 | 내용 | 결과 |
| --- | --- | --- |
| [#3](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/3/) | 기본 HTTP 앱 → FastAPI v1 준비 | SUCCESS, 전체 관측 2,237건 오류 0건 |
| [#6](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/6/) | v2 10% 후 승인 취소 | ABORTED, v1 복구 확인 388건 오류 0건 |
| [#7](http://1.201.117.194:8080/job/taewook/job/deploy-pipeline/7/) | v1 → v2 정상 전환 | SUCCESS, 전체 관측 1,867건 오류 0건 |

#7 측정 결과:

| 구간 | 요청 수 | 실패 | v2 응답 비율 |
| --- | ---: | ---: | ---: |
| 배포 전 | 383 | 0 | 0% |
| 10% | 388 | 0 | 11.34% |
| 50% | 388 | 0 | 47.68% |
| 100% | 388 | 0 | 100% |

각 구간에서 필요한 서버 3대의 응답을 모두 확인했다. 전체 관측과 단계별 측정은 별도 요청이므로 수치를 더하지 않는다.
#6은 의도적인 승인 취소이며, 후속 50%·100% 단계는 실행되지 않고 v1으로 돌아왔다.
#4, #5는 복구 변수 수정 반영 과정에서 트래픽 변경 전에 중단했다.
장애 버전 주입, SSH 단절, Jenkins 중단 시나리오는 이번에 실행하지 않았다.

Artifact에는 단계별 JSON 요약, 요청별 JSONL, 배포 변수와 이전 설정이 남는다.
#7에서 검증한 코드 커밋은 `448e9f3`이다. 이후 변경은 결과 문서 정리다.
