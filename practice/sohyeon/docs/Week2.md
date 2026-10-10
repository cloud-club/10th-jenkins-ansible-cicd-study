> 문서 역할: Week2 Rolling 배포의 구현 구조·역할 분담·실행 절차·검증 상태를 설명한다.

# Week 2 — Rolling 무중단 배포 구현

Week2의 정상 Rolling 배포·실패 시 중단·가용성 측정을 코드로 구현했다. **로컬 검증과 실제 서버 배포 결과는 구분한다.** 실제 v1 → v2 성공률은 Jenkins 실행 후 기록한다. 장애 버전 재현·이전 버전 자동 복구는 [Week3](Week3.md), 배포 후 정리는 [정리 정책](deployment-extensions.md)에 따라 구현했고 Galaxy의 `community.docker` 모듈도 실제 배포·정리에 적용했다.

## 1. 목표와 역할 분담

앱 서버 3대 중 한 대만 Nginx에서 제외하고 기존 요청이 끝난 뒤 교체한다. 새 버전이 정상일 때만 재등록하고 다음 서버로 진행한다.

| 과제 | 구현 |
| --- | --- |
| Rolling 전략 | `deploy.yml`의 `serial: 1`, 정렬된 서버 순서, 서버별 전체 배포 절차 |
| Jenkins Pipeline | 소스 테스트·이미지 빌드와 검사·배포 준비 호출·연속 요청 측정·증거 보관 |
| Ansible Playbook | 서버 사전 검사·이미지 전달·컨테이너 교체·Nginx 제어·배포 후 검사 |
| Nginx 트래픽 제어 | `excluded_hosts`로 대상 한 대만 `down`, 검증 후 제외 목록 해제 |
| Health Check | 이미지·현재 서비스·교체 후 로컬·LB에서 직접 접근·재등록·최종 검사 |
| 실패 시 중단 | `any_errors_fatal: true`, rescue 후에도 명시적 fail |
| Role·Handler·Variable | app·nginx_lb·verification role, reload handler, group_vars |
| 무중단 검증 | 배포 전 30초·배포 중·배포 후 60초 요청, 서버 ID별 릴리스 변화 기록 |

Jenkins에는 서버별 루프나 Nginx 편집 명령을 넣지 않는다. Ansible은 원격 서버에서 이미지를 빌드하지 않고 Jenkins가 검사한 tar를 사용한다. 불필요한 stage·role을 늘리지 않도록 기존 설계의 preflight와 이미지 준비를 `prepare.yml`로, 서버별 Rolling 흐름을 `deploy.yml` 하나로 모았다.

## 2. 서버와 트래픽 흐름

```text
사용자 → Nginx :18007 → 앱 서버 :20007 → 컨테이너 :80

초기       LB → app1 v1 + app2 v1 + app3 v1
app1 교체  LB →           app2 v1 + app3 v1
app1 복귀  LB → app1 v2 + app2 v1 + app3 v1
app2 교체  LB → app1 v2 +           app3 v1
app2 복귀  LB → app1 v2 + app2 v2 + app3 v1
app3 교체  LB → app1 v2 + app2 v2
최종       LB → app1 v2 + app2 v2 + app3 v2
```

앱 컨테이너는 서버당 하나이며 추가 색상·포트를 두지 않는다. 남은 두 대가 실습 트래픽을 감당해야 하고 서비스 요청은 LB로만 들어와야 한다. 직접 앱 포트 접근은 배포 검사에 한정한다. 단일 LB 자체 장애와 DB 마이그레이션은 이번 실습 범위가 아니다.

## 3. 앱과 이미지

[server.py](../app/server.py)는 Python 표준 라이브러리로 만든 실습용 HTTP 앱이다.

| 경로 | 응답 |
| --- | --- |
| `/` | service·version·release_id·git_revision·server_id·ready JSON |
| `/health` | HTTP 요청을 처리하면 `OK`와 200 |
| `/ready` | 빌드 메타데이터·서버 ID가 준비됐으면 JSON과 200, 아니면 503 |
| `/version` | 이미지에 고정된 버전 |
| 나머지 | 404 |

Docker 빌드 시 버전·커밋·릴리스를 `/app/release.json`에 기록한다. 실행 시에는 `SERVER_ID=inventory_hostname`만 주입한다. 환경변수로 버전 표시만 바꾸지 않는다. 응답에는 `Cache-Control: no-store`를 넣고 SIGTERM 종료 시 진행 중인 요청의 처리를 기다린다.

`/health` 하나만으로 서비스 정상을 판단하지 않고 readiness·실제 응답·서버 식별·릴리스를 함께 검사한다. 앱에 존재하지 않는 DB나 외부 의존성을 검사한다고 가정하지 않는다.

## 4. Jenkins — 배포와 정리 절차 관리

[Jenkinsfile](../Jenkinsfile)의 stage는 다음과 같다.

| Stage | 작업 |
| --- | --- |
| Check & Unit Test | 입력값·도구 확인, 고정 Galaxy 컬렉션 설치·로딩 검사, 커밋/릴리스 식별, 로컬 테스트 |
| Build & Test Image | 이미지 빌드, 임시 컨테이너에서 실제 응답 검사, tar·SHA256 생성 |
| Prepare Deployment | SSH 준비, inventory 조회, Ansible 사전 검사·이미지 준비 |
| Rolling Deploy & Verify Availability | probe가 배포 전 측정 → Ansible Rolling/최종 검증 → 배포 후 측정을 실행 |
| Cleanup Plan & Archive | 서비스 재확인, 보호 이미지·삭제 목록 작성, 증거 사전 보관 |
| Cleanup Apply & Verify | 앱·LB·Agent 정리, 원격 서비스 재검증. 오류는 UNSTABLE |

같은 job은 `disableConcurrentBuilds()`로 직렬화하고 전체 실행 시간은 30분으로 제한한다. 동일 서버를 조작하는 별도 job이나 수동 변경을 동시에 실행하지 않는다. 공용 Nginx 작업은 다른 작업자와 조율한다.

파라미터는 `APP_VERSION`과 `BOOTSTRAP` 두 개다. 버전은 `v1`, `v2`처럼 지정하고 릴리스는 `버전-커밋12자리-빌드번호`로 구분한다. `BOOTSTRAP=true`는 기존 Week1 앱을 v1으로 옮길 때만 허용한다.

`post / always`에서 빌드 결과·요청 원본·집계·배포 로그·릴리스 정보·체크섬을 아티팩트로 보관한다. `post / cleanup`에서는 해당 빌드의 테스트 컨테이너·tar·inventory 임시 파일·known_hosts를 정리한다. 최종 archive가 성공한 보고서 중복본은 workspace에서 삭제한다. 정상 배포 뒤 원격 이미지 정리는 현재·직전 정상 이미지를 보호하며 실행한다.

SSH 키는 기존 Jenkins Credential `sohyeon-deploy-ssh`를 `withCredentials`로 전달한다. SSH 구간은 셸 tracing을 끄고 키나 환경 전체를 출력하지 않는다. `.ssh`, inventory 전체, 키 파일은 아티팩트 패턴에 포함하지 않는다. Jenkins/Agent 강제 종료로 증거가 누락되면 실제 실행 결과와 함께 기록한다.

## 5. Ansible — 준비와 서버별 Rolling

공통 변수는 [group_vars/all.yml](../ansible/group_vars/all.yml)에 모았다. 서버 포트·LB 포트·검사 timeout·재시도·drain 제한 시간·재등록 관찰 횟수를 한 곳에서 조정한다.

### 준비: prepare.yml

1. 앱 3대·LB 1대와 릴리스 입력값을 확인한다.
2. LB에서 현재 앱 세 대의 health·ready·실제 응답·버전을 검사한다. 일반 배포는 시작 릴리스가 모두 같아야 한다.
3. 기존 컨테이너 실행과 tar/Docker 저장소 여유 공간을 검사한다. 디스크 검사는 부하 수용 능력 검사를 대신하지 않는다.
4. 모든 서버에 tar를 전송·로드한다. 전송은 Ansible copy의 체크섬 검증을 사용하고 기존 컨테이너는 유지한다.
5. LB 설정의 앱 주소·포트·등록 상태를 확인한다. 제외 서버가 남았으면 설정을 초기화하지 않고 실패한다.
6. 프로젝트 Nginx 설정·관측 도우미를 준비하고 reload한다.

준비 중 실패하면 Rolling stage로 넘어가지 않는다. 운영 서버에서 빌드하지 않으며 이미지 전달 때문에 서버가 제외된 채 오래 기다리지 않도록 한다.

### 순차 배포: deploy.yml

```yaml
hosts: app_servers
strategy: linear
serial: 1
order: sorted
any_errors_fatal: true
```

정렬된 inventory 이름 기준 app1 → app2 → app3 순서로 다음 작업 전체를 수행한다.

1. 나머지 두 서버와 LB health, 대상에 준비된 이미지를 확인한다.
2. **ROLLING 1:** 기존 Nginx 워커를 기록하고 대상 한 대만 upstream에서 제외한다.
3. **ROLLING 2:** reload handler를 즉시 실행하고 기존 워커 종료·앱 포트 연결 종료를 확인한다.
4. **ROLLING 3:** app role로 기존 컨테이너를 정상 종료·삭제하고 검사된 이미지로 새 컨테이너를 실행한다.
5. **ROLLING 4:** 로컬에서 한 차례 검사하고 LB에서 대상 앱으로 직접 접근해 목표 릴리스와 서버 ID를 확인한다.
6. **ROLLING 5:** 검증된 서버를 upstream에 다시 등록하고 즉시 reload한다.
7. **ROLLING 6:** LB 경유 요청에서 해당 서버의 목표 릴리스를 실제 관측한다. 이어 2회 직접·LB 검사와 회당 3초 대기로 관찰한다.
8. **ROLLING COMPLETE:** 이 서버의 모든 검증이 끝난 뒤 다음 서버를 시작한다.

완료 후 `verify.yml`이 전 서버 목표 릴리스, 모든 upstream 등록, LB 실제 응답을 확인한다. 재등록 이후 반복 검사는 `observe.yml`에 두고 health·ready·응답 검사는 공통 verification role로 재사용한다. 이 역할은 Python 코드를 표준 입력으로 전달해 한 번의 원격 실행에서 HTTP 경로를 모두 검사하므로 별도 도우미 설치가 필요 없다.

## 6. Nginx — 제외·복귀와 기존 요청 완료 확인

[템플릿](../ansible/roles/nginx_lb/templates/sohyeon.conf.j2)은 `excluded_hosts`에 포함된 서버만 `down`으로 표시한다. 포트는 공통 변수를 사용한다. 앱 서버의 제외·복귀 작업은 `delegate_to`로 LB에서 실행한다.

설정 적용은 후보 생성 → 전체 구성 문법 검사 → 프로젝트 파일의 원자적 교체 → 실제 구성 검사 → handler 즉시 실행 순서다. 후보는 `conf.d/*.conf` 밖에 두고, 검증용 main config에서는 기존 프로젝트 파일만 후보로 대체한다. 다른 conf.d 파일과 sites-enabled 등 공용 include를 유지한다. 예상한 include 구조가 아니면 적용하지 않는다.

reload 자체는 기존 요청 완료를 뜻하지 않는다. `nginx_workers.py`는 `/proc`에서 기존 워커의 PID와 시작 시각을 기록하고 reload 뒤 이전 워커가 모두 종료되고 새 워커가 있는지 확인한다. 이후 앱 서버의 `wait_for: state=drained`로 연결이 없는지 확인한다. 고정 sleep만으로 교체 시점을 판단하지 않는다. [Nginx reload 동작](https://nginx.org/en/docs/control.html)

기한은 60초다. 공용 LB의 다른 서비스에 긴 연결이 있으면 보수적으로 배포가 중단될 수 있다. 공용 워커를 강제 종료하거나 timeout을 줄이지 않는다. `/run/nginx.pid`, `/proc` 관측 권한, 표준 Nginx include 구조가 사전 조건이다. 일반 배포에서 `become: true`는 심소현의 Nginx 후보·설정 파일 검사·교체·reload와 워커 drain에만 사용한다.

## 7. 실패 시 처리

| 실패 | 동작 |
| --- | --- |
| 이미지 테스트·준비·baseline 측정 | 원격 컨테이너 교체 시작 안 함 |
| 대상 제외·drain | 컨테이너 교체 안 함, 다음 서버 중단 |
| 새 컨테이너 실행·검증 | 대상 제외 유지, 명시적 fail로 후속 서버 중단 |
| 재등록 후 검증 | 제어 가능하면 다시 제외하고 다음 서버 중단 |
| 최종 fleet 검사·가용성 기준 미달 | Jenkins 실패, 결과 보관 |
| SSH 단절·Jenkins 중단 | 확인되지 않은 서버를 자동 재등록하지 않음, 수동 상태 점검 필요 |

rescue는 트래픽 제외와 오류 반환만 수행한다. 이전 버전 자동 복구는 하지 않는다. rescue가 성공해도 마지막 fail로 원래 배포를 실패 처리한다. unreachable이나 프로세스 강제 중단은 rescue 실행을 보장하지 않으므로 실패 후 재실행 전 실제 컨테이너·Nginx를 점검한다.

## 8. 기존 Week1 → v1 → v2 실행

기존 Week1 앱에는 `/ready`와 서버 ID JSON이 없으므로 최초 전환만 기존 계약을 허용한다.

1. 기존 Week1의 앱 3대·Nginx 서비스가 정상인지 확인한다.
2. Jenkins에서 `APP_VERSION=v1`, `BOOTSTRAP=true`로 실행한다.
3. 기존 앱은 health·version으로, 교체된 앱은 새 JSON·ready 계약으로 확인한다. 기존 응답의 처리 서버는 `X-Upstream-Addr`와 LB 로그로 식별한다.
4. v1 전환 성공 후 `APP_VERSION=v2`, `BOOTSTRAP=false`로 실행한다.
5. 이 v1 → v2 실행의 콘솔·아티팩트로 과제를 검증한다.

최초 앱 설치나 서버 프로비저닝은 별도다. BOOTSTRAP은 기존 서비스가 없는 서버를 자동 설치하는 기능이 아니다.

## 9. 연속 요청과 결과 판정

[scripts/probe.py](../scripts/probe.py)는 Jenkins Agent에서 배포 명령을 감싸 실행한다. 독립적인 측정 스레드가 배포 전 30초부터 배포 종료 후 60초까지 `/`에 요청한다. 기본 간격은 0.2초, 요청 timeout은 2초다. 요청이 느려져 측정하지 못한 슬롯은 별도로 기록한다.

baseline에서 모든 서버가 정상 응답하고 관측되어야 Ansible 배포를 시작한다. 배포 중에는 서버별 기존 릴리스와 목표 릴리스를 허용하고, 배포 명령 성공 후에는 목표 릴리스만 허용한다. 배포 명령 실패 후 남은 구버전의 정상 응답을 서비스 장애로 오인하지 않으며 배포 결과는 별도로 실패 처리한다.

| 파일/지표 | 의미 |
| --- | --- |
| `availability.jsonl` | UTC 요청·완료 시각, before/rolling/after, HTTP 상태, 오류, 지연, 서버·버전·릴리스, upstream |
| `summary.json` | HTTP 성공률, 유효 응답 성공률, 오류 수, 평균·p95·최대 지연, 서버별 릴리스 집계, 단계별 요청 수 |
| `deployment.log` | UTC 시각과 서버별 Ansible 작업. 요청 원본과 대조해 전환 흐름 확인 |
| `observation_complete` | 배포 전·후 관측 구간 완료 여부 |
| `command_exit_code` | Ansible 배포 종료 코드. HTTP 성공률이 높아도 실패 코드를 숨기지 않음 |
| `passed` | 관측 완료·Ansible 성공·실패 요청 0건·종료 후 세 서버 목표 릴리스 관측 |

연결 실패·timeout·5xx·JSON 오류도 전체 시도 수에 포함한다. 실제 서비스의 정상 구버전 응답은 Rolling 중 실패가 아니다. BOOTSTRAP의 구앱은 버전 `legacy`로 표시하며 정식 전환 검증과 구분한다. LB의 프로젝트 access log와 `X-Upstream-Addr`도 처리 서버를 확인하는 근거다.

Agent 관점의 표본 결과이며 장시간 연결·다른 외부 네트워크·고부하 가용성의 보장은 아니다. JVM/Agent 강제 종료로 summary가 없거나 관측이 끊기면 정상 완료로 보고하지 않는다.

## 10. 검증 상태와 제출 체크리스트

로컬 검증은 앱 HTTP 응답·초기화 실패·정상 종료, probe의 정상 전환·잘못된 응답·배포 명령 실패·baseline 실패, Nginx 후보 검증/워커 대기 로직, 실제 Ansible verification role, app2 모의 실패 시 app3 미실행을 대상으로 한다. 현재 로컬 테스트 **37개가 통과**했고, `prepare_ssh`·`prepare`·`deploy`·`verify`·`nginx`·`cleanup` 플레이북 6개의 Ansible 문법 검사도 통과했다. `observe.yml`은 `deploy.yml`에 포함되는 task 파일이므로 단독 플레이북으로 실행하지 않는다. Jenkins에 포함된 셸·Python 문법을 검사했으며, Jenkins Declarative DSL 자체의 검증과 실제 job 실행은 아직 수행하지 않았다.

- [x] Jenkins·Ansible 역할 분리, `serial: 1` Rolling 흐름 구현
- [x] 제외·drain·교체·검증·재등록과 후속 배포 중단 구현
- [x] 서버 ID·빌드 릴리스·연속 요청 원본·집계와 결과 보관 구현
- [ ] Jenkins에서 이미지 빌드·임시 컨테이너 검사 성공
- [ ] 실제 Nginx에서 제외·reload·기존 연결 완료·복귀 검증
- [ ] 실제 v1 → v2 배포의 app1 → app2 → app3 전환 확인
- [ ] 실제 연속 요청 성공률·가용성 측정값과 결과 첨부

현재 로컬 환경에는 사용할 수 있는 Docker 엔진과 Nginx가 없어 실제 컨테이너·원격 배포 검증은 수행하지 않았다. 로컬 모의 테스트 결과를 실제 서버의 무중단 성공률로 보고하지 않는다. Jenkins 실행 후 제출할 자료는 정상 전환의 콘솔·요청 JSONL·집계·릴리스 정보와 필요 시 프로젝트 LB 로그다.

정리 단계의 구현 범위와 보호 조건·확인법은 [배포 후 정리 정책](deployment-extensions.md)을 따른다. 앞의 로컬 검증 수치는 최초 Week2 구현 당시 기록이며 정리 추가분은 `tests/test_cleanup.py`로 별도 검증한다.

Galaxy 적용 후 로컬 테스트 37개가 통과했다. 고정 컬렉션의 실제 `docker_image_remove` 모듈을 로컬 모의 Docker API에 실행해 정확한 대상·`force=false`·`noprune=true` 전달을 확인했다. prepare_ssh·prepare·deploy·verify·nginx·cleanup 플레이북 6개와 Jenkins 내 셸 문법 검사도 통과했다. 실제 원격 Docker 및 Jenkins DSL 실행 결과는 별도 검증 대상이다.
