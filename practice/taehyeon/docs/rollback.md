# 실습 3주차: 배포 12시간 뒤 이전 버전으로 롤백

## 구현 방향

2주차 카나리는 배포 중 실패했을 때 기존 슬롯으로 복구했다. 이번 실습은 배포가 성공한 뒤 장애를 발견한 경우, 별도 Jenkins 실행에서 직전 운영 버전으로 복구한다.

기존 슬롯으로 빠르게 돌아갈 수 있게 컨테이너를 유지하며, 슬롯이 없어져도 동일 이미지를 재생성하도록 이미지와 실행 정보를 영구 보관한다. 소스를 다시 빌드하지 않는다. 12시간은 장애 발견 시점에 대한 가정이며 Jenkins에 대기 시간을 추가하지 않는다.

현재 앱에 DB와 데이터 볼륨이 없어 복구 범위는 앱 이미지·지원 실행 설정·개인 Nginx 라우팅·운영 상태다. 서비스의업무 데이터나 VM·Jenkins 자체의 백업은 포함하지 않는다.

## 실행 방법

기존 개인 Jenkins Job 하나를 계속 사용한다.

| 설정 | 값 |
| --- | --- |
| SCM Branch | `*/week8/taehyeon` |
| Script Path | `practice/taehyeon/Jenkinsfile` |
| Agent Label | `ansible-agent` |
| SSH Credential | `taehyeon-appserver-ssh` |
| ACTION | `DEPLOY` 또는 `ROLLBACK` |
| OBSERVE_SECONDS / MIN_SAMPLES / MAX_RESPONSE_MS | 기존 관찰 파라미터 재사용 |

새 Pipeline 파라미터가 Jenkins에 반영된 후 Build with Parameters에서 ACTION을 선택한다. 최초 파라미터 등록 실행이 자동 배포되지 않도록 Job 설정과 실행 파라미터를 확인한다. 같은 서비스의 별도 Job을 만들거나 수동 배포를 병행하지 않는다.

### DEPLOY

1. 테스트·Playbook 문법 검사와 미완료 작업 조회를 수행한다.
2. 미완료 작업이 있으면 해당 작업만 복구하고 종료한다.
3. 기존 앱 테스트·이미지 빌드·이미지 실행 검증을 수행한다.
4. 현재 서비스 baseline을 검증하고 기존 운영 이미지도 보관한다. 첫 실행에서는 기존 state.json을 새 형식으로 이관한다.
5. 신규 이미지·실행 설정·개인 라우팅 설정을 보관한다. 보관 실패 시 슬롯을 변경하지 않는다.
6. 영구 pending 마커를 기록하고 10% → 50% → 100% 카나리를 수행한다.
7. 단계 검사와 지속 관찰이 성공하면 현재/직전 운영 릴리스를 원자적으로 확정한다.

### ROLLBACK

1. Jenkins에서 ACTION을 ROLLBACK으로 선택한다. 앱 빌드와 현재 버전 baseline 단계는 실행하지 않는다.
2. 현재 상태와 개인 Nginx 설정이 일치하는지 확인하고 state.json의 previous_release를 선택한다.
3. 이전 이미지·명세·설정의 체크섬을 검증하고 pending을 기록한다.
4. 현재 활성 슬롯의 반대 슬롯에 이전 버전을 준비한다. 이미지 ID·실행 설정·두 API가 같은 정상 컨테이너는 재사용하고, 없거나 다르면 보관 이미지로 재생성한다.
5. 세 서버의 두 API를 검사하고 개인 Nginx를 이전 버전 100%로 전환한다.
6. Nginx 경유 HTTP 응답에서 이전 버전만 관찰되고 세 인스턴스가 모두 나타나는지 확인한다.
7. 검증 성공 후 운영 상태를 확정하고 pending을 지운다.

기본 롤백 대상은 실제 직전 운영 릴리스다. `BUILD_NUMBER - 1`이나 Jenkins의 마지막 성공 빌드로 계산하지 않는다. 롤백 후 previous_release를 비우므로 반복 실행으로 장애 버전에 돌아가지 않는다. 이후 새 배포가 성공하면 그 배포 직전의 운영 버전을 새 복구 대상으로 기록한다.

## 저장 구조와 동일성 확인

Nginx VM에 다음 파일을 저장한다. 이미지 원본은 Jenkins Artifacts에 의존하지 않는다.

```text
/var/lib/taehyeon-deploy/
  state.json
  pending-operation.json
  releases/<release-id>/
    manifest.json
    image.tar
    nginx.conf
  operations/<operation-id>-before.conf
  operations/<operation-id>.json
```

디렉터리는 root 소유 0700, 자료 파일은 0600으로 보관한다. manifest.json에는 버전·SHA·릴리스·이미지 ID·이미지 파일 SHA-256·서버별 지원 실행 설정·개인 설정 체크섬·출처를 기록한다. 임의 컨테이너 환경값이나 원본 inspect 전체는 Artifacts에 내보내지 않는다.

이미지 태그만으로 재사용 여부를 판단하지 않는다. 저장소·Agent·App 서버에서 이미지 파일 SHA-256을 확인하고, load한 이미지 ID를 확인한 뒤 ID로 실행한다. 현재 지원 범위를 벗어난 볼륨·추가 포트·실행 옵션은 조용히 생략하지 않고 중단한다. 현재 런타임은 init 비활성, 기본 공유 메모리 64 MiB, 추가 옵션 없는 json-file 로깅을 지원하며, 다른 설정은 이관 전에 거부한다.

같은 릴리스 ID는 다른 이미지·런타임·설정으로 덮어쓰지 않는다. 완성되지 않은 staging 디렉터리는 정상 릴리스로 읽지 않는다. 현재·직전·pending 참조 릴리스는 수동 정리에서도 보존한다. 자동 삭제는 없으며 이미지 크기와 Nginx VM의 디스크 여유를 운영자가 확인한다. 저장 VM 자체의 유실은 별도 백업이 필요하다.

## 실패와 중단 복구

state.json의 원자적 교체를 운영 상태 확정 지점으로 삼는다. pending에는 변경 전 상태와 개인 설정, 대상 릴리스·슬롯, 작업 ID를 기록한다.

| 중단 시점 | 다음 실행의 처리 |
| --- | --- |
| 슬롯·트래픽 변경 전 검증 실패 | 트래픽을 변경하지 않고 실패 |
| pending 기록 후, 상태 확정 전 | 변경 전 개인 라우팅으로 복원하고 이전 메타데이터 HTTP 검사 |
| 상태 확정 후, 마커 정리 전 | 이미 확정된 버전과 라우팅을 검증한 뒤 정리 |
| 복구 관찰 실패 또는 SSH 단절 | pending 유지, 새 작업 중단, 실패와 조치 대상 기록 |
| Artifacts 보관만 실패 | 서버의 완료된 배포를 보고서 오류만으로 되돌리지 않음 |

Jenkins post는 실패한 현재 실행이 소유한 pending만 복구한다. 초기 단계에서 발견한 과거 pending 복구가 실패하면 같은 실행의 post에서 반복하지 않는다. 다음 실행은 미완료 복구만 수행하고 종료하므로, 새로운 배포·롤백은 별도 실행한다.

원래 버전도 장애 상태이면 변경 전 라우팅 복원 후 HTTP 검증이 실패할 수 있다. 이 경우 pending과 실패를 유지한다. 현재 상태를 확인하지 않고 마커를 지워 새 배포를 강행하지 않는다.

### 수동 재시도

현재 Job 실행이 끝나고 동일 서비스를 변경하는 작업이 없을 때만 수행한다. SSH Credential과 검증된 known_hosts가 있는 Agent에서 아래처럼 빈 보고서 디렉터리를 만든 뒤 서버의 기록으로 복구한다.

```bash
cd practice/taehyeon
mkdir -p .canary/manual-recovery
chmod 700 .canary/manual-recovery
report_dir="$PWD/.canary/manual-recovery"
cd ansible
ansible-playbook -i inventory/hosts.ini playbooks/release-operation.yml \
  -e operation_phase=recover \
  -e operation_id=manual-recover-20261019 \
  -e "canary_report_dir=$report_dir"
```

실제 복구 대상과 원본 개인 설정은 서버 pending에서 읽는다. 예전 workspace의 deployment-vars.json을 복원할 필요는 없다. 작업 결과는 로컬 operation-status.json과 관찰 보고서, 서버 operations 디렉터리에서 확인한다. 과거 canary-commit.yml을 직접 호출해 새 state.json을 덮어쓰지 않는다.

## 검증 시나리오와 확인할 증거

| 시나리오 | 확인할 결과 |
| --- | --- |
| V1 → V2 정상 배포 → 별도 롤백 실행 | state.json의 릴리스와 세 서버/Nginx 응답이 V1 |
| Jenkins 작업 폴더 초기화 후 롤백 | 서버 자료에서 대상·이미지를 조회하고 복구 |
| 이전 비활성 컨테이너·이미지 소실 | 보관 파일 load 후 같은 이미지 ID로 재생성 |
| 현재 버전 HTTP 500 | 현재 baseline 실패로 막히지 않고 이전 버전 준비 |
| 이미지 파일 누락·변조 | 슬롯 삭제·트래픽 전환 전에 실패 |
| 확정 전 강제 중단 | 새 실행에서 변경 전 라우팅 복원 |
| 확정 후 마커 삭제 전 중단 | 이미 성공한 배포 유지·검증·정리 |
| 복구 대상 HTTP 오류 | 성공으로 기록하지 않고 pending 유지 |

컨테이너·이미지 제거와 장애 주입 실험은 격리된 조건에서 개인 비활성 슬롯만 대상으로 수행한다. 공유 이미지 일괄 삭제나 docker prune을 검증 절차로 사용하지 않는다.

로컬 검증은 실제 Ansible Task의 임시 파일 조작과 로컬 HTTP 서버를 사용하며 외부 Docker·Nginx 서비스 명령만 대체한다. Jenkins 분기 테스트는 실제 Jenkinsfile을 Groovy로 평가하되 Jenkins/SSH/shell 경계만 대체한다. 실제 Jenkins CPS·플러그인·병렬 취소·원격 Docker·SSH 검증은 별도로 필요하다.

실제 환경의 실행 증거와 12시간 경과 여부는 PR의 검증 항목에 실행한 범위대로 기록한다. 테스트 환경에서 시간을 기다리지 않고 별도 실행과 작업 폴더 소실을 재현한 결과를 12시간 실측으로 표현하지 않는다.
