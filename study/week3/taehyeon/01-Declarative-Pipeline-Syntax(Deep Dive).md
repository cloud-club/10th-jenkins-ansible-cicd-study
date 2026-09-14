# Declarative Pipeline Syntax (Deep Dive)

## Declarative Pipeline이란?

> Jenkins pipeline을 정해진 구조로 작성하는 방식. 
다른 버전으로는 Scripted Pipeline이 있음
> 

Scripted Pipeline보다는 문법 제약이 있지만 장점이 있다.

장점

- Jenkinsfile 구조가 일정하다
- Stage와 실행 조건을 쉽게 파악할 수 있다
- Pipeline 문법 검증과 시각화가 쉽다.
- 팀마다 서로 다른 방식으로 pipleline을 작성하는 문제를 줄인다.
- post, when, environment, options 같은 운영 기능을 구조적으로 표현할 수 있다.

## 전체 구조

---

<aside>
🧩

Jenkinsfile은 크게 **실행 준비 → 작업 실행 → 결과 처리** 순서로 읽으면 된다.

</aside>

```
pipeline
├── 실행 준비
│   ├── agent        어디에서 실행할지
│   ├── environment  공통 환경 변수
│   ├── parameters   사용자 입력값
│   └── options      실행 정책
├── 작업 실행
│   └── stages
│       └── stage
│           ├── when   실행 조건
│           ├── steps  실제 작업
│           └── post   해당 Stage 후처리
└── 결과 처리
    └── post           전체 Pipeline 후처리
```

### 1. 문법 뼈대

아래 코드는 구조를 이해하기 위한 뼈대이며 그대로 실행하는 코드는 아니다.

```groovy
pipeline {
    agent <실행할 장소>

    environment {
        <환경 변수>
    }

    parameters {
        <사용자 입력값>
    }

    options {
        <실행 정책>
    }

    stages {
        stage('<단계 이름>') {
            when {
                <실행 조건>
            }

            steps {
                <실제 작업>
            }

            post {
                <이 Stage의 결과 처리>
            }
        }
    }

    post {
        <전체 Pipeline의 결과 처리>
    }
}
```

### 2. 실제 실행 예제

```groovy
pipeline {
    // 1. 실행할 장소
    agent any

    // 2. Pipeline 전체에서 사용할 값
    environment {
        APP_NAME = 'sample-api'
    }

    // 3. 실행할 때 입력받을 값
    parameters {
        choice(
            name: 'DEPLOY_ENV',
            choices: ['none', 'staging', 'production'],
            description: '배포 환경'
        )
        booleanParam(
            name: 'RUN_INTEGRATION_TEST',
            defaultValue: true,
            description: '통합 테스트 실행 여부'
        )
    }

    // 4. 실행 정책
    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(
            logRotator(
                numToKeepStr: '20',
                artifactNumToKeepStr: '5'
            )
        )
        disableConcurrentBuilds(abortPrevious: true)
    }

    // 5. 실제 작업: 위에서 아래로 실행
    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh './gradlew --no-daemon clean assemble'
            }
        }

        stage('Test') {
            steps {
                sh './gradlew --no-daemon test'
            }

            // Test Stage만 끝났을 때 실행
            post {
                always {
                    junit(
                        testResults: 'build/test-results/test/*.xml',
                        allowEmptyResults: true
                    )
                }
            }
        }

        stage('Deploy') {
            // main이면서 DEPLOY_ENV가 none이 아닐 때만 실행
            when {
                allOf {
                    branch 'main'
                    expression {
                        return params.DEPLOY_ENV != 'none'
                    }
                }
            }

            steps {
                sh "./scripts/deploy.sh '${params.DEPLOY_ENV}'"
            }
        }
    }

    // 6. 전체 Pipeline이 끝났을 때 실행
    post {
        success {
            echo 'Pipeline 성공'
        }
        unstable {
            echo '확인이 필요한 항목이 있습니다.'
        }
        failure {
            echo 'Pipeline 실패'
        }
        cleanup {
            deleteDir()
        }
    }
}
```

### 실행 순서

```
Agent 할당
    ↓
환경 변수와 Parameter 준비
    ↓
Checkout
    ↓
Build
    ↓
Test → Test 결과 등록
    ↓
조건이 맞으면 Deploy
    ↓
전체 결과에 맞는 post 실행
    ↓
Workspace 정리
```

# 1-1. Declarative Pipeline 핵심 구성 요소

---

- **agent**: Pipeline 또는 Stage를 실행할 Node/Agent를 선택한다.
- **stages**: Pipeline의 전체 작업 흐름을 정의한다.
- **stage**: Build, Test, Deploy 같은 논리적인 작업 구간이다.
- **steps**: sh, checkout, junit 등 실제 Jenkins Step을 실행한다.
- **post**: 성공, 실패, 중단 이후에 결과 게시, 알림, 정리 작업을 수행한다.
- **environment**: 환경 변수 또는 Jenkins Credential을 주입한다.
- **options**: Timeout, 로그 보존, 동시 실행 정책 등을 설정한다.
- **parameters**: 수동 실행 시 사용자가 선택할 입력값을 정의한다.
- **triggers**: cron, pollSCM, upstream 등 자동 실행 조건을 정의한다.
- **when**: Branch, PR, Parameter 등에 따라 Stage 실행 여부를 결정한다.

## agent 전략

---

### Pipeline 전체에서 동일한 Agent 사용

```groovy
pipeline {
    agent {
        label 'linux && java21'
    }

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }
    }
}
```

- Stage 간 동일한 Workspace를 사용하기 쉽다.
- 구성이 단순하지만 Pipeline이 끝날 때까지 Executor를 점유한다.
- input을 이용한 장시간 승인 대기가 있다면 Agent가 불필요하게 묶일 수 있다.

### Stage마다 Agent 할당

```groovy
pipeline {
    agent none

    stages {
        stage('Build') {
            agent {
                label 'java21'
            }
            steps {
                checkout scm
                sh './gradlew assemble'
            }
        }

        stage('Deploy') {
            agent {
                label 'deploy'
            }
            steps {
                sh './scripts/deploy.sh'
            }
        }
    }
}
```

- 최상위 agent none을 사용하면 Pipeline 전체에 Executor를 미리 할당하지 않는다.
- Build와 Deploy처럼 서로 다른 실행 환경을 Stage별로 선택할 수 있다.
- Stage 단위 timeout은 Agent가 할당되기를 기다리는 시간도 포함한다.

## environment와 Credentials

---

일반 환경 변수:

```groovy
environment {
    APP_NAME = 'payment-service'
    REGISTRY = 'registry.example.com'
}
```

Credential 사용:

```groovy
environment {
    GITHUB_TOKEN = credentials('github-token')
}
```

Username/Password Credential은 변수 이름 뒤에 _USR과 _PSW가 붙은 환경 변수도 함께 제공한다.

```
REGISTRY_AUTH
REGISTRY_AUTH_USR
REGISTRY_AUTH_PSW
```

<aside>
🔐

Secret은 Jenkinsfile에 직접 작성하거나 echo로 출력하지 않는다. Secret Masking은 우발적인 로그 노출을 줄여 주지만, Credential 사용 권한 자체를 대신 통제해 주지는 않는다.

</aside>

## 주요 options

---

```groovy
options {
    timestamps()
    timeout(time: 30, unit: 'MINUTES')
    retry(2)
    buildDiscarder(logRotator(numToKeepStr: '20'))
    disableConcurrentBuilds(abortPrevious: true)
    parallelsAlwaysFailFast()
    skipDefaultCheckout(true)
}
```

- **timestamps**: Console Log에 실행 시간을 표시한다.
- **timeout**: 무한 대기하는 Pipeline을 중단한다.
- **retry**: 일시적인 네트워크 오류처럼 재시도할 가치가 있는 구간에 제한적으로 사용한다.
- **buildDiscarder**: 오래된 빌드와 Artifact를 정리한다.
- **disableConcurrentBuilds**: 같은 Job의 동시 실행을 막는다.
- **abortPrevious: true**: 새 빌드가 시작되면 이전 빌드를 취소한다.
- **parallelsAlwaysFailFast**: 병렬 작업 하나가 실패하면 나머지도 중단한다.
- **skipDefaultCheckout**: 자동 Checkout을 끄고 필요한 Stage에서 checkout scm을 직접 실행한다.

## parameters와 when

---

```groovy
parameters {
    choice(
        name: 'DEPLOY_ENV',
        choices: ['none', 'staging', 'production'],
        description: '배포 환경'
    )
    booleanParam(
        name: 'RUN_SECURITY_SCAN',
        defaultValue: true,
        description: '보안 검사 실행'
    )
}
```

Branch 조건:

```groovy
when {
    branch 'main'
}
```

PR에서만 실행:

```groovy
when {
    changeRequest()
}
```

main을 대상으로 하는 PR:

```groovy
when {
    changeRequest target: 'main'
}
```

여러 조건 조합:

```groovy
when {
    allOf {
        branch 'main'
        expression {
            return params.DEPLOY_ENV == 'production'
        }
    }
}
```

비싼 Cloud Agent를 생성하기 전에 조건을 검사하려면 beforeAgent를 사용할 수 있다.

```groovy
when {
    beforeAgent true
    branch 'main'
}
```

# 1-2. Parallel Execution, Matrix Build와 Error Handling

---

서로 의존하지 않는 Unit Test, Static Analysis, Security Scan은 병렬로 실행할 수 있다.

```groovy
stage('Verification') {
    failFast true

    parallel {
        stage('Unit Test') {
            steps {
                sh './gradlew test'
            }
            post {
                always {
                    junit 'build/test-results/test/*.xml'
                }
            }
        }

        stage('Static Analysis') {
            steps {
                sh './gradlew checkstyleMain'
            }
        }

        stage('Security Scan') {
            steps {
                sh './scripts/security-scan.sh'
            }
        }
    }
}
```

주의 사항:

- 병렬 Stage가 같은 파일을 동시에 수정하면 Workspace 충돌이 발생할 수 있다.
- 사용할 수 있는 Agent 또는 Executor가 부족하면 병렬 Stage도 Queue에서 대기한다.
- 모든 검사 결과가 필요하다면 failFast를 사용하지 않는다.
- 하나의 실패가 나머지 작업을 무의미하게 만든다면 failFast를 사용한다.

## Matrix Build

---

Matrix는 여러 실행 환경의 조합을 자동으로 만들고 각 조합을 병렬 실행한다.

```groovy
stage('Compatibility Test') {
    matrix {
        axes {
            axis {
                name 'JDK_VERSION'
                values '17', '21'
            }
            axis {
                name 'DATABASE'
                values 'postgresql', 'mysql'
            }
        }

        excludes {
            exclude {
                axis {
                    name 'JDK_VERSION'
                    values '17'
                }
                axis {
                    name 'DATABASE'
                    values 'mysql'
                }
            }
        }

        agent {
            label "jdk-${JDK_VERSION}"
        }

        stages {
            stage('Test') {
                steps {
                    sh "./gradlew test -Pdatabase=${DATABASE}"
                }
            }
        }
    }
}
```

위 설정은 다음 Cell을 만든다.

- JDK 17 + PostgreSQL
- JDK 21 + PostgreSQL
- JDK 21 + MySQL

axes는 전체 조합을 정의하고 excludes는 지원하지 않거나 불필요한 조합을 제거한다.

## Error Handling

---

즉시 실패:

```groovy
error '필수 설정 파일이 존재하지 않습니다.'
```

실패를 기록하고 다음 단계 진행:

```groovy
catchError(
    buildResult: 'UNSTABLE',
    stageResult: 'UNSTABLE',
    catchInterruptions: false,
    message: '정적 분석에서 경고가 발견되었습니다.'
) {
    sh './gradlew checkstyleMain'
}
```

직접 UNSTABLE 처리:

```groovy
script {
    if (env.BRANCH_NAME != 'main') {
        unstable 'main 브랜치가 아니므로 배포를 생략합니다.'
    }
}
```

- 빌드를 계속할 수 없는 오류는 error 또는 Step 실패를 그대로 전달한다.
- 선택적 검사 실패는 catchError 또는 warnError를 검토한다.
- 품질 경고는 있지만 결과를 확인할 수 있으면 unstable로 표시할 수 있다.
- Timeout과 수동 중단을 catchError가 삼키지 않게 하려면 catchInterruptions: false를 사용한다.
- 정리 작업은 try/finally 또는 post cleanup에 둔다.

# 1-3. Triggers와 Webhook

---

Declarative Pipeline의 기본 Trigger:

```groovy
triggers {
    cron('H H * * 1-5')
    pollSCM('H/15 * * * *')
}
```

- **cron**: 정해진 주기에 실행한다.
- **pollSCM**: 주기적으로 SCM 변경 여부를 확인한다.
- **upstream**: 다른 Job의 완료 결과에 따라 실행한다.
- Jenkins cron에서는 고정된 시각보다 H를 사용하면 여러 Job의 실행 시점을 분산할 수 있다.
- GitHub/GitLab Branch Source 기반 Multibranch Pipeline은 Webhook이 실행을 담당하므로 Jenkinsfile에 pollSCM이 필요하지 않은 경우가 많다.

### 확인 질문

1. top-level agent와 stage-level agent는 언제 선택해야 하는가?
    - **답:** 모든 Stage가 같은 실행 환경과 Workspace를 사용하면 top-level agent를 선택한다. Build와 Deploy처럼 필요한 환경이 다르거나 Agent를 필요한 시간에만 사용하려면 stage-level agent를 선택한다.
2. catchError로 실패를 무조건 무시하면 어떤 문제가 생기는가?
    - **답:** Test나 Build가 실패했는데도 다음 Deploy가 실행될 수 있다. 반드시 중단해야 하는 작업은 실패를 그대로 전달하고, 선택적인 검사처럼 계속 진행해도 되는 작업에만 catchError를 사용한다.
3. 병렬 실행이 실제 수행 시간을 줄이지 못하는 경우는 무엇인가?
    - **답:** 사용할 Agent나 Executor가 부족하면 작업이 Queue에서 기다리므로 빨라지지 않는다. 작업끼리 의존하거나 같은 Workspace·Network·Disk를 함께 사용해 병목이 생기는 경우에도 효과가 작다.
4. Matrix에서 axes와 excludes는 각각 어떤 역할을 하는가?
    - **답:** axes는 JDK와 Database처럼 테스트할 값과 전체 조합을 정의한다. excludes는 그중 지원하지 않거나 테스트할 필요가 없는 조합을 제외한다.
5. Webhook이 구성된 Multibranch Pipeline에 pollSCM을 추가하면 어떤 비용이 생기는가?
    - **답:** Webhook이 이미 변경 사항을 즉시 알려주는데 Jenkins가 SCM을 주기적으로 다시 확인하게 된다. 그만큼 Jenkins Controller와 GitHub·GitLab에 불필요한 조회, Network 요청, Branch Scan 부하가 추가된다.

## 참고 자료

---

- [Jenkins 공식 문서 - Pipeline Syntax[1]](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Jenkins 공식 문서 - Using a Jenkinsfile[2]](https://www.jenkins.io/doc/book/pipeline/jenkinsfile/)
- [Jenkins 공식 문서 - Pipeline Basic Steps[3]](https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/)