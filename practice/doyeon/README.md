# 박도연 1·2주차 과제: 기본 CI/CD와 롤링 배포

실제 모임 일정은 7주차지만, 과제 문서의 1주차 기본 배포와 2주차 롤링 배포 요구사항을 함께 구현한다.

- 1주차: Jenkins와 Ansible로 빌드, 테스트, 이미지 Push, App 서버 3대 배포, Nginx 경유 검증
- 2주차: 한 대씩 Nginx upstream에서 제외하고 배포한 뒤 복귀시키는 롤링 배포와 무중단 검증

## 전용 리소스

| 항목 | 값 |
| --- | --- |
| Jenkins | 박도연 개인 Folder / Job, Script Path: practice/doyeon/Jenkinsfile |
| Jenkins Agent | 공용 Agent의 개인 Job Workspace, 예제 label: ansible-agent |
| Nginx | 1.201.116.156:18005, /etc/nginx/conf.d/doyeon.conf |
| App 3대 | 1.201.118.202, 1.201.118.10, 1.201.118.90 |
| App 포트와 컨테이너 | 20005, doyeon-app |
| 예약 포트 | 21005 (현재 사용하지 않음) |

Controller 1.201.117.194와 Agent 1.201.116.180은 배포 대상이 아니다. 다른 사용자의 Job, 컨테이너, 설정 파일, 포트, Workspace는 수정하지 않는다.

## 사전 준비

1. Jenkins 개인 Folder에 Pipeline Job을 만들고 SCM Script Path를 practice/doyeon/Jenkinsfile로 지정한다. Agent label이 다르면 Jenkinsfile에서 바꾼다.
2. Jenkins Credentials에 Docker Hub Username/Token (ID: doyeon-dockerhub, 사용자명: dodopoo), 앱 서버와 Nginx에 접속할 SSH 키 (ID: doyeon-app-ssh)를 등록한다. 키와 토큰을 Git에 저장하지 않는다.
3. Docker Hub에 공개 저장소 dodopoo/doyeon-app을 만든다. Jenkins는 처음부터 이 저장소 이름으로 이미지를 빌드·Push하고, App 서버는 공개 이미지를 pull한다.
4. App 서버에 Docker, LB에 Nginx가 이미 있어야 한다. SSH 접속 계정 doyeon에는 필요한 비밀번호 없는 sudo 권한이 있어야 한다. 공용 패키지 설치·Docker 재시작은 자동화하지 않는다.
5. Nginx 개인 설정 추가와 reload는 공용 Nginx에 영향을 줄 수 있으므로 스터디원에게 먼저 공유하고 동시 변경을 피한다.

## 1주차 실행: 첫 배포

1. APP_VERSION=v1, DEPLOY_MODE=bootstrap으로 Jenkins 빌드를 실행한다. Python 테스트 → 이미지 빌드·Push → App 3대 배포·직접 검증 → 개인 Nginx 설정 반영·검증 순서다.
2. 브라우저 또는 curl로 http://1.201.116.156:18005/health 와 /version을 확인한다. 응답의 instance가 실제 요청 처리 서버다.
3. 각 App 서버의 20005 포트를 직접 조회해 3대 모두 같은 version과 release인지 확인한다.

## 2주차 실행: 롤링 배포

Jenkinsfile에 DEPLOY_MODE 파라미터를 추가한 뒤 처음 실행하는 빌드에서는 Jenkins가 새 파라미터를 등록만 한다. 빌드가 한 번 끝난 뒤 Build with Parameters에서 DEPLOY_MODE=rolling을 선택할 수 있다.

1. 먼저 1주차 첫 배포(v1)가 완료되어 있어야 한다.
2. 다음 명령으로 연속 요청 기록을 시작한다.

       python3 practice/doyeon/scripts/probe.py --duration 180 --output rolling-results.csv

3. 프로브 실행 중 APP_VERSION=v2, DEPLOY_MODE=rolling, ROLLING_BATCH_SIZE=1로 Jenkins 빌드를 실행한다. 각 서버를 개인 upstream에서 한 대씩 제외 → Nginx 검사·reload → 컨테이너 교체 → 직접 /health·/version 검증 → upstream 복귀·reload한다.
4. CSV에서 HTTP 실패 수가 0인지, 전환 중 v1·v2가 관찰되는지, instance가 3대에 분산되는지 확인한다. 완료 후 각 App 서버의 20005 포트를 직접 조회해 모두 v2인지 확인한다.

### 두 대씩 배포 실험

Jenkins의 `ROLLING_BATCH_SIZE` 기본값은 `1`이다. `DEPLOY_MODE=rolling`, `ROLLING_BATCH_SIZE=2`를 선택하면 앱1·앱2를 한 배치에서 교체한 뒤 앱3을 교체한다. 각 배치의 Nginx 설정 변경은 `run_once` 작업 하나가 `ansible_play_batch` 목록을 차례대로 수정하고, 검사·reload도 한 번씩 수행한다. 앱 컨테이너 교체와 직접 헬스체크는 배치 내 서버에서 병렬 실행한다.

두 대를 제외한 동안에는 남은 한 대만 요청을 처리한다. 현재 3대 구성에서는 그 서버가 실패하거나 용량이 부족하면 요청 실패가 생길 수 있으므로 먼저 기본값 `1`로 확인하고, 실험할 때 `probe.py` 결과와 Jenkins Console Output을 함께 기록한다. 현재 구현은 자동 롤백을 제공하지 않는다.

터미널에서 문법만 확인하려면 Agent의 `practice/doyeon/ansible` 디렉터리에서 다음처럼 실행한다. 이 명령은 서버에 배포하지 않는다.

       ansible-playbook playbooks/rolling.yml --syntax-check -e rolling_batch_size=2

## 실패 처리와 범위

- 시작 전에 App 3대의 /health를 확인한다. 하나라도 실패하면 롤링을 시작하지 않는다.
- 배포·검증 실패 시 이후 배치를 시작하지 않는다. 실패 시점에 따라 해당 배치의 Nginx 설정과 실제 트래픽 상태가 다를 수 있으므로 두 상태를 확인한 뒤 수동으로 복구한다. `ROLLING_BATCH_SIZE=2`에서는 두 서버가 함께 제외된 상태로 남을 수 있다.
- 자동 롤백은 과제 문서의 3주차 범위다. 이번 구현에는 없다.
- 상태 없는 데모 앱으로 HTTP 요청을 검증한다. 긴 요청, WebSocket, 세션, DB 스키마 변경이 있는 실제 앱은 별도 검증이 필요하다.
- 이미지 태그는 Jenkins 빌드 번호로 구분한다. 운영용 고정 식별에는 이미지 digest 사용이 더 적합하다.
- 빌드 후 Agent의 로컬 이미지와, 배포 후 App 서버의 이전 doyeon-app 이미지는 정리한다.

## 서버 접속 없는 확인

       cd practice/doyeon/app
       python3 -m unittest test_main.py -v

       cd ../ansible
       ansible-inventory --graph
       ansible-playbook playbooks/bootstrap.yml --syntax-check
       ansible-playbook playbooks/rolling.yml --syntax-check
       ansible-playbook playbooks/rolling.yml --list-hosts

실제 서버 실행은 계정·Credential·SSH 연결 및 공용 Nginx 변경 협의가 끝난 뒤 진행한다.
