# Sohyeon CI/CD Practice

Jenkins와 Ansible을 사용해 Docker 이미지의 빌드, 테스트, 서버 배포, 배포 후 검증을 자동화하는 실습 프로젝트입니다.

Nginx 기반의 작은 앱을 서버 3대에 배포하고, 로드밸런서의 단일 주소로 요청을 전달합니다. 파일별 역할과 전체 실행 흐름은 [Week 1 상세 문서](Prj-week1.md)에 정리했습니다.

## 주요 기능

- Jenkins 빌드 번호로 Docker 이미지와 앱 버전 관리
- 임시 컨테이너에서 `/health`, `/version` 검사
- Ansible로 앱 서버 3대에 이미지 전달 및 컨테이너 교체
- Nginx를 통한 요청 분산과 배포 버전 검증

## 구성

```text
사용자 → Nginx 로드밸런서 :18007
           ├─ 앱 서버 1 :20007 → 앱 컨테이너 :80
           ├─ 앱 서버 2 :20007 → 앱 컨테이너 :80
           └─ 앱 서버 3 :20007 → 앱 컨테이너 :80
```

| 구성 요소 | 역할 |
| --- | --- |
| Jenkins | 이미지 빌드·테스트 및 배포 절차 실행 |
| Docker | 동일한 이미지로 앱 실행. 현재 이미지는 tar 파일로 전달 |
| Ansible `app` role | 앱 서버의 서비스 컨테이너 배포 |
| Ansible `nginx_lb` role | 로드밸런서의 요청 전달 규칙 설정 |
| `verify.yml` | 로드밸런서를 경유한 상태·버전 검사 |

## 디렉터리 구조

```text
.
├── README.md                 # 프로젝트 안내
├── Dockerfile                # 실습 앱 이미지
├── Jenkinsfile               # CI/CD 파이프라인
├── app/
│   └── default.conf.template # 앱 응답 및 버전 설정
├── ansible/
│   ├── inventory.ini         # 앱 서버·로드밸런서 목록
│   ├── deploy.yml            # 앱 배포
│   ├── nginx.yml             # 로드밸런서 설정
│   ├── verify.yml            # 배포 후 경유 검사
│   └── roles/
│       ├── app/              # 배포 변수와 컨테이너 교체 작업
│       └── nginx_lb/         # Nginx 설정 템플릿·task·handler
└── docs/                     # 실습 기록
```

## 로컬에서 실행하기

Docker를 사용할 수 있는 환경에서 프로젝트 루트를 기준으로 실행합니다.

```sh
docker build -t sohyeon-cicd-app:local .
docker run -d --name sohyeon-cicd-local \
  -e APP_VERSION=local \
  -p 20007:80 \
  sohyeon-cicd-app:local
```

응답을 확인합니다.

```sh
curl http://localhost:20007/
curl http://localhost:20007/health
curl http://localhost:20007/version
```

| 경로 | 기대 응답 |
| --- | --- |
| `/` | `Sohyeon Jenkins + Ansible CI/CD` |
| `/health` | `OK` |
| `/version` | `local` |

실습 후 컨테이너를 정리합니다.

```sh
docker rm -f sohyeon-cicd-local
```

## Jenkins로 배포하기

### 사전 준비

- `ansible-agent` label을 가진 Jenkins agent와 Docker·Ansible·Git·curl·SSH 도구
- agent의 Docker 소켓 접근 권한 및 `sg docker -c` 실행 환경
- 대상 서버에 접속할 Jenkins SSH credential: `sohyeon-deploy-ssh`
- 앱 서버의 Docker, 로드밸런서의 Nginx, Ansible 원격 실행 환경 및 권한 상승 권한
- agent에서 서버로의 SSH 연결과 서비스 포트 접근: 로드밸런서 `18007`, 앱 서버 `20007`

### 실행 순서

1. [inventory.ini](ansible/inventory.ini)의 서버 주소를 확인합니다. 현재 주소는 Jenkinsfile의 `Prepare SSH`와 [Nginx 템플릿](ansible/roles/nginx_lb/templates/sohyeon.conf.j2)에도 작성돼 있으므로 환경 변경 시 함께 수정합니다.
2. 저장소의 `Jenkinsfile`을 사용하는 Pipeline을 구성합니다. `PROJECT_DIR`은 현재 `${WORKSPACE}/practice/sohyeon` 구조를 전제로 하므로 checkout 위치에 맞춥니다.
3. 최초 Nginx 설정 또는 설정 변경 시 `CONFIGURE_NGINX=true`로 빌드합니다. 설정이 준비된 이후 앱만 배포할 때는 기본값 `false`를 사용합니다.
4. 파이프라인 결과와 배포된 앱의 응답을 확인합니다.

```text
Check Environment → Build → Test → Prepare Artifact → Prepare SSH
  → Deploy → Configure Nginx [선택] → Verify
```

Jenkins는 이미지 태그에 `BUILD_NUMBER`를, 앱 버전에는 `v${BUILD_NUMBER}`를 사용합니다. 예를 들어 빌드 번호가 `42`면 `/version`의 기대 응답은 `v42`입니다.

현재 inventory 기준 서비스 접속 주소는 `http://1.201.116.156:18007`입니다. 실행 중인 서버의 가용성은 별도로 확인해야 합니다.

```sh
curl http://1.201.116.156:18007/health
curl http://1.201.116.156:18007/version
```

## 현재 구현 범위

- 앱 배포는 기존 컨테이너를 제거하고 새로 실행하는 방식입니다. 무중단 배포와 자동 롤백은 구현돼 있지 않습니다.
- 서버별 앱 검사와 로드밸런서 경유 검사를 수행합니다. 경유 검사는 로드밸런서 내부에서 실행하므로 외부 사용자 접근까지 보장하지 않습니다.
- Docker·Nginx 설치와 방화벽 설정은 사전에 준비합니다.

## 상세 문서

- [Week1: 파일별 역할, role의 task 순서, URL·포트 연결, Jenkins stage 설명](docs/Week1.md)
