# Jenkins CI/CD Integration & Operations

## CI 환경

Jenkins agent는 컨테이너 네트워크 안에서 돌므로 `127.0.0.1:포트` 방식 인벤토리는 쓸 수 없다(컨테이너 안에서 127.0.0.1은 자기 자신이다). 로컬용 인벤토리는 그대로 두고 컨테이너 이름으로 접속하는 CI용 인벤토리를 따로 만들었다.

```ini
[web]
node1 ansible_host=node1
node2 ansible_host=node2
...
```

SSH 키 경로는 넣지 않았다. 키는 Jenkins Credential이 실행 시점에 넘긴다.

## Ansible agent 구성

3주차 Controller/Agent 분리 원칙을 지키기 위해, Controller에서는 빌드를 돌리지 않고 Ansible이 설치된 agent를 따로 붙였다.

- agent 이미지: `jenkins/inbound-agent`에 `python3` + venv에 `ansible-core` + `ansible-lint`.
- `ansible` 전체 패키지가 아니라 `ansible-core`만 설치했다. 필요한 컬렉션은 파이프라인에서 `requirements.yml`로 설치한다.
- Controller의 실행기 수를 0으로 바꿨다. 모든 빌드가 agent에서만 돈다. Controller에서 빌드가 돌면 빌드 코드가 Jenkins 전체 설정과 Credential 저장소에 접근할 수 있다.

설치된 버전:

| 도구 | agent | Mac (brew) |
|---|---|---|
| ansible-core | 2.21.4 | 2.21.4 |
| ansible-lint | 26.9.0 | — |
| Python | 3.13.5 | — |

버전 번호는 우연히 같았지만 설치된 컬렉션 구성은 달랐다. Mac은 brew가 전부 묶어 설치했고, agent는 `requirements.yml`에 적은 것만 받아온다. `ansible.cfg`에서 쓰는 `ansible.posix.profile_tasks` 콜백이 agent에는 없어서 `requirements.yml`에 `ansible.posix`를 추가해야 했다.

### agent secret

agent는 연결 시 노드 전용 secret을 제시한다. 셸 기록에는 남기지 않고 입력받아 넘겼지만, 컨테이너 설정에는 환경변수로 남는다.

```
$ docker inspect ansible-agent --format '{{range .Config.Env}}{{println .}}{{end}}' | grep SECRET
JENKINS_SECRET=c5ac5c9dc...
```

Docker에 접근할 수 있는 사람은 이 명령으로 agent secret을 볼 수 있고, 그것으로 가짜 agent를 붙여 빌드를 가로챌 수 있다.

## Credentials

세 개를 등록했다.

| ID | 종류 | 용도 |
|---|---|---|
| `ansible-ssh` | SSH Username with private key | node 접속 |
| `ansible-vault-dev` | Secret file | vault 복호화 |
| `github-ro` | Username with password | private 레포 checkout |

- vault 비밀번호는 Secret text가 아니라 **Secret file**로 넣었다. 02-5에서 본 대로, 우발적 노출에는 파일 방식이 덜 새기 때문이다.
- GitHub 토큰은 최소 권한으로 새로 만들었다. `gh`가 쓰는 토큰은 `repo` 권한이라 모든 레포를 읽고 쓸 수 있다. 대신 이 레포 하나만 읽는 **읽기 전용 · 7일 만료** fine-grained 토큰을 발급해 넣었다. Jenkins가 뚫려도 얻는 것은 한 레포를 일주일 읽을 권한뿐이다.

Credential 값은 Controller 안에 암호화되어 저장되지만, 암호화 키도 같은 Jenkins 폴더 안에 있어 서버 파일에 접근할 수 있는 사람은 풀 수 있다. Controller에서 빌드를 안 돌리게 한 이유다.

## 첫 파이프라인

Jenkinsfile을 레포 안에 두었다. 파이프라인도 코드 리뷰와 변경 기록의 대상이 되고, 동시에 레포 쓰기 권한이 곧 파이프라인 수정 권한이 된다.

Credential은 `withCredentials` 블록 안에서만 존재하고, SSH 키와 vault 비밀번호 모두 값이 아니라 임시 파일 경로로 전달된다. `sh` 블록은 작은따옴표를 써서 Groovy가 아니라 셸이 실행 시점에 환경변수를 읽게 했다(큰따옴표를 쓰면 비밀 값이 명령 문자열에 박힌다).

### SSH 키 Credential 오류

Ping 단계가 다섯 대 모두 `Permission denied (publickey)`로 실패했다.

```
Load key "****": error in libcrypto
```

진단 stage를 넣어 Jenkins가 만든 키 파일의 비밀이 아닌 정보(크기, 첫 줄, 지문)만 확인했다.

```
-r-------- 1 jenkins jenkins 29 ... ****       ← 29바이트
head -1: pbcopy < ~/.ssh/ansible_lab           ← 첫 줄이 명령어
wc -l: 2
ssh-keygen -l: **** is not a public key file
```

개인 키가 아니라 `pbcopy < ~/.ssh/ansible_lab`이라는 명령어 문자열이 저장돼 있었다. 명령을 터미널에서 실행하지 않고 복사해서 Jenkins 입력 칸에 붙여넣어, 클립보드에 키가 아니라 명령어 글자가 들어간 것이다.

Jenkins는 "SSH 개인 키" 종류의 Credential에 키가 아닌 문자열을 넣어도 형식 검사 없이 저장했다. 문제는 실제로 쓰는 순간에야 드러난다.

Credential을 올바른 키로 바꾸니 지문이 원본과 일치하고 Ping이 통과했다.

```
256 SHA256:Ao/kK9s16BYRVcoHhxqDT5VCpPDgRTXVqm+01RVR4Zc ansible-labv (ED25519)
```

빌드 로그에서 확인한 점: Jenkins가 가린 것은 키 내용이 아니라 파일 경로였다(`--private-key ****`). `withCredentials`가 환경변수에 넣은 값이 경로이기 때문이다. 키 내용은 처음부터 로그에 찍힐 일이 없었다.

### 배포 버전이 되돌아간 문제

첫 Converge가 성공한 뒤 서비스가 v6.0에서 v1.0으로 내려갔다. 버전은 04 내내 `-e app_version=...`으로만 지정했고, 레포에는 버전이 어디에도 적혀 있지 않았다. 있는 것은 Role defaults의 `app_version: "1.0"`뿐이라, `site.yml`을 그냥 돌리면 모든 서버를 v1.0으로 되돌린다. 04의 M(의도하지 않은 롤백)과 같은 구조이고, 이번에는 Jenkins가 초록불을 켠 상태에서 일어났다.

"어떤 서버에 어떤 버전이 떠 있어야 하는가"를 레포에 적었다.

```yaml
# group_vars/blue/vars.yml
app_version: "6.0"
# group_vars/green/vars.yml
app_version: "7.0"
```

배포는 이 값을 바꾸는 커밋이 된다. 누가 언제 무엇을 배포했는지가 git 기록으로 남는다.

두 번 빌드해 멱등성을 확인했다.

| 빌드 | web(node1,2,4,5) | node3 | 의미 |
|---|---|---|---|
| 첫 번째 | changed=2 | changed=0 | v1.0 → 레포 버전으로 복구 |
| 두 번째 | changed=0 | changed=0 | 레포와 서버 일치 |

실행 환경(Mac brew → agent ansible-core), 접속 경로(포트 → 컨테이너 이름), 실행 주체(사람 → Jenkins)가 모두 바뀌었는데 결과가 같았다. 멱등성이 실행 환경과 무관하게 유지됐다.

참고로 Jenkins 로그 앞의 시각은 KST, Ansible 출력 안의 시각은 UTC였다(agent 컨테이너가 UTC). 여러 로그의 시간을 맞춰볼 때 시간대 차이가 분석을 헷갈리게 한다.

## 파라미터 연계와 함정

빌드 화면에서 값을 입력받아 `--limit`, `--tags`, `-e`로 넘긴다. 앞에서 만난 함정 세 개가 Jenkins 환경에서 재현됐다.

### 빈 값 함정

파라미터를 정의한 곳은 레포의 Jenkinsfile이라, Jenkins는 한 번 빌드하며 Jenkinsfile을 읽기 전까지 이 job에 파라미터가 있다는 것을 모른다. 그래서 첫 빌드는 기본값이 아니라 빈 값이 넘어간다.

```
+ ansible-playbook ... --limit  -e dry_run=
"msg": "host=node1 version=6.0 dry_run= (type=str)"
```

| 파라미터 | 의도한 기본값 | 실제로 넘어간 값 | 결과 |
|---|---|---|---|
| DRY_RUN | true (배포 안 함) | `""` | `"" \| bool`은 거짓 → 배포 실행 |
| LIMIT | web | `""` | 제한 없음 → 대상 전체 |

"배포 안 함"이 기본값인 안전장치가 값이 비었을 때 "배포 함"으로, 대상 제한이 전체로 뒤집혔다. 실패했을 때 위험한 쪽으로 열리는 구조다. 값이 비면 안전한 쪽으로 닫히게 두 겹으로 고쳤다.

- Jenkinsfile(셸): `LIMIT`이 비면 즉시 실패, `DRY_RUN`이 비면 true로 간주.

```sh
: "${LIMIT:?LIMIT is empty - refusing to run against all hosts}"
DRY_RUN="${DRY_RUN:-true}"
```

- playbook: `| bool`이 아니라 정확히 `"false"`일 때만 배포(`when: (dry_run | string | lower) == 'false'`). 빈 값이든 오타든 그 밖의 값은 전부 드라이런.

수정 전(빈 LIMIT)은 전체 서버 배포로, 수정 후는 실행 거부로 끝났다.

```
(수정 전) + ansible-playbook ... --limit  -e dry_run=          → 4대 배포 실행
(수정 후) LIMIT: LIMIT is empty - refusing to run against all hosts  → exit 2
```

Jenkins 체크박스가 불리언이 아니라 문자열로 넘어오는 것도 확인했다. DRY_RUN 체크를 해제하면 `dry_run=false (type=str)`가 되고, playbook의 판정이 이를 거짓으로 처리해 배포가 실행됐다.

### `-e` 함정

green에 `-e app_version=8.0`으로 배포하면(Q3) `version=8.0`으로 배포되지만, 레포는 여전히 7.0이다. 다음에 버전을 비우고 다시 돌리면(Q4) 아무도 롤백을 결정하지 않았는데 `version=7.0`으로 돌아간다. 파라미터로 넣은 버전은 레포에 기록이 남지 않는다.

해결책 두 가지의 대가:

| 방법 | 장점 | 대가 |
|---|---|---|
| A. 배포 = 레포 커밋 | 레포가 유일한 기준, 변경 기록이 git에 남음 | 배포할 때마다 커밋 필요 |
| B. Jenkins가 배포 후 레포에 버전 커밋 | 파라미터 편의성 유지 | Jenkins 토큰에 쓰기 권한 필요 |

B를 택하면 Jenkins가 뚫렸을 때 공격자가 레포에 코드를 넣을 수 있고, 그 코드는 다음 빌드에서 모든 서버에 root로 실행된다. 5-3에서 토큰을 읽기 전용으로 제한한 것과 배치된다. A를 택했다.

### 태그 함정

`deploy.yml`의 배포 task는 `include_role`에 `apply` 없이 `tags: deploy`만 붙였다(01 실험 B의 구조).

- Q5(수정 전): `TAGS=deploy`, `-e app_version=8.0`으로 실행하니 로그에 `version=8.0`이 찍히고 `Finished: SUCCESS`가 떴는데, 서버는 여전히 7.0이었다. `ok=2 changed=0`. 태그가 내부 task에 전달되지 않아 배포가 0건이었다.
- Q6(수정 후): `apply`를 추가하고 같은 입력으로 실행하니 `changed=2`, green이 8.0이 됐다.

```yaml
ansible.builtin.include_role:
  name: webapp
  apply:
    tags: deploy
```

세 함정 모두 Jenkins는 초록불인데 실제 결과가 의도와 달랐다. 04의 정리와 같은 문제가 파라미터 계층에서 반복됐다.

## 보안 실험

공격 실험은 `master`가 아니라 별도 브랜치(`attack-demo`)에서 했다. 브랜치를 하나 파서 Jenkinsfile을 고치는 것만으로 공격이 된다는 것 자체가 실험의 일부다.

### vault 비밀번호 추출

빌드 중에만 잠깐 파일로 풀리는 vault 비밀번호를, Jenkinsfile을 고쳐 출력해봤다. 2주차 Secret Masking을 `rev`로 뒤집어 뚫었던 것과 같은 방식이다.

| 방법 | 결과 |
|---|---|
| `cat` | 평문 그대로 노출 |
| `rev` | 뒤집힌 채 노출 |
| `base64` | 인코딩되어 노출 |
| `fold`(한 글자씩) | 공백으로 나뉘어 노출 |

네 개 전부 비밀번호가 보였다. 로그 위에 `Masking supported pattern matches of $VAULT_PASS`가 떴는데도 `cat` 결과에 원문이 그대로 찍혔다. 2주차 Secret text는 `cat`이 마스킹되고 `rev`만 뚫렸는데, 여기서는 `cat`부터 뚫렸다. 차이는 Credential 종류다. `ansible-vault-dev`는 Secret file이고, Jenkins의 자동 마스킹은 Secret text 값에는 걸리지만 파일 내용에는 걸리지 않는 것으로 보인다(원인 추정). Jenkins가 아는 것은 파일 경로지 파일 내용이 아니다.

5-4에서 Secret file이 Secret text보다 낫다고 골랐는데, 우발적 노출에는 파일이 더 안전하지만 의도적 공격 앞에서는 파일이 오히려 마스킹조차 걸리지 않아 더 취약하다. 실수에 강한 것과 공격에 강한 것이 반대로 갈린다.

공격에 master 접근이 필요 없었다. `attack-demo` 브랜치를 만들어 올렸을 뿐이다. master에 보호 규칙이 걸려 있어도 job이 다른 브랜치를 빌드할 수 있으면 그 규칙을 우회한다. "누가 코드를 넣을 수 있는가"가 master 하나가 아니라 레포의 모든 브랜치다.

이 공격을 막는 것은 더 나은 마스킹이 아니라, 브랜치 보호 + job이 보호된 브랜치만 빌드하게 제한, PR 리뷰 필수, Credential 범위 최소화다.

### 파라미터 명령 주입

취약한 버전(`sh """...${params.VERSION}..."""`, Groovy 큰따옴표 보간)과 안전한 버전(`withEnv` + `sh '''...$VERSION...'''`)을 나란히 두고 같은 입력을 넣었다.

| 입력 | A (취약) | B (안전) |
|---|---|---|
| `1.0` | `받은 버전: 1.0` | `받은 버전: 1.0` |
| `1.0; id; echo INJECTED` | `받은 버전: 1.0; id; echo INJECTED` (실행 안 됨) | 글자 그대로 |
| `1.0"; id; echo INJECTED; echo "done` | `id` 실행됨 (`uid=1000(jenkins)...`) | 글자 그대로 |

두 번째 입력은 A에서도 실행되지 않았다. `echo`가 큰따옴표 안에 있어 주입된 `; id;`도 그 따옴표 안에 갇혀 문자열의 일부가 됐다. 취약한 코드가 특정 시도에 안 뚫린다고 안전한 것이 아니다.

세 번째 입력은 따옴표를 먼저 닫아(`1.0"`) 세미콜론을 밖으로 꺼냈다. A에서 `id`가 독립된 명령으로 실행됐다.

```
+ echo 받은 버전: ... 1.0
+ id
uid=1000(jenkins) gid=1000(jenkins) groups=1000(jenkins)
+ echo INJECTED
```

B는 세 입력 모두 글자 그대로 출력됐다. 값이 환경변수로만 전달돼 셸이 코드로 읽지 않기 때문이다. 따옴표를 어떻게 닫든 상관없다.

이 `id` 자리에 vault 비밀번호 추출을 넣으면, Jenkinsfile을 못 고치는 사람도 빌드 파라미터 입력만으로 비밀번호를 훔칠 수 있다. 방어는 `sh`에 파라미터를 큰따옴표 Groovy 보간으로 넣지 않고, `withEnv`/`environment`로 환경변수에 담아 작은따옴표로 받는 것이다. 5-4·5-5에서 쓴 방식이다.

## ansible-lint

지금까지 만든 Role에 `ansible-lint`를 돌리고, 파이프라인에 품질 게이트로 넣었다.

첫 실행은 20건이 잡혔다(프로파일 `min`).

| 규칙 | 개수 | 판단 |
|---|---|---|
| `schema[meta]` (license 누락, min_ansible_version 타입) | 3 | 고침 |
| `meta-incorrect` (author/company/license 기본값) | 3 | 고침 |
| `var-naming[no-role-prefix]` | 3 | 부분 고침 (haproxy 전용 변수는 접두사, app_version은 역할 공유라 예외) |
| `name[play]` (tests/test.yml) | 3 | 제외 (galaxy 자동생성 테스트 파일) |
| `yaml[comments]` (주석 앞 공백) | 8 | 제외 (galaxy 자동생성 주석) |

의미 있는 6건을 고치고 14건은 근거를 들어 `.ansible-lint`의 `exclude_paths`·`skip_list`로 제외했다. 결과는 위반 0, 프로파일이 `min`에서 `production`(가장 엄격)으로 올라갔다.

```
Passed: 0 failure(s), 0 warning(s) ... Last profile that met the validation criteria was 'production'.
```

`|| true`를 떼어 lint가 지적을 하나라도 찾으면 빌드가 실패하고 배포로 넘어가지 못하게 했다. 품질 게이트 도입은 규칙을 다 지키는 것이 아니라 무엇을 지키고 무엇을 예외로 둘지 정하는 일이었다.

## 성능 — SSH pipelining

Ansible은 task 하나에 원격 서버로 여러 번 SSH 연결을 한다. pipelining을 켜면 이를 한 연결로 묶는다. `profile_tasks`로 측정했다(apt 없는 file 모듈 8개 × web 4대).

| | 조건 | 시간 |
|---|---|---|
| A | OFF (첫 실행) | 2.04s |
| B | OFF (재측정) | 1.72s |
| C | ON (첫 실행) | 1.26s |
| D | ON (재측정) | 1.23s |

두 번째 값끼리 비교하면 1.72s → 1.23s, 약 28% 단축이다(A→B 감소는 첫 실행의 SSH 연결 수립 비용). 로컬 컨테이너처럼 네트워크 지연이 거의 0인 환경에서 28%이므로, 원격 서버(수십 ms 지연)라면 효과가 더 커진다.

pipelining은 대상 서버 sudo 설정에 `requiretty`가 있으면 동작하지 않는다. 이 호환성 문제 때문에 Ansible이 기본으로 꺼둔다. 켜는 것은 서버 환경에서 안전함을 확인한 뒤의 선택이다.

## ansiblePlaybook 플러그인 vs sh

Ansible 플러그인의 `ansiblePlaybook` step과 `sh 'ansible-playbook ...'`을 같은 배포로 비교했다.

```
# A. sh (직접 조립)
ansible-playbook -i inventory_ci.ini deploy.yml --private-key **** --vault-id dev@**** --limit green -e dry_run=false

# B. ansiblePlaybook step (플러그인 조립)
ansible-playbook deploy.yml -i inventory_ci.ini -l green --private-key /home/jenkins/.../ssh...key -u root -e ******** --vault-id dev@****
```

세 가지가 드러났다.

1. **플러그인이 위험 패턴을 경고했다.** `extras`에 큰따옴표 Groovy 보간(`"--vault-id dev@${VAULT_PASS}"`)을 썼더니 플러그인이 `A secret was passed ... using Groovy String interpolation, which is insecure` 경고를 냈다. `sh` 방식은 같은 실수를 경고해주지 않는다.
2. **그런데 마스킹은 허술했다.** B의 명령줄에서 SSH 키 경로가 그대로 노출됐고(`--private-key /home/jenkins/.../ssh....key`), vault 경로도 `sh`(`dev@****`)보다 덜 가려졌다. 플러그인이 Jenkins 자동 마스킹 경로를 안 거치고 자체적으로 명령을 찍기 때문으로 보인다(원인 추정).
3. **파라미터 타입을 바꿨다.** 같은 `dry_run=false`를 넘겼는데 A는 `type=str`, B는 `type=bool`로 들어갔다. 플러그인이 `extraVars`를 처리하며 타입을 변환했다. 이번에는 playbook이 `| string | lower`로 방어해 양쪽 다 정상 동작했지만, 실행 방식에 따라 파라미터 타입이 바뀔 수 있다.

| 축 | sh | ansiblePlaybook step |
|---|---|---|
| 명령 제어 | 완전 자유 | 파라미터로 제한, 나머지는 extras |
| SSH 키·username | 직접 지정 | credentialsId로 자동(`-u root`까지) |
| 위험 패턴 경고 | 없음 | 있음 |
| 로그 마스킹 | Jenkins 자동 마스킹 | 자체 출력이라 일부 노출 |
| 파라미터 타입 | 넘긴 그대로(문자열) | 플러그인이 변환(불리언) |
| 이식성 | 어디서든 | 플러그인 설치 필요 |

어느 쪽이 낫다기보다 각자 다른 실수를 잡고 다른 구멍을 낸다. 어느 쪽을 쓰든 그 방식의 약점을 알고 방어해야 한다.

## 참고 자료

- [Jenkins - Using credentials](https://www.jenkins.io/doc/book/using/using-credentials/)
- [Jenkins - Injecting secrets into builds](https://www.jenkins.io/doc/developer/security/secrets/)
- [ansible-lint](https://ansible.readthedocs.io/projects/lint/)
- [Ansible - SSH pipelining](https://docs.ansible.com/ansible/latest/reference_appendices/config.html#ansible-pipelining)
