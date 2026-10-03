# Week 6 · 김동욱 Jenkins / Ansible 배포 실습

Jenkins Agent에서 FastAPI 이미지를 빌드·테스트하고 Docker Hub에 Push한다. Ansible은 Push한 이미지의 digest를 지정해 App Server 3대에 같은 이미지를 배포한다. Nginx 및 각 서버의 `/health`, `/version` 응답으로 결과를 확인한다.

## 디렉터리

```text
dongwook/
├── README.md
├── Jenkinsfile                         # CI: 테스트·빌드 / CD: Push·배포·검증
├── .gitignore                          # 키, 환경변수, 임시 산출물 제외
├── app/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── main.py                         # 단일 FastAPI 앱: /, /health, /version
│   ├── requirements.txt                # 앱 실행 및 테스트 의존성
│   └── tests/test_main.py
├── ansible/
│   ├── ansible.cfg
│   ├── inventory/
│   │   ├── hosts.yml                   # App Server 3대 + Nginx
│   │   └── group_vars/all.yml          # 개인 이름, 포트, 컨테이너 변수
│   ├── playbooks/
│   │   ├── deploy.yml                  # App Server 순차 배포
│   │   └── render-nginx.yml            # Nginx 개인 설정을 로컬에 생성
│   └── roles/
│       ├── app/tasks/main.yml
│       └── nginx/
│           ├── tasks/main.yml
│           └── templates/dongwook.conf.j2
├── scripts/
│   └── verify.py                       # App 3대 / Nginx 상태와 release 검증
└── docs/
    ├── setup.md                        # Jenkins / SSH / Nginx 준비
    └── results.md                      # 실습 결과 기록 양식
```

`.artifacts/`는 실행 중 생성되며 Git에 포함하지 않는다. 모든 명령은 별도 안내가 없으면 이 디렉터리에서 실행한다.

## 서버와 개인 리소스

| 서버 | Public IP | 역할 |
| --- | --- | --- |
| VM 1 | `1.201.117.194` | Jenkins Controller |
| VM 2 | `1.201.116.180` | Jenkins Agent + Ansible Control Node |
| VM 3 | `1.201.116.156` | Nginx Load Balancer |
| VM 4 | `1.201.118.202` | App Server 1 |
| VM 5 | `1.201.118.10` | App Server 2 |
| VM 6 | `1.201.118.90` | App Server 3 |

| 항목 | 값 |
| --- | --- |
| Jenkins Folder / Job | `dongwook/deploy-pipeline` |
| Jenkins Agent label | `jenkins-agent` — 실제 공통 Agent label에 맞춰 수정 |
| Nginx 서비스 포트 | `18003` |
| App 호스트 포트 | `20003` |
| 추가 App 포트 | `21003` — 예약, 기본 구성에서는 사용하지 않음 |
| 컨테이너 내부 포트 | `8080` |
| 컨테이너 / Docker Hub 이미지 | `dongwook-app` / `<Docker Hub ID>/dongwook-app:<version>-<commit>-<build>` |
| Nginx 설정 / upstream | `/etc/nginx/conf.d/dongwook.conf` / `dongwook_backend` |

## 실행 흐름

1. [환경 준비](docs/setup.md)에 따라 개인 Jenkins Folder, SCM, Credentials 및 Nginx 라우팅을 준비한다.
2. Jenkins UI의 `dongwook/deploy-pipeline`에서 **Build with Parameters**로 `APP_VERSION`(기본 `v1`)을 입력한다. 첫 실행은 **Build Now**로 기본값을 사용하고 이후 파라미터 메뉴가 표시될 수 있다.
3. Agent가 GitHub 소스를 체크아웃하고 `<APP_VERSION>-<commit 12자리>-<build 번호>`를 고유한 `RELEASE_ID`이자 이미지 태그로 사용한다.
4. `CI: Python Test`에서 `test_main.py`를 실행한다. 통과하면 이미지를 한 번 빌드한 뒤 `CI: Test Image`에서 `/health`, `/version` HTTP 응답과 빌드 정보를 검사한다. 테스트 컨테이너는 호스트 포트를 사용하지 않으며 종료 시 삭제한다.
5. `dockerhub-credentials`의 Username과 액세스 토큰으로 `<Docker Hub ID>/dongwook-app`에 Push한다. Ansible은 같은 Credential로 인증하고 `repository@sha256:...` 형식으로 Pull한다. Private Repository도 지원한다.
6. 서버별 `dongwook-app` 컨테이너를 순서대로 교체하고 상태와 버전을 검사한다. 실패하면 후속 서버 배포를 중단한다.
7. Agent에서 세 App 서버와 Nginx에 직접 요청하여 표시 버전과 고유 `release`가 일치하는지 검증한다.
8. Jenkins Artifact의 `deploy-vars.json`에 이미지 digest와 빌드 정보를 보관한다. [결과 기록](docs/results.md)에 실행 URL과 응답을 남긴다.

Jenkinsfile은 `CI:`와 `CD:` 접두사가 붙은 개별 Stage로 구분한다. CI는 소스 확인 → Python 테스트 → 이미지 빌드 → 이미지 실행 테스트, CD는 Docker Hub Push → Ansible 배포 → 결과 검증 순서다. 별도 Job이나 중첩 Stage 없이 Jenkins 화면에서 각 단계의 성공·실패를 확인할 수 있다.

## 앱 구성과 이후 배포 전략 실습

앱 로직은 `app/main.py` 하나이며 업무 API, DB, 별도 서비스 계층은 없다. `/`와 `/version`은 아래 정보를 반환하고 `/health`는 여기에 `status: ok`를 추가한다. 조회 결과에는 `Cache-Control: no-store`를 지정한다.

```json
{
  "service": "dongwook-app",
  "version": "v2",
  "release": "v2-abcdef123456-7",
  "revision": "abcdef1234567890abcdef1234567890abcdef1234",
  "instance": "dongwook_app1",
  "hostname": "f3a12b4c5d6e",
  "slot": "primary"
}
```

| 필드 | 설정 시점 | 용도 |
| --- | --- | --- |
| `version` | 빌드 시 `APP_VERSION` | `v1` / `v2`처럼 실습에서 비교할 표시 버전 |
| `release` | 빌드 시 `RELEASE_ID` | 같은 `v1`을 재빌드해도 실행별 식별 가능 |
| `revision` | 빌드 시 `GIT_REVISION` | 이미지에 포함된 Git 커밋 추적 |
| `instance` | 실행 시 `INSTANCE_ID` | 응답한 App 서버 구분 |
| `hostname` | 컨테이너 hostname | 재생성된 컨테이너 구분 |
| `slot` | 실행 시 `DEPLOYMENT_SLOT` | 현재 `primary`, 추후 `blue` / `green` / `canary` 등 구분 |

버전·release·커밋은 이미지에 포함하고 서버·슬롯은 컨테이너 실행 시 주입하므로 동일 이미지를 다른 서버나 슬롯에서 재사용할 수 있다. 실제 배포 대상은 태그를 다시 해석하지 않고 Push한 digest로 고정한다.

이후 롤링 실습에서는 서버별 `release` 변경 순서, 카나리 실습에서는 Nginx 응답의 버전별 비율, 블루그린 실습에서는 `slot`과 `release` 전환을 관찰할 수 있다. 이번 변경에는 트래픽 가중치 조절, blue/green 동시 실행, 전환 및 롤백 자동화를 추가하지 않는다. 기존 `serial: 1` 순차 교체만 유지하고 추가 포트 `21003`은 예약한다. 현재 `Verify`는 모든 서버가 같은 release여야 통과하므로 향후 카나리 중간 단계 검증은 별도로 확장해야 한다.

## 로컬 실행 및 확인

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r app/requirements.txt
(cd app && ../.venv/bin/python -m unittest discover -s tests -v)

# 개발 실행: http://127.0.0.1:8080/version, /health, /docs
APP_VERSION=v1 .venv/bin/python -m uvicorn main:app --app-dir app --port 8080
```

```bash
# Agent에서 배포 전 대상 및 문법 확인 — 접속/배포하지 않음
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
ansible-inventory -i ansible/inventory/hosts.yml --graph
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/deploy.yml --list-hosts
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/deploy.yml --syntax-check

# 실제 배포 후 조회
curl --fail http://1.201.116.156:18003/health
curl --fail http://1.201.116.156:18003/version
python3 scripts/verify.py --version v1 --release '<Jenkins에서 배포한 RELEASE_ID>'
```

## 공유 환경 운영 범위

- 자신의 Folder, Workspace, `dongwook-` 리소스와 할당 포트만 사용한다. Controller와 Agent에는 Playbook을 배포하지 않는다.
- 시스템 패키지 설치, Docker 재시작, 서버 재부팅 및 다른 사용자 리소스 변경은 자동화에 포함하지 않는다.
- SSH는 Agent 실행 계정에 준비한 키와 `~/.ssh/known_hosts`를 사용한다. 대상 서버의 `authorized_keys`에 해당 공개키를 등록하고 호스트 키 확인을 유지한다. SSH 키와 `known_hosts`용 Jenkins Credential은 별도로 사용하지 않는다.
- App 서버에서는 SSH 접속 후 `become`으로 root 권한을 사용해 배포한다. 현재 Pipeline은 sudo 비밀번호를 주입하지 않으므로 접속 계정에 비밀번호 없는 sudo 권한이 필요하다.
- Docker Hub 토큰은 `--password-stdin`으로 전달한다. Agent Workspace와 원격 서버에 각각 전용 임시 Docker 설정을 만들고 작업 후 정리한다. 공통 `~/.docker/config.json`을 수정하거나 인증 파일을 Artifact로 보관하지 않는다.
- Nginx 설정은 로컬에서 생성한다. 실제 반영은 사전 공유한 작업 시간에 공통 잠금 절차로 수행한다.
- 이 예제는 컨테이너 교체 방식이며 무중단 전환이나 자동 롤백을 구현하지 않는다. 실패하면 일부 서버에 이전 버전이 남을 수 있으므로 응답을 확인한 뒤 원인을 수정하고 재배포한다.
- Docker Hub 이미지와 원격 서버의 이미지는 수동 롤백 판단을 위해 남긴다. 실습 종료 시 자신의 컨테이너와 사용하지 않는 정확한 이미지 digest만 정리한다. `docker system prune`, 전체 컨테이너 삭제 명령은 사용하지 않는다.

## 종료 후 개인 리소스 정리

진행 중인 개인 배포가 없는지 확인한 뒤 각 App Server에서 아래처럼 지정한다. 이미지 버전은 직접 확인해서 입력한다.

```bash
docker ps -a --filter name=dongwook-app
docker inspect dongwook-app --format '{{json .Config.Labels}}'
# owner=dongwook 확인 후, 본인 컨테이너만 삭제
docker rm -f dongwook-app
docker image ls --digests '<Docker Hub ID>/dongwook-app'
docker image rm '<Docker Hub ID>/dongwook-app@sha256:<정리할 digest>'
```

Nginx 개인 설정 제거도 최초 설치와 동일하게 사전 공유, 공통 잠금, `nginx -t`, Reload 순서로 진행한다.
