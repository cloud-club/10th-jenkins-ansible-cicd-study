# 8주차: Failure Recovery & Rollback

이 브랜치는 도연의 기존 3대 롤링 배포에 장애 재현과 자동 롤백을 추가한다.

## 동작 순서

1. Jenkins가 새 이미지를 빌드·푸시한다.  `FAILURE_SCENARIO=health`이면 `/health`가 503과 `status=fail`을 반환하고, `startup`이면 앱 프로세스가 시작 즉시 종료한다. 기본값 `none`은 정상 이미지다.
2. 롤링 배포 전에 `snapshot.yml`이 세 서버의 직접 `/health`를 확인하고, 버전과 릴리스가 같은지 검사해 Jenkins Workspace에 기록한다. `prepare-rollback.yml`은 각 서버에서 현재 컨테이너의 **이미지 ID**를 `doyeon-app:rollback`으로 보존한다. 롤백은 레지스트리의 이전 태그나 네트워크 상태에 의존하지 않는다.
3. 기존 `rolling.yml`이 배치별로 Nginx에서 서버를 제외하고, 컨테이너를 교체한 뒤 직접 Health Check와 버전을 검사한다. 실패하면 다음 배치를 중단한다.
4. Jenkins가 배포 또는 최종 검증의 실패를 감지하면 `rollback.yml`을 실행한다. 서버별로 트래픽을 제외하고 보존 이미지를 다시 실행해 정확한 이전 버전·릴리스·서버 ID를 확인한 뒤 Nginx에 복귀시킨다. 마지막에 모든 서버와 Nginx 응답을 다시 검사한다. **배포 Job의 결과는 실패로 유지**하고 알림에 복구 성공/실패를 구분한다.
5. 정상 배포라면 `verify.yml`이 세 서버 각각의 `/health`와 Nginx 경유 `/health`를 검사한다.

롤백 이미지를 유지하기 위해 앱 서버에서 이전 이미지를 즉시 지우던 작업을 제거했다. 서버의 이미지 사용량은 별도로 관찰해야 한다. `bootstrap`은 최초 설치 모드로 롤백 대상이 없어 이 자동 복구 흐름에 포함하지 않는다.

## 재현 절차

| 순서 | Jenkins 입력 | 예상 결과 |
| --- | --- | --- |
| 정상 기준 | `APP_VERSION=v2`, `DEPLOY_MODE=rolling`, `FAILURE_SCENARIO=none` | 세 서버가 새 `v2-<빌드번호>` 릴리스로 응답 |
| Health Check 장애 | `APP_VERSION=v3`, `DEPLOY_MODE=rolling`, `FAILURE_SCENARIO=health` | 첫 배치에서 `/health` 503 감지 → Job 실패 → 이전 v2 릴리스로 복구 |
| 실행 장애 | `APP_VERSION=v3`, `DEPLOY_MODE=rolling`, `FAILURE_SCENARIO=startup` | 첫 배치에서 컨테이너 시작 실패 감지 → Job 실패 → 이전 v2 릴리스로 복구 |

`v2`가 이미 정상 동작 중이라면 첫 행은 생략할 수 있다. 확인할 때는 Jenkins Console Output에서 실패한 Ansible task, 롤백 task, 마지막 직접·Nginx 검증 결과를 차례로 기록한다. 릴리스 ID는 빌드 번호를 포함하므로 정확한 이전 `release` 값도 함께 비교한다.

## 검증 기록

| 항목 | 결과 |
| --- | --- |
| Python 단위 테스트 | `2 tests`, 통과. 정상 응답과 의도적 Health Check 실패를 확인 |
| 앱 실행 실패 | `FAILURE_SCENARIO=startup python3 main.py`가 의도대로 종료 코드 1을 반환 |
| 로컬 Docker 정상/장애 이미지 | `none` 이미지의 `/health`는 HTTP 200·`status=ok`, `health` 이미지는 HTTP 503·`status=fail`, `startup` 컨테이너는 종료 코드 1을 확인 |
| 로컬 이전 이미지 재실행 | 정상 v2 이미지에 테스트용 롤백 태그를 붙여 새 컨테이너로 실행한 뒤 `/health` HTTP 200과 이전 릴리스를 확인. Ansible/Nginx를 포함한 전체 롤백 검증은 아님 |
| Ansible 문법 | `bootstrap`, `rolling`, `snapshot`, `prepare-rollback`, `rollback`, `verify` 문법 검사 통과 |
| 가비아 VM 장애 재현 | 2026-10-19 실제 앱 서버 3대와 LB에 Ansible로 접속. 세 서버가 모두 `v2-7`임을 확인하고 각 서버의 실행 이미지에 `doyeon-app:rollback` 태그를 붙임. `linux/amd64` 장애 이미지 `v3-live-health-20261019`를 세 서버에 로드한 뒤 `rolling.yml` 실행. 첫 서버 `doyeon_app1`의 `/health`가 12회 연속 HTTP 503·`status=fail`이어서 배포가 실패 코드 2로 중단됐고, 나머지 두 서버는 교체되지 않음 |
| 가비아 VM 롤백 및 최종 검증 | 실패 직후 `rollback.yml`을 실행해 세 서버를 보존한 `v2-7` 이미지로 순차 복구. 앱 서버 3대 직접 `/version`, LB `/version` 검사 통과. 별도 `verify.yml`에서도 앱 서버 3대 직접 `/health`와 LB `/health`가 모두 `v2-7`로 통과 |
| 연속 요청 | 장애 배포와 복구를 포함한 180초 동안 LB `/version`에 766회 요청. HTTP 실패 0회, 766회 모두 `v2-7`; 앱1 130회, 앱2 322회, 앱3 314회 응답. 원본 CSV는 이 실행 환경의 `/private/tmp/doyeon-week8-live-probe-20261019.csv`에 기록 |
| Jenkins Job 통합 실행 | 개인 Job의 브랜치를 `week7/doyeon`에서 `week8/doyeon`으로 변경. 정상 빌드 #8(`v2`, `none`)이 성공해 세 서버와 Nginx가 기준 릴리스 `v2-8`로 응답. 장애 빌드 #9(`v3`, `health`)와 #10(`v3`, `startup`)은 모두 의도대로 FAILURE로 끝났고, 각각 `post` 단계에서 `rollback.yml`이 자동 실행되어 `v2-8`로 복구 |
| Jenkins 자동 롤백 시간 | #9 `health`: 첫 서버 `/health` 503 감지 후 10:30:50 롤백 시작 → 10:31:17 완료(약 27초). #10 `startup`: 첫 서버 연결 거부 감지 후 10:34:56 시작 → 10:35:25 완료(약 29초). 시각은 Jenkins 콘솔 기준(KST). 2026-10-19 콘솔 로그에서 직접 대조했고, 롤백 playbook의 앱 서버 3대와 LB 모두 failed=0 |
| Jenkins 롤백 후 검증 | 두 빌드 모두 롤백 후 앱 서버 3대 직접 `/health`와 Nginx `/health`가 `v2-8`로 통과 |
| Jenkins 연속 요청 (#9 `health`) | 약 4분(01:28:43~01:32:42 UTC) 동안 LB 요청 1,020회. HTTP 200 1,020회, 실패 0회, 전부 `v2-8`; 앱1 232회, 앱2 396회, 앱3 392회 |
| Jenkins 연속 요청 (#10 `startup`) | 약 4분(01:32:52~01:36:52 UTC) 동안 LB 요청 1,021회. HTTP 200 1,021회, 실패 0회, 전부 `v2-8`; 앱1 232회, 앱2 398회, 앱3 391회 |

실배포 결과 기록 양식:

| 빌드 URL | 장애 시나리오 | 직전 릴리스 | 첫 실패 시각 | 롤백 시작/완료 | 복구 후 3대 직접 검사 | Nginx 검사 | 요청 실패 수 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [Jenkins #9](http://1.201.117.194:8080/job/doyeon/job/deploy-pipeline/9/) | `health` | `v2-8` | 앱1 `/health` 503 감지 | 10:30:50 / 10:31:17 | 앱1·앱2·앱3 모두 `v2-8` 통과 | `/health` `v2-8` 통과 | 0/1,020 |
| [Jenkins #10](http://1.201.117.194:8080/job/doyeon/job/deploy-pipeline/10/) | `startup` | `v2-8` | 앱1 새 컨테이너 연결 거부 감지 | 10:34:56 / 10:35:25 | 앱1·앱2·앱3 모두 `v2-8` 통과 | `/health` `v2-8` 통과 | 0/1,021 |
| 로컬 Ansible 직접 실행(사전 실험) | `health` | `v2-7` | 2026-10-19 01:22:22 UTC | 실패 직후 실행, 시각 미기록 | 3대 모두 `v2-7` 통과 | 통과 | 0/766 |

## 상호 검증을 위한 코드 리뷰

`practice/minjun`의 Jenkinsfile과 `ansible/site.yml`, 앱 role, `verify.yml`을 정적으로 검토했다. 앱 서버를 `serial: 1`로 교체하고 직접 Health Check 및 Nginx 경유 버전 검증을 수행한다. 다만 교체 전 Nginx에서 해당 서버를 제외하는 단계가 없어 교체 중 요청이 그 서버에 도달할 수 있다. 배포 또는 검증이 실패했을 때 이전 이미지로 복원하는 단계도 없다. 상대방 Jenkins Job의 실제 실행과 장애 주입 검증은 아직 수행하지 않았다. 상호 실험에서는 먼저 정상 배포를 확인하고, 일부러 실패한 릴리스를 배포해 트래픽 실패 수와 수동 복구 여부를 함께 기록하면 된다.
