# Jenkins 2주차 — Advanced Pipeline, Shared Library & Operations

---

## 1. Declarative Pipeline

Jenkins Pipeline은 빌드·테스트·배포 과정을 코드로 정의하는 기능이다. 공식 문서에서는 Pipeline을 `Jenkinsfile`로 작성해 애플리케이션 코드와 함께 버전 관리하는 방식을 권장한다.

Declarative Pipeline의 기본 구조는 다음과 같다.

```groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }

        stage('Test') {
            steps {
                sh './gradlew test'
            }
        }
    }

    post {
        always {
            echo 'finished'
        }
    }
}
```

여기서 자주 사용하는 구성은 다음 정도다.

- `agent`: Pipeline 또는 Stage가 실행될 Agent
- `stages`, `stage`, `steps`: 실제 작업 흐름
- `environment`: 환경 변수
- `options`: timeout, 동시 실행 제한, Build 보관 정책
- `parameters`: 수동 실행 시 입력값
- `triggers`: cron, SCM polling 같은 실행 조건
- `when`: Stage 실행 조건
- `post`: 성공·실패 이후 후처리

### agent

`agent any`는 사용 가능한 Agent에서 Pipeline을 실행한다.

```groovy
pipeline {
    agent any
}
```

Stage마다 다른 Agent를 사용하려면 Top-level을 `agent none`으로 둘 수 있다.

```groovy
pipeline {
    agent none

    stages {
        stage('Build') {
            agent { label 'builder' }
            steps {
                sh './build.sh'
            }
        }

        stage('Deploy') {
            agent { label 'deploy' }
            steps {
                sh './deploy.sh'
            }
        }
    }
}
```

공식 문서에서는 이 방식이 Pipeline 전체가 불필요하게 하나의 Executor를 계속 점유하는 것을 막을 수 있다고 설명한다.

또한 `timeout`을 Stage-level `agent`와 함께 사용할 때는 Agent 할당을 기다리는 시간도 timeout에 포함될 수 있다. Cloud Agent처럼 Provisioning 시간이 있는 환경에서는 이 차이를 알아둘 필요가 있다.

### environment와 credentials

환경 변수는 Pipeline 전체 또는 Stage 범위에 설정할 수 있다.

```groovy
environment {
    APP_NAME = 'backend'
    SERVICE_CREDS = credentials('service-account')
}
```

`credentials()`는 Jenkins Credentials Store에 저장된 Credential을 ID로 불러온다. Secret을 Jenkinsfile에 직접 적는 방식보다 이 방법을 사용해야 한다.

### options

실무에서 자주 쓸 만한 옵션은 다음과 같다.

```groovy
options {
    timestamps()
    timeout(time: 30, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '20'))
    disableConcurrentBuilds(abortPrevious: true)
}
```

`buildDiscarder`는 오래된 Build와 Artifact가 계속 쌓이는 것을 막고, `disableConcurrentBuilds`는 같은 Pipeline의 동시 실행을 제어한다.

```groovy
options {
    disableConcurrentBuilds()
}
```

는 이전 Build가 끝날 때까지 새 Build를 Queue에 대기시킨다.

```groovy
options {
    disableConcurrentBuilds(abortPrevious: true)
}
```

는 새 Build가 시작되면 이전 실행을 중단한다. PR에 Commit을 여러 번 연속 Push하는 환경에서 특히 유용하다.

### parameters와 when

배포 대상이나 실행 옵션을 사용자가 선택하게 할 수 있다.

```groovy
parameters {
    choice(
        name: 'DEPLOY_ENV',
        choices: ['dev', 'staging', 'prod'],
        description: '배포 환경'
    )
}
```

값은 `params.DEPLOY_ENV`처럼 사용한다.

`when`을 이용하면 특정 Branch나 PR에서만 Stage를 실행할 수 있다.

```groovy
stage('Deploy') {
    when {
        allOf {
            branch 'main'
            expression { params.DEPLOY_ENV == 'prod' }
        }
    }

    steps {
        sh './deploy.sh'
    }
}
```

PR에서만 실행하려면 다음처럼 쓸 수 있다.

```groovy
when {
    changeRequest()
}
```

### post

`post`는 Pipeline 또는 Stage가 끝난 뒤의 처리를 정의한다.

```groovy
post {
    success {
        echo 'success'
    }

    failure {
        echo 'failed'
    }

    cleanup {
        deleteDir()
    }
}
```

주로 테스트 결과 기록, Artifact 보관, Workspace 정리, 알림 등에 사용한다.

공식 문서에서 제공하는 조건에는 `always`, `success`, `failure`, `unstable`, `aborted`, `changed`, `fixed`, `regression`, `cleanup` 등이 있다.

### Parallel과 Matrix

서로 독립적인 테스트는 `parallel`로 동시에 실행할 수 있다.

```groovy
stage('Validation') {
    parallel {
        stage('Unit Test') {
            steps { sh './ci/test.sh' }
        }

        stage('Lint') {
            steps { sh './ci/lint.sh' }
        }

        stage('Security Scan') {
            steps { sh './ci/security.sh' }
        }
    }
}
```

`matrix`는 같은 작업을 여러 환경 조합에서 반복할 때 사용한다.

```groovy
stage('Compatibility') {
    matrix {
        axes {
            axis {
                name 'PLATFORM'
                values 'linux', 'windows'
            }
            axis {
                name 'JDK'
                values '17', '21'
            }
        }

        stages {
            stage('Test') {
                steps {
                    sh './ci/test.sh'
                }
            }
        }
    }
}
```

위 예시는 Linux/Windows × JDK 17/21의 네 조합을 만든다.

정리하면 `parallel`은 **서로 다른 독립 작업**, `matrix`는 **같은 작업의 여러 환경 조합**에 적합하다.

### Error Handling

기본적으로 `sh`가 0이 아닌 Exit Code를 반환하면 Step이 실패한다.

실패를 기록하되 Pipeline을 계속 진행하고 싶다면 `catchError`를 사용할 수 있다.

```groovy
catchError(
    buildResult: 'UNSTABLE',
    stageResult: 'FAILURE'
) {
    sh './integration-test.sh'
}
```

`unstable()`은 Build와 Stage를 `UNSTABLE` 상태로 표시한다.

```groovy
unstable('quality gate failed')
```

`warnError`는 실패 시 Build와 Stage를 `UNSTABLE`로 만들면서 다음 작업을 계속 진행하는 간단한 형태다.

```groovy
warnError('Lint failed') {
    sh './lint.sh'
}
```

### Trigger와 Webhook

Declarative Pipeline에는 다음과 같은 Trigger가 있다.

```groovy
triggers {
    cron('H 3 * * *')
}
```

SCM Polling도 가능하다.

```groovy
triggers {
    pollSCM('H/5 * * * *')
}
```

하지만 GitHub/GitLab 기반 Multibranch Pipeline에서는 Branch Source Plugin과 Webhook을 이용해 Push, PR/MR 이벤트에 반응하게 구성하는 경우가 일반적이다.

```text
Developer
   │ push / PR / MR
   ▼
GitHub / GitLab
   │ webhook
   ▼
Jenkins
   │
   ▼
Branch indexing / Pipeline build
```

Polling은 Jenkins가 주기적으로 변경 여부를 확인하는 방식이고, Webhook은 SCM에서 이벤트가 발생했을 때 Jenkins에 알려주는 방식이다.

---

## 2. Multibranch Pipeline과 Pull Request 검증

Branch마다 Jenkins Job을 직접 만들면 관리가 복잡해진다.

```text
backend-main
backend-develop
backend-feature-login
...
```

Multibranch Pipeline은 Repository를 Scan해서 **`Jenkinsfile`이 있는 Branch를 자동으로 발견하고 관리**한다.

```text
repository
├── main/Jenkinsfile
├── develop/Jenkinsfile
└── feature/login/Jenkinsfile
```

Jenkins에서는 각 Branch가 자동으로 별도 Pipeline처럼 관리된다.

이 구조의 장점은 Pipeline 코드도 애플리케이션 코드처럼 Git으로 관리할 수 있다는 점이다. Pipeline 변경도 Commit, Review, Rollback 대상이 된다.

### Branch Scan과 checkout scm

Multibranch Pipeline에서 Jenkins는 Repository를 Scan해 `Jenkinsfile`이 있는 Branch를 찾는다.

코드를 Checkout할 때는 다음 형태가 중요하다.

```groovy
checkout scm
```

공식 Pipeline as Code 문서에서는 이 명령이 현재 Jenkinsfile이 온 정확한 SCM Revision을 Checkout하도록 보장하며, Pull Request처럼 Origin이 달라지는 경우도 고려한다고 설명한다.

### Branch/PR 환경 변수

Multibranch Pipeline에서는 Branch와 Change Request 정보를 환경 변수로 받을 수 있다.

```text
BRANCH_NAME
CHANGE_ID
CHANGE_TARGET
CHANGE_BRANCH
```

예를 들어 PR에서만 검증 Stage를 실행할 수 있다.

```groovy
stage('PR Validation') {
    when {
        changeRequest()
    }

    steps {
        sh './ci/validate-pr.sh'
    }
}
```

반대로 배포는 `main`에서만 실행하게 만들 수 있다.

### PR / MR Pipeline

GitHub Branch Source, GitLab Branch Source 등의 Plugin을 사용하면 Pull Request나 Merge Request를 Pipeline 대상으로 다룰 수 있다.

일반적인 흐름은 다음과 같다.

```text
PR 생성 또는 업데이트
        │
        ▼
      Webhook
        │
        ▼
      Jenkins
        │
        ├─ Build
        ├─ Unit Test
        ├─ Lint
        └─ Security Scan
        │
        ▼
GitHub/GitLab 상태 반영
```

PR 단계에서 CI가 성공한 Commit만 Merge하도록 만들면 Jenkins가 Merge Gate 역할을 하게 된다.

GitLab Branch Source 공식 Plugin 문서에서는 Build 결과를 해당 HEAD Commit의 Pipeline Status로 GitLab에 통지한다고 설명한다. GitHub도 Branch Source와 관련 Plugin을 통해 Commit Status/Check를 연결할 수 있다.

### 중복 PR Build 처리

PR에 Commit을 연속으로 Push하면 오래된 Build가 의미 없이 계속 실행될 수 있다.

```text
Commit A → Build #20
Commit B → Build #21
Commit C → Build #22
```

이 경우:

```groovy
options {
    disableConcurrentBuilds(abortPrevious: true)
}
```

를 사용하면 최신 Build가 시작될 때 이전 Build를 중단할 수 있다.

### milestone

`milestone`은 단순한 동시 실행 금지와 목적이 다르다.

공식 Milestone Step 문서에서는 **새 Build가 특정 milestone을 이미 통과했다면 오래된 Build가 그 지점을 뒤늦게 통과하지 못하게 하는 기능**이라고 설명한다.

```groovy
milestone 10
sh './test.sh'

milestone 20
sh './deploy.sh'
```

이 기능은 특히 오래된 Build가 최신 Build보다 나중에 배포되는 상황을 막는 데 유용하다.

| 기능 | 목적 |
|---|---|
| `disableConcurrentBuilds()` | 같은 Pipeline의 동시 실행 제한 |
| `abortPrevious: true` | 새 Build가 시작되면 이전 Build를 즉시 중단 |
| `milestone` | Build들이 중요한 진행 지점을 순서대로 통과하도록 제어 |

### Organization Folder

Multibranch Pipeline이 Repository 하나를 대상으로 한다면 Organization Folder는 Organization 전체를 대상으로 한다.

```text
GitHub/GitLab Organization
├── backend
├── frontend
└── batch
```

Organization Folder는 Repository를 발견하고 각 Repository의 Branch/PR을 Multibranch Pipeline으로 관리할 수 있다. Repository가 많은 조직에서는 Job을 하나씩 수동 등록하는 것보다 이 구조가 자연스럽다.

---

## 3. Shared Library

서비스가 많아지면 Jenkinsfile에 같은 코드가 반복된다.

```text
Docker Build
Docker Push
Helm Deploy
Notification
```

Jenkins 공식 문서는 이런 공통 Pipeline 코드를 재사용하기 위해 **Shared Library**를 제공한다.

### 기본 구조

공식 문서의 구조는 다음과 같다.

```text
(root)
├── src/
│   └── org/foo/Bar.groovy
├── vars/
│   ├── foo.groovy
│   └── foo.txt
└── resources/
    └── org/foo/bar.json
```

- `vars/`: Pipeline에서 바로 호출할 Global Variable / Custom Step
- `src/`: 일반 Groovy Class
- `resources/`: JSON, YAML, Template 같은 정적 파일

### vars/와 Custom Step

```groovy
// vars/buildImage.groovy

def call(String image) {
    sh "docker build -t ${image} ."
}
```

Jenkinsfile에서는 다음처럼 사용할 수 있다.

```groovy
@Library('company-ci') _

pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                buildImage('backend:latest')
            }
        }
    }
}
```

`call()`을 정의하면 Shared Library의 Global Variable을 Jenkins 기본 Step처럼 호출할 수 있다.

하나의 `vars` 파일에 여러 Method를 두는 것도 가능하다.

```groovy
// vars/log.groovy

def info(message) {
    echo "INFO: ${message}"
}

def warning(message) {
    echo "WARNING: ${message}"
}
```

Declarative Pipeline에서 객체 Method를 호출할 때는 `script {}` 안에서 호출해야 하는 경우가 있다.

### src/와 Class

복잡한 로직은 `src/`에 Class로 분리할 수 있다.

```groovy
package com.company.pipeline

class Image implements Serializable {
    String registry
    String name

    String fullName(String tag) {
        return "${registry}/${name}:${tag}"
    }
}
```

Pipeline 상태를 저장해야 하는 Class는 `Serializable`을 고려해야 한다. Jenkins Pipeline이 실행 도중 중단되고 다시 Resume될 수 있기 때문이다.

Class에서 `sh`, `tool` 같은 Pipeline Step을 사용하려면 Script Context를 전달하는 방식이 있다.

```groovy
class BuildUtils implements Serializable {
    def steps

    BuildUtils(steps) {
        this.steps = steps
    }

    def build() {
        steps.sh './gradlew build'
    }
}
```

공식 Shared Library 문서도 `this`를 전달해 Class에서 Pipeline Step에 접근하는 예제를 제공한다.

### resources/

정적 YAML/JSON/Template은 `resources/`에 저장하고 `libraryResource`로 읽을 수 있다.

```groovy
def manifest =
    libraryResource 'com/company/k8s/deployment.yaml'
```

Kubernetes Manifest Template이나 공통 설정 파일을 Shared Library와 함께 관리할 때 사용할 수 있다.

### Library 로드와 Version

기본 사용:

```groovy
@Library('company-ci') _
```

특정 Version:

```groovy
@Library('company-ci@v1.2.0') _
```

공식 문서에 따르면 Version은 Git Branch, Tag, Commit Hash 등 SCM이 이해하는 값으로 지정할 수 있다.

모든 Pipeline이 Library의 `main`만 바라보면 Library 변경 하나가 여러 서비스에 동시에 영향을 줄 수 있다. 그래서 운영 환경에서는 Version을 명시적으로 고정하는 편이 안전하다.

### Global Variable은 Stateless하게

공식 Shared Library 문서에서는 `vars/`의 Global Variable에 상태를 저장하지 말라고 강조한다.

```groovy
// 좋은 방향

def call(String image) {
    sh "docker build -t ${image} ."
}
```

Global Variable은 함수 모음처럼 Stateless하게 두는 것이 좋다. Controller Restart 시 내부 상태가 유지된다고 가정하면 안 된다.

### Shared Library를 너무 크게 만들지 않기

Best Practices 문서에서는 다음을 주의하라고 한다.

- Built-in Pipeline Step 이름을 덮어쓰지 않기
- 너무 큰 Global Variable 파일 만들지 않기
- Shared Library 자체를 지나치게 크게 만들지 않기

그래서 하나의 거대한 `companyPipeline.groovy`보다 기능별로 나누는 편이 관리하기 쉽다.

```text
vars/
├── buildImage.groovy
├── pushImage.groovy
├── deployHelm.groovy
├── runTests.groovy
└── notifySlack.groovy
```

### Shared Library 테스트

공식 Shared Library 문서에는 Library 변경을 미리 검증하고 PR 변경을 테스트하는 내용이 별도로 있다.

구조적으로는 다음처럼 분리하는 편이 테스트하기 쉽다.

```text
Jenkinsfile
    ↓
Shared Library 호출

vars/
    ↓
Jenkins DSL 연결

src/
    ↓
재사용 가능한 Groovy Logic

Shell / Python / Build Tool
    ↓
실제 Build/Test/Deploy
```

복잡한 Build Logic은 Jenkins Groovy 안에 넣기보다 외부 Script로 빼면 Jenkins 없이도 로컬에서 테스트할 수 있다는 장점이 있다.

---

## 4. Pipeline 운영과 Best Practices

공식 **Pipeline Best Practices** 문서에서 가장 중요한 내용은 Pipeline의 Groovy 코드를 **glue**로 사용하라는 것이다.

즉 Jenkinsfile은 Build 프로그램 자체가 아니라 여러 작업을 연결하는 오케스트레이션 계층에 가깝다.

```text
Jenkinsfile
    │
    ├─ 실행 순서
    ├─ 조건
    ├─ Agent 선택
    └─ 실패 처리
         │
         ▼
Shell / Python / Maven / Gradle
Docker / Terraform / Helm / kubectl
```

### Controller에서 무거운 Groovy 연산을 피하기

공식 Best Practices 문서에 따르면 Pipeline의 Groovy 코드는 Controller에서 실행되므로 CPU와 Memory를 사용한다.

따라서 큰 JSON/XML 파일을 Groovy에서 직접 파싱하거나, 대규모 반복·변환 작업을 수행하는 것은 피하는 편이 좋다.

```groovy
// 피하고 싶은 방향
script {
    def json = readFile('large.json')
    // Groovy로 대량 처리
}
```

가능하면 Agent에서 외부 Tool을 실행한다.

```groovy
sh '''
    jq '.items[] | select(.enabled == true)' \
        large.json > result.json
'''
```

이렇게 하면 실제 파일 처리 비용을 Agent 쪽에서 부담한다.

### Build Logic은 외부 Script로

Pipeline 안에 명령을 계속 쌓기보다 복잡한 Build 과정은 Script로 분리할 수 있다.

```groovy
sh './ci/build.sh'
```

```bash
#!/usr/bin/env bash
set -euo pipefail

npm ci
npm run lint
npm test
npm run build
```

이 방식은 Jenkins가 없어도 로컬에서 같은 Build Script를 실행해볼 수 있고, Jenkinsfile도 단순해진다.

### CPS와 Serializable

Jenkins Pipeline은 일반 Groovy와 달리 대부분의 코드를 **CPS(Continuation Passing Style)** 형태로 변환해서 실행한다.

목적은 Pipeline 실행 상태를 Disk에 저장해 Controller Restart 이후에도 실행을 이어갈 수 있게 만드는 것이다.

```text
Build → Test → Controller Restart → Resume
```

이 때문에 Pipeline이 보관하고 있는 값은 직렬화 가능한 형태여야 한다. 그렇지 않으면 `NotSerializableException`이 발생할 수 있다.

가능하면 Pipeline 상태에는 String, Number, List, Map 같은 단순한 값을 두고, 복잡한 Object를 오래 유지하지 않는 편이 안전하다.

### @NonCPS

CPS 변환을 적용하지 않을 Method에는 `@NonCPS`를 사용할 수 있다.

```groovy
@NonCPS
def sortData(List values) {
    return values.sort()
}
```

하지만 공식 CPS 문서에서 중요한 제한은 다음과 같다.

> `@NonCPS` Method에서는 CPS 기반 Pipeline Step을 호출하면 안 된다.

따라서 다음 코드는 잘못된 사용이다.

```groovy
@NonCPS
def build() {
    sh './build.sh'
}
```

또 `@NonCPS`를 붙인다고 연산이 Agent로 이동하는 것도 아니다. 무거운 작업은 외부 Script로 넘기는 것이 우선이다.

### stash / unstash와 Artifact

서로 다른 Agent 사이에서 같은 Pipeline Run의 파일을 전달할 때 `stash` / `unstash`를 사용할 수 있다.

```groovy
stage('Build') {
    steps {
        sh './gradlew build'
        stash name: 'app', includes: 'build/libs/*.jar'
    }
}

stage('Deploy') {
    steps {
        unstash 'app'
        sh './deploy.sh'
    }
}
```

`stash`는 같은 Pipeline Run 안에서 임시 파일을 전달하는 용도다.

공식 Basic Steps 문서에서는 큰 파일 전송에는 적합하지 않다고 설명한다. 기본 구현에서는 압축 TAR를 만들기 때문에 Controller CPU를 많이 사용할 수 있으며, 대략 5~100MB 수준부터는 다른 방법을 검토할 필요가 있다고 안내한다.

큰 Artifact는 다음과 같은 별도 저장소가 더 적합하다.

```text
Nexus
Artifactory
S3-compatible Object Storage
Container Registry
```

Build 결과를 Jenkins Build와 함께 보관하려면 `archiveArtifacts`를 사용할 수 있다.

```groovy
archiveArtifacts(
    artifacts: 'build/libs/*.jar',
    fingerprint: true
)
```

### Pipeline Durability

Pipeline은 Controller 장애 이후 Resume를 위해 실행 상태를 자주 Disk에 기록한다.

공식 Scaling Pipelines 문서는 이를 **Speed/Durability Trade-off**로 설명한다.

```text
Durability ↑
→ 상태 저장 빈도 증가
→ 장애 복구에 강함
→ Disk I/O 증가

Performance ↑
→ 상태 저장 빈도 감소
→ I/O 감소
→ 갑작스러운 종료 시 복구 가능성 일부 감소
```

Performance Optimized 설정은 모든 Pipeline을 무조건 빠르게 만드는 옵션은 아니다.

특히 Pipeline 대부분이 `sh` 명령의 완료를 기다리는 구조라면 큰 효과가 없을 수 있다. 반대로 Step 수가 매우 많거나, Controller Storage가 느리거나, Pipeline이 큰 데이터 구조를 상태에 유지하는 경우에는 영향이 커질 수 있다.

### Log와 Notification

실패 알림에는 Console Log 전체보다 사람이 바로 판단할 수 있는 요약을 보내는 편이 낫다.

```text
FAILED: backend/main #124
Stage: Unit Test
Failed tests: 3
Build URL: ...
```

세부 로그는 Jenkins Build 페이지나 Artifact에서 확인한다.

Slack은 Jenkins Slack Notification Plugin, Teams는 Office 365 Connector / Power Automate 계열 Plugin을 통해 연동할 수 있다.

```groovy
post {
    failure {
        slackSend(
            message: "FAILED: ${env.JOB_NAME} #${env.BUILD_NUMBER}\n${env.BUILD_URL}"
        )
    }
}
```

여러 Pipeline에서 같은 알림 코드를 쓴다면 `notifySlack()` 같은 Shared Library Step으로 분리할 수 있다.

### 운영 관점에서 정리

이번 주 문서를 읽으면서 Jenkins의 역할을 다음처럼 정리했다.

```text
GitHub / GitLab
      │ Webhook
      ▼
Jenkins Controller
      │ Pipeline orchestration
      ▼
Jenkins Agent
      │
      ├─ Build
      ├─ Test
      ├─ Docker
      ├─ Terraform
      ├─ Helm
      └─ Deploy
      │
      ▼
Artifact Repository / Registry
      │
      ▼
Deployment Target
```

역할을 나누면 다음과 같다.

```text
Jenkinsfile
→ 서비스별 Pipeline 흐름과 정책

Shared Library
→ 여러 서비스의 공통 Pipeline 코드

Shell / Python / Build Tool
→ 실제 Build/Test/Deploy 작업

Controller
→ Scheduling과 Orchestration

Agent
→ 실제 작업 실행
```

Jenkinsfile이 복잡한 Application Code처럼 변하고 있다면 Pipeline에 너무 많은 책임이 들어간 것은 아닌지 다시 볼 필요가 있다.

---

## 보충 — JenkinsPipelineUnit

> 이 부분은 Jenkins 공식 Handbook 본문이 아니라 `jenkinsci/JenkinsPipelineUnit` 프로젝트 문서를 참고한 보충 내용이다.

`JenkinsPipelineUnit`은 Jenkins Pipeline과 Shared Library의 조건·분기·Step 호출을 Mock 환경에서 테스트할 수 있는 Framework다.

주요 기능은 다음과 같다.

- Jenkins Step Mocking
- Shared Library Loading
- Declarative Pipeline 테스트
- Call Stack 확인
- 조건/분기 로직 검증

예를 들어 `sh`를 실제로 실행하지 않고 Mock할 수 있다.

```groovy
helper.registerAllowedMethod(
    'sh',
    [String],
    { command -> println "mock sh: ${command}" }
)
```

테스트 가능한 구조를 만들려면 `vars/`는 얇게 두고, 복잡한 로직은 `src/`나 외부 Script로 분리하는 편이 좋다.

```text
vars/ → Jenkins DSL 연결
src/  → 테스트할 Groovy Class
Script → 실제 Build/Test/Deploy
```

JenkinsPipelineUnit이 있어도 복잡한 Build Logic을 Jenkins Groovy 안에 계속 넣는 것이 좋은 것은 아니다. 외부 Script로 분리하면 Jenkins 없이도 직접 실행하고 테스트할 수 있다.

---

## 정리

2주차에서 가져가야 할 내용은 다음과 같다.

- Declarative Pipeline은 `agent`, `when`, `post`, `options`, `parallel`, `matrix` 등을 이용해 실행 흐름과 정책을 명확하게 만든다.
- Multibranch Pipeline은 `Jenkinsfile`을 기준으로 Branch와 PR Pipeline을 자동 관리한다.
- Shared Library는 여러 Jenkinsfile에서 반복되는 공통 Pipeline 로직을 `vars/`, `src/`, `resources/`로 분리해 재사용한다.
- Jenkins Groovy는 Controller에서 실행되므로 무거운 작업을 넣지 않고, 가능한 한 Agent의 Shell/Python/Build Tool에 넘긴다.
- `stash`는 같은 Pipeline Run의 작은 파일 전달용이고, 큰 Artifact는 별도 Repository나 Object Storage를 사용한다.
- CPS와 Serialization 구조 때문에 Pipeline 상태에 복잡한 Object를 오래 유지하지 않는 것이 좋다.

결국 Jenkinsfile은 **작업 자체를 구현하는 코드보다 CI/CD 흐름을 조정하는 코드**에 가깝게 유지하는 것이 좋다.

---

## 참고한 Jenkins 공식 문서

- Jenkins Pipeline  
  https://www.jenkins.io/doc/book/pipeline/