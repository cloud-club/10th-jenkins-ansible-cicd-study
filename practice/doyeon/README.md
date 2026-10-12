# 박도연 1주차 과제: 기본 CI/CD Pipeline

Jenkins와 Ansible로 빌드, 테스트, 이미지 Push, App 서버 3대 배포, Nginx 경유 검증까지 자동화한다.

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
2. Jenkins Credentials에 Docker Hub Username/Token (ID: doyeon-dockerhub), 앱 서버와 Nginx에 접속할 SSH 키 (ID: doyeon-app-ssh)를 등록한다. 키와 토큰을 Git에 저장하지 않는다.
3. Docker Hub에 공개 저장소 계정명/doyeon-app을 만든다. 이 예제는 App 서버에서 공개 이미지를 pull한다.
4. App 서버에 Docker, LB에 Nginx가 이미 있어야 한다. SSH 접속 계정 doyeon에는 필요한 비밀번호 없는 sudo 권한이 있어야 한다. 공용 패키지 설치·Docker 재시작은 자동화하지 않는다.
5. Nginx 개인 설정 추가와 reload는 공용 Nginx에 영향을 줄 수 있으므로 스터디원에게 먼저 공유하고 동시 변경을 피한다.

## 실행

1. APP_VERSION=v1로 Jenkins 빌드를 실행한다. Python 테스트 → 이미지 빌드·Push → App 3대 배포·직접 검증 → 개인 Nginx 설정 반영·검증 순서다.
2. 브라우저 또는 curl로 http://1.201.116.156:18005/health 와 /version을 확인한다. 응답의 instance가 실제 요청 처리 서버다.
3. 각 App 서버의 20005 포트를 직접 조회해 3대 모두 같은 version과 release인지 확인한다.

## 범위

- 이미지 태그는 Jenkins 빌드 번호로 구분한다. 운영용 고정 식별에는 이미지 digest 사용이 더 적합하다.
- 상태 없는 데모 앱으로 HTTP 요청을 검증한다.
- 무중단 배포 전략은 2주차 범위이므로 이번 구현에는 없다.

## 서버 접속 없는 확인

       cd practice/doyeon/app
       python3 -m unittest test_main.py -v

       cd ../ansible
       ansible-inventory --graph
       ansible-playbook playbooks/bootstrap.yml --syntax-check
       ansible-playbook playbooks/bootstrap.yml --list-hosts

실제 서버 실행은 계정·Credential·SSH 연결 및 공용 Nginx 변경 협의가 끝난 뒤 진행한다.
