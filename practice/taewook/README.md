# 1주차 배포 실습

Python 기본 라이브러리로 만든 앱을 Jenkins에서 빌드하고 Ansible로 서버 3대에 배포한다.
별도 레지스트리 없이 `docker save`로 만든 이미지 파일을 전달한다.

## 구성

| 항목 | 값 |
| --- | --- |
| Jenkins Job | `taewook/deploy-pipeline` |
| Agent 라벨 | `ansible-control` |
| SSH Credential | `SSH_KeyPair-cc10-cicd.pem` (공통 `ubuntu` 계정) |
| 저장소 브랜치 | `week6/taewook` (스터디 6주차, 프로젝트 1주차) |
| Script Path | `practice/taewook/Jenkinsfile` |
| 앱 서버 | `1.201.118.202`, `1.201.118.10`, `1.201.118.90` |
| 컨테이너 / 포트 | `taewook-app`, `20004:8080` |
| Nginx | `1.201.116.156:18004` |
| Nginx 설정 | `/etc/nginx/conf.d/taewook.conf` |

## 실행 흐름

`Checkout → Preflight → Build → Test → Package → Deploy → Verify`

- SSH, sudo, Docker, Nginx 상태를 먼저 확인한다. 패키지 설치나 서비스 재시작은 하지 않는다.
- 앱 테스트 후 이미지를 빌드하고, 해당 이미지를 실행해서 `/health`, `/version`을 검사한다.
- 호스트 포트를 열지 않고 테스트 컨테이너 안에서 요청한다.
- 이미지 태그에는 버전, 커밋, 빌드 번호를 넣는다. 서버 3대에서 로드한 이미지 ID가 빌드한 이미지 ID와 같은지 확인한다.
- 세 서버의 헬스 체크와 버전 검증이 끝나면 개인 Nginx 설정을 적용한다.
- Nginx를 통해 12회 요청해서 버전 일치와 세 서버의 응답 여부를 확인한다.
- 배포 정보와 검증 결과는 Jenkins 빌드의 Artifacts에 남긴다. 임시 이미지 파일과 테스트 컨테이너는 정리한다.

## 확인 방법

```sh
curl http://1.201.116.156:18004/health
curl http://1.201.116.156:18004/version
```

`/version`은 `version`, `git_sha`, `release`, `instance`를 반환한다.
`instance`는 `app1`, `app2`, `app3` 중 하나다.

버전을 바꾸려면 `app/VERSION`을 수정하고 커밋한 뒤 Jenkins에서 다시 빌드한다.

## 공유 서버 작업 범위

컨테이너에는 `owner=taewook` 라벨을 붙인다. 같은 이름의 기존 컨테이너에 이 라벨이 없으면 배포를 중단한다.
Nginx는 개인 설정만 변경하며, 검증 실패 시 해당 설정만 복구한다.
설정 적용은 `/var/lock/nginx-cicd.lock`을 잡고 진행한다. 다른 사용자의 동시 변경까지 막으려면 모두 같은 잠금을 사용해야 한다.
SSH 키는 Jenkins가 실행 시점에 주입하며 저장소에 포함하지 않는다. SSH 호스트 키 검증도 유지한다.

1주차에는 기존 컨테이너를 교체하므로 배포 중 중단이 생길 수 있다. 무중단 배포와 앱 자동 롤백은 이번 범위에 포함하지 않는다.

## 로컬 테스트

```sh
python3 -m unittest discover -s app -p 'test_*.py' -v
```
