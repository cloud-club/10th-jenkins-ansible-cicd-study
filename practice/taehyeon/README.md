# 태현 CI/CD 실습

이론 정리는 `study/`, 실습 코드는 `practice/taehyeon/`에서 관리한다.

```text
practice/taehyeon/
├── app/                       # Spring Boot, Gradle, Dockerfile
├── ansible/
│   ├── ansible.cfg
│   ├── inventory/hosts.ini    # App Server 3대와 SSH 사용자
│   ├── playbooks/             # deploy.yml, ping.yml
│   └── roles/
│       ├── app/              # 이미지 전달, 컨테이너 교체, 빌드 정보 검증
│       └── nginx/            # 개인 설정 템플릿, 공통 잠금, 검사 및 복구
├── scripts/
│   ├── gradle-in-docker.sh    # JDK 25 컨테이너에서 Gradle 실행
│   ├── test-image.sh          # 배포 이미지 실행 테스트
│   └── verify.py              # 상태와 빌드 메타데이터 검증
└── Jenkinsfile
```

## 로컬 빌드

저장소 루트에서 실행한다.

```bash
cd practice/taehyeon/app
./gradlew test bootJar
docker build -t taehyeon-app:local .
```

## Docker 이미지 실행 테스트

저장소 루트에서 실행한다. Docker와 Python 3가 필요하다.

```bash
sh practice/taehyeon/scripts/test-image.sh taehyeon-app:local local local local
```

임시 컨테이너에 자동 배정된 로컬 포트로 접속해 `/health`의 `UP` 상태와
두 API의 버전·Git SHA·릴리스·인스턴스를 검사한다. 앱 시작은 최대 90초 기다린다.
실패하면 컨테이너 로그를 출력하며, 성공 여부와 관계없이 임시 컨테이너를 제거한다.
Jenkins에서는 Docker Build → Docker Image Test → Docker Save 순서로 실행하므로
이미지 실행 테스트가 실패하면 서버 배포를 진행하지 않는다.

## Jenkins 연결

- 브랜치: `week6/taehyeon`
- Pipeline Script Path: `practice/taehyeon/Jenkinsfile`
- Agent Label: `ansible-agent` (실제 VM 2의 Label과 일치해야 한다)
- SSH Credential ID: `taehyeon-appserver-ssh`
- Jenkinsfile의 `sshagent` 단계에는 SSH Agent 플러그인이 필요하다.
- Agent에는 Docker, Python 3, Ansible이 필요하다. 테스트와 JAR 빌드는 JDK 25 컨테이너에서 실행하므로 Agent에 Java 25를 설치할 필요가 없다.
- App Server 포트: `20001`, Nginx 포트: `18001`
- 앱 배포·검증 후 nginx Role이 개인 설정을 적용하고, Jenkins가 Nginx를 통해 최종 검증한다.

## Ansible 문법 확인

```bash
cd practice/taehyeon/ansible
ansible-playbook -i inventory/hosts.ini playbooks/deploy.yml --syntax-check
```

이미지는 Jenkins Agent에서 tar 파일로 저장한 뒤 App Server 3대로 전달한다.
SSH 개인키는 Jenkins Credentials에서 관리하며 저장소에 넣지 않는다.

## 빌드 메타데이터 검증

Jenkins는 버전에 빌드 번호, Git SHA에 체크아웃한 커밋의 전체 해시,
릴리스에 `build-빌드번호-SHA앞12자리`를 사용한다.
Docker 빌드 인자로 이미지의 환경 변수에 저장하므로 이미지 테스트와 서버 배포에서
같은 정보를 사용한다. `/health`와 `/version`은 `version`, `gitSha`, `release`,
`instance`를 반환하며 `/health`에는 `status: UP`도 포함한다.

이미지 테스트, App Server 3대의 Ansible 검증, Nginx를 통한 최종 검증에서
메타데이터가 다르면 배포 파이프라인이 실패한다. Nginx 검증은 응답한 서버의
정보를 검사하며, 세 서버 각각의 검증은 Ansible이 수행한다.

## Agent의 Java 버전과 독립적으로 빌드

Jenkins의 Test와 Build 단계는 `eclipse-temurin:25-jdk` 컨테이너에서
Gradle Wrapper를 실행한다. Agent의 Java가 21이어도 프로젝트의 Java 25를 유지한다.
Docker Hub, Gradle 배포 서버와 Maven Central에 접근할 수 있어야 한다.

저장소 루트에서 같은 빌드를 실행할 수 있다.

```bash
sh practice/taehyeon/scripts/gradle-in-docker.sh test
sh practice/taehyeon/scripts/gradle-in-docker.sh bootJar
```

앱 디렉터리를 컨테이너에 연결하므로 생성된 JAR은 기존 `app/build/libs/`에 남고,
다음 Docker Build 단계가 그대로 사용한다. Agent의 UID/GID로 실행해 결과물이
root 소유가 되는 것을 방지하며, Gradle 캐시는 `app/.gradle/ci-cache/`에 보관한다.
컨테이너는 종료 시 자동 제거된다. Agent 작업 디렉터리는 Docker daemon에서도
동일한 호스트 경로로 접근할 수 있어야 한다.

App Server의 Docker 작업(이미지 로드, 기존 컨테이너 확인·삭제, 컨테이너 실행)은
`become: true`로 실행한다. SSH 접속 계정 `taehyeon`에 비밀번호 없는 sudo 권한이
미리 허용되어 있어야 하며, 이 설정 자체가 서버 계정에 권한을 부여하지는 않는다.
이미지 파일 복사와 API 검증은 기존 SSH 계정으로 실행한다.

## Nginx Role

`roles/nginx/`의 defaults, template, tasks와 적용 스크립트로 개인 설정을 관리한다.
App Server 3대의 배포가 모두 성공해야 Nginx Play가 실행된다.
`1.201.116.156:18001`에서 세 App Server의 `20001` 포트로 요청을 분산한다.

Nginx 서버의 `taehyeon` 계정에도 SSH 공개키와 비밀번호 없는 sudo 권한이 필요하다.
서버에 설치된 Nginx가 `/etc/nginx/conf.d/*.conf`를 포함하고, `flock` 및 systemctl을
사용할 수 있어야 한다. Nginx 설치나 서비스 재시작은 수행하지 않는다.

설정은 `/tmp/taehyeon-nginx/`에 먼저 생성한다. Nginx 서버에서 세 앱의 상태와
빌드 정보를 확인한 뒤 공통 잠금 `/var/lock/nginx-cicd.lock` 안에서 개인 설정의
백업·적용·`nginx -t`·reload를 실행한다. 검사나 reload가 실패하면 개인 설정을
복구하고 파이프라인을 실패 처리한다. 설정이 같으면 reload하지 않는다.
다른 배포도 같은 잠금을 사용해야 동시 적용을 막을 수 있다.
공용 Nginx 설정 적용·reload는 스터디 운영 규칙에 맞춰 조율한다.

적용 스크립트의 로컬 테스트는 Linux 환경에서 실행한다.

```bash
bash practice/taehyeon/tests/test-nginx-config.sh
```
