> 문서 역할: 구현된 배포 후 정리 정책과 Ansible Galaxy 적용을 설명한다.

# 배포 후 정리와 Ansible Galaxy

## 1. 구현된 서버별 정리

정상 Rolling 배포와 가용성 측정을 통과하면 Jenkins가 `Cleanup Plan & Archive` → `Cleanup Apply & Verify`를 자동 실행한다. 별도 정리 파라미터 없이 실행하며, 배포 실패 시 두 단계는 실행하지 않는다. 현재 구현은 `scripts/cleanup.py`, `scripts/cleanup_workspace.py`, `ansible/playbook/cleanup.yml`, `ansible/roles/cleanup/tasks/main.yml`에 있다.

### 순서와 실패 처리

1. prepare에서 앱의 배포 직전 정상 컨테이너 전체 설정과 이미지 ID를 배포 계정의 프로젝트 상태 디렉터리에 저장한다. 같은 릴리스 재시도에서는 덮어쓰지 않는다. 배포가 생성한 tar·후보 설정·백업의 정확한 경로와 파일 식별 정보도 프로젝트 상태 디렉터리에 기록한다. LB도 검증한 배포 전 설정을 `nginx.previous.conf`로 보존한다.
2. 배포·측정 성공 후 전체 서비스 상태를 다시 검사하고 서버별 삭제 계획을 생성한다. Agent는 앱 3대의 보호 이미지 ID도 합쳐 사용한다.
3. 배포 증거와 `cleanup-plan-*.json`을 Jenkins에 archive한다. 보관 실패 시 삭제 단계는 실행하지 않는다.
4. 앱 서버를 한 대씩 정리하고 HTTP 검사한다. LB 파일을 정리하고 전 서버와 LB를 다시 검사한 뒤 Agent를 정리한다.
5. 삭제 직전 계획을 다시 계산한다. 계획 이후 자원이 바뀌면 삭제를 중단한다. 이미지 참조·컨테이너 사용 여부와 파일 식별 정보를 항목별로 다시 확인한다. 일괄 정리의 이미지·종료 컨테이너 삭제에는 force를 사용하지 않는다.
6. `cleanup-result-*.json`과 정리 로그를 보관한다. 삭제 실패는 해당 stage 실패와 Jenkins UNSTABLE로 표시하며 이미 성공한 배포를 롤백하지 않는다. 부분 삭제 결과도 기록한다.
7. post에서 최종 archive가 성공한 번호별 산출물 폴더에 소유자·프로젝트·Jenkins job이 기록된 `.archived` 표시를 쓰고 workspace 중복본을 지운다. archive 실패 폴더와 과거 표시 없는 폴더는 보존한다.

### 삭제·보존 범위

| 위치 | 정리 대상 | 보존 대상 |
| --- | --- | --- |
| Agent | 소유자·프로젝트 라벨이 확인된 보호 목록 밖 `sohyeon-cicd-app` 이미지 태그, 소유자·프로젝트 label이 있는 dangling 이미지, 소유자·프로젝트·test label과 정확한 이름이 있는 종료된 테스트 컨테이너, archive 완료 보고서 중복본 | 목표·앱 서버별 이전 정상 이미지 ID, 모든 실행/중지 컨테이너 참조 이미지, 다른 프로젝트 자원 |
| 앱 서버 | 소유자·프로젝트 라벨이 확인된 보호 목록 밖 동일 저장소 이미지, 소유자·프로젝트 label이 있는 dangling 이미지, 생성 기록과 파일 식별 정보가 일치하는 프로젝트 전달 tar | 현재 이미지, 배포 직전 정상 이미지와 실행 설정, 다른 컨테이너의 참조 이미지 |
| LB | 생성 기록과 파일 식별 정보가 일치하는 후보 설정·중간 백업 | 현재 설정, `nginx.previous.conf`, 도우미, 요청 로그 |
| Jenkins | job 보관 정책에 따른 오래된 빌드·아티팩트 | 기본 최근 20개·30일 한도 내 결과; Jenkins가 보호하는 빌드 등은 별도 |

이미지는 `io.sohyeon.owner=sohyeon`과 `io.sohyeon.project=sohyeon-cicd` 라벨을 모두 요구한다. 이름만 같은 기존 label 없는 이미지·테스트 컨테이너는 보존한다. tar·Nginx 백업도 파일명 패턴만으로 삭제하지 않으며 생성 기록이 없는 과거 파일과 기록 이후 수정된 파일은 보존한다. workspace 보고서도 archive 표시의 소유자·프로젝트·job이 모두 일치해야 정리한다. post의 현재 테스트 컨테이너 강제 종료 역시 소유자·프로젝트·test·이번 릴리스가 모두 일치해야 허용한다. 종료 컨테이너에 참조되던 이미지는 이번 계획에서 보호되어 다음 성공한 정리 때 제거될 수 있다.

공용 Docker 빌드 캐시·volume에 전역 prune을 실행하지 않는다. 앱 컨테이너 로그는 새 배포부터 json-file 드라이버의 `max-size=10m`, `max-file=3`으로 제한한다. LB access log의 회전은 서버의 기존 Nginx logrotate 정책을 사용하며 이 코드에서 로그를 직접 삭제하거나 공용 정책을 덮어쓰지 않는다.

Nginx 역할은 후보 파일을 만든 직후와 설정 교체가 반환한 `backup_file`에 대해 `cleanup.py record --scope lb`를 실행한다. 같은 후보 경로의 기록은 최신 파일 정보로 갱신한다. 배포·측정·계획 보관이 성공하면 등록된 후보와 중간 백업을 삭제하므로 정상 배포마다 백업이 누적되지 않는다. 등록과 계획·검사는 배포 계정으로 실행하며, `/etc/nginx` 아래 파일 삭제만 정확한 프로젝트 경로를 다시 검사한 뒤 `become`을 사용한다. 과거 등록되지 않은 백업은 이름만으로 자동 삭제하지 않는다. 단독 Nginx 역할 실행에도 정리 도우미와 상태 디렉터리가 준비되어 있고 유효한 `image_tag`가 전달되어야 한다.

같은 환경을 조작하는 job·수동 작업은 동시에 실행하지 않는 기존 전제가 유지된다. 여러 역할이 같은 Docker daemon을 공유해 계획이 달라지면 안전하게 정리를 중단하므로 별도 실행 조율이 필요하다. 실패 배포 자료의 원격 자동 정리나 자동 롤백은 구현 범위에 포함하지 않는다.

### 확인 방법

- Jenkins에서 두 Cleanup stage와 `cleanup-plan.log`, `cleanup-apply.log` 확인.
- `cleanup-plan-<서버>.json`: `protected_images`, `candidates` 확인.
- `cleanup-result-<서버>.json`: `deleted`, `failed` 확인. 모든 결과 파일이 있는지와 정리 후 verify 성공도 함께 확인.
- 앱 서버에서 `docker image ls sohyeon-cicd-app`, `docker ps`로 현재·이전 이미지 및 서비스를 확인한다. 배포 계정의 Docker 권한이 없다면 정리하지 말고 관리자에게 권한 범위를 확인한다.
- LB에서 `sudo -n nginx -t`, `sudo -n ls -l /etc/nginx/conf.d/sohyeon.conf`로 확인한다. 임의의 `sudo rm`, `sudo python`, 다른 사용자 설정 변경은 실행하지 않는다.
- 로컬 보호 로직 테스트: `python3 -m unittest discover -s tests -p test_cleanup.py -v`.

실제 Docker 삭제·원격 정리와 Jenkins DSL 실행은 Jenkins 환경에서 검증해야 한다. 원격 복구용 전체 컨테이너 설정에는 환경변수가 포함될 수 있으므로 Jenkins 아티팩트에 넣지 않는다.

### 관리자 권한 범위

일반 `prepare`, `deploy`, `verify`, `cleanup` 플레이북은 배포 계정으로 실행한다. Docker 조회·이미지 로드·컨테이너 교체·이미지 삭제 모듈과 Docker 저장소 공간 검사에만 개별 `become`을 사용한다. Nginx 후보 검증·설치·임시 파일 삭제·`nginx -t`·reload와 워커 관측도 기존 권한을 사용한다. 별도 설치 파일, sudoers·계정 그룹·Docker 소켓 권한 변경, Docker 서비스 재시작, 서버 재부팅은 없다.

원격 앱의 정리 도우미에는 `SOHYEON_DOCKER_SUDO=1`을 전달한다. 이 모드에서는 Docker 목록·inspect 명령만 `sudo -n -- docker`로 실행하며, Docker 변경 명령은 거부한다. Python 도우미 자체는 배포 계정으로 실행하므로 HOME이나 상태 파일의 소유자는 바뀌지 않는다. Agent의 기존 Docker 접근 방식은 유지한다. 다른 프로젝트의 컨테이너 정보도 이미지 참조 보호를 위해 읽지만 변경하지 않는다.

컨테이너 교체 전에 고정된 이름·포트와 소유자/프로젝트 라벨을 검사한다. 프로젝트 소유권 라벨이 없는 Week1 컨테이너만 bootstrap과 서버별 승인된 전체 ID로 예외 처리하며, 다른 소유자·프로젝트 라벨이 있으면 ID가 일치해도 거부한다. `maintainer` 같은 일반 이미지 라벨은 허용한다. 실패 로그에는 이름·포트·소유권·bootstrap·ID 일치 여부만 출력하고 전체 컨테이너 설정은 숨긴다. 이미지 로드 전에는 tar의 manifest가 이번 프로젝트 태그 하나만 포함하고 이미지의 소유자·프로젝트·릴리스 라벨이 일치하는지 확인한다. 정리는 기존 소유권·참조 검사와 force/prune 금지를 유지한다. 이 검사는 코드의 작업 범위를 제한하며 서버의 sudo 권한 자체를 프로젝트 단위로 격리하는 정책은 아니다. 같은 대상에 대한 동시 수동 변경은 피해야 한다. 공용 LB reload는 다른 스터디원의 배포와 겹치지 않게 조율한다.

## 2. 구현된 Ansible Galaxy 적용

`ansible/requirements.yml`에 `community.docker:4.8.1`과 전이 의존성 `community.library_inventory_filtering_v1:1.0.0`을 고정했다. 4.8.1의 [공식 runtime 요구사항](https://github.com/ansible-collections/community.docker/blob/4.8.1/meta/runtime.yml)은 ansible-core 2.15 이상이며 이 프로젝트의 2.16.3에서 컬렉션 설치·모듈 로딩을 확인했다.

Jenkins 첫 stage에서 `ansible-galaxy collection install`을 실행하고 `scripts/check_collections.py`로 설치 버전과 6개 모듈의 실제 로딩 위치를 검증한다. `ansible.cfg`는 컬렉션·Galaxy 캐시·토큰 경로와 로컬 임시 디렉터리를 프로젝트 `.ansible/`로 제한한다. Jenkins도 `ANSIBLE_CONFIG`와 `ANSIBLE_COLLECTIONS_PATH`를 절대 경로로 지정한다. 공용 Agent의 기존 컬렉션을 설치·갱신하지 않는다.

| 실제 사용 위치 | Galaxy 모듈 | 역할 |
| --- | --- | --- |
| `prepare.yml` | `community.docker.docker_container_info` | 현재 앱 컨테이너 실행 상태 조회 |
| `prepare.yml` | `community.docker.docker_host_info` | Docker 저장 경로와 API 연결 확인 |
| `prepare.yml` | `community.docker.docker_image_load` | Jenkins에서 전달한 이미지 tar 로드 |
| `deploy.yml` | `community.docker.docker_image_info` | 대상 제외 전 준비 이미지 존재 확인 |
| `roles/app/tasks/main.yml` | `community.docker.docker_container` | drain 이후 정상 종료·제거·새 컨테이너 시작 |
| `roles/cleanup/tasks/delete_item.yml` | `community.docker.docker_image_remove` | 소유권·보호 조건을 통과한 이미지 하나만 제거 |

컨테이너는 `pull: never`로 이미 검사·로드된 이미지만 사용하고, 제거 시 `keep_volumes: true`로 volume을 보존한다. 이미지 삭제는 `force: false`, `prune: false`로 부모 이미지까지 연쇄 삭제하지 않는다. 이 모듈의 기본 prune 값은 true이므로 명시적으로 비활성화했다. [공식 모듈 소스](https://github.com/ansible-collections/community.docker/blob/4.8.1/plugins/modules/docker_image_remove.py)

정리 정책 도우미는 삭제 계획·소유권·현재/이전 이미지 보호·삭제 직전 재검사를 맡는다. 원격에서는 `validate-plan → check-item → Galaxy 이미지 삭제 또는 builtin.file → record-deleted` 순서로 실행하고, 모듈 실패 시 `record-failure` 후 중단한다. 도우미의 Docker 조회와 Agent의 빌드·테스트·정리는 기존 CLI를 사용한다. CLI와 모듈 모두 로컬 `/var/run/docker.sock`을 명시해 다른 Docker endpoint로 잘못 정리하지 않게 한다.

### 실행 조건과 설치 확인

모듈이 실행되는 앱 서버의 Ansible Python에는 `requests`가 필요하다. 이번에 선택한 모듈들은 별도 Docker SDK(`docker` Python 패키지)를 요구하지 않는다. [4.8.1 모듈의 requirements](https://github.com/ansible-collections/community.docker/blob/4.8.1/plugins/modules/docker_container.py)를 따른다. Galaxy 설치는 Agent에 모듈 코드만 설치하며 원격 Docker Engine이나 Python 의존성을 설치하지 않는다. 공용 서버의 Python 패키지를 자동 업그레이드하지 않으며, requests/API/권한 문제가 있으면 prepare의 첫 Docker 모듈에서 컨테이너 교체 전에 실패한다. 누락된 의존성은 서버 관리 방식에 맞춰 모듈 실행 Python에 준비해야 한다.

프로젝트 루트에서 다음을 실행한다.

```sh
export ANSIBLE_CONFIG="$PWD/ansible.cfg"
export ANSIBLE_COLLECTIONS_PATH="$PWD/.ansible/collections"
ansible-galaxy collection install -r ansible/requirements.yml -p .ansible/collections
python3 scripts/check_collections.py
ansible-galaxy collection list
ansible-playbook -i ansible/inventory.ini ansible/playbook/deploy.yml --syntax-check
ansible-playbook -i ansible/inventory.ini ansible/playbook/cleanup.yml --syntax-check
```

컬렉션 다운로드에는 Galaxy 네트워크 접근이 필요하다. 실제 원격 컨테이너 교체·정리와 Jenkins DSL 실행은 Jenkins 환경에서 검증한다.

검증 결과: 로컬 테스트 30개 통과, 플레이북 6개 문법 검사 및 Jenkins 셸 문법 검사 통과. 실제 Galaxy 이미지 삭제 모듈은 로컬 모의 Docker API로 대상·force·prune 전달을 검증했으며 원격 서버 자원을 삭제하지 않았다.
