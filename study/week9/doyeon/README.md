# 카나리 → 롤링 배포와 자동 롤백

`practice/doyeon/Jenkinsfile`에서 `DEPLOY_MODE=canary-rolling`을 선택한다. Jenkins는 선택한 모드에 대응하는 `playbooks/$DEPLOY_MODE.yml`을 한 번 실행한다. `canary-rolling.yml`이 카나리 준비, 1대 배포, 관찰, 잔여 2대 배포, 가중치 복원을 순서대로 묶는다. 최초 설치는 `bootstrap`, 기존 3대 롤링은 `rolling`을 사용한다. 카나리 실행 전에는 세 앱 서버가 동일한 정상 릴리스로 동작하고, 개인 Nginx upstream의 세 줄이 모두 기본 가중치 상태여야 한다.

## 배포 순서

1. Jenkins가 이미지를 빌드·테스트·푸시하고, 세 서버의 현재 이미지 ID를 `doyeon-app:rollback`으로 보존한다.
2. `start-canary.yml`이 앱1의 Nginx 가중치를 1, 앱2·앱3의 가중치를 각각 9로 설정한다. 앱1에 향하는 예상 요청 비율은 `1/(1+9+9)`, 약 5.3%다.
3. `rolling.yml`의 `rollout_phase=canary`가 앱1을 트래픽에서 제외하고 새 컨테이너로 교체해 직접 `/health`와 `/version`을 확인한 뒤 낮은 가중치로 복귀시킨다.
4. `verify-canary.yml`이 Nginx 경유 `/health`를 60회 요청한다. 모든 응답이 정상이고, 앱1은 새 릴리스, 앱2·앱3은 직전 릴리스여야 한다. 세 서버 모두 적어도 한 번 관찰되고 카나리 응답 비율이 20% 이하여야 다음 단계로 진행한다.
5. `rolling.yml`의 `rollout_phase=remaining`이 앱2·앱3을 배치 크기 1 또는 2로 교체한다. `normalize-canary.yml`이 세 서버의 가중치를 기본값으로 되돌린다. `verify.yml`이 세 서버의 직접 응답과 Nginx 응답·설정 줄을 최종 검사한다.

각 단계에서 실패하면 Jenkins의 기존 `post.failure`가 `rollback.yml`을 실행한다. 각 서버의 보존 이미지를 다시 실행하고 직접 응답을 확인한 다음 Nginx에 기본 가중치로 복귀시킨다. 마지막에 모든 서버와 Nginx의 직전 릴리스 및 기본 가중치 설정을 검사한다. 실패한 배포의 Job 결과는 실패로 남는다. `bootstrap`에는 직전 릴리스가 없어 자동 롤백하지 않는다.

## 실행과 확인

- 먼저 `APP_VERSION=v2`, `DEPLOY_MODE=rolling`, `FAILURE_SCENARIO=none`으로 기준 릴리스를 만든다.
- 다음 빌드에서 `APP_VERSION=v3`, `DEPLOY_MODE=canary-rolling`, `ROLLING_BATCH_SIZE=1`, `FAILURE_SCENARIO=none`을 선택한다. Jenkins 파라미터를 새로 등록하는 첫 빌드에서는 새 선택지가 다음 빌드부터 보일 수 있다.
- 장애 재현에는 `FAILURE_SCENARIO=health` 또는 `startup`을 선택한다. 앱1 검증에서 중단되고 직전 릴리스로 복구돼야 한다.
- 연속 요청 기록은 `python3 practice/doyeon/scripts/probe.py --duration 180 --output canary-rolling-results.csv`로 남길 수 있다. Jenkins 콘솔의 카나리 응답 수, 실패 지점, 롤백 후 직접·Nginx 검증 결과도 함께 확인한다.

2026-10-21 실제 VM에서 정상 카나리→롤링 배포와 Health Check 장애 주입 후 롤백을 실행했다. 측정값, 트래픽 CSV, Ansible 로그 및 타임아웃·재시도 설정의 근거는 [실배포 검증 기록](live-test-20261021.md)에 있다. 이 실행은 로컬 Ansible에서 수행했으며, Jenkins Job의 `post.failure` 자동 호출은 아직 실환경 검증하지 않았다.
