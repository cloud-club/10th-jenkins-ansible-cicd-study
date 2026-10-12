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

## 2주차: Canary 배포

FastAPI로 바꾸고 `/`에 버전·서버·상태를 보여주는 Demo App 화면을 추가했다.
`/health`, `/version`은 기존 JSON 형식을 유지한다.

배포 순서는 기존 서비스 확인 → 후보 서버 3대 준비 → 10% → 승인 → 50% → 승인 → 100%다.
현재 Nginx 설정에서 활성 포트를 읽고, 20004와 21004 중 반대 포트에 후보를 배포한다.
세 서버마다 기존:후보 가중치를 9:1, 1:1로 바꾸고, 100% 단계에서는 기존 서버를 upstream에서 제외한다.

Jenkins의 VERSION을 v1으로 실행해 FastAPI 기준 버전을 준비한 뒤 v2로 실행한다.
각 단계는 60초 이상, 최소 300건을 측정한다. 오류가 없어야 하고 후보 비율은 목표의 ±5%p,
0%와 100%는 정확히 일치해야 한다. 후보 서버 세 대의 응답도 모두 확인한다.
전체 배포 중에는 별도 관측을 계속하며 오류가 나오면 후속 작업을 중단한다.

실패·취소·승인 시간 초과 시 배포 전 Nginx 설정을 복구하고 기존 릴리스를 다시 검사한다.
SSH 단절이나 Jenkins 자체 중단으로 복구가 실행되지 못할 수 있다. 이때는 이전 빌드의
`previous.conf`, `state.json`과 실제 Nginx 상태를 확인한 뒤 복구해야 한다.
기존 컨테이너는 다음 배포 때 비활성 포트를 재사용할 때까지 유지한다.

- `ansible/discover.yml`: 현재 포트와 기존 릴리스 확인
- `ansible/prepare.yml`: 후보 배포 및 LB에서 접근 검사
- `ansible/roles/traffic`: 개인 Nginx 설정, 공유 잠금, 검사와 reload
- `scripts/observe.py`: HTTP 요청 기록과 단계별 판정
- Jenkins Artifact: 단계별 JSON 요약, 요청별 JSONL, 배포 변수와 이전 설정

현재 로컬 앱·관측 테스트 8개, Ansible 문법 검사와 Jenkins 문법 검사는 통과했다.
실서버 결과는 실행 후 기록한다. 요청 표본에서 오류가 없었다는 결과가 모든 요청의 무중단을 보장하지는 않는다.
