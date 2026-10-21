# 태현 CI/CD 실습

이론 정리는 `study/`, 실습 코드는 `practice/taehyeon/`에서 관리한다.
week8에서는 성공한 배포를 직전 운영 버전으로 되돌리는 사후 롤백을 추가했다. 실행 방법과 보관·복구 범위는 [사후 롤백 실습](docs/rollback.md)을 참고한다.

기존 week7은 기존 서비스를 유지하며 새 버전 트래픽을 10% → 50% → 100%로 확대하는 카나리 배포다.
Jenkins가 단계와 실패 처리를 제어하고, Ansible이 슬롯 선택·가중치 계산·VM 변경·복구를 수행한다. Python은 HTTP 관찰과 집계만 담당한다.

아키텍처와 배포 흐름, Playbook별 역할, 모니터링 고민은 [카나리 배포 정리](docs/canary-deployment.md)에서 확인할 수 있다.

## 구성

```text
Jenkins Controller (VM 1)
  └─ Agent + Ansible (VM 2): Checkout → Gradle Test/Build → Docker Build/Test/Save
       ├─ SSH → App Server 1~3: 비활성 슬롯에 동일 이미지 배포
       └─ SSH → Nginx (VM 3): Handler가 공통 잠금 안에서 적용·검사·reload

사용자 → Nginx 1.201.116.156:18001
          ├─ app1 / app2 / app3:20001 → 슬롯 A 컨테이너:8080
          └─ app1 / app2 / app3:21001 → 슬롯 B 컨테이너:8080
```

| 슬롯 | 호스트 포트 | 컨테이너 |
| --- | --- | --- |
| A | 20001 | taehyeon-app-a |
| B | 21001 | taehyeon-app-b |

첫 실행에서는 week6의 `taehyeon-app:20001`이 기존 A 역할을 한다.
기존 앱을 삭제하지 않고 app1 B를 먼저 배포한다. A→B 승격 이후 다음 배포는 B→A로 진행한다.
다음 A 배포 때만 비활성 포트 20001의 week6 컨테이너를 정리한다.

```text
practice/taehyeon/
├── app/                         # Spring Boot, Gradle, Dockerfile
├── ansible/
│   ├── inventory/hosts.ini
│   ├── playbooks/
│   │   ├── deploy.yml           # week6 최초 기본 배포
│   │   ├── canary-state.yml     # 활성 슬롯·기존 API 검증 및 로컬 스냅샷
│   │   ├── canary-app.yml       # 지정 서버의 비활성 슬롯만 배포
│   │   ├── canary-route.yml     # 검증된 대상과 가중치를 Nginx에 적용
│   │   ├── canary-commit.yml    # 최종 검증 후 활성 슬롯 기록
│   │   └── canary-recover.yml   # 기존 라우팅·상태 복원 및 복구 검증
│   ├── tasks/canary-backends.yml # Ansible에서 슬롯·가중치 계산
│   └── roles/{app,nginx}/
├── scripts/
│   ├── observe.py               # HTTP 관찰·비율 검증·가용성 집계 전용
│   ├── verify.py                # 단일 버전 API 검증(이미지 실행 테스트)
│   ├── test-image.sh
│   └── gradle-in-docker.sh
├── tests/                       # 단위·실제 로컬 HTTP·Ansible 보호 조건 테스트
└── Jenkinsfile
```

## Jenkins 설정

- 기존 개인 배포 Job의 SCM Branch: `*/week8/taehyeon` (원격에 브랜치 반영 후 설정)
- Pipeline Script Path: `practice/taehyeon/Jenkinsfile`
- Agent Label: `ansible-agent`
- SSH Credential ID: `taehyeon-appserver-ssh`, SSH Agent 플러그인 필요
- 동일 서비스를 배포하는 개인 Job은 하나만 사용한다. `disableConcurrentBuilds()`는 같은 Job의 동시 실행을 막는다.
- Agent: Docker, Python 3, Ansible 필요. JDK 25 컨테이너에서 Gradle을 실행한다.
- App 3대와 Nginx: `taehyeon` SSH 계정, 공개키 및 기존 비밀번호 없는 sudo 권한 필요.
- Agent의 known_hosts에 App 서버 3대와 Nginx의 검증된 호스트 키가 있어야 한다. host key 검사를 끄지 않는다.
- Nginx에서 각 App 서버의 20001/21001에 접근 가능해야 한다. 두 슬롯을 동시에 실행할 자원이 필요하다.

| Parameter | 기본값 | 의미 |
| --- | --- | --- |
| ACTION | DEPLOY | 새 버전 배포 또는 직전 운영 버전 ROLLBACK |
| OBSERVE_SECONDS | 60 | baseline·각 단계·복구 관찰 시간(초) |
| MIN_SAMPLES | 100 | 각 관찰에서 필요한 최소 `/version` 응답 수 |
| MAX_RESPONSE_MS | 2000 | 개별 HTTP 요청의 최대 허용 응답 시간(ms) |

관찰은 약 0.1초 간격으로 `/health`, `/version`을 순서대로 요청한다.
관찰 시간이 끝났는데 표본이 부족하면 실패한다. 파라미터는 양의 정수여야 한다.
Jenkins의 로컬 테스트에는 Ansible/Jinja2가 같은 Python 환경에 있어야 한다.
배포 결과는 `.canary/reports/`에 생성하고 성공·실패와 관계없이 Jenkins Artifact로 보관한다.
이미지 태그는 `build-빌드번호-SHA앞12자리`이며 모든 서버에 같은 이미지를 전달한다.

## 최초 실행 전 baseline

기존 week6 기본 배포가 App 3대와 Nginx에서 정상이어야 한다.
상태 파일이 없으면 A(20001)를 조회하고, 세 서버의 두 API가 동일 메타데이터를 반환해야 한다.
Nginx를 통한 baseline 관찰도 통과해야 앱 변경을 시작한다.
아직 기본 배포가 없다면 week6 브랜치/기존 파이프라인에서 먼저 배포한다.
`deploy.yml`은 최초 기본 배포용이며, week7 승격 이후에는 실행하지 않는다.

## 카나리 실행 순서

| 단계 | 기존 버전 | 신규 버전 |
| --- | --- | --- |
| 10% | 기존 슬롯 3대, 각각 weight 3 | app1 신규 슬롯, weight 1 |
| 50% | 기존 슬롯 3대, 각각 weight 1 | app1/2/3 신규 슬롯, 각각 weight 1 |
| 100% | upstream에서 제외, 컨테이너 유지 | 신규 슬롯 3대, 각각 weight 1 |

Jenkins 화면에 아래 작업이 각각 Stage로 표시된다.

1. **Check Existing Service**: Ansible이 Nginx의 `/var/lib/taehyeon-deploy/state.json`을 읽고 실제 기존 API와 비교한다. HTTP baseline 관찰을 통과해야 배포를 시작한다.
2. **Deploy Candidate to app1**: Ansible이 app1의 비활성 슬롯에 새 이미지를 배포하고 두 API를 검사한다.
3. **Canary 10%**: Ansible이 가중치를 계산하고 Nginx에서 대상별 API를 검사한 뒤 설정을 적용한다. HTTP 관찰을 통과해야 다음 Stage로 간다.
4. **Deploy Candidate to app2 and app3**: 같은 이미지를 나머지 두 서버의 비활성 슬롯에도 배포한다.
5. **Canary 50% / Canary 100%**: 단계마다 Ansible로 전환하고 HTTP 응답을 검사한다.
6. **Record Successful Promotion**: 배포와 지속 관찰의 두 병렬 분기가 모두 성공해야 Ansible로 활성 슬롯과 새 메타데이터를 원자적으로 저장한다.

10/50% 관찰에서는 기존·신규 릴리스별 메타데이터와 허용 인스턴스를 검사한다.
신규 응답 비율은 목표 ±5%p 범위여야 하고 모든 라우팅 대상이 관찰되어야 한다.
비율과 대상별 응답 수는 `/health`와 `/version`의 모든 응답으로 집계한다.
100%에서는 신규 릴리스만 허용하고 세 인스턴스 모두 응답해야 한다.
각 요청의 버전·SHA·릴리스는 한 세트로 비교하며 `/health`와 `/version`이 같은 서버에 도착한다고 가정하지 않는다.

단계 관찰 외에도 Jenkins의 **Continuous HTTP Observation** 병렬 분기가 앱 변경 전부터 최종 전환 검증까지 지속 요청을 보낸다.
배포 분기는 `monitor.ready`를 기다리고 종료·실패·취소 시 `monitor.stop`을 기록한다.
HTTP 감시가 실패하면 `failFast`로 배포 분기를 중단하며, 승격 기록 단계는 실행하지 않는다.
HTTP/메타데이터 오류나 응답 시간 초과가 있으면 승격하지 않는다.
`proxy_next_upstream off`로 upstream 오류를 다른 서버 재시도로 가리지 않는다.

## 관측 결과

각 관찰의 `.jsonl`은 요청 시각·경로·HTTP 결과·버전·서버·응답 시간을 기록한다.
같은 이름의 `.summary.json`에는 요청 수, 실패 수, 성공률, 최대 응답 시간, 릴리스·서버별 응답 수를 저장한다.
단계별 보고서에는 신규 응답 비율과 `/version` 표본 수도 포함된다. 실패 관찰도 원본과 요약을 남긴다.
`whole-rollout.summary.json`은 실제 관측 구간의 결과이며 서비스 전체 시간의 가용성을 보증하지 않는다.

## 실패와 복구

week8의 복구 기준은 Nginx VM의 `/var/lib/taehyeon-deploy/`다. 이미지·실행 설정·개인 Nginx 설정은 `releases/<release-id>/`에, 현재/직전 운영 버전은 `state.json`에, 미완료 작업은 `pending-operation.json`에 저장한다. Jenkins 작업 폴더와 빌드 Artifacts가 없어도 서버의 자료로 복구할 수 있다.

- 배포 완료 후 장애: 같은 Jenkins Job에서 `ACTION=ROLLBACK`을 실행한다. 현재 버전의 HTTP 정상 여부를 요구하지 않고 직전 버전을 비활성 슬롯에 준비·검증한 뒤 100% 전환한다.
- 정상 이전 슬롯이 있으면 이미지 ID·실행 설정·두 API를 확인해 재사용한다. 없으면 보관 이미지의 체크섬과 ID를 검사한 뒤 같은 이미지를 재생성한다.
- 배포나 롤백 도중 실패: 서버의 pending 마커와 확정된 상태를 비교해 원래 라우팅을 복구하거나 이미 완료된 작업을 검증·정리한다. 성공한 상태를 보고서 오류만으로 되돌리지 않는다.
- Agent 유실·강제 종료: 다음 빌드가 서버의 pending 작업부터 복구하고 종료한다. 새 작업은 별도 실행한다. SSH 단절 중 즉시 복구까지 보장하지 않는다.
- 복구 검증 실패: pending을 유지하고 실패를 보고한다. 파일을 지워 검사를 우회하지 않는다.
- 최초 이관 시 예전 `.canary/reports/recovery-needed.json`이 있으면 기존 복구를 먼저 실행하고 종료한다. 이후 새 실행부터 영구 자료를 사용한다.

`canary-recover.yml`은 이전 workspace 마커의 이관 복구용이다. week8 배포의 수동 복구에는 [사후 롤백 문서](docs/rollback.md)의 `release-operation.yml` 절차를 사용한다. 기존 `canary-commit.yml`을 직접 호출해 확장 상태를 덮어쓰지 않는다.

롤백 성공 후 기본 롤백 대상은 비워 같은 버튼을 다시 눌러 장애 버전으로 왕복하지 않게 한다. 이후 새 배포가 성공하면 그 직전 운영 버전이 다시 복구 대상이 된다.

이전 슬롯은 다음 배포 전까지 유지하고 릴리스 자료는 자동 삭제하지 않는다. Nginx reload는 기존 공통 잠금 `/var/lock/nginx-cicd.lock`을 사용한다.

## 로컬 검증

표준 라이브러리 테스트(실제 로컬 HTTP 서버 포함):

```bash
python3 -m unittest discover -s practice/taehyeon/tests -p 'test_observe*.py'
```

Ansible/Jinja2가 같은 Python 환경에 있는 경우 전체 테스트를 실행한다.
로컬 검증은 Ansible Core 2.19 / Python 3.11에서 수행한다. 공유 Agent에는 테스트 때문에 패키지를 임의로 설치하지 않는다.

```bash
python3 -m unittest discover -s practice/taehyeon/tests -p 'test_*.py'
cd practice/taehyeon/ansible
ansible-playbook -i inventory/hosts.ini playbooks/deploy.yml --syntax-check
for playbook in canary-state canary-app canary-route canary-commit canary-recover release-archive release-operation rollback-prepare deployment-plan; do
  ansible-playbook -i inventory/hosts.ini "playbooks/$playbook.yml" --syntax-check
done
```

Ansible 보호 조건·가중치 테스트는 `--tags validate` / `--tags plan`으로 VM 변경 없이 실행한다. Handler 테스트는 로컬 임시 디렉터리에서 외부 서비스 명령을 대체한다.
실제 배포에서는 `--tags`로 일부 작업만 실행하지 않는다.
Nginx 설정 적용·복구 스크립트 테스트는 `flock`/GNU install이 있는 Linux에서 실행한다.

```bash
bash practice/taehyeon/tests/test-nginx-config.sh
sh practice/taehyeon/scripts/gradle-in-docker.sh test bootJar
```

Jenkinsfile의 DEPLOY/ROLLBACK 분기와 실패 처리는 Groovy 4 환경에서 검사한다. 이 테스트는 실제 Jenkins CPS·병렬 취소·플러그인 검증을 대체하지 않는다.

```bash
groovy practice/taehyeon/tests/test_pipeline.groovy
```

## 빌드와 이미지 테스트

```bash
cd practice/taehyeon/app
./gradlew test bootJar
docker build -t taehyeon-app:local .
cd ../../..
sh practice/taehyeon/scripts/test-image.sh taehyeon-app:local local local local
```

`/health`는 `status: UP`과 `version`, `gitSha`, `release`, `instance`를 반환하고,
`/version`은 같은 빌드 메타데이터를 반환한다. 새 이미지 실행 테스트에서 실패하면 VM 배포를 진행하지 않는다.
