# 1주 차: Basic CI/CD Pipeline (기본 배포 자동화) - minjun

Jenkins와 Ansible로 **Checkout → Build → Test → Package → Deploy → Verify** 파이프라인을 구성하고,
App Server 3대에 같은 이미지를 배포한 뒤 Nginx를 통해 결과를 검증했다.

- 실행 레포: https://github.com/cynkai/jenkins-ansible-cicd (이 폴더는 커밋 `05a6ce7` 스냅샷)
- Jenkins Job: `minjun/deploy-pipeline` (Pipeline script from SCM, `*/main`)

## 할당 자원

| 항목 | 값 |
|---|---|
| Nginx 포트 | 18006 |
| App 포트 | 20006 (blue, 1주차 사용) / 21006 (green, 2주차 예정) |
| 컨테이너 | `minjun-app-blue` |
| Nginx 설정 | `/etc/nginx/conf.d/minjun.conf`, `upstream minjun_backend` |
| Agent 라벨 | `ansible-control` |
| SSH Credential | `SSH_KeyPair-cc10-cicd.pem` (공용, `ubuntu`) |

## 구조

```
.
├── app/            # 표준 라이브러리만 쓰는 최소 앱 (/health, /version)
│   └── VERSION     # 배포 버전 (v1). 바꾸고 커밋하면 새 버전 배포
├── Dockerfile      # 버전·커밋 SHA를 이미지에 고정
├── Jenkinsfile
├── scripts/test.sh # Agent에서 이미지 테스트
└── ansible/
    ├── inventory.ini        # app1~3, lb1
    ├── group_vars/all.yml   # 포트, 색(blue/green), 접두사
    ├── site.yml             # app Role → nginx Role
    ├── verify.yml           # Nginx 경유 검증
    └── roles/
        ├── app/     # 이미지 전달·로드, 컨테이너 실행, 서버별 헬스체크
        └── nginx/   # 연결 사전 확인, 락 안에서 conf 교체·검증·reload
```

## 파이프라인

| Stage | 하는 일 |
|---|---|
| Checkout | `app/VERSION`과 커밋 SHA로 이미지 태그 생성 (`v1-05a6ce7`) |
| Build | Agent에서 `docker build`. 버전·SHA를 이미지에 고정해 `/version`이 실제 배포된 이미지를 가리키게 함 |
| Test | 컨테이너를 띄워 `docker exec`로 `/health`, `/version` 검사 |
| Package | 레지스트리가 없어 `docker save`로 파일화 (workspace 안에서만) |
| Deploy | Ansible로 App 3대에 같은 이미지 배포 → 내 nginx conf 교체 |
| Verify | LB에서 18006으로 12회 호출, 버전 일치와 3대 분산 확인 |

## 공용 인프라라서 내린 결정

| 결정 | 이유 |
|---|---|
| Test에서 호스트 포트를 publish하지 않음 | 공용 Agent에서 다른 사람 테스트와 포트 충돌 방지 |
| 모든 이름에 `minjun` 접두사 (컨테이너, upstream, conf, 작업 디렉터리) | 운영 규칙 2.4. `conf.d/*.conf`는 같은 `http` 블록에 들어가므로 upstream 이름이 겹치면 `nginx -t`가 전원 실패함 |
| nginx 변경 전 LB → App 포트 연결부터 확인 | 방화벽이 막혀 있으면 reload 전에 멈춰서 공용 nginx를 깨진 상태로 두지 않음 |
| `flock` 락 안에서 `백업 → 교체 → nginx -t → reload` | 운영 규칙 2.5 "Reload 동시 실행 방지". `nginx -t`가 실패하면 내 변경만 원복 |
| conf 내용이 같으면 reload 생략 | 같은 코드 재배포 시 공용 nginx를 건드리지 않음 |
| 빌드 후 아카이브·이미지 정리 (`post { always }`) | 공용 Agent 디스크 관리 |
| `sh '''...'''` 작은따옴표 | Groovy가 아니라 셸이 실행 시점에 키 경로를 읽게 해서 명령 문자열에 비밀이 박히지 않게 함 |

`app_color`·`app_port`를 변수로 둬서, 2주차 Blue-Green은 같은 Role로 green(21006)을 배포하고 전환하는 단계만 추가하면 된다.

## 사전 환경 확인 (`minjun/recon` Job)

설계 전에 읽기 전용 명령으로 확인한 사항.

| 대상 | 결과 | 설계 반영 |
|---|---|---|
| Agent | `ubuntu`, docker 그룹 소속, ansible-core 2.21.4, `community.docker` 5.3.0 설치됨 | Agent에서 바로 `docker build` |
| App 서버 | `ubuntu`는 docker 그룹 아님, sudo 가능, docker SDK 없음 | 컨테이너 작업은 `become: true` |
| App 서버 | `community.docker.docker_host_info` 3대 SUCCESS | `docker_container` 모듈 사용 (멱등성 확보) |
| LB | 기존 `sohyeon_backend` upstream, `flock` 있음 | `minjun_backend`, flock 락 |

## 결과

### 빌드 #1 — 최초 배포

```
PLAY RECAP
app1 : ok=8  changed=5  failed=0
app2 : ok=8  changed=5  failed=0
app3 : ok=8  changed=5  failed=0
lb1  : ok=5  changed=3  failed=0

nginx apply: syntax is ok / test is successful / RELOADED
verify: versions=['v1'] counts={'app1': 5, 'app2': 4, 'app3': 3}
```

로컬에서 Nginx 경유 확인:

```
$ for i in $(seq 6); do curl -s http://<LB>:18006/version; echo; done
{"version": "v1", "git_sha": "05a6ce7", "host": "app1", "color": "blue", "port": "20006"}
{"version": "v1", "git_sha": "05a6ce7", "host": "app2", "color": "blue", "port": "20006"}
{"version": "v1", "git_sha": "05a6ce7", "host": "app3", "color": "blue", "port": "20006"}
...
```

### 빌드 #2 — 같은 커밋 재배포 (멱등성)

```
PLAY RECAP
app1 : ok=4  changed=0  skipped=4
app2 : ok=4  changed=0  skipped=4
app3 : ok=4  changed=0  skipped=4
lb1  : ok=5  changed=0

nginx apply: UNCHANGED
verify: versions=['v1'] counts={'app1': 4, 'app2': 4, 'app3': 4}
```

| | #1 | #2 |
|---|---|---|
| 이미지 복사·로드 | 실행 | skipping (이미 있음) |
| 컨테이너 | 생성 | ok (재생성 없음) |
| nginx | RELOADED | **UNCHANGED** |
| Deploy 소요 | 10.8s | 7.4s |

같은 코드를 다시 배포해도 공용 nginx를 reload하지 않는다.
또한 두 빌드의 이미지 config digest(`sha256:fcf1a2e6...`)가 같아서, 같은 커밋이면 같은 이미지가 나온다는 것도 확인했다.

## 요구사항 대조

| 요구사항 | 근거 |
|---|---|
| 개인 Job 생성, GitHub 연동 | `minjun/deploy-pipeline`, `Obtained Jenkinsfile from git` |
| Agent에서 Build / Test / Deploy | `Running on ansible-agent`, `PASS: version v1` |
| Credentials로 SSH 인증 | `withCredentials(sshUserPrivateKey)`, `--private-key ****` |
| Inventory·Playbook·Role | `roles/app`, `roles/nginx` |
| App Server 3대에 같은 이미지 | app1~3 `minjun-app-blue`, `/version` 검증 |
| Nginx 접근, `/health`·`/version` 확인 | `verify.yml` 전 항목 통과, 3대 모두 응답 |

## 관찰과 한계

- **분배 편차.** #1은 5/4/3, #2는 4/4/4. #1이 reload 직후였던 점과 관련 있어 보이지만 두 번 관찰로는 원인을 확정할 수 없다. 2주차 트래픽 기록에서는 reload 직후 여부를 함께 기록한다.
- **Verify 속도.** 12회 호출에 약 5.8초. 요청마다 Ansible의 SSH 왕복이 들어가기 때문이다. 2주차 무중단 측정은 별도 curl 루프로 한다.
- **이미지 로드 생략 기준이 "태그 존재 여부"다.** 태그에 커밋 SHA가 들어가서 현재 구조에선 안전하지만, 같은 태그로 내용이 다른 이미지가 만들어지면 구분하지 못한다.
