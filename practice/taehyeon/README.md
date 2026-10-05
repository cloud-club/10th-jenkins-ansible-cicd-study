# 태현 CI/CD 실습

이론 정리는 `study/`, 실습 코드는 `practice/taehyeon/`에서 관리한다.

```text
practice/taehyeon/
├── app/                       # Spring Boot, Gradle, Dockerfile
├── ansible/
│   ├── ansible.cfg
│   ├── inventory/hosts.ini    # App Server 3대와 SSH 사용자
│   ├── playbooks/             # deploy.yml, ping.yml
│   └── roles/app/
│       ├── defaults/main.yml # 앱 포트와 배포 경로 기본값
│       └── tasks/main.yml    # 이미지 전달, 컨테이너 교체, Health Check
├── scripts/
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
- Agent에는 Docker, Python 3, Ansible과 Java 25 빌드 환경이 필요하다.
- App Server 포트: `20001`, Nginx 포트: `18001`
- Nginx 검증 단계는 개인별 Nginx 설정을 적용한 뒤 실행한다.

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
