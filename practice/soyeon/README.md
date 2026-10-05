# Soyeon Week 1 CI/CD Practice

FastAPI 애플리케이션을 Jenkins에서 테스트하고 Docker Hub에 게시한 뒤, Ansible로 App Server 3대가 같은 이미지 digest를 pull하여 배포하는 실습입니다.

## 할당 자원

| 구분 | 값 |
| --- | --- |
| 서비스 이름 | `soyeon-app` |
| Nginx 주소 | `http://1.201.116.156:18002` |
| App Server 포트 | `20002` |
| 컨테이너 포트 | `8000` |

## 디렉터리

```text
practice/soyeon/
├── ansible/
│   ├── ansible.cfg
│   ├── inventory/hosts.ini
│   ├── playbooks/deploy.yml
│   ├── playbooks/configure-nginx.yml
│   ├── roles/app/
│   └── templates/soyeon.conf.j2
├── app/main.py
├── scripts/verify.sh
├── tests/test_main.py
├── Dockerfile
├── Jenkinsfile
├── requirements.txt
└── requirements-dev.txt
```

## API

- `GET /health`: 상태와 배포 정보 확인
- `GET /version`: 버전과 인스턴스 확인
- `GET /`: `/version`과 같은 정보 확인

## 로컬 확인

`practice/soyeon`에서 실행합니다.

```bash
docker build --target test -t soyeon-app:test .
docker build --target runtime -t soyeon-app:local .
docker run --rm -p 8000:8000 \
  -e APP_VERSION=local \
  -e RELEASE_ID=local-test \
  -e GIT_REVISION=local \
  soyeon-app:local
```

다른 터미널에서 확인합니다.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/version
```

## Jenkins 준비

1. 개인 Folder 안에 `deploy-pipeline` Pipeline Job을 만듭니다.
2. Definition을 `Pipeline script from SCM`으로 선택합니다.
3. SCM은 `Git`을 선택하고 이 저장소 URL과 브랜치를 입력합니다.
4. Script Path를 `practice/soyeon/Jenkinsfile`로 입력합니다.
5. `SSH Username with private key` 타입의 Credential을 개인 Folder 범위에 등록합니다.
6. 기본 Credential ID는 `soyeon-app-server-ssh`입니다. 다른 ID를 사용하면 빌드 파라미터에서 변경합니다.
7. Docker Hub 계정 `wosyh18`의 `cc-practice` 저장소를 **공개**로 설정합니다.
8. Docker Hub에서 발급한 Access Token을 Jenkins의 `Username with password` Credential로 등록합니다. Username에는 `wosyh18`, Password에는 Access Token을 넣습니다. 기본 ID는 `soyeon-dockerhub`입니다.
9. `DOCKERHUB_NAMESPACE` 빌드 파라미터의 기본값 `wosyh18`을 확인합니다.
10. `AGENT_LABEL`의 기본값은 공통 Jenkins Agent 이름인 `ansible-agent`입니다. 노드 이름이 바뀌면 이 값도 변경합니다.

첫 저장 후 `Build with Parameters`에서 Agent Label, namespace, 두 Credential ID를 확인합니다. Jenkins Agent는 Docker Hub에 push할 수 있어야 하고, App Server 3대는 Docker Hub에서 이미지를 pull할 수 있어야 합니다. Pipeline은 SSH 키나 Access Token을 저장소에 기록하지 않습니다.

게시되는 저장소는 `wosyh18/cc-practice`입니다. 태그는 `build-<Jenkins 빌드 번호>-<Git revision>` 형태이고, 배포에는 push 결과에서 얻은 `wosyh18/cc-practice@sha256:...` 값을 사용합니다. 따라서 서버 3대가 같은 이미지 내용으로 실행됩니다. App Server의 컨테이너 이름은 계속 `soyeon-app`입니다.

공개 저장소 기준이므로 App Server에는 Docker Hub 로그인이 필요하지 않습니다. 비공개 저장소를 쓰려면 App Server용 pull 인증을 별도로 추가해야 합니다.

## Nginx 최초 설정

Nginx 설정은 공용 서버를 reload하므로 팀원과 먼저 공유한 다음 한 번만 실행합니다. Jenkins의 일반 애플리케이션 배포에는 Nginx reload가 포함되지 않습니다.

```bash
cd ansible
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook \
  -i inventory/hosts.ini \
  -u '<SSH 사용자>' \
  --private-key '<개인 키 경로>' \
  playbooks/configure-nginx.yml
```

설정 파일은 `/etc/nginx/conf.d/soyeon.conf`만 변경하고, 반영 전에 `nginx -t`를 수행합니다.

## 배포 흐름

1. Git Checkout
2. 테스트용 Docker stage에서 `pytest` 실행
3. 런타임 Docker 이미지 한 번 빌드
4. 임시 컨테이너로 `/health` 검증
5. Docker Hub에 이미지를 push하고 응답에서 digest 확인
6. Ansible로 App Server 3대가 같은 digest를 pull
7. 각 서버에서 `soyeon-app` 컨테이너만 교체
8. 각 서버의 `/health`와 배포 버전 확인
9. Nginx `18002`를 통한 최종 확인

현재 Inventory에는 제공받은 Public IP가 들어 있습니다. 서버의 Private IP를 제공받으면 `ansible/inventory/hosts.ini`의 `ansible_host`와 Nginx upstream을 Private IP로 변경하는 것을 권장합니다.

> `ANSIBLE_HOST_KEY_CHECKING=False`는 실습 편의를 위한 설정입니다. 실제 운영에서는 Jenkins Agent의 `known_hosts`에 서버 호스트 키를 등록하고 검증을 활성화해야 합니다.
