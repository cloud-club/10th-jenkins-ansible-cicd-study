# 배포 완료 후 이전 슬롯으로 롤백

정상 배포 후 기능 장애를 발견했을 때, **문제가 생긴 배포 빌드의 기록**을 읽어 그 배포 직전 슬롯으로 돌아간다. 매 배포마다 기록하며 최초 한 번만 저장하는 방식은 아니다. 이미지 재빌드·다운로드·컨테이너 교체 없이 Nginx의 연결 대상만 변경한다.

## 동작

1. 배포 시작 시 Nginx에서 활성 슬롯과 릴리스를 읽고, 세 서버가 같은 릴리스인지 확인한다.
2. 기존 블루그린 배포를 수행한다. Nginx 전환과 세 서버의 응답 검증까지 성공하면 Agent의 `.artifacts/deployment-result.json`에 배포 전후 정보를 저장한다.
3. Jenkins가 이 파일을 해당 배포 빌드의 Artifact로 보관한다. Agent 작업 공간이 정리되어도 보관된 Artifact를 사용한다.
4. 롤백 Job이 지정한 배포 빌드의 Artifact를 가져와, 현재 릴리스와 이전 슬롯을 확인하고 기존 Nginx 템플릿을 이전 슬롯으로 적용한다.
5. `nginx -t` → Reload → 기존 `verify.py`로 Nginx 경유 `/health`·`/version`에서 세 instance를 모두 확인한다. 실패하면 롤백 시작 시 읽은 설정을 복원하고 Job은 실패로 끝난다.

기록에는 `status=completed`, 원본 Job·빌드 번호, 서버 주소, `before`/`after` 슬롯·버전·release·revision, 신규 이미지 digest가 들어간다. 기존 `.artifacts/deploy-vars.json`은 이미지 빌드 시 생성되어 이전 슬롯을 알 수 없으므로 유지하고, 실제 배포 결과만 별도 JSON 하나로 추가한다. 이전 이미지 digest는 그 릴리스를 배포한 빌드의 `deploy-vars.json`에서 확인한다.

배포 전환 실패나 자동 복구 시에는 완료 기록을 만들지 않는다. 이후 지속 관측에서 오류를 발견해 Jenkins 빌드가 실패하더라도, 전환 자체가 완료되어 기록이 남았다면 해당 빌드 번호로 롤백할 수 있다. 기록이 없는 빌드나 변경 전 코드로 수행한 배포는 이 Job으로 롤백할 수 없다.

## Jenkins 설정

- **Copy Artifact**, **Lockable Resources** 플러그인을 설치한다.
- 기존 `dongwook/blue-green-deploy-pipeline(week7)`은 Script Path `practice/dongwook/Jenkinsfile`을 사용한다. 롤백 Job의 `DEPLOY_JOB_NAME`은 실제 배포 Job의 전체 경로와 일치해야 한다. 배포 기록의 `source.job`은 생성 당시 이름이므로, 같은 Job의 이름을 변경한 경우 이전 이름이 남아 있어도 사용할 수 있다. Artifact는 현재 지정한 Job에서 가져오고 빌드 번호·서버 구성·릴리스 정보를 검증한다.
- 같은 Folder에 `rollback-pipeline`을 만들고, 같은 저장소·브랜치에 Script Path `practice/dongwook/Jenkinsfile.rollback`을 지정한다. 두 Job 모두 `ansible-agent`에서 실행한다.
- 배포 Job의 `copyArtifactPermission('/dongwook/rollback-pipeline')`이 해당 롤백 Job의 Artifact 조회를 허용한다. Job 경로를 바꾸면 이 값과 롤백 Job의 `DEPLOY_JOB_NAME`도 수정한다.
- 두 Job은 `dongwook-production` 잠금을 공유한다. 배포의 슬롯 확인·교체·전환과 롤백은 동시에 진행하지 않는다. 직접 Ansible을 실행할 때는 이 잠금이 적용되지 않으므로 두 Job의 실행과 트리거를 먼저 막는다.

기존 Agent의 Python·Ansible과 SSH 접근 설정을 그대로 사용한다. 롤백은 Docker Hub 인증이 필요 없다. 현재 컨테이너의 릴리스 확인에는 App 서버의 Docker 조회 권한이 필요하다.

## 롤백 실행

예를 들어 배포 **#42가 blue A → green B**로 성공했는데 B에서 기능 장애가 발생했다면:

1. `blue-green-deploy-pipeline(week7)`의 **#42** Artifact에서 `deployment-result.json`을 확인한다. `before`가 blue A, `after`가 green B여야 한다.
2. `rollback-pipeline`의 **Build with Parameters**에서 `DEPLOY_BUILD_NUMBER=42`와 `REASON`에 장애 증상을 입력한다. A를 배포했던 빌드 번호를 입력하는 것이 아니다.
3. Job 성공과 Console Output의 검증 결과를 확인하고, 실제 문제가 발생한 기능을 직접 재확인한다. 사용한 JSON은 롤백 빌드에도 보관되고, 사유와 결과는 Jenkins 파라미터·로그에 남는다.

같은 빌드로 다시 실행해도 항상 기록의 `before` 슬롯을 목표로 하므로 B로 되돌아가지 않는다. 현재 앱은 배포 정보와 health 응답만 제공하므로, 기능 장애 판단과 복구된 기능의 검증은 운영자가 수행한다.

## 남겨 둔 검증과 제한

- 현재 Nginx의 세 upstream 주소·포트와 기록의 서버 구성이 일치해야 한다.
- 현재 슬롯이 `after`라면 세 컨테이너의 release·version·revision·slot이 기록과 일치해야 한다. HTTP가 실패하거나 컨테이너가 정지한 상황도 조회할 수 있다. 컨테이너 ID는 비교하지 않으므로 동일 릴리스로 재생성한 경우도 허용한다.
- 복구할 `before` 슬롯은 세 서버 모두 health와 기록된 릴리스 정보가 일치해야 한다. **다음 배포로 이전 슬롯의 릴리스가 교체됐다면 이 롤백을 사용할 수 없다.** 필요한 이전 이미지 재배포는 별도 작업이다.
- 실행 도중 설정이 바뀌면 덮어쓰지 않고 중단한다. 전환 실패 시 설정 복구는 원래 경로를 돌려놓는 것이며, 원래 서비스의 기능 장애까지 해결했다는 뜻은 아니다.
- 프로세스 강제 종료·SSH 단절 또는 완료 기록 저장 실패가 발생하면 실제 전환 여부를 로그와 서버에서 확인해야 한다. 기록이 없다는 이유만으로 전환 전이라고 판단하지 않는다.
- 이 구성은 저장소의 기존 Nginx 템플릿으로 전환한다. 서버에만 별도 설정을 추가했다면 먼저 저장소 템플릿에도 반영한다.

완료 기록이 생성된 배포 빌드는 `keepLog=true`로 보존하여 최근 10개 빌드 정리 대상에서 제외한다. 이전 슬롯이 교체되어 더 이상 롤백에 쓰지 않는 기록은 운영자가 Jenkins의 **Keep this build forever**를 해제할 수 있다. 현재 배포 기록과 복구 대상으로 유지할 릴리스의 빌드는 보존한다. Jenkins의 일반 백업·디스크 관리도 그대로 필요하다.

## 검증

2026-10-18 로컬 확인: 기존 보조 로직 29개와 앱 테스트 5개, 두 Playbook 구문 검사, 두 Jenkinsfile의 Groovy 컴파일과 shell 구문 검사를 통과했다. 임시 환경에서 원격 I/O를 대체해 실행한 Ansible 시나리오 11개도 통과했다. 정상·반복·역방향·legacy 롤백, 현재 서비스 중단, 동일 릴리스 재생성, 변경된 릴리스·비정상 이전 슬롯·잘못된 기록 거부, 동시 설정 변경, 전환 실패 시 복원, 배포 성공 시에만 기록 생성을 확인했다. 이 임시 검증 코드는 저장소 구성에 포함하지 않는다.

`practice/dongwook/`에서 기존 테스트와 두 Playbook의 구문 검사를 실행한다.

```bash
python3 -m unittest discover -s scripts/tests -v
# 앱 의존성이 설치된 Python 환경에서 실행
(cd app && python3 -m unittest discover -s tests -v)
export ANSIBLE_CONFIG="$PWD/ansible/ansible.cfg"
ansible-playbook -i ansible/inventory/hosts.yml \
  ansible/playbooks/deploy.yml ansible/playbooks/rollback.yml --syntax-check
```

실제 Jenkins에서는 새 코드로 한 번 배포하여 Artifact 생성을 확인한 뒤, 해당 빌드 번호로 롤백하고 동일 번호로 재실행한다. 이전 슬롯이 교체된 경우의 거부와 Reload 실패 시 설정 복구는 별도 검증 환경에서 확인한다. 실서버 배포·롤백은 아직 수행하지 않았다.
