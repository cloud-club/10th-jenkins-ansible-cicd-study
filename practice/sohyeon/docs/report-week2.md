> 문서 역할: Jenkinsfile의 stage 순서대로 관련 파일을 읽으며, 각 파일의 역할·실행 위치·입출력과 Rolling 배포가 연결되는 방식을 이해하도록 안내한다.

# Week2 프로젝트 읽기 — Jenkins 실행 순서 따라가기

이 프로젝트의 출발점은 [Jenkinsfile](../Jenkinsfile)이다. Jenkins가 전체 실행 순서를 관리하고, 원격 서버 작업이 필요한 시점에 Ansible을 호출한다. 따라서 **Jenkinsfile에서 stage를 읽고 → 그 stage가 부르는 파일을 확인하고 → 다시 다음 stage로 돌아오는 순서**로 읽으면 된다.

이 문서는 오류 수정과 실제 배포 검증을 반영한 코드 읽기 안내서다. 2026년 10월 10일 Jenkins #24의 v1 실행과 #25의 v1→v2 실행이 정리 단계까지 성공했다. 단계별 실행 시각과 측정 근거는 [성공 실행 기록](logs-week2.md), 원본은 [#24](./%2324.txt)와 [#25](./%2325.txt)를 참고한다.

## 1. 먼저 실행 장소와 전체 흐름을 구분하기

같은 `127.0.0.1`이라도 명령이 실행되는 장소에 따라 가리키는 서버가 다르다. 아래 세 장소를 구분하고 파일을 읽어야 한다.

| 실행 장소 | 하는 일 |
| --- | --- |
| Jenkins Agent | 테스트, 이미지 빌드·검사, tar 생성, Ansible 실행, 연속 HTTP 요청, 결과 보관 준비 |
| 앱 서버 app1·app2·app3 | 이미지 로드, 컨테이너 교체, 서버 내부 Health Check |
| Nginx LB | 사용자 요청 분산, 배포 대상 제외·복귀, LB에서 앱 서버로 직접 검사 |

Ansible 명령 자체는 Agent에서 시작한다. 그러나 플레이북의 `hosts`, 태스크의 `delegate_to`에 따라 실제 작업 장소가 달라진다. 예를 들어 앱 서버를 배포하는 play 안에서도 Nginx 수정은 `delegate_to: lb_host`로 LB에서 실행한다.

배포 제어와 사용자 요청은 다음 두 흐름으로 볼 수 있다.

```text
배포 제어
Jenkins Agent
  ├─ 소스 테스트 → Docker 이미지 빌드·검사
  ├─ Ansible prepare.yml → 이미지 준비·서비스 사전 검사
  └─ probe.py
       ├─ HTTP 요청을 계속 보내며 측정
       └─ Ansible deploy.yml
            ├─ app1 제외 → 대기 → 교체 → 검사 → 복귀
            ├─ app2 제외 → 대기 → 교체 → 검사 → 복귀
            ├─ app3 제외 → 대기 → 교체 → 검사 → 복귀
            └─ verify.yml로 전체 확인

사용자 요청
사용자 또는 측정 도구 → Nginx LB :18007
                        ├─ app1 :20007 → 컨테이너 :80
                        ├─ app2 :20007 → 컨테이너 :80
                        └─ app3 :20007 → 컨테이너 :80
```

Nginx에서 제외된 서버는 새 요청 분산 대상에서 빠진다. 그동안 나머지 두 서버가 요청을 처리하고, 제외된 서버의 기존 요청까지 끝난 뒤 컨테이너를 교체한다.

## 2. 파일을 확인할 순서

처음에는 아래 순서로 읽는다. 같은 Role을 여러 단계에서 재사용하므로 모든 파일을 매번 처음부터 읽을 필요는 없다.

| 순서 | Jenkins 기준 위치 | 확인할 파일 | 읽으면서 확인할 내용 |
| --- | --- | --- | --- |
| 1 | 공통 설정 | [Jenkinsfile](../Jenkinsfile) 상단 | 실행 Agent, 파라미터, 동시 실행 제한, 작업 경로 |
| 2 | Check & Unit Test | [app/server.py](../app/server.py), [test_week2.py](../tests/test_week2.py), [test_ansible.py](../tests/test_ansible.py) | 배포할 앱의 응답과 테스트 대상 |
| 3 | Build & Test Image | [Dockerfile](../Dockerfile), [.dockerignore](../.dockerignore), [check_image.py](../scripts/check_image.py) | 이미지에 무엇을 넣고 어떻게 검사하는가 |
| 4 | Prepare Deployment | [inventory.ini](../ansible/inventory.ini), [all.yml](../ansible/group_vars/all.yml), [prepare_ssh.yml](../ansible/playbook/prepare_ssh.yml) | 어디에 접속하고 어떤 공통 값을 쓰는가 |
| 5 | Prepare Deployment | [prepare.yml](../ansible/playbook/prepare.yml), [verification Role](../ansible/roles/verification/tasks/main.yml) | 기존 서비스 확인과 이미지 사전 준비 |
| 6 | Prepare Deployment | [nginx_lb tasks](../ansible/roles/nginx_lb/tasks/main.yml), [템플릿](../ansible/roles/nginx_lb/templates/sohyeon.conf.j2), [검증 도우미](../ansible/roles/nginx_lb/files/nginx_candidate.py), [handler](../ansible/roles/nginx_lb/handlers/main.yml) | Nginx 설정 생성·검사·적용 |
| 7 | Rolling Deploy & Verify Availability | [probe.py](../scripts/probe.py) | 배포 명령과 연속 요청 측정을 함께 실행하는 방법 |
| 8 | 같은 stage 내부 | [deploy.yml](../ansible/playbook/deploy.yml), [워커 도우미](../ansible/roles/nginx_lb/files/nginx_workers.py) | 한 서버의 제외·기존 요청 종료 대기 |
| 9 | 같은 stage 내부 | [app tasks](../ansible/roles/app/tasks/main.yml), [app defaults](../ansible/roles/app/defaults/main.yml), verification Role | 컨테이너 교체와 재등록 전 검사 |
| 10 | 같은 stage 내부 | [observe.yml](../ansible/playbook/observe.yml), [verify.yml](../ansible/playbook/verify.yml) | 재등록 후 관찰과 전 서버 최종 검사 |
| 11 | Cleanup Plan & Archive / Cleanup Apply & Verify | [cleanup.yml](../ansible/playbook/cleanup.yml), [cleanup Role](../ansible/roles/cleanup/tasks/main.yml), [cleanup.py](../scripts/cleanup.py) | 삭제 계획 보관, 소유권·참조 재검사, 정리 후 서비스 검증 |
| 12 | post | Jenkinsfile 하단과 [cleanup_workspace.py](../scripts/cleanup_workspace.py) | 최종 증거 보관·임시 파일 정리 |

## 3. Jenkinsfile 상단 — 실행 규칙과 입력값

stage를 읽기 전에 다음 설정을 확인한다.

| 설정 | 현재 의미 |
| --- | --- |
| `agent { label 'ansible-agent' }` | Docker·Ansible·Python이 준비된 Agent에서 작업한다. |
| `disableConcurrentBuilds()` | 같은 job이 같은 서버에 동시에 배포하는 것을 막는다. 별도 job이나 수동 작업까지 막는 환경 잠금은 아니다. |
| `timestamps()` | Jenkins 콘솔에 실행 시각을 표시한다. |
| `timeout(...30 MINUTES)` | 전체 파이프라인 실행 시간을 제한한다. |
| `APP_VERSION` | 사람이 구분할 앱 버전이다. 예: `v1`, `v2`. |
| `BOOTSTRAP` | 기존 Week1 앱을 새 앱 v1으로 옮기는 최초 실행인지 나타낸다. |
| `PROJECT_DIR` | checkout된 저장소 안에서 이 프로젝트가 있는 경로다. 현재 값은 `.`이며 저장소 루트에서 실행한다. |
| `IMAGE_NAME` | Docker 이미지 이름이다. 현재 값은 `sohyeon-cicd-app`이다. |

Jenkins Declarative Pipeline의 기본 `Checkout SCM`이 저장소를 workspace 루트에 준비한다. 실제 성공 로그의 작업 경로는 `/var/jenkins/workspace/sohyeon/deploy-pipeline`이다. 기존의 `practice/sohyeon` 하위 경로 때문에 requirements와 정리 스크립트를 찾지 못했던 문제를 `PROJECT_DIR='.'`로 수정했다.

## 4. Stage 1 — Check & Unit Test

**실행 위치: Jenkins Agent.**

이 단계는 배포 입력값과 도구를 확인하고, 고정 버전 Galaxy 컬렉션을 프로젝트 전용 경로에 설치·검사하며, 새 이미지를 만들기 전에 코드의 기본 동작을 검사한다.

### 4-1. 필수 파일을 확인하고 배포 식별자를 만든다

먼저 `ansible.cfg`, `ansible/requirements.yml`, `scripts/cleanup.py`, `scripts/cleanup_workspace.py`의 존재를 확인한다. 통과하면 `PROJECT_READY=true`를 설정한다. 파일 확인 이전에 실패한 경우 post 정리에서 존재하지 않는 스크립트를 다시 호출하지 않는다.

`APP_VERSION`은 `v` 다음에 숫자가 오는 형식이어야 한다. `BOOTSTRAP=true`는 `APP_VERSION=v1`일 때만 허용한다.

그다음 현재 커밋과 Jenkins 빌드 번호로 이번 실행의 값을 만든다. 예를 들어 버전이 v2이고 빌드 번호가 42이면 다음과 같다.

| 값 | 예시 | 용도 |
| --- | --- | --- |
| `GIT_REVISION` | 현재 Git 커밋 전체 값 | 어떤 소스로 만들었는지 확인 |
| `RELEASE_ID` | `v2-a1b2c3d4e5f6-42` | 이미지 태그와 정확한 배포 릴리스 식별 |
| `TEST_CONTAINER` | `sohyeon-cicd-test-42` | 다음 Build stage에서 설정하는 임시 검사 컨테이너 이름 |
| `ARTIFACT_DIR` | `.artifacts/42` | 이번 실행의 파일과 측정 결과 저장 |

`APP_VERSION`과 `RELEASE_ID`를 구분하는 이유는 같은 v2라도 커밋이나 빌드가 달라질 수 있기 때문이다. 실제 배포 검증은 단순히 v2 문자열뿐 아니라 정확한 릴리스도 비교한다.

### 4-2. app/server.py를 먼저 읽는다

테스트가 무엇을 검사하는지 이해하려면 앱이 어떤 응답을 주는지 알아야 한다.

| 함수 | 역할 |
| --- | --- |
| `load_metadata()` | 이미지 안의 버전·릴리스·커밋 JSON을 읽고 필수 값을 확인한다. |
| `make_handler()`와 `do_GET()` | 서버 ID와 메타데이터를 사용해 요청 경로별 응답을 만든다. |
| `main()` | HTTP 서버를 실행하고 종료 신호를 처리한다. |

앱이 제공하는 경로는 다음과 같다.

| 경로 | 확인하는 내용 |
| --- | --- |
| `/health` | 프로세스가 HTTP 요청에 `OK`로 응답하는가 |
| `/ready` | 메타데이터와 서버 ID가 준비되어 있는가 |
| `/` | 실제 응답의 서비스명·버전·릴리스·서버 ID가 무엇인가 |
| `/version` | 이미지에 기록된 앱 버전은 무엇인가 |

예를 들어 `/` 응답의 `server_id=sohyeon-app2`, `version=v2`를 보면 app2가 v2 요청을 처리했다는 것을 알 수 있다. `/health`가 정상이어도 메타데이터나 서버 ID가 준비되지 않으면 `/ready`와 `/`는 503을 반환한다.

### 4-3. 테스트 파일을 읽는다

Jenkins는 `python3 -m unittest discover -s tests -v`로 테스트를 찾고 실행한다.

- `tests/test_week2.py`: 앱 경로와 서버 ID, 초기화 실패, 정상 종료, Nginx 도우미, 연속 요청 도구의 성공·실패 판정을 검사한다.
- `tests/test_ansible.py`: 실제 verification Role과 Nginx 템플릿, 앱 준비 완료 후에만 LB 작업을 허용하는 조건, app2 실패 후 app3 중단을 검사한다.
- `tests/test_verification.py`: 한 번의 원격 실행으로 수행하는 HTTP 검사에서 잘못된 상태·서버 ID·릴리스·버전과 legacy 응답을 거부하는지 검사한다.
- `tests/test_cleanup.py`: 소유권, 현재·이전 이미지 보호, 파일 변경·심볼릭 링크 거부, tar 내부 이미지 검사와 삭제 실패 기록을 검사한다.
- `tests/test_privileges.py`, `tests/test_galaxy.py`: 권한 상승 범위, 외부 프로젝트 거부, 실제 Docker 모듈의 강제 삭제·부모 이미지 정리 방지 옵션을 검사한다.

#24와 #25에서는 각각 50개 테스트가 실행되어 모두 통과했다. 이 수치는 당시 unittest 실행 횟수다.

이 테스트는 운영 서버에 배포하지 않는다. 통과하면 다음 stage에서 실제 Docker 이미지를 만든다. 소스 테스트와 컨테이너 이미지 검사는 서로 다른 단계다.

## 5. Stage 2 — Build & Test Image

**실행 위치: Jenkins Agent와 Agent의 임시 컨테이너.**

```text
Jenkins의 버전·커밋·릴리스
  → Dockerfile로 이미지 빌드
  → 임시 컨테이너 실행
  → check_image.py로 응답 검사
  → 검사한 이미지를 tar로 저장
  → Ansible에 전달할 release.json 작성
```

### 5-1. Dockerfile과 .dockerignore

`Dockerfile`은 Python 기본 이미지 위에 `app/server.py`를 복사한다. Jenkins가 전달한 `APP_VERSION`, `RELEASE_ID`, `GIT_REVISION`을 `/app/release.json`에 기록한다.

컨테이너가 시작되면 `python -u server.py`가 실행되고 앱이 이 파일을 읽는다. 따라서 배포 후 환경변수로 버전 이름만 바꾸는 방식이 아니다. 컨테이너 실행 시 달라지는 것은 `SERVER_ID`이며, 실제 앱 서버에서는 인벤토리 이름을 넣는다.

`.dockerignore`는 Git 정보, 인증 임시 파일, 문서와 테스트 등 이미지 빌드에 필요 없는 파일을 컨텍스트에서 제외한다.

### 5-2. scripts/check_image.py

Jenkins는 방금 만든 이미지로 임시 컨테이너를 띄우고 `SERVER_ID=image-test`를 전달한다. 이어 `docker exec -i ... python -`로 `check_image.py` 내용을 컨테이너 안에 전달해 실행한다. 이 스크립트 자체를 이미지에 복사할 필요는 없다.

스크립트가 요청하는 `127.0.0.1`은 **임시 컨테이너 자신**이다. 다음 조건을 확인한다.

1. `/ready`와 `/`가 정상 응답한다.
2. 응답의 릴리스와 버전이 Jenkins의 목표 값과 같다.
3. 서버 ID가 `image-test`다.
4. `/health`는 `OK`, `/version`은 목표 버전을 반환한다.

처음 실행되는 동안의 지연을 허용하기 위해 재시도하며, 준비 대기 기한을 넘기면 실패한다. 검사가 성공하면 임시 컨테이너를 제거한다.

### 5-3. 배포 파일을 준비한다

`docker save`로 **검사한 이미지**를 `.artifacts/빌드번호/image.tar`에 저장하고 `image.sha256`을 만든다. 앱 서버에서는 이 이미지를 `community.docker.docker_image_load`하므로 별도 빌드를 하지 않는다.

같은 디렉터리의 `release.json`에는 Ansible에 전달할 값이 들어간다.

```json
{
  "image_name": "sohyeon-cicd-app",
  "image_tag": "v2-a1b2c3d4e5f6-42",
  "app_version": "v2",
  "image_tar": "/var/jenkins/workspace/sohyeon/deploy-pipeline/.artifacts/42/image.tar",
  "bootstrap": false
}
```

이 JSON의 경로와 값은 설명용 예시다. 실제 tar 경로는 Jenkins workspace를 기준으로 계산한다.

이름이 같은 두 파일을 구분해야 한다.

| 파일 | 소비하는 쪽 | 내용 |
| --- | --- | --- |
| 이미지 내부 `/app/release.json` | `app/server.py` | 버전·릴리스·커밋 메타데이터 |
| Agent의 `.artifacts/42/release.json` | Ansible `-e @파일` | 이미지 이름·태그·tar 경로·앱 버전·bootstrap 설정 |

`image.sha256`은 생성된 tar의 체크섬 기록이다. 현재 원격 전송 검증은 Ansible `copy`가 수행하며, 플레이북이 이 SHA256 파일을 별도로 읽는 구조는 아니다.

## 6. Stage 3 — Prepare Deployment

**제어 명령은 Agent에서 시작하고, 각 태스크는 Agent·앱 서버·LB에 나뉘어 실행된다.**

### 6-1. inventory.ini와 group_vars/all.yml

`inventory.ini`는 접속 대상이다. `app_servers`에 앱 서버 세 대, `load_balancer`에 LB 한 대가 있다. `sohyeon-app1` 같은 인벤토리 이름과 `ansible_host`의 접속 IP를 구분한다. 이 인벤토리 이름이 앱 응답의 `SERVER_ID`가 된다.

`group_vars/all.yml`은 공통 설정이다. 현재는 앱 호스트 포트 `20007`, 컨테이너 포트 `80`, LB 포트 `18007`을 사용한다. health 검사 횟수, 요청 timeout, drain 제한 시간, 재등록 후 관찰 횟수도 여기서 읽는다.

Ansible은 인벤토리 옆 `group_vars`의 값을 읽고, Jenkins의 `-e @release.json`으로 이번 실행의 릴리스 정보를 받는다. 공통 인프라 값과 빌드마다 달라지는 값을 나누어 관리하는 구조다.

### 6-2. 인증 연결과 prepare_ssh.yml

Jenkins의 `withCredentials`는 `sohyeon-deploy-ssh` Credential에서 임시 키 경로와 접속 사용자명을 제공한다. 셸에서 이를 `ANSIBLE_PRIVATE_KEY_FILE`과 `ANSIBLE_REMOTE_USER`로 전달한다.

`prepare_ssh.yml`은 `hosts: localhost`, `connection: local`이므로 **Agent에서** 실행된다. 인벤토리 서버들의 공개 SSH 호스트 키를 `ssh-keyscan`으로 수집해 프로젝트의 `.ssh/known_hosts`를 만든다. 개인 인증 키를 생성하는 플레이북이 아니다.

후속 SSH 연결은 `ANSIBLE_SSH_COMMON_ARGS`로 이 파일과 `StrictHostKeyChecking=yes`를 지정한다. 기존 `ANSIBLE_SSH_ARGS` 덮어쓰기를 제거해 Ansible 기본 연결 재사용 옵션을 유지한다. [ansible.cfg](../ansible.cfg)는 연결 소켓을 `.ansible/cp`에 두고 SSH 전송 실패 재시도를 2회로 설정한다. verification 태스크의 `throttle: 1`은 같은 LB로 검사 연결이 동시에 몰리는 것을 줄인다. 공유 서버의 sshd 설정은 변경하지 않는다. 키 수집만으로 원격 인증 성공이 검증되는 것은 아니며, 실제 원격 작업에서 접속이 이루어진다.

Jenkins는 이어 `ansible-inventory --list` 결과를 `inventory.json`으로 저장한다. 이 파일은 마지막 stage의 `probe.py`가 LB 주소와 앱 서버 목록을 알아내는 데 사용한다.

### 6-3. prepare.yml의 첫 번째 play — 앱 서버 준비

첫 번째 play의 `hosts`는 `app_servers`다. 다음 순서로 실행한다.

1. runtime Role로 비 root 배포 계정과 프로젝트 전용 디렉터리·정리 도구를 준비한다.
2. 앱 3대·LB 1대와 배포 입력값을 확인하고 ownership Role로 컨테이너 이름·포트·소유권을 검사한다.
3. verification Role을 LB에서 실행해 현재 서비스를 검사하고 시작 릴리스를 기록한다. 일반 배포에서는 세 서버의 시작 릴리스가 같아야 한다.
4. 기존 컨테이너 실행 상태를 확인하고 이전 정상 이미지·컨테이너 설정을 보존한 뒤 디스크 여유 공간을 검사한다.
5. Agent의 tar를 배포 계정의 `~/.local/share/sohyeon-cicd/tmp/`에 복사하고 생성 이력을 등록한다.
6. `cleanup.py validate-archive`로 tar 안에 정확히 목표 이미지와 태그만 있는지, 소유권·릴리스 라벨이 맞는지 확인한다.
7. 권한을 올려 `community.docker.docker_image_load`를 실행하고 전송 tar를 삭제한다.
8. 해당 호스트의 `prepared_release`에 이번 릴리스를 기록한다.

여기까지는 현재 실행 중인 앱 컨테이너를 교체하지 않는다. 이미지 전달·로드는 여러 서버에서 진행할 수 있지만 **컨테이너 교체는 다음 stage의 `serial: 1` 안에서만** 수행한다.

### 6-4. verification Role — 같은 검사를 여러 위치에서 재사용한다

`ansible/roles/verification/tasks/main.yml`은 준비 단계뿐 아니라 새 앱 검사·재등록 후 관찰·최종 검증에서도 사용한다.

| 입력 변수 | 의미 |
| --- | --- |
| `check_host` | 응답에서 기대하는 앱 서버 이름 |
| `check_from` | HTTP 요청을 실행할 호스트 |
| `check_url` | 검사할 HTTP 주소 |
| `expected_release` | 반드시 일치해야 하는 목표 릴리스. 비어 있으면 현재 상태 검사 |

예를 들어 새 app1을 검사할 때는 다음 두 경로를 모두 사용한다.

```text
app1에서 요청 → 127.0.0.1:20007       : 서버 내부 앱 동작 확인
LB에서 요청   → app1의 IP:20007       : LB와 앱 사이의 접근 경로 확인
```

Role은 [verify_application.py](../ansible/roles/verification/files/verify_application.py)를 표준 입력으로 전달해 `python3 -` 한 번으로 실행한다. 원격 검사 스크립트를 별도 파일로 설치하지 않는다. `/health`, `/`, `/ready`, `/version`의 HTTP 상태와 내용, 서비스명·서버 ID·릴리스를 함께 확인하고 준비 응답과 기본 응답의 일치도 검사한다. 실패 시 기본 최대 30회 재시도와 2초 간격을 사용하며, 관찰 단계는 1회로 제한한다.

기존 Week1 문자열 응답은 `bootstrap=true`이고 목표 릴리스를 지정하지 않은 사전 검사에서만 허용한다. 새 컨테이너 검증에는 정확한 목표 릴리스를 요구한다. 각 경로마다 Ansible 원격 태스크를 실행하던 비용을 줄였으며, 필수 HTTP 검사 자체는 유지했다.

### 6-5. prepare.yml의 두 번째 play — LB 준비

두 번째 play는 `hosts: load_balancer`에서 실행된다. 먼저 앱 서버 세 대의 `prepared_release`가 모두 이번 릴리스인지 검사한다. 앱 준비 중 SSH 연결 불가가 발생했는데도 다음 LB play가 진행되던 문제를 막는 조건이다.

현재 프로젝트 설정을 읽고 제외된 서버가 남아 있지 않은지, 주소·포트가 기대한 값인지 검사한다. 설정이 예상과 다르면 모든 서버를 임의로 재등록하지 않고 실패한다.

runtime Role이 LB의 전용 `tools/`에 `nginx_workers.py`와 `nginx_candidate.py`를 복사한다. 두 파일을 설치하지 않은 채 호출하던 오류를 해결한 부분이다. 앱 서버에는 복사하지 않는다. 그다음 `nginx -t`와 현재 LB health를 검사하고 정상 설정을 `state/nginx.previous.conf`에 보존하며 워커 관측 가능 여부를 확인한다. 마지막으로 nginx_lb Role을 호출해 프로젝트 설정을 적용한다.

기존 설정의 제외 여부를 검사할 때는 주석을 제거한 뒤 `down`을 확인한다. 주석의 설명 문구를 실제 제외 설정으로 잘못 판단하던 문제를 prepare·최종 검증·정리 검사에서 수정했다.

### 6-6. nginx_lb Role에 연결된 네 파일

이 Role은 준비 단계에서 정상 upstream을 구성하고, Rolling 단계에서는 같은 코드로 서버를 제외·복귀시킨다.

| 파일 | 역할과 다음 연결 |
| --- | --- |
| `roles/nginx_lb/tasks/main.yml` | 후보 생성·이력 등록 → 후보 검사 → 실제 파일 복사·반환된 백업 등록 → 전체 설정 검사를 실행한다. |
| `templates/sohyeon.conf.j2` | 인벤토리 서버를 upstream에 넣고 `excluded_hosts`에 포함된 서버만 `down`으로 표시한다. |
| `files/nginx_candidate.py` | 기존 전체 Nginx 구성에서 프로젝트 설정만 후보로 대체한 임시 구성으로 `nginx -t`를 실행한다. |
| `handlers/main.yml` | 설정 변경 알림을 받으면 LB의 Nginx를 reload한다. |

템플릿은 검사 전 후보인 `/etc/nginx/sohyeon.candidate`를 만들고, 검증을 통과하면 `/etc/nginx/conf.d/sohyeon.conf`에 반영된다. 공용 include를 유지한 상태에서 검사하므로 upstream 조각만 단독 검사하는 방식과 다르다.

`notify: Reload Nginx`는 handler 실행을 예약한다. 호출한 플레이북의 `meta: flush_handlers`가 예약된 handler를 즉시 실행한다. 그래서 트래픽 제외가 실제로 적용되기 전에 컨테이너 교체로 넘어가지 않는다.

이 stage가 성공하면 **모든 서버에 새 이미지가 준비되어 있고 기존 서비스와 LB가 정상인 상태**다. 아직 앱 컨테이너는 이전 버전이다.

### 6-7. Docker 권한과 프로젝트 소유권을 구분한다

[ownership Role](../ansible/roles/ownership/tasks/main.yml)은 준비 단계와 컨테이너 종료 직전에 대상이 이 프로젝트의 것인지 확인한다.

- 이름은 `sohyeon-cicd-app`, 포트 바인딩은 `20007→80/tcp`로 제한한다.
- 일반 배포는 `io.sohyeon.owner=sohyeon`, `io.sohyeon.project=sohyeon-cicd` 라벨이 모두 맞아야 한다.
- 라벨 없는 Week1 컨테이너는 BOOTSTRAP이 켜져 있고, 서버별로 사전에 확인한 전체 컨테이너 ID가 일치하며, 두 소유권 라벨 키가 모두 없을 때만 예외로 허용한다.
- 기반 이미지에서 상속받은 일반 라벨은 허용하지만 다른 소유권을 나타내는 라벨은 예외로 통과시키지 않는다.

컨테이너를 재생성하면 ID가 바뀐다. 새 배포 컨테이너는 정상 소유권 라벨로 판정하므로 이후 배포마다 legacy ID를 갱신하지 않는다. Docker inspect의 전체 설정은 `no_log`로 숨기되 실패 메시지에는 이름·포트·라벨·승인 ID의 일치 여부만 표시한다.

Docker 소켓 접근 권한 오류는 원격 Docker 모듈 작업에 필요한 `become: true`를 개별 적용해 해결했다. 플레이 전체를 root로 실행하지 않으며 프로젝트 디렉터리, 상태 기록, 전송 tar와 도구는 배포 계정으로 관리한다. 정리 도구의 `SOHYEON_DOCKER_SUDO=1` 모드는 Docker 조회 명령만 `sudo -n --`로 실행하고, 원격 변경은 검사를 거친 Ansible 모듈이 담당한다. Agent는 기존 `sg docker -c` 방식으로 실행한다.

이 코드는 Docker 그룹 가입, 소켓 권한 완화, sudoers 변경을 수행하지 않는다. 배포 계정에 필요한 기존 sudo 실행 권한이 있어야 한다. 또한 공유 Nginx의 reload는 다른 서비스와 공유하는 프로세스 작업이므로, 프로젝트 설정 파일의 변경 범위와 프로세스 차원의 영향을 구분해야 한다.

## 7. Stage 4 — Rolling Deploy & Verify Availability

이 stage에서 실제 컨테이너 교체와 배포 중 가용성 측정을 함께 수행한다.

### 7-1. 먼저 probe.py가 실행된다

Jenkins가 실행하는 명령은 아래 형태다. 실제 파일에서는 inventory·버전·출력 경로 등의 인자도 전달한다.

```text
python3 scripts/probe.py [측정 옵션] -- ansible-playbook ... deploy.yml ...
```

`--` 뒤의 명령은 `probe.py`가 실행할 배포 명령이다. `probe.py`는 서버 교체 방법을 결정하지 않고, Ansible 명령을 실행하는 동안 계속 HTTP 요청을 보내는 역할을 한다.

| 함수 | 읽을 내용 |
| --- | --- |
| `run()` | 배포 전 측정 → 배포 명령 실행 → 배포 후 측정 → 최종 판정 |
| `collect()` | 별도 스레드에서 반복 요청과 JSONL 저장 |
| `sample()` | 요청 한 건의 상태·JSON·서버 ID·릴리스·응답 시간 확인 |
| `summarize()` | 성공률·오류·응답 시간·서버별 릴리스 집계 |

처음 30초 동안 LB에 요청한다. 모든 앱 서버가 관측되고 정상 응답해야 실제 배포 명령을 시작한다. 일반 배포에서는 시작 릴리스도 동일해야 한다. 이 검사를 통과하지 못하면 Ansible 배포 명령을 시작하지 않는다.

기본 요청 간격은 0.2초이며 요청 timeout은 2초다. 느린 요청이 생기면 정확히 초당 5회를 유지하지 못하므로 누락된 측정 슬롯을 별도로 기록한다.

### 7-2. deploy.yml 상단 — Rolling을 결정하는 설정

```yaml
hosts: app_servers
strategy: linear
serial: 1
order: sorted
any_errors_fatal: true
```

핵심은 `serial: 1`이다. **현재 서버의 제외부터 복귀·관찰까지 모두 마친 뒤 다음 서버를 처리한다.** `order: sorted`에 따라 현재 이름 기준 app1 → app2 → app3로 진행한다.

`any_errors_fatal: true`는 한 서버의 실패가 다음 서버 배포로 이어지지 않게 하는 설정이다. 모든 서버를 한꺼번에 제외하고 모든 컨테이너를 바꾼 뒤 다시 등록하는 구조가 아니다.

### 7-3. 제외 전 사전 확인

app1 차례라면 먼저 app2와 app3의 정상 상태, LB health, app1에 새 이미지가 준비되어 있는지 확인한다. 나머지 서버가 정상이 아니면 app1까지 제외해서 서비스 여유를 줄이지 않고 중단한다.

### 7-4. ROLLING 1 — 대상 서버 한 대를 제외한다

`nginx_workers.py snapshot`으로 기존 워커의 PID와 시작 시각을 기록한다. 이 기록은 다음 단계에서 기존 요청 처리가 끝났는지 판단하는 기준이다.

그다음 nginx_lb Role에 `excluded_hosts: [현재 서버]`를 전달한다. app1 차례라면 설정은 아래처럼 된다. 주소는 설명용이다.

```nginx
upstream sohyeon_backend {
    server APP1_IP:20007 down;
    server APP2_IP:20007;
    server APP3_IP:20007;
}
```

handler를 즉시 실행해 reload하면 새 요청은 app2와 app3로 전달된다. 앱 서버의 컨테이너는 아직 종료하지 않는다.

### 7-5. ROLLING 2 — 기존 요청이 끝날 때까지 기다린다

reload 이전에 받은 요청은 이전 워커가 계속 처리할 수 있으므로, reload 명령이 끝났다는 이유만으로 앱을 즉시 종료하지 않는다.

`nginx_workers.py`의 `workers()`는 `/proc`에서 워커의 PID와 시작 시각을 읽는다. `wait_for_drain()`은 snapshot에 있던 이전 워커가 모두 종료되고 새 워커가 있는지 확인한다. PID가 재사용될 수 있어 시작 시각도 비교한다.

이후 앱 서버에서 `wait_for`의 `state: drained`로 서비스 포트에 처리 중인 연결이 없는지 확인한다. 각 대기에는 기본 60초 제한이 있다. 시간 내에 조건을 만족하지 못하면 컨테이너를 교체하지 않고 중단한다.

이 과정이 가능한 전제는 일반 서비스 요청이 LB를 통해서만 들어온다는 것이다. 공용 LB의 다른 서비스에 긴 연결이 있으면 이전 워커 종료가 늦어져 배포가 중단될 수 있다.

### 7-6. ROLLING 3 — app Role이 컨테이너를 교체한다

여기서 [app/tasks/main.yml](../ansible/roles/app/tasks/main.yml)을 읽는다. 실제 앱 서버에서 수행하는 작업은 세 가지다.

1. `community.docker.docker_container(state=stopped, stop_timeout=30)`으로 기존 컨테이너 종료를 요청한다.
2. `community.docker.docker_container(state=absent, keep_volumes=true)`로 종료된 컨테이너를 제거한다.
3. 같은 모듈의 `state=started`, `pull=never`로 준비된 `image_name:image_tag` 컨테이너를 실행한다.

새 컨테이너에는 `SERVER_ID=inventory_hostname`, 호스트 포트와 컨테이너 포트 연결, 재시작 정책을 전달한다. 버전은 이미지 안에 이미 고정되어 있다.

`app/defaults/main.yml`에는 이미지 관련 기본값이 있다. 실제 릴리스 태그는 Jenkins가 만든 배포용 JSON에서 전달되며, 이미지 tar의 전달·로드는 앞선 prepare 단계에서 끝났다.

### 7-7. ROLLING 4 — 재등록 전에 새 앱을 확인한다

verification Role을 다시 사용한다.

- 앱 서버 내부에서 `127.0.0.1:20007`을 한 차례 검사한다. 실패 시 Role의 준비 재시도는 유지한다.
- LB에서 대상 IP의 `20007`로 직접 요청해 접근 경로까지 확인한다.
- 응답이 목표 릴리스이며 서버 ID와 버전도 맞는지 확인한다.

컨테이너가 실행 중이라는 사실만으로 재등록하지 않는다. 새 앱의 실제 응답을 검사하는 동안 사용자 트래픽은 나머지 두 서버가 처리한다.

### 7-8. ROLLING 5 — 정상 서버를 다시 등록한다

검증이 끝나면 nginx_lb Role에 `excluded_hosts: []`를 전달하고 reload한다. app1의 새 버전이 요청 분산에 다시 참여한다.

이 시점에는 다음처럼 구버전과 신버전이 함께 요청을 처리한다.

```text
LB → app1 v2 + app2 v1 + app3 v1
```

이 버전 혼재는 Rolling 배포의 정상적인 중간 상태다.

### 7-9. ROLLING 6 — 실제 트래픽 처리와 재등록 후 상태를 확인한다

LB에 `/` 요청을 반복해 **현재 서버 ID와 목표 릴리스가 반환되는 응답을 실제로 확인**한다. Nginx 설정 파일에 등록되어 있다는 사실만 확인하고 끝내지 않는다.

이후 [observe.yml](../ansible/playbook/observe.yml)을 기본 2회 실행한다. 한 번 실행할 때 다음을 수행한다.

1. LB에서 재등록된 서버로 직접 요청해 새 릴리스를 검사한다.
2. LB 경유 health를 검사한다.
3. 3초 기다린다.

검사 시간에 회당 3초 대기를 더하므로 총 6초의 명시적 대기와 실제 검사 시간이 걸린다. 이를 통과해야 `ROLLING COMPLETE` 로그가 나오고 app2 배포를 시작한다.

### 7-10. 실패하면 어떤 파일이 다음 진행을 막는가

컨테이너 교체부터 재등록 후 관찰까지는 `deploy.yml`의 `block` 안에 있다. 여기서 일반 태스크 실패가 발생하면 `rescue`로 이동한다.

`rescue`는 실패 서버를 Nginx에서 제외하고 설정을 적용한 뒤, 마지막에 `ansible.builtin.fail`을 실행한다. 제외 작업이 성공해도 원래 배포를 성공으로 바꾸지 않기 위해서다. 이 실패와 `any_errors_fatal`이 결합해 후속 서버 배포가 중단된다.

제외·drain 단계의 실패는 교체 block에 들어가기 전이므로 컨테이너 교체 자체를 시작하지 않는다. SSH 연결 불가나 프로세스 강제 종료에서는 rescue 실행을 보장하지 않는다.

Week2의 실패 처리는 **감지·제외·후속 배포 중단**이다. 이전 정상 이미지로 자동 복구하는 로직은 [Week3 설계](Week3.md)의 범위다.

### 7-11. verify.yml — 세 서버 배포 후 전체를 확인한다

`deploy.yml` 마지막의 `import_playbook: verify.yml`이 최종 검증을 연결한다. Jenkins에 별도 Verify stage를 만들지 않고 현재 stage 안에서 이어서 실행한다.

첫 play는 LB에서 각 앱 서버로 직접 접근해 세 서버 모두 목표 릴리스인지 확인한다. 두 번째 play는 LB 설정에 제외된 서버가 없는지, 등록된 주소가 맞는지, LB 응답이 목표 버전인지 확인한다.

LB 응답 한 번만 성공한 것으로 세 서버 전체가 정상이라고 판단하지 않도록, 서버별 직접 검사와 LB 검사를 함께 수행한다.

### 7-12. probe.py로 돌아와 배포 후 60초를 관측한다

Ansible 명령이 끝나면 probe는 `after` 단계로 바꾸고 60초 더 요청한다. 정상 배포 후에는 목표 릴리스만 허용하고 세 서버가 모두 관측되었는지 확인한다.

배포 중에는 서버별 기존 릴리스와 목표 릴리스의 응답을 모두 허용한다. Ansible 배포가 실패한 경우 남아 있는 정상 구버전 응답을 서비스 오류로 단정하지 않고, 배포 명령의 실패 여부를 별도로 유지한다.

`summary.json`의 `passed=true`가 되려면 관측 완료, Ansible 성공, 측정된 실패 요청 0건, 종료 후 세 서버의 목표 릴리스 관측이 필요하다. HTTP 응답이 정상이더라도 Ansible이 실패하면 probe는 실패 종료 코드를 Jenkins에 반환한다.

## 8. Cleanup stage와 post — 결과 보관 및 정리

정상 배포 뒤에는 Cleanup Plan & Archive → Cleanup Apply & Verify가 실행된다. 계획·배포 증거를 먼저 archive한 뒤 현재·직전 정상 이미지와 서비스 설정을 보호하며 정리하고 원격 서비스를 재검증한다. 배포 실패 시 정리는 건너뛰고, 정리만 실패하면 Jenkins UNSTABLE로 표시한다. 세부 범위는 [정리 정책](deployment-extensions.md)을 참고한다. 이후 Jenkinsfile의 `post`로 이어진다.

### 8-0. 삭제 계획을 먼저 보관하고 승인된 항목만 처리한다

`Cleanup Plan & Archive`는 `summary.json`의 `passed=true`를 확인하고 앱 서버·LB·Agent의 정리 계획을 생성한다. 계획과 배포 증거의 archive가 성공해야 `CLEANUP_READY=true`가 설정되고 `Cleanup Apply & Verify`로 넘어간다.

이미지는 정확한 프로젝트 저장소와 소유권 라벨을 검사한다. 현재 이미지, 직전 정상 이미지 및 다른 프로젝트·중지된 컨테이너를 포함한 모든 컨테이너의 참조 이미지를 보호한다. 삭제 직전에 소유권과 참조를 다시 검사하며, 원격 삭제는 `docker_image_remove(force=false, prune=false)`를 사용한다.

파일은 생성 시 등록한 경로와 파일 식별 정보가 일치하는 경우만 정리한다. 후보 파일은 생성 직후 등록하고, Nginx 백업은 설정 교체 모듈이 실제 반환한 `backup_file`만 등록한다. 심볼릭 링크나 미등록·변경된 파일은 삭제 대상으로 임의 채택하지 않는다. 권한이 필요한 LB 삭제는 정확한 `/etc/nginx/sohyeon.candidate`와 제한된 `sohyeon.conf` 백업 경로 형식만 허용한다. 실제 서비스 설정과 고정 복구 파일은 유지한다.

계획이 달라지거나 삭제가 실패하면 이후 삭제를 중단하고 부분 결과를 기록한다. 성공·실패 결과를 수집한 뒤 서비스도 재검증한다. 접근 로그 `/var/log/nginx/sohyeon-access.log`는 이 임시 파일 정리 대상이 아니며 기존 서버 logrotate 적용 여부는 별도 확인 사항이다.

### 8-1. always: 실행 결과 보관

산출물 디렉터리가 만들어졌다면 빌드 결과를 기록하고 지정한 파일을 Jenkins 아티팩트로 보관한다.

| 결과 파일 | 읽는 목적 |
| --- | --- |
| `prepare.log` | 사전 검사·이미지 준비가 어느 서버에서 성공하거나 실패했는지 확인 |
| `deployment.log` | UTC 시각이 붙은 서버별 제외·교체·검증·복귀 작업 확인 |
| `availability.jsonl` | 요청 한 건씩 시각·상태 코드·지연·서버·버전·릴리스·오류 확인 |
| `summary.json` | 성공률·실패 수·지연 통계·서버별 릴리스·최종 판정 확인 |
| `release.json` | 이번 Ansible 배포에 전달한 이미지와 버전 정보 확인 |
| `image.sha256` | 빌드한 이미지 tar의 체크섬 기록 확인 |
| `build-result.txt` | 보관 시점 Jenkins 빌드 결과 확인 |
| `cleanup-plan-*.json`, `cleanup-result-*.json`, `cleanup-*.log` | 보호 이미지, 삭제 목록·결과와 정리 후 서비스 검증 확인 |

초기 stage에서 실패하면 뒤 단계의 파일은 생성되지 않을 수 있다. 측정이 시작되지 않았거나 Agent가 강제로 종료돼 summary가 없다면 무중단 검증이 완료됐다고 판단하면 안 된다.

### 8-2. cleanup: 임시 자원 정리

`PROJECT_READY`가 확인된 경우에만 정리 스크립트를 실행한다. 마지막으로 이번 빌드의 테스트 컨테이너, Agent의 image tar와 inventory JSON, `.ssh/known_hosts`를 정리한다. 테스트 컨테이너도 이름만으로 제거하지 않고 프로젝트 라벨과 릴리스를 검사한다. SSH 개인 키는 Credentials 바인딩 범위에서 관리하며 아티팩트에 포함하지 않는다.

최종 archive가 성공한 산출물 폴더만 `.archived` 표시 후 workspace에서 삭제한다. archive 실패 시 원본은 보존한다. 앱 서버의 현재·직전 정상 이미지는 보호하고 그 외 미사용 프로젝트 이미지는 앞선 Cleanup stage에서 정리한다.

## 9. 실행 결과에서 Rolling과 무중단을 확인하는 방법

정식 실험은 v1이 세 서버에서 정상 동작하는 상태에서 `APP_VERSION=v2`, `BOOTSTRAP=false`로 실행한다. 기존 Week1 앱이라면 먼저 `APP_VERSION=v1`, `BOOTSTRAP=true`로 전환한다. 최초 전환의 기존 앱 응답은 측정에서 `legacy`로 표시되므로 정식 v1 → v2 결과와 구분한다.

결과는 다음 순서로 읽으면 된다.

1. **Jenkins 콘솔 또는 deployment.log**: app1의 `ROLLING COMPLETE` 뒤에 app2가, app2 완료 뒤에 app3가 시작되는지 확인한다.
2. **availability.jsonl**: 각 시각에 어떤 서버가 어떤 버전을 처리했는지 확인한다. 중간에는 v1과 v2가 함께 나와도 정상이다.
3. **summary.json**: `command_exit_code`, `observation_complete`, `failed_requests`, `http_success_rate`, `valid_success_rate`, `passed`를 확인한다.
4. **로그와 요청 시각 대조**: 제외·drain 완료·교체·재등록 시점과 서버별 응답 변화를 함께 확인한다.

Nginx는 응답의 `X-Upstream-Addr` 헤더와 `/var/log/nginx/sohyeon-access.log`에도 실제 처리 서버 주소를 남긴다. 이 LB 로그는 현재 Jenkins 아티팩트에 자동 수집되지 않으므로 필요하면 LB에서 별도로 확인한다.

자동 집계는 요청 성공률과 목표 릴리스 관측을 판정한다. 전환 타임라인과 제외 효과를 제출 자료로 설명할 때는 요청 원본·배포 로그를 함께 읽어야 한다. Agent 관점의 표본 측정 결과를 모든 네트워크와 부하에서의 무중단 보장으로 확대하지 않는다.

### 9-1. #24와 #25에서 실제로 확인한 결과

| 항목 | #24 | #25 |
| --- | --- | --- |
| 실행 설정(실행자 제공) | v1, BOOTSTRAP 체크 | v2, BOOTSTRAP 해제 |
| 실제 시작 릴리스 | `v1-2ad296ee2e48-22` | `v1-e2cbef6dde5b-24` |
| 최종 릴리스 | `v1-e2cbef6dde5b-24` | `v2-e2cbef6dde5b-25` |
| 롤링 및 최종 검증 시간 | 약 2분 21초 | 약 1분 41초 |
| 전체 측정 요청 / 실패 | 1,155 / 0 | 959 / 0 |
| 롤링 중 요청 / 실패 | 705 / 0 | 509 / 0 |
| HTTP·유효 응답 성공률 | 모두 100% | 모두 100% |
| 앱 서버별 삭제 이미지 | #21의 이전 v1 이미지 | #22의 이전 v1 이미지 |
| LB 정리 | 등록된 백업 13개 + 후보 파일 | 등록된 백업 6개 + 후보 파일 |
| Jenkins 최종 결과 | SUCCESS | SUCCESS |

#24는 BOOTSTRAP 실행이지만 시작 당시 이미 #22의 v1이 응답하고 있었다. 따라서 이 로그를 Week1 문자열 응답에서 처음 전환한 증거로 설명하지 않는다. #24는 v1 재배포부터 정리까지 전체 성공한 기록이며, #25가 그 결과를 기준으로 한 v1→v2 전환 기록이다.

두 실행 모두 app1→app2→app3 순서로 교체·복귀했고, 최종 recap에서 앱 서버 3대와 LB의 실패·연결 불가가 0이었다. 배포 후 터미널 확인에서도 세 서버가 동일한 목표 릴리스와 `ready=true`를 응답했으며 LB 12회 요청에서 각 서버가 4회씩 관측됐다. 이 터미널 결과는 실행자가 별도로 제공한 확인 자료이며 Jenkins 원본 로그와 구분한다.

50개 테스트의 통과와 별개로 실제 Docker 이미지 실행, SSH 원격 작업, Nginx 설정 적용과 가용성 측정도 완료됐다. 다만 장애 주입·자동 롤백은 이번 두 성공 실행으로 검증한 범위가 아니며, 측정한 요청 밖의 모든 트래픽에 대한 무중단을 보장하지 않는다.

## 10. 주 실행 흐름 밖의 파일

| 파일 | 언제 확인하는가 |
| --- | --- |
| [ansible/playbook/nginx.yml](../ansible/playbook/nginx.yml) | 최초 수동 Nginx 구성용이다. 현재 Jenkins의 정상 배포에서는 직접 호출하지 않는다. |
| [.gitignore](../.gitignore) | 인증 자료·산출물·Python 캐시가 Git에 들어가지 않도록 하는 규칙을 확인할 때 |
| [README.md](../README.md) | 환경 준비 조건과 Jenkins 실행 방법을 빠르게 확인할 때 |
| [Week2.md](Week2.md) | 구현 요구사항과 현재 검증 상태를 확인할 때 |
| [Week3.md](Week3.md) | 장애 주입과 이전 버전 자동 복구 설계를 이어서 공부할 때 |
| [deployment-extensions.md](deployment-extensions.md) | 구현된 정리 정책과 Galaxy 적용을 확인할 때 |
| [Week1.md](Week1.md), [report-week1.md](report-week1.md), [nginx-report.md](nginx-report.md) | 이전 Week1 구조와 기본 개념을 복습할 때 |

현재 Week2는 실제 Jenkins에서 이미지 검사, 앱 서버 3대 롤링, LB 복귀, 요청 측정, 정리 및 정리 후 검증까지 성공했다. 상세 진행 기록은 [logs-week2.md](logs-week2.md)에 정리했다.
