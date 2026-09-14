# Pipeline Best Practices & Operations

## 운영 관점의 핵심

---

Pipeline이 동작하는 것과 운영 가능한 것은 다르다. 운영 가능한 Pipeline은 다음 조건을 만족해야 한다.

- Controller의 CPU와 Memory를 과도하게 사용하지 않는다.
- Build는 재현 가능하고 서로 격리되어 있다.
- 오래된 Build와 Artifact가 자동으로 정리된다.
- 실패 원인을 빠르게 찾을 수 있다.
- 일시적인 오류와 코드 오류를 구분한다.
- Secret이 Console Log와 알림에 노출되지 않는다.
- 오래된 Commit이 최신 Commit보다 늦게 배포되지 않는다.
- 알림은 행동에 필요한 정보만 제공한다.

# 4-1. Controller OOM 방지와 Groovy CPS

---

Jenkins Pipeline의 Groovy 코드는 일반 Groovy와 다르게 **CPS(Continuation Passing Style)** 변환을 거친다.

> jenkins pipeline의 실행 상태를 중간중간 저장하고, Jenkins가 재시작되거나 실행이 중단되더라도 이전 지점부터 Pipeline을 이어서 실행할 수 있도록 Groovy 코드를 변환하는 실행방식
> 

```
일반 프로그램
A → B → C → 종료

Jenkins Pipeline(CPS)
A → 상태 저장 → B 대기
               ↓
          다시 실행 가능
               ↓
              C
```

예를 들어 `input`에서 몇 시간 동안 승인을 기다리거나 Controller가 재시작되더라도, Jenkins는 처음부터 Pipeline을 다시 실행하지 않고 저장된 실행 상태를 바탕으로 가능한 지점부터 이어서 실행한다.

CPS의 목적:

- Pipeline 실행 상태 저장
- Jenkins Controller 재시작 후 실행 재개
- `input`, `sleep`, `sh` 같은 비동기 Step 처리
- 중단된 위치에서 Pipeline을 계속 실행

```
Pipeline Groovy
      ↓ CPS Transform
실행 가능한 Continuation
      ↓
상태를 program.dat 등에 저장
      ↓
Controller 재시작 후 재개
```

Pipeline의 Groovy 제어 로직은 주로 Controller 자원을 사용한다. 따라서 Jenkinsfile이나 Shared Library에서 큰 Collection 처리, 대규모 JSON Parsing, 긴 반복문을 수행하면 Controller CPU와 Heap에 부담을 준다.

### 피해야 할 예시

```groovy
script {
    def values = []

    for (int i = 0; i < 1_000_000; i++) {
        values.add([
            id: i,
            value: i * 2
        ])
    }

    echo "size=${values.size()}"
}
```

문제:

- Controller CPU와 Heap을 사용한다.
- 큰 객체가 Pipeline 상태에 포함될 수 있다.
- Pipeline 저장과 재개 비용이 증가한다.
- 여러 Job에서 동시에 실행하면 Controller OOM 위험이 커진다.

### 권장 예시

```groovy
sh '''
    python3 scripts/generate-report.py         --input build/raw-data.json         --output build/summary.json
'''
```

또는:

```groovy
sh '''
    jq       '{total: length, failed: map(select(.status == "failed")) | length}'       build/results.json       > build/summary.json
'''
```

<aside>
🧭

Jenkinsfile은 실행 순서와 정책을 조정하고, 실제 데이터 처리와 빌드는 Agent에서 Shell, Python, Gradle, Maven 등의 외부 프로세스로 수행한다.

</aside>

## @NonCPS 주의

---

@NonCPS는 CPS 변환을 하지 않을 짧은 메서드에 사용할 수 있다.

```groovy
@NonCPS
String normalizeName(String value) {
    return value
        .trim()
        .toLowerCase()
        .replaceAll('[^a-z0-9-]', '-')
}
```

@NonCPS 메서드 안에서는 sh, echo, sleep, checkout 같은 Pipeline Step을 호출하면 안 된다.

```groovy
@NonCPS
void wrongExample() {
    echo 'Pipeline Step을 호출하면 안 된다.'
}
```

적합한 범위:

- 짧고 순수한 데이터 변환
- Jenkins Step을 호출하지 않는 계산
- 단순하고 직렬화 가능한 결과 반환

대규모 데이터 처리는 @NonCPS로 감싸기보다 Agent의 외부 프로그램으로 옮긴다.

## Controller OOM 방지 체크

---

- [ ]  Built-in Node의 Executor를 0으로 설정한다.
- [ ]  Groovy에서 큰 JSON/XML 파일을 직접 Parsing하지 않는다.
- [ ]  Pipeline에서 수천 번 반복되는 로직을 작성하지 않는다.
- [ ]  큰 Map/List를 Step 사이에 오래 보관하지 않는다.
- [ ]  매우 큰 Shared Library를 모든 Job에서 로드하지 않는다.
- [ ]  긴 Shell Script는 Jenkinsfile이 아니라 Repository 파일로 분리한다.
- [ ]  큰 Artifact 압축과 전송이 Controller를 경유하지 않게 한다.
- [ ]  Build와 Test는 별도 Agent에서 수행한다.
- [ ]  Controller Heap만 늘리기 전에 원인이 되는 Pipeline을 찾는다.

# 4-2. Artifact 관리와 Pipeline 성능 최적화

---

### stash / unstash

- 같은 Pipeline 실행 안에서 Stage 또는 Agent 간 파일을 전달한다.
- 기본적으로 Build가 끝나면 제거된다.
- 작은 파일 묶음에 적합하다.
- 압축 과정에서 Controller CPU를 사용할 수 있다.

```groovy
stage('Build') {
    steps {
        sh './gradlew clean bootJar'
        stash(
            name: 'application-jar',
            includes: 'build/libs/*.jar'
        )
    }
}

stage('Image') {
    agent {
        label 'docker'
    }

    steps {
        unstash 'application-jar'
        sh './scripts/build-image.sh'
    }
}
```

Jenkins 공식 Step 문서는 Stash 크기가 대략 5~100MB 범위에 들어가기 시작하면 외부 Artifact 저장소나 Remote Artifact Manager를 검토하라고 안내한다.

### archiveArtifacts

- Build 결과를 Jenkins에 보관하고 다운로드할 수 있게 한다.
- Build 보존 정책의 영향을 받는다.
- 작은 보고서나 학습 환경의 결과물에 유용하다.

```groovy
archiveArtifacts(
    artifacts: 'build/libs/*.jar',
    fingerprint: true,
    onlyIfSuccessful: true
)
```

### Artifact Repository

배포 가능한 결과물은 Jenkins Controller에 장기간 쌓기보다 전용 저장소로 전송한다.

- Nexus
- JFrog Artifactory
- Docker/OCI Registry
- Amazon S3

### Build Cache

다시 만들 필요가 없는 중간 결과를 재사용한다.

- Gradle Build Cache
- Maven Local Repository Cache
- Docker Layer Cache
- 언어별 Dependency Cache

## 선택 기준

---

```
같은 Build 내부의 작은 파일 전달
        → stash / unstash

Jenkins Build 화면에서 작은 결과 다운로드
        → archiveArtifacts

배포 가능한 Version Artifact 보관
        → Nexus / Artifactory / Registry / S3

Dependency 또는 중간 Build 결과 재사용
        → Build Cache
```

Cache 운영 원칙:

- Cache가 없어도 Build가 성공해야 한다.
- 배포 Artifact와 Cache를 구분한다.
- 서로 다른 Build가 같은 Workspace를 동시에 수정하지 않게 한다.
- Cache Key에 Build Tool과 Dependency 정보를 반영한다.
- .gradle 전체를 매 Build마다 stash하지 않는다.
- Dynamic Agent에서는 Remote Cache 또는 적절한 Persistent Volume을 검토한다.

## Pipeline 성능 튜닝

---

### Build 보존

```groovy
options {
    buildDiscarder(
        logRotator(
            daysToKeepStr: '14',
            numToKeepStr: '30',
            artifactNumToKeepStr: '5'
        )
    )
}
```

### Timeout

```groovy
options {
    timeout(time: 30, unit: 'MINUTES')
}
```

외부 API 호출이나 배포 명령에도 더 작은 Timeout을 둘 수 있다.

```groovy
timeout(time: 5, unit: 'MINUTES') {
    sh './scripts/deploy.sh'
}
```

### Retry

```groovy
retry(3) {
    sh './scripts/push-image.sh'
}
```

Retry 대상:

- 일시적인 Network 오류
- Registry 연결 오류
- 일시적인 Cloud API 오류

Retry하면 안 되는 대상:

- Compile 실패
- Unit Test 실패
- 문법 오류
- 항상 같은 입력에서 재현되는 오류

### Durability

Jenkins는 Controller 재시작 후 Pipeline을 복구하기 위해 실행 상태를 디스크에 자주 기록한다. Durability 설정을 조정하면 Disk I/O를 줄일 수 있지만 갑작스러운 종료 후 복구 가능성과 교환 관계가 있다.

- 성능 측정 없이 전역 설정을 바꾸지 않는다.
- Controller Disk I/O와 iowait를 먼저 확인한다.
- 중요 CD Pipeline과 짧은 CI Pipeline의 요구가 다를 수 있다.
- 설정 변경 전에 장애 복구 요구 사항을 정의한다.

## Workspace 격리

---

동시에 실행되는 Pipeline이 같은 Workspace 또는 외부 디렉터리를 공유하면 파일이 섞일 수 있다.

권장:

- Build별 고유 Workspace 사용
- 일회성 Container/Cloud Agent 사용
- 공유 배포 환경은 Lockable Resources로 보호
- Cache와 Workspace 분리
- Pipeline 종료 후 Workspace 정리

```groovy
post {
    cleanup {
        deleteDir()
    }
}
```

단, 장애 분석을 위해 Workspace가 필요하다면 Test Report와 필요한 로그를 먼저 게시하거나 외부 저장소에 보관한 후 정리한다.

# 4-3. Notifications와 실패 Log 요약

---

좋지 않은 알림:

```
Build failed.
```

좋은 알림:

```
❌ payment-service PR-42 실패

Stage: Unit Test
Branch: feature/refund
Commit: a1b2c3d
Duration: 4m 18s
Summary: RefundServiceTest 2건 실패
Build: https://jenkins.example.com/job/payment/42/
```

알림에 포함할 정보:

- Application 또는 Job 이름
- Branch와 PR/MR 번호
- Commit SHA
- 실패한 Stage
- 짧은 오류 요약
- 실행 시간
- Jenkins Build URL
- 담당자가 취할 다음 행동

## Slack 연동

---

```groovy
post {
    failure {
        slackSend(
            channel: '#ci-alerts',
            color: 'danger',
            message: """
                *${env.JOB_NAME} #${env.BUILD_NUMBER} 실패*
                Branch: \`${env.BRANCH_NAME}\`
                URL: ${env.BUILD_URL}
            """.stripIndent()
        )
    }
}
```

Slack Bot Token은 Jenkins Credential에 저장하고 Jenkinsfile에 직접 작성하지 않는다. 성공 알림을 모든 Build마다 보내면 Noise가 커질 수 있으므로 failure, unstable, fixed 또는 상태 변경 중심으로 알림을 구성한다.

## Teams 연동

---

Office 365 Connector 또는 Power Automate Workflow 기반 Webhook을 사용할 수 있다.

운영 원칙:

- Webhook URL을 Jenkins Credential에 저장한다.
- Repository나 Jenkinsfile에 URL을 Commit하지 않는다.
- 전체 Log를 Message에 포함하지 않는다.
- Message에는 요약과 Jenkins Build URL을 포함한다.
- Teams Workflow 변경이나 만료를 정기적으로 확인한다.

## 실패 로그 요약

---

전체 Console Log를 Slack 또는 Teams에 그대로 전송하지 않는다.

문제:

- 메시지가 너무 길어진다.
- 중요한 오류를 찾기 어렵다.
- Secret 또는 개인정보가 노출될 수 있다.
- 메시지 크기 제한에 걸릴 수 있다.

권장 흐름:

```
Build Tool
    ↓
구조화된 Test/Scan Report 생성
    ↓
Agent에서 요약 Script 실행
    ↓
1000~2000자 이내 요약
    ↓
Slack/Teams 전송
    ↓
상세 내용은 Jenkins URL 또는 Artifact로 확인
```

```groovy
post {
    failure {
        script {
            String summary = sh(
                script: '''
                    if [ -f build/ci-summary.txt ]; then
                        tail -n 40 build/ci-summary.txt
                    else
                        echo "요약 파일이 없습니다. Jenkins 로그를 확인하세요."
                    fi
                ''',
                returnStdout: true
            ).trim()

            slackSend(
                channel: '#ci-alerts',
                color: 'danger',
                message: """
                    *${env.JOB_NAME} #${env.BUILD_NUMBER} 실패*
                    ${summary.take(1500)}
                    ${env.BUILD_URL}
                """.stripIndent()
            )
        }
    }
}
```

Log 요약 전에는 Token, Password, Authorization Header, 개인정보가 포함되지 않았는지 확인한다.

## 운영 장애 확인 순서

---

### Queue가 계속 증가함

1. Online Agent와 사용 가능한 Executor 수를 확인한다.
2. Label 조건이 실제 Agent Label과 일치하는지 확인한다.
3. 장시간 input 또는 lock 대기 Build를 확인한다.
4. 병렬 Stage 수가 Agent 용량을 초과하는지 확인한다.
5. 오래된 PR Build가 취소되지 않고 남아 있는지 확인한다.

### Controller Memory가 증가함

1. 최근 추가된 Jenkinsfile과 Shared Library 변경을 확인한다.
2. 대규모 JSON/XML Parsing과 반복문을 찾는다.
3. 큰 변수와 객체를 Step 사이에 보관하는지 확인한다.
4. 대용량 stash와 archive 작업을 확인한다.
5. 동시에 실행되는 Pipeline 수와 Library 크기를 확인한다.

### Build가 느려짐

1. Queue 대기와 실제 실행 시간을 분리한다.
2. Dependency Download와 Compile 시간을 분리한다.
3. Cache Hit/Miss를 확인한다.
4. Parallel Stage가 실제 다른 Executor에서 실행되는지 확인한다.
5. Controller Disk I/O와 Agent Disk/Network I/O를 구분한다.

## 종합 실습

---

다음 흐름을 구성한다.

```
GitHub PR
   ↓
Webhook
   ↓
Multibranch Pipeline
   ↓
Shared Library
   ├── gradleBuild
   ├── publishTestResult
   └── notifyBuild
   ↓
Parallel Verification
   ├── Unit Test
   ├── Static Analysis
   └── Security Scan
   ↓
GitHub Status Check
   ↓
Slack 실패 요약
```

### 완료 조건

- [ ]  PR/MR 생성 시 Jenkins Job이 자동 생성된다.
- [ ]  새 Commit이 들어오면 이전 PR/MR Build가 중단된다.
- [ ]  Unit Test와 Static Analysis가 병렬 실행된다.
- [ ]  Static Analysis 실패는 UNSTABLE로 처리된다.
- [ ]  Unit Test 실패는 FAILURE로 처리된다.
- [ ]  Test Report가 Jenkins에 게시된다.
- [ ]  Build 결과가 GitHub/GitLab에 표시된다.
- [ ]  Shared Library 변경은 Unit Test를 통과한다.
- [ ]  실패 알림에 Branch, Build URL, 요약이 포함된다.
- [ ]  오래된 Build와 Artifact가 자동으로 정리된다.
- [ ]  큰 Artifact를 외부 Repository로 전송하는 개선 방향을 설명할 수 있다.

## 확인 질문

---

1. Pipeline Groovy가 Controller OOM의 원인이 될 수 있는 이유는 무엇인가?
2. @NonCPS 메서드 안에서 Pipeline Step을 호출하면 안 되는 이유는 무엇인가?
3. stash와 Artifact Repository의 경계는 무엇인가?
4. Retry가 코드 오류를 감추는 문제가 발생하지 않게 하려면 어떻게 해야 하는가?
5. 성공 알림을 모든 Build마다 보내는 것이 왜 좋지 않을 수 있는가?
6. Queue 대기 시간과 실제 Build 실행 시간을 어떻게 분리해 관찰할 것인가?

# 4-4. Pipeline Best Practices 참고 자료

---

- [Jenkins 공식 문서 - Pipeline Best Practices[1]](https://www.jenkins.io/doc/book/pipeline/pipeline-best-practices/)
- [Jenkins 공식 문서 - CPS Method Mismatches[2]](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
- [Jenkins 공식 문서 - Scaling Pipelines[3]](https://www.jenkins.io/doc/book/pipeline/scaling-pipeline/)
- [Jenkins 공식 문서 - Pipeline Basic Steps[4]](https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/)
- [Jenkins 공식 문서 - Hardware Recommendations[5]](https://www.jenkins.io/doc/book/scaling/hardware-recommendations/)
- [Slack Notification Plugin[6]](https://plugins.jenkins.io/slack/)
- [Office 365 Connector Plugin[7]](https://plugins.jenkins.io/Office-365-Connector)
- [CloudBees CI Application Best Practices[8]](https://docs.cloudbees.com/docs/cloudbees-ci-kb/latest/best-practices/app-performance-best-practices)