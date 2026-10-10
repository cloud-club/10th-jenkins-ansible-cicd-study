> 문서 역할: 프로젝트의 Rolling 배포 구조, 실행 조건, Jenkins 실행 방법과 검증 결과 읽는 법을 안내한다.

# Sohyeon CI/CD — Week2 Rolling 배포

Jenkins가 이미지를 빌드·검사하고, Ansible이 앱 서버 3대를 **한 대씩** 교체하는 실습 프로젝트다. Nginx가 배포 중인 서버를 제외한 나머지 서버로 요청을 전달한다.

```text
Jenkins: 테스트 → 이미지 빌드·검사 → 배포 준비 → Rolling 배포 + 연속 요청 측정 → 결과 보관 → 정리 계획·보관 → 정리·재검증
                                              │
Ansible: app1 제외 → 연결 종료 대기 → 교체 → 검사 → 복귀
         app2 제외 → 연결 종료 대기 → 교체 → 검사 → 복귀
         app3 제외 → 연결 종료 대기 → 교체 → 검사 → 복귀
         전 서버 목표 버전 확인
```

`ansible/playbook/deploy.yml`의 `serial: 1`과 `any_errors_fatal: true`가 순차 실행과 실패 시 중단을 제어한다. 실패한 서버는 트래픽에서 제외하고 다음 서버는 배포하지 않는다. 이전 버전 자동 복구는 Week3 범위다.

## 역할과 파일

| 파일 | 책임 |
| --- | --- |
| `Jenkinsfile` | 빌드·이미지 검사, SSH 인증 전달, Ansible 실행, 측정·아티팩트 보관 |
| `app/server.py`, `Dockerfile` | 이미지에 고정된 버전·릴리스와 실행 서버 ID 반환 |
| `ansible/playbook/prepare.yml` | 현재 서비스·LB·디스크 검사, 전 서버 새 이미지 사전 전달·로드 |
| `ansible/playbook/deploy.yml` | 한 서버의 제외부터 복귀까지 Rolling 절차 전체 |
| `ansible/playbook/observe.yml`, `verify.yml` | 재등록 후 관찰과 전 서버 최종 확인 |
| `ansible/roles/app` | 제외·drain된 서버의 컨테이너 교체 |
| `ansible/roles/nginx_lb` | 프로젝트 upstream 변경, 전체 설정 검사, reload handler |
| `ansible/roles/verification` | Health Check·readiness·서버 ID·릴리스 검사 |
| `ansible/group_vars/all.yml` | 포트·검사 재시도·drain 제한 시간 등 공통 변수 |
| `scripts/probe.py` | 배포 전·중·후 HTTP 요청과 성공률·서버별 버전 집계 |
| `tests/` | 앱·측정 도구·Nginx 보조 로직·Ansible 검증과 실패 중단 테스트 |

## 실행 조건

- 기존 Week1 서비스가 앱 서버 3대와 Nginx LB에서 정상 동작하는 환경. 최초 서버 설치는 포함하지 않는다.
- Jenkins `ansible-agent`에서 Python 3.10 이상, Ansible Core 2.16 이상, Docker·Git·SSH·Bash·`sha256sum` 사용 가능. Agent의 Docker 접근은 해당 Job의 이미지·테스트 컨테이너 범위로 운영한다.
- SSH Credential `sohyeon-deploy-ssh`. 앱 서버는 비root 배포 계정과 기존 sudo 권한, Ansible 실행 Python의 `requests`가 필요하다. Docker 모듈은 개별 작업에서 `become`을 사용하고, 정리 도우미의 Docker 조회만 `sudo -n -- docker`로 실행한다. 상태·임시 파일은 배포 계정 소유로 유지한다. LB는 기존 Ansible `become` 정책으로 심소현 설정 파일을 검사·적용·reload할 수 있어야 한다.
- 현재 inventory의 공인 IPv4 서버 주소를 사용한다. 앱 `20007`, LB `18007`을 변수로 관리한다.
- LB는 `/etc/nginx/nginx.conf`의 `include /etc/nginx/conf.d/*.conf;` 구조와 `/run/nginx.pid`를 사용한다. 다른 구조면 검증 도우미·변수를 먼저 조정한다.
- 서비스 트래픽은 LB로만 들어와야 한다. 앱 포트 직접 접근은 배포 검사에 한정한다. 남은 두 서버가 실습 트래픽을 감당할 수 있어야 한다.
- 동일 환경은 이 Jenkins job 하나로 배포하고, 공용 Nginx 설정 변경은 다른 작업자와 시간을 조율한다.

## Jenkins 실행

이 저장소는 `Jenkinsfile`, `ansible.cfg`, `ansible/`, `scripts/`가 checkout 루트에 있으므로 `PROJECT_DIR='.'`를 사용한다. 로컬의 `practice/sohyeon` 경로를 Jenkins workspace에 덧붙이지 않는다. 시작 시 필수 파일을 확인하고 누락되면 작업 경로와 누락 목록을 출력한다. 경로 검증에 실패하면 post 정리도 건너뛴다.

1. [inventory.ini](ansible/inventory.ini)와 [공통 변수](ansible/group_vars/all.yml)를 확인한다.
2. 기존 Week1 앱을 처음 전환할 때 `APP_VERSION=v1`, `BOOTSTRAP=true`로 실행한다. 기존 `/health`·`/version` 계약을 허용하면서 한 대씩 새 앱으로 교체한다.
3. 이후 `APP_VERSION=v2`, `BOOTSTRAP=false`로 실행한다. 이 실행이 정식 **v1 → v2 무중단 배포 검증**이다.
4. Jenkins 콘솔에서 `ROLLING 1`부터 `ROLLING COMPLETE`까지 app1 → app2 → app3 순서를 확인한다.
5. 빌드 아티팩트의 `summary.json`, `availability.jsonl`, `deployment.log`를 확인한다.

별도 `CONFIGURE_NGINX` 옵션은 필요 없다. 서버 제외·복귀는 매 배포 Ansible에서 자동 실행한다. `nginx.yml`은 최초 수동 구성용이며 실패 후 제외 상태를 임의로 해제하는 데 사용하지 않는다.

`APP_VERSION`과 별도로 `v2-커밋12자리-빌드번호` 형식의 릴리스를 이미지에 기록한다. `/` 응답 예시는 다음과 같다.

```json
{"service":"sohyeon-cicd-app","version":"v2","release_id":"v2-a1b2c3d4e5f6-42","git_revision":"a1b2c3d4e5f6...","server_id":"sohyeon-app2","ready":true}
```

```sh
curl http://1.201.116.156:18007/
curl http://1.201.116.156:18007/health
curl http://1.201.116.156:18007/ready
```

`/health`는 프로세스 응답, `/ready`는 메타데이터와 서버 ID 준비, `/version`은 이미지의 버전을 확인한다. 존재하지 않는 경로는 404다.

## 검증 결과 읽기

배포 전 30초부터 배포 후 60초까지 약 0.2초 간격으로 요청한다. baseline에서 세 서버가 모두 관측되고 정상이어야 실제 배포를 시작한다. 요청이 느리면 다음 요청도 늦어지므로 누락된 측정 슬롯을 별도로 기록한다.

- `availability.jsonl`: 요청 시각·단계·HTTP 상태·지연·서버·버전·릴리스·오류 원본.
- `summary.json`: HTTP/유효 응답 성공률, 실패 수, 평균·p95·최대 지연, 서버별 릴리스 집계, 관측 완료 여부와 배포 명령 종료 코드.
- `deployment.log`: UTC 시각이 붙은 Ansible 작업 로그. 서버별 제외·교체·복귀 시점과 요청 기록을 대조한다.
- LB의 `/var/log/nginx/sohyeon-access.log`: 실제 upstream 주소·상태·요청 시간. `X-Upstream-Addr` 응답 헤더에도 처리 주소가 표시된다.

정상 실험의 성공 조건은 관측 실패 0건, Ansible 성공, 종료 후 세 서버 모두 목표 릴리스 응답이다. 구버전과 신버전이 혼재하는 중간 응답은 정상이다. HTTP가 정상이어도 Ansible이 실패하면 Jenkins는 실패한다. 실패 뒤에는 자동 재시도하지 말고 제외 서버·컨테이너·Nginx를 점검한다.

Agent 관점의 표본 측정이며, 모든 네트워크 경로나 트래픽 부하에서 무중단을 보장한다는 의미는 아니다. BOOTSTRAP의 기존 응답은 서버 주소로 식별하고 버전은 `legacy`로 기록하므로 정식 v1 → v2 결과와 구분한다.

## 로컬 검사

```sh
python3 -m unittest discover -s tests -v
ansible-playbook -i ansible/inventory.ini ansible/playbook/prepare.yml --syntax-check
ansible-playbook -i ansible/inventory.ini ansible/playbook/deploy.yml --syntax-check
```

테스트는 로컬 임시 HTTP 서버와 모의 Ansible 작업을 사용하며 원격 서버에 접속하지 않는다. Docker 빌드·실제 Nginx reload·원격 Rolling 성공률은 Jenkins 환경에서 별도로 검증해야 한다.

- [Jenkins stage 순서로 읽는 Week2 프로젝트 안내](docs/report-week2.md)
- [Week2 구현 설명·검증 상태](docs/Week2.md)
- [Week1 당시 구현 기록](docs/Week1.md)
- [Week3 장애 대응·롤백 설계](docs/Week3.md)
- [배포 후 정리·Galaxy 구현](docs/deployment-extensions.md)

## 배포 후 자동 정리

성공한 배포는 `Cleanup Plan & Archive` → `Cleanup Apply & Verify`를 이어 실행한다. 삭제 계획과 배포 증거의 Jenkins 보관을 먼저 완료한 뒤, 앱 서버별 현재·직전 정상 이미지와 다른 컨테이너의 참조 이미지를 보호하면서 오래된 프로젝트 이미지를 정리한다. LB 후보·중간 백업과 프로젝트 전달 tar도 정리한다. 복구용 이미지·실행 설정 및 정상 Nginx 설정은 원격에 보존한다.

정리 결과는 `cleanup-plan-*.json`, `cleanup-result-*.json`, `cleanup-*.log`로 확인한다. 정리 실패는 Jenkins UNSTABLE이며 자동 롤백하지 않는다. 최종 archive 성공 후 workspace 보고서 중복본을 삭제하고, job의 빌드 보관 한도는 기본 30일·20개다. 공용 Docker 캐시·볼륨은 정리하지 않는다. 세부 범위와 확인법은 [배포 후 정리 정책](docs/deployment-extensions.md)을 참고한다.

공용 서버의 정리는 소유자(`sohyeon`)·프로젝트(`sohyeon-cicd`) 라벨이 확인된 Docker 자원과 배포가 직접 생성했다고 기록한 임시 파일에 한정한다. 이름만 같은 기존 자원, 미등록·변경된 파일, 다른 job의 보고서는 보존한다.

### 관리자 권한 경계

Jenkins는 호스트 키 검증 옵션을 `ANSIBLE_SSH_COMMON_ARGS`로 추가해 기본 SSH 연결 재사용(`ControlMaster`/`ControlPersist`)을 유지한다. 연결 소켓은 프로젝트 `.ansible/cp`에 두고, SSH 연결 오류에는 최대 2회 재시도한다. HTTP 검증의 원격 실행은 `throttle: 1`로 제한한다. 앱 3대 모두 이번 이미지 준비를 완료해야 LB 준비 단계가 진행된다. 서버의 sshd 설정은 변경하지 않는다.

상태·임시 파일은 배포 계정 권한으로 처리하고, Docker 모듈과 Docker 저장소 공간 검사는 개별 `become`으로 실행한다. 정리 도우미는 Docker 조회 명령에만 sudo를 사용한다. LB에서는 심소현의 `/etc/nginx/conf.d/sohyeon.conf` 후보 검증·원자적 교체·등록된 임시 파일 삭제·`nginx -t`·reload와 워커 drain에 기존 관리자 권한을 사용한다. 컨테이너 이름·소유권·포트, 이미지 tar의 태그·라벨과 삭제 대상의 소유권을 검사한다. 다른 사용자 설정 파일, 공용 `nginx.conf`, sudoers·계정 그룹·Docker 소켓 권한은 변경하지 않는다. 공용 LB reload는 다른 스터디원의 배포와 동시에 실행하지 않도록 작업 시간을 조율해야 한다.

## Ansible Galaxy

Jenkins 첫 stage가 `ansible/requirements.yml`의 `community.docker 4.8.1`을 프로젝트 전용 `.ansible/collections`에 설치하고 버전·모듈 로딩을 검사한다. 이미지 로드·조회, 앱 컨테이너 교체, 원격 이미지 삭제에 Galaxy 모듈을 사용한다. 공용 컬렉션과 Python 패키지를 자동 변경하지 않는다. 로컬 검사를 처음 실행하기 전에도 `ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections`를 실행한다. 원격 Python 의존성과 모듈별 적용 위치는 [Galaxy 구현 문서](docs/deployment-extensions.md)를 참고한다.
