# Week 2 실습 기록

정리본: [controller-agent&jcasc&security.md](controller-agent&jcasc&security.md)

> 개념은 정리본에, 실습 과정/명령어/결과는 여기에.

---

## 1. Controller / Agent — SSH 연결 실습

**환경**: `jenkins-controller` (`jenkins/jenkins:lts-jdk21`, `jenkins` 네트워크, 8080/50000 포트)

### 진행 순서

1. **SSH 키페어 생성** (Agent 연결 전용, 로컬 스크래치 디렉토리 보관)
   ```bash
   ssh-keygen -t ed25519 -f jenkins_agent_key -N "" -C "jenkins-agent-lab"
   ```

2. **Agent 컨테이너 기동** — Public Key를 `authorized_keys`로 자동 주입
   ```bash
   docker run -d --name jenkins-agent1 --network jenkins \
     -e "JENKINS_AGENT_SSH_PUBKEY=$(cat jenkins_agent_key.pub)" \
     jenkins/ssh-agent:jdk21
   ```

3. **SSH 연결 테스트** (Controller → Agent) → 성공, Java 21 확인

4. **Jenkins UI 설정**
   - Credential 등록: `SSH Username with private key`, ID `jenkins-agent1-ssh-key`
   - Node 등록: `jenkins-agent1`, Label `linux`, Launch via SSH
   - Built-in Node Executor → `0`

5. **테스트 Job**으로 최종 확인

   ```groovy
   pipeline {
       agent { label 'linux' }
       stages {
           stage('Check Agent') {
               steps { sh 'hostname'; sh 'whoami'; sh 'pwd' }
           }
       }
   }
   ```

   ```
   Running on jenkins-agent1 in /home/jenkins/agent/workspace/agent-label-test
   + hostname
   66f2fef615fa   ← jenkins-agent1 컨테이너 ID와 일치
   Finished: SUCCESS
   ```

   ✅ Built-in Node가 아니라 `jenkins-agent1`에서 빌드 실행 확인

### 배운 점

- `agent any` = Agent 자동 생성 아님, "비어있는 Executor 아무거나" 스케줄링 지시일 뿐 → Built-in Node Executor를 0으로 안 하면 여전히 거기서 돌 수 있음
- 정적(Static) Agent ≠ Dynamic Agent Provisioning — 지금 한 건 사람이 미리 띄워둔 컨테이너를 등록한 정적 방식
- Label은 자유 텍스트(예약어 아님), Jenkins가 자동 감지하는 Architecture와는 별개 개념
- Credential ID는 자동생성 UUID 대신 의미 있는 이름으로 직접 지정하는 게 나중에 알아보기 좋음
- SSH 키는 Jenkins가 아니라 `ssh-keygen`으로 직접 생성하는 것 — EC2 접속키와 원리 동일
- Remote root directory(`/home/jenkins/agent`)는 Agent 컨테이너 **내부** 경로, 볼륨 마운트 없으면 컨테이너 삭제 시 캐시도 같이 사라짐

**Built-in Node 대신 별도 Agent를 쓰는 이유**
- 보안 격리: 빌드가 Controller 파일시스템/Credential에 직접 접근하는 걸 막음
- 자원 분리: Controller는 스케줄링/관리에만 집중
- 환경 유연성: Agent별로 OS/도구를 다르게, Label로 구분
- 확장성: Agent를 늘리면 병렬 빌드 가능
- 안정성: 빌드 문제가 Controller 전체를 마비시키지 않음

---

## 2. Configuration as Code (JCasC) 실습

**환경**: `Configuration as Code` 플러그인 설치 안 되어있어서 `jenkins-plugin-cli`로 설치 후 컨테이너 재시작

### 진행 순서

1. `Export configuration`으로 현재 설정 전체를 YAML로 추출 (267줄, 대부분 기본값)
2. 의미 있는 부분만 골라서 [jenkins.yaml](jenkins.yaml) 작성
   - `jenkins.nodes` (jenkins-agent1 Permanent Agent 정의)
   - `jenkins.numExecutors: 0`
   - `credentials` (SSH Key), 단 `privateKey`는 실제 값 대신 `${SSH_PRIVATE_KEY}` 변수로 치환
3. **1차 시도 — `Setup configuration`(재시작 없이 적용)**
   - 컨테이너에 `SSH_PRIVATE_KEY` 환경변수가 없는 상태로 적용
   - 결과: 에러 없이 적용됨. 로그에 경고만 찍힘
     ```
     WARNING: Configuration import: Found unresolved variable 'SSH_PRIVATE_KEY'. Will default to empty string
     ```
   - Credential의 Private Key가 **빈 값으로 조용히 덮어써짐** → Agent 재연결 시 `Authentication failed`
4. **2차 시도 — 컨테이너 재생성**
   ```bash
   docker run -d --name jenkins-controller --network jenkins \
     -p 8080:8080 -p 50000:50000 \
     -v jenkins_home:/var/jenkins_home \
     -e CASC_JENKINS_CONFIG=/var/jenkins_home/casc_configs/jenkins.yaml \
     -e SSH_PRIVATE_KEY="$(cat jenkins_agent_key)" \
     jenkins/jenkins:lts-jdk21
   ```
   - 부팅 시 JCasC가 YAML을 자동 적용, 이번엔 변수가 채워져서 정상 동작
   - Agent 로그: `Agent successfully connected and online` ✅

### 배운 점

- **JCasC는 변수가 없어도 에러로 죽지 않고 빈 값으로 조용히 넘어간다.** 이게 오히려 더 위험함 — 잘못된 설정이 "성공"으로 보이면서 조용히 기존 값을 깨뜨릴 수 있음. 문서에서 Secret 관리에 신중해야 한다고 강조하는 이유를 실습으로 체감.
- **환경변수는 컨테이너가 처음 뜰 때만 주입 가능.** 이미 떠 있는 컨테이너에 나중에 환경변수를 추가하는 방법은 없음 (재생성 필수) — `Setup configuration`(무중단)과 `CASC_JENKINS_CONFIG`(재시작 시 적용) 두 방식의 근본적인 차이.
- Export 결과를 그대로 쓰면 안 되고, 실제로 우리가 설정한 부분만 골라내야 함 — Export에서 `authorizationStrategy: loggedInUsersCanDoAnything`처럼 위험한 기본 설정도 같이 눈에 띔.

### Configuration Drift 재현

1. UI(`Manage Jenkins → System`)에서 System Message를 직접 입력 (`긴급 점검 중입니다`) — `jenkins.yaml`엔 없는 값
2. `Export configuration`으로 다시 뽑아서 diff → `systemMessage` 필드가 새로 생긴 것 확인 = **Drift 발생**
3. `Apply/Reload configuration` 눌러서 되돌아가는지 테스트 → **안 사라짐**
4. 원인 확인 후 `jenkins.yaml`에 `systemMessage` 항목을 추가해서 코드에 반영 → Drift 해소

**배운 점**: JCasC의 재적용은 "Jenkins 상태를 YAML과 완전히 동기화"하는 게 아니라 **YAML에 적힌 필드만 그 값으로 설정**하는 것.
- YAML에 필드가 있으면(값이 비어도) → 적용되어 덮어씀 (앞서 `privateKey`가 빈 값으로 덮어써진 이유)
- YAML에 필드가 아예 없으면 → 건드리지 않고 그대로 둠 (`systemMessage`가 재적용해도 안 사라진 이유)

→ 그래서 "관리하기로 한 설정은 반드시 YAML에 명시적으로 다 적어야 한다." 빠뜨린 항목은 Drift를 자동으로 잡아주지 않음.

---

## 3. Security & Credentials 실습

### Matrix-based Security 전환

1. `Manage Jenkins → Security → Authorization` → `Matrix-based security`로 전환
2. `admin`에 `Overall/Administer` 부여 (전환 직후 잠기지 않게 필수 선행)
3. `dev` 계정 생성 후 `Overall/Read`, `Job/Read`, `Job/Build`만 부여

### 권한 제한 테스트 (dev 계정)

| 시도 | 결과 |
|---|---|
| 대시보드 접근 | ✅ 정상 |
| `agent-label-test` Build Now | ✅ 정상 실행 |
| Job Configure / Manage Jenkins 메뉴 | UI에 **버튼 자체가 안 보임** |
| `/manage` 직접 URL 접근 | ❌ `Access Denied: dev is missing a permission, one of Overall/Manage, Overall/Administer is required` |

**배운 점**: Jenkins는 권한 없는 기능을 "보여주고 클릭 시 차단"하는 게 아니라 **UI 렌더링 단계에서부터 숨김** → 서버 단 권한 체크(`/manage` 직접 접근 시 403)와 이중으로 방어함. 버튼이 안 보이는 것 자체가 권한 설정이 정상 동작 중이라는 증거.

### Credential Masking 실습

`test-userpass` (Username/Password) Credential 만들고 `withCredentials`로 사용:

```groovy
sh 'echo $PASSWORD'
```
→ `echo ****` / 출력 `****` — 정상 마스킹

**마스킹 우회 실험** (같은 Credential로 인코딩 방식 바꿔가며 테스트):

| 방법 | 결과 |
|---|---|
| `echo $PASSWORD \| base64` (개행 포함) | `****Ao=` — **부분 노출** |
| `echo -n $PASSWORD \| base64` (개행 없음) | `****` — 완전 마스킹 |
| `echo $PASSWORD \| rev` (문자열 뒤집기) | `4321-terces-tset` — **완전 노출** (원본 시크릿 그대로) |

**배운 점**:
- Jenkins는 원본 값뿐 아니라 **Base64 인코딩 값도 미리 계산**해서 마스킹 패턴에 포함시켜 놓음 (base64가 워낙 유명한 우회법이라 대응해둔 것)
- 하지만 이 방어도 완벽하지 않음 — `echo`가 자동으로 붙이는 개행문자 하나 때문에 base64 3바이트 정렬이 틀어져서 **뒷부분이 부분 노출**됨
- Jenkins가 전혀 모르는 인코딩(`rev`, hex 등)은 **100% 그대로 노출**
- 결론: Secret Masking은 "알려진 패턴만 가려주는 보조 장치"일 뿐 보안 경계가 아님 → 진짜 방어는 Credential에 접근 가능한 Job/Folder/사용자 자체를 최소화하는 것

### Credential Scope 실습 (Global vs Folder)

1. Folder `secure-folder` 생성
2. 그 안에 Folder 전용 Credential(`folder-scoped-cred`) 등록 (Global 아님)
3. `secure-folder` 안의 Job에서 사용 → 정상 성공 (`Got it: folder-user`)
4. 루트 레벨 Job의 Credential 드롭다운 확인 → `folder-scoped-cred`는 **목록에 아예 없음**, Global Credential(`test-userpass`)만 보임

**배운 점**: Credential Scope를 Folder로 좁히면, 그 폴더 밖 Job은 존재 자체를 모름(드롭다운에 안 뜸) — 접근 시도 자체가 차단되는 게 아니라 애초에 "보이지 않아서" 쓸 수 없는 구조. 민감한 배포 Credential은 이렇게 필요한 최소 범위(Folder)로 좁혀서 관리해야 한다는 원칙을 직접 확인함.

---

## 4. Docker with Pipeline 실습

**환경 준비**: `jenkins-agent1`(SSH Agent 컨테이너)엔 원래 Docker가 없어서, Docker Pipeline 실습을 위해 재구성함
- 호스트 `docker.sock`을 `jenkins-agent1`에 마운트 (Docker-outside-of-Docker)
- 컨테이너 안에 Docker CLI 설치, `jenkins` 유저를 `root` 그룹에 추가 (소켓 권한)
- Jenkins 플러그인 `docker-workflow`(Docker Pipeline), `docker-commons` 설치

### `reuseNode true` 확인

```groovy
stage('Build') {
    agent { docker { image 'gradle:8.14.0-jdk21-alpine'; reuseNode true } }
    steps { sh 'gradle -g gradle-user-home --version'; sh 'pwd' }
}
```

콘솔 로그에서 실제 내부 동작 확인:
```
docker run ... --volumes-from <jenkins-agent1 컨테이너 ID> ... gradle:8.14.0-jdk21-alpine cat
```
→ `reuseNode true`의 실체는 `--volumes-from`으로 Agent 컨테이너의 볼륨을 그대로 빌려 쓰는 것. `pwd` 결과가 Agent의 워크스페이스 경로와 동일함을 확인. 빌드 끝나면 이 컨테이너는 `docker rm`으로 삭제되지만 `jenkins-agent1`(Agent)은 계속 살아있음 — 정리본의 "Docker 실행환경" 표와 정확히 일치.

### 캐싱 실습 (`-v $HOME/.m2:/root/.m2` → 환경 제약으로 우회)

**시행착오 3단계**:
1. 문서 예시 그대로 `-v $HOME/.m2:/root/.m2` 시도 → `mounts denied: path is not shared from host` 에러. 원인: `$HOME`이 `jenkins-agent1` **컨테이너 내부** 경로로 해석되는데, 이 경로는 실제 Docker 데몬(Docker Desktop) 입장에서는 존재하지 않는 경로임 (Docker-outside-of-Docker 환경에서 호스트 bind mount가 안 통하는 이유)
2. 호스트 경로 대신 **Named Volume**(`docker volume create maven-repo-cache`)으로 전환 → mount 자체는 성공했지만 `/root/.m2`가 이미지 안에서 `root` 소유라 `-u 1000:1000`으로 실행되는 컨테이너가 쓰기 권한 없음 (`Permission denied`)
3. `/tmp/m2-cache`로 마운트 경로를 바꿔도 여전히 실패 — Docker가 새 마운트 지점을 만들 때 기본적으로 `root` 소유로 생성하기 때문. **볼륨 자체 권한을 미리 열어줘야 함**:
   ```bash
   docker run --rm -v maven-repo-cache:/data alpine chmod -R 777 /data
   ```

최종 성공 결과 — 컨테이너가 매번 새로 만들어지고 삭제돼도 `build-history.txt` 내용이 계속 누적됨:
```
빌드 시각: Mon Sep  7 10:42:55 AM UTC 2026
빌드 시각: Mon Sep  7 10:43:12 AM UTC 2026
빌드 시각: Mon Sep  7 10:43:17 AM UTC 2026
```

**배운 점**:
- 문서의 `-v $HOME/.m2:/root/.m2` 예시는 **Agent가 실제 물리서버/VM**일 때를 가정한 것. Agent 자체가 컨테이너인 구조(DooD)에서는 호스트 경로가 아니라 **Named Volume**을 써야 함
- Docker 컨테이너의 UID/GID 권한 문제는 캐싱 실습에서 실무적으로 자주 만나는 장애물 — 이미지마다 기본 사용자가 다르고(`root` vs `ubuntu` 등), Named Volume의 초기 소유권도 기본적으로 `root`라 별도로 열어줘야 함

### Executor 부족 → 데드락 재현 (체크리스트 1번과 연결)

`Cache Test` stage에 `reuseNode`를 빼고 돌렸을 때 실제로 발생한 상황:
```
[Pipeline] stage
[Pipeline] { (Cache Test)
[Pipeline] node
Still waiting to schedule task
Waiting for next available executor
```

**원인**: 최상위 `agent any`가 이미 `jenkins-agent1`의 Executor 1개를 점유 중인데, `reuseNode` 없는 stage가 별도 Executor를 새로 요구 → Executor가 1개뿐이라 **자기 자신이 자기 자신을 막는 데드락** 발생.

**배운 점**: `reuseNode`는 단순 편의 옵션이 아니라, 여러 docker stage를 쓸 때 **Executor 고갈로 인한 데드락을 막는 실질적 안전장치**이기도 함. Executor를 넉넉히 늘리거나(체크리스트 1번 심화 항목과 연결), `reuseNode`로 같은 노드를 재사용하거나 — 상황에 맞게 선택해야 함.

---
