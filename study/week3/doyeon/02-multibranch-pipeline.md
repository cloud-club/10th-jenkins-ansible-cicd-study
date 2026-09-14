# Week 3 실습 기록 — Multibranch Pipeline

> **환경**: `jenkins-controller` + `jenkins-agent1`. GitHub 저장소는 `do-dop/10th-jenkins-ansible-cicd-study`(fork) 사용.
> Job `multibranch-lab`(Multibranch Pipeline) 생성해서 실습.

---

## Multibranch Pipeline이란

일반 Pipeline Job은 Job 1개 = Jenkinsfile 1개(브랜치 고정). 브랜치가 여러 개면 브랜치마다 Job을 사람이 직접 만들어야 한다.

**Multibranch Pipeline**은 Job이 아니라 **"Job을 자동으로 만들어주는 폴더"**에 가깝다:
- GitHub 저장소 하나를 연결
- Jenkins가 저장소의 **모든 브랜치를 스캔**
- 지정한 경로에 **Jenkinsfile이 있는 브랜치만** 골라서 그 브랜치 전용 하위 Job을 자동 생성
- 브랜치가 새로 생기면 하위 Job도 자동 생성, 브랜치가 삭제되면 하위 Job도 자동 삭제

---

## 1. Job 생성

- New Item → Multibranch Pipeline
- Branch Sources → GitHub → Credentials + Repository HTTPS URL
- Build Configuration → Mode: **by Jenkinsfile**, Script Path: `study/week3/doyeon/Jenkinsfile`
- Scan Multibranch Pipeline Triggers: Periodically (1 minute) — 로컬 환경이라 GitHub → Jenkins 인바운드 웹훅이 안 되므로 폴링으로 대체

**Script Path를 루트가 아닌 특정 경로로 지정한 이유**: 이 경로가 없는 브랜치는 자동으로 스캔 대상에서 제외되어, 팀 저장소의 다른 브랜치를 건드리지 않고 내 브랜치만 격리해서 실습 가능.

---

## 2. Scan Repository Log로 확인한 자동 판단 로직

```
Checking branch main
  'study/week3/doyeon/Jenkinsfile' not found
Does not meet criteria

Checking branch doyeon
  'study/week3/doyeon/Jenkinsfile' not found
Does not meet criteria

Checking branch week1/minjun
Ignoring SCMHead{'week1/minjun'} because current strategy excludes branches that ARE also filed as a pull request

Checking branch week3/doyeon
  'study/week3/doyeon/Jenkinsfile' found
Met criteria
```

**배운 점**:
- Script Path 필터가 정확히 동작 — 팀원 브랜치(`doyeon`, `week2/minjun` 등)는 Jenkinsfile 경로가 없어서 조용히 무시됨.
- **`week1/minjun`이 제외된 이유는 다른 브랜치와 다름** — "Jenkinsfile 없음"이 아니라 "이 브랜치가 이미 PR로 열려있어서 현재 전략이 제외시킴". `Discover branches`의 기본 전략 자체가 "PR로 열린 브랜치는 브랜치 목록에서 제외"라서, 같은 커밋이 "브랜치 Job"과 "PR Job" 양쪽에서 중복 빌드되는 걸 막아준다. → 3주차 계획의 **Concurrency & Branch Strategies**가 기본값으로 이미 동작 중이었던 사례.

---

## 3. 브랜치 자동 감지 + 자동 재빌드 확인

`study/week3/doyeon/Jenkinsfile`에 `env.BRANCH_NAME`을 출력하는 stage를 추가하고 push:

```groovy
stage('Multibranch Check') {
    steps {
        echo "BRANCH_NAME = ${env.BRANCH_NAME}"
    }
}
```

**결과**:
- 버튼을 누르지 않아도 1분 폴링 주기 안에 **새 커밋을 감지해서 자동으로 새 빌드 트리거**됨.
- 콘솔 로그에 `BRANCH_NAME = week3/doyeon` 정상 출력.

**배운 점**:
- `env.BRANCH_NAME`은 Multibranch Pipeline에서만 자동으로 주입되는 변수 — 일반 Pipeline Job에는 존재하지 않음.
- 워크스페이스 경로가 `multibranch-lab_week3_doyeon`처럼 **Job 이름 + 브랜치 이름을 언더스코어로 합쳐서** 자동 생성됨.

---

## 4. Status Check Feedback (Commit Status API)

**개념**: GitHub의 모든 커밋(SHA)에는 외부 도구(Jenkins 등)가 검사 결과를 붙일 수 있는 슬롯이 있음(Commit Status API). Jenkins가 빌드 결과를 GitHub에 API로 알려주면:
- 커밋 목록/PR 페이지에 ✅/❌/🟡 아이콘으로 표시됨
- PR의 "Details" 링크를 누르면 Jenkins 콘솔 로그로 바로 이동
- Branch Protection Rule로 "이 check가 SUCCESS여야 머지 가능"하게 강제할 수 있음 (실무에서 CI 통과 안 하면 머지 못 하게 막는 방식의 기반)

**확인 결과**: 커밋 페이지에 `continuous-integration/jenkins/branch — This commit looks good` ✅ 체크가 정상적으로 붙는 것 확인.

(GitHub PAT 권한/스코프 설정 관련 트러블슈팅 과정은 별도 기록하지 않음 — 최종적으로 fork 저장소를 대상으로 하는 Credential 설정 후 정상 동작 확인함.)

---

## 5. PR 빌드 + Status Check 확인

`Discover pull requests from origin` behavior 추가(Strategy: `Merging the pull request with the current target branch revision`) 후, fork 저장소 안에서 `week3/doyeon-multibranch` → `week3/doyeon`으로 테스트 PR 생성.

**결과**:
- Pull Requests 탭에 `PR-1` Job 자동 생성
- 콘솔 로그에서 `CHANGE_ID=1`, `CHANGE_TARGET=week3/doyeon` 정상 확인 (일반 브랜치에는 없는, PR 빌드에서만 채워지는 변수)
- 로그에 `Merging remotes/origin/week3/doyeon ... into PR head ...` — PR 브랜치 원본이 아니라 **target과 미리 머지한 결과**를 빌드함 (머지 시 충돌 여부를 PR 단계에서 미리 검증하는 방식)
- GitHub PR 페이지에 `continuous-integration/jenkins/pr-merge — This commit looks good` ✅ Status Check 정상 표시
- (새 커밋 기준으로 재확인한 결과 체크가 1개만 뜨는 것도 확인 — 초기엔 설정 변경 이력이 같은 커밋에 누적되어 여러 개로 보였을 뿐, 최종 설정은 문제 없었음)

---

## 6. Concurrency — `milestone`으로 오래된 빌드 자동 취소

### 6-1. `milestone` 개념

Pipeline은 기본적으로 **여러 빌드를 동시에 실행**할 수 있다. `milestone` step은 빌드들이 milestone을 **빌드 번호 순서대로** 통과하도록 강제하는 체크포인트다.

**공식 규칙 4가지**:
- 빌드는 빌드 번호 순서에 따라 milestone을 통과한다.
- 최신 빌드가 이미 milestone을 통과했다면, 그 milestone에 아직 도달 못한 이전 빌드는 통과할 수 없고 **중단(abort)**된다.
- 어떤 빌드가 milestone을 통과하면, 이전 milestone은 통과했지만 현재 milestone엔 아직 도달 못한 더 오래된 빌드들이 중단된다.
- **한 번 milestone을 통과한 빌드는, 아직 그 milestone을 통과하지 않은 최신 빌드 때문에 취소되지 않는다.**

마지막 규칙이 핵심이다 — 판단 기준은 "최신 빌드가 존재하는가"가 아니라 **"최신 빌드가 실제로 이 지점을 통과했는가"**다.

```
              milestone
                  │
#10 ──────────────●──────── Deploy   (이미 통과함 → 안전)
#11 ───────────────────                (아직 진행 중)
#12 ─────────●                         (아직 도달 전)
```
→ #10이 이미 통과했다면, #12가 새로 시작됐다는 이유만으로 #10을 죽이지 않는다.

**왜 필요한가**: 빌드는 동시에 실행되므로 꼭 번호 순서로 끝나지 않는다.

```
#10 : 테스트가 오래 걸림
#11 : 테스트가 오래 걸림
#12 : 테스트 빨리 끝남 → 배포
```

`milestone`이 없으면 #12(최신)가 먼저 배포된 뒤, 나중에 #10(구버전)이 테스트를 끝내고 배포되면서 **최신 버전이 예전 버전으로 되돌아가는 사고**가 날 수 있다. 배포 직전에 `milestone`을 두면:

```
Build #10 ── Test ─────────→ milestone  ❌ Abort
Build #11 ── Test ──────→ milestone     ❌ Abort
Build #12 ── Test ─→ milestone ─→ Deploy ✅
```

**옵션**
- `ordinal`: milestone의 순번(숫자). 실제 비교 로직에 쓰임. 보통 자동 생성되지만, 파이프라인 코드를 수정하면서 기존 빌드가 실행 중인 상황이면 명시 지정이 안전 (우리 환경은 자동 생성이 안 돼서 필수였음 — 아래 배운 점 참고).
- `label`: 로그에 표시되는 이름표. 비교 로직과 무관, 가독성용.
- `unsafe`: `parallel` 블록 안에서 milestone을 쓰게 허용하는 옵션. 위험성을 이해 못했다면 켜지 말라고 공식 문서가 경고 — 학습 단계에서는 신경 안 써도 됨.

**`milestone` vs `disableConcurrentBuilds`**

| | 동시 실행 자체 | 목적 |
|---|---|---|
| `disableConcurrentBuilds` | **원천 차단** — 한 번에 1개만 실행 | 순서 보장을 "실행 자체를 막는" 방식으로 해결 |
| `milestone` | **허용** — 여러 빌드가 동시에 돔 | 빌드/테스트는 병렬로 빠르게 돌리되, 특정 지점(배포 등)에서만 최신 빌드만 살아남게 함 |

빌드가 오래 걸리는 프로젝트라면 매번 순차 실행은 비효율적이니, **테스트는 병렬로 돌리고 배포 직전에만 milestone으로 순서를 강제**하는 조합이 실무에서 더 널리 쓰인다.

**실무 파이프라인 적용 예**:
```
Git Push → Build → Test → milestone → Docker Build → Deploy → Health Check → Cutover
```
"더 이상 오래된 빌드가 넘어오면 안 되는 경계"(배포 직전)에 두는 것이 핵심 패턴. `lock` step과 조합하면 더 강력함 — `lock`은 "한 번에 하나만 배포", `milestone`은 "최신 빌드가 지나갔으면 오래된 빌드는 폐기"로 역할이 다르다.

**참고 문헌**:
- [Pipeline Steps Reference - milestone step](https://www.jenkins.io/doc/pipeline/steps/pipeline-milestone-step/)
- [Jenkins Blog - Stage, Lock, and Milestone](https://www.jenkins.io/blog/2016/10/16/stage-lock-milestone/)

### 6-2. 실습

같은 로직이 브랜치/PR 어디서든 동일하게 적용되므로, 빠른 검증을 위해 `pipeline-syntax-lab` Job(일반 Pipeline)으로 진행.

```groovy
pipeline {
    agent { label 'linux' }
    options { timestamps() }
    parameters {
        string(name: 'SLEEP_SECONDS', defaultValue: '10', description: 'milestone 도달 전 대기 시간(초)')
    }
    stages {
        stage('Slow Work') {
            steps {
                echo "빌드 #${env.BUILD_NUMBER} 시작 — ${params.SLEEP_SECONDS}초 대기"
                sh "sleep ${params.SLEEP_SECONDS}"
            }
        }
        stage('Milestone Gate') {
            steps {
                milestone ordinal: 1, label: 'gate'
                echo "빌드 #${env.BUILD_NUMBER}가 milestone 통과"
            }
        }
        stage('Deploy') {
            steps {
                sh 'sleep 5'
                echo "빌드 #${env.BUILD_NUMBER} 배포 완료"
            }
        }
    }
}
```

**실행**: `SLEEP_SECONDS=30`(구버전, #26)으로 먼저 실행 → 5초 뒤 `SLEEP_SECONDS=5`(신버전, #27) 실행.

**결과**:
| Build | SLEEP_SECONDS | 시작 | 결과 |
|---|---|---|---|
| #26 | 30 | 18:01:45 | `sleep 30` 도중 `Superseded by pipeline-syntax-lab#27` → 강제 종료 → 이후 stage `skipped due to earlier failure(s)` → **`NOT_BUILT`** |
| #27 | 5 | 18:01:49 | 18:01:55에 milestone 통과 → 정상 배포 → **`SUCCESS`** |

**실습에서 추가로 확인한 것** (공식 문서/개념 정리에는 없는, 이 환경 고유의 디테일):
- 이 Jenkins 버전에서는 `ordinal`을 생략하면 `Missing required parameter: "ordinal"` **컴파일 에러**가 남 — 문서상 자동 생성되어야 하지만 이 환경에서는 명시 지정이 필수였음.
- #27이 milestone을 통과한 시각(18:01:55)과 #26이 `Superseded` 메시지를 받은 시각(18:01:55)이 **정확히 일치** — 초 단위로 즉시 취소되는 것 확인.
- milestone에 의해 취소된 빌드는 `ABORTED`가 아니라 **`NOT_BUILT`**로 표시됨 — 사람이 직접 취소 버튼을 누른 경우(`ABORTED`)와 최종 상태 코드가 다름.
- 같은 원리가 PR/브랜치에 빠르게 커밋을 연달아 push했을 때도 그대로 적용되어, 오래된(낡은 커밋 기준) 빌드가 자동으로 정리됨.

