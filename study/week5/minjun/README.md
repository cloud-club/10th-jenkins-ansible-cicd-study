# Week 5 — Roles, Security & Deployment Orchestration

Role 기반으로 재사용 가능한 Ansible 구조를 설계하고, Secret 관리와 멀티 서버 오케스트레이션을 적용해 Jenkins와 연계 가능한 배포 자동화 구조를 구성했다.

## 실습 환경

Docker 컨테이너를 Managed Node로 구성했다. web 4대(node1·node2·node4·node5), lb 1대(node3, haproxy). 키 인증 전용, 컨테이너 이름 기반 네트워크(`ansible-lab`). Jenkins Controller + Ansible 전용 agent를 같은 네트워크에 연결했다.

실습 코드 전체(roles, playbook, Jenkinsfile)는 별도 레포에 있다: [github.com/cynkai/ansible-week5-lab](https://github.com/cynkai/ansible-week5-lab) (private)

## 문서 구성

- **[01-roles.md](01-roles.md)** — Role 구조(`ansible-galaxy init`, `meta` 의존성, `validate`), 소켓 디렉터리 멱등성 문제, 변수 우선순위 실험, `import_role`/`include_role` 비교, Galaxy·`requirements.yml`·`verify`
- **[02-vault-and-secrets.md](02-vault-and-secrets.md)** — 파일/값 단위 암호화, `no_log`·`-vvv`·`--diff`·`ANSIBLE_DEBUG` 노출 실험(4주차 결론 정정 포함), `encrypt_string`, `--vault-id` 라벨, CI 비밀번호 전달, rekey 사고, External Secret Manager 개념
- **[03-orchestration.md](03-orchestration.md)** — `linear`/`free` 전략과 `forks`, 완료 순서, `throttle`·`run_once`·`delegate_to`, `any_errors_fatal`
- **[04-rolling-deployment.md](04-rolling-deployment.md)** — LB 제외→배포→헬스체크→복귀, 무중단 대조 실험, Canary·batch, 실패 주입, `block/rescue` 롤백, Blue-Green, 설정과 실제 상태의 충돌
- **[05-jenkins-integration.md](05-jenkins-integration.md)** — agent 구성, Credentials, 파라미터 연계(빈 값·`-e`·태그 함정), 보안 실험(vault 추출·명령 주입), `ansible-lint`, SSH pipelining, `ansiblePlaybook` 플러그인 비교

## 주요 실험

- **변수 우선순위** — defaults < group_vars < role vars < `-e`. `vars/`의 값은 인벤토리로 덮어쓸 수 없고 `-e`만 이긴다.
- **`no_log` 경계 재측정** — 4주차 "`-vvv`가 no_log를 우회한다"를 task별로 분리해 정정했다. 우회 여부는 모드가 아니라 비밀이 실리는 위치(모듈 결과/SSH 명령줄/파일 전송/컨트롤 노드 내부)에 달려 있다.
- **배포 도구 성공 보고 ≠ 서비스 상태** — 재시작 중 요청 실패, batch 오설정으로 요청 73% 실패, 불량 버전 반복 배포, 의도하지 않은 롤백이 모두 `failed=0`으로 보고됐다. 실제 영향은 외부 감시 로그나 LB 상태로만 보였다.
- **레포 쓰기 = 배포 시크릿 접근** — Jenkinsfile을 고칠 수 있으면 Secret file로 저장한 vault 비밀번호도 `cat`으로 노출됐다. 브랜치 하나만 파도 성립했다. 파라미터 명령 주입으로는 빌드 실행 권한만으로도 가능했다.
