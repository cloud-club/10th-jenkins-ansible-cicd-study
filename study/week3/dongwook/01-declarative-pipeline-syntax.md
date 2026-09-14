# Declarative Pipeline Syntax

## 1. 문서 범위

다음 내용을 다룬다.

- Declarative Pipeline의 기본 구조
- Core Directives: `agent`, `stages`, `steps`, `post`, `environment`, `options`, `parameters`, `triggers`, `when`
- 실행 구조: sequential stages, parallel execution, matrix builds
- 에러 처리: `catchError`, `unstable`, `warnError`, `error`, `retry`, `timeout`
- Trigger와 Webhook: `cron`, `pollSCM`, `upstream`, GitHub/GitLab webhook
- Declarative와 Scripted Pipeline의 차이

## 2. Declarative Pipeline이란?

Jenkins Pipeline은 CI/CD 흐름을 `Jenkinsfile`이라는 코드로 정의하는 방식이다. Jenkins Pipeline 문법은 크게 두 가지가 있다.

| 구분 | 설명 |
| --- | --- |
| Declarative Pipeline | 정해진 구조 안에 CI/CD 단계를 선언하는 방식 |
| Scripted Pipeline | Groovy 기반 DSL을 자유롭게 사용하는 방식 |

Declarative Pipeline은 구조가 고정되어 있어 팀 단위로 읽고 관리하기 좋다. 일반적인 CI/CD Pipeline은 Declarative로 시작하는 것이 가장 무난하다.

Scripted Pipeline은 더 자유롭지만 Groovy 이해가 필요하고, 작성자 스타일에 따라 유지보수성이 크게 달라질 수 있다.

## 3. 기본 구조

Declarative Pipeline은 반드시 최상위에 `pipeline {}` 블록이 있어야 한다.

```groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }
    }
}
```

핵심 구성은 다음과 같다.

| 요소 | 역할 |
| --- | --- |
| `pipeline` | Declarative Pipeline의 최상위 블록 |
| `agent` | Pipeline 또는 stage가 실행될 위치 |
| `stages` | 여러 stage를 담는 영역 |
| `stage` | Build, Test, Deploy 같은 작업 단위 |
| `steps` | 실제로 실행할 명령 |

Declarative Pipeline의 규칙은 다음처럼 이해하면 된다.

- 최상위는 `pipeline {}`이어야 한다.
- 대부분의 작업은 `stages -> stage -> steps` 구조 안에 들어간다.
- 세미콜론으로 문장을 구분하지 않고 줄 단위로 작성한다.
- 복잡한 Groovy 로직은 기본적으로 제한되며, 필요하면 `script` 블록을 사용한다.
- `pipeline {}` 안이 너무 커지면 Shared Library로 분리하는 것이 좋다.

## 4. 전체 실행 흐름

Declarative Pipeline은 보통 아래 순서로 읽으면 이해하기 쉽다.

1. `agent`로 실행 위치를 정한다.
2. `environment`, `options`, `parameters`, `triggers`로 전체 설정을 잡는다.
3. `stages` 안에 `stage`를 나눈다.
4. 각 `stage`에서 `when`, `agent`, `options`, `environment` 등 stage 단위 설정을 적용한다.
5. `steps`에서 실제 명령을 실행한다.
6. 마지막에 `post`로 성공/실패/항상 실행할 후처리를 수행한다.

## 5. Core Directives

### 5.1 `agent`

`agent`는 Pipeline 또는 특정 stage가 어디에서 실행될지 지정한다.

| 위치 | 의미 |
| --- | --- |
| top-level `agent` | 전체 Pipeline의 기본 실행 환경 |
| stage-level `agent` | 해당 stage만 별도 실행 환경 사용 |

대표적인 agent 종류는 다음과 같다.

| agent | 설명 |
| --- | --- |
| `any` | 사용 가능한 아무 agent에서 실행 |
| `none` | 전체 Pipeline에는 agent를 잡지 않음. stage마다 agent 필요 |
| `label` | 특정 label이 붙은 Jenkins node에서 실행 |
| `node` | label과 비슷하지만 `customWorkspace` 같은 추가 옵션 사용 가능 |
| `docker` | 지정한 Docker image 컨테이너에서 실행 |
| `dockerfile` | repository의 Dockerfile로 image를 빌드한 뒤 실행 |
| `kubernetes` | Kubernetes Pod 안에서 실행 |

top-level agent와 stage-level agent는 `timeout` 동작에서 차이가 있다.

| 구분 | timeout 기준 |
| --- | --- |
| top-level agent | agent가 할당된 뒤 timeout 시작 |
| stage-level agent | agent 할당 전부터 stage timeout 적용 |

즉, Docker/Kubernetes agent를 새로 띄우는 시간이 오래 걸리면 stage-level timeout에 포함될 수 있다.

예시는 다음과 같다.

```groovy
pipeline {
    agent none

    stages {
        stage('Build') {
            agent { docker 'gradle:8-jdk17' }
            steps {
                sh 'gradle build'
            }
        }

        stage('Deploy') {
            agent { label 'deploy-node' }
            steps {
                sh './deploy.sh'
            }
        }
    }
}
```

### 5.2 `stages`, `stage`, `steps`

`stages`는 전체 작업 목록을 담는 컨테이너다. 그 안에 여러 `stage`가 들어가고, 각 `stage`의 실제 명령은 `steps`에 작성한다.

```groovy
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
```

보통 stage는 CI/CD의 의미 있는 단위로 나눈다.

- `Checkout`
- `Build`
- `Test`
- `Package`
- `Deploy`

Jenkins UI에서도 stage 단위로 진행 상태가 보이기 때문에, 모든 작업을 하나의 stage에 몰아넣기보다 흐름별로 분리하는 것이 좋다.

### 5.3 `post`

`post`는 Pipeline 또는 stage가 끝난 뒤 실행할 후처리 작업을 정의한다.

| 조건 | 실행 시점 |
| --- | --- |
| `always` | 결과와 상관없이 항상 실행 |
| `success` | 성공했을 때 실행 |
| `failure` | 실패했을 때 실행 |
| `unstable` | 테스트 실패 등으로 unstable 상태일 때 실행 |
| `aborted` | 사용자가 중단했거나 aborted 상태일 때 실행 |
| `changed` | 이전 빌드와 결과가 달라졌을 때 실행 |
| `fixed` | 이전 실패/불안정 상태에서 성공으로 회복됐을 때 실행 |
| `regression` | 이전 성공에서 실패/불안정/중단으로 나빠졌을 때 실행 |
| `unsuccessful` | 성공이 아닌 모든 상태에서 실행 |
| `cleanup` | 다른 post 조건 처리 후 마지막에 실행 |

실무에서는 테스트 리포트 수집, 알림, workspace 정리 등에 자주 사용한다.

```groovy
post {
    always {
        junit 'build/test-results/**/*.xml'
    }
    failure {
        echo '빌드가 실패했습니다.'
    }
    cleanup {
        deleteDir()
    }
}
```

### 5.4 `environment`

`environment`는 환경 변수를 정의한다.

| 위치 | 적용 범위 |
| --- | --- |
| `pipeline` 내부 | 전체 Pipeline |
| `stage` 내부 | 해당 stage |

```groovy
pipeline {
    agent any

    environment {
        APP_ENV = 'staging'
    }

    stages {
        stage('Deploy') {
            environment {
                DEPLOY_TARGET = 'blue'
            }
            steps {
                sh 'echo "$APP_ENV / $DEPLOY_TARGET"'
            }
        }
    }
}
```

Jenkins Credentials는 `credentials()` helper로 가져올 수 있다.

```groovy
environment {
    DOCKER_CREDS = credentials('docker-registry-login')
}
```

Username/Password 타입 credentials라면 보통 다음 변수가 함께 생긴다.

| 변수 | 의미 |
| --- | --- |
| `DOCKER_CREDS` | `username:password` 형식 |
| `DOCKER_CREDS_USR` | username |
| `DOCKER_CREDS_PSW` | password |

### 5.5 `options`

`options`는 Pipeline 또는 stage의 동작 방식을 설정한다.

자주 쓰는 Pipeline-level options는 다음과 같다.

| 옵션 | 설명 |
| --- | --- |
| `timeout` | 전체 Pipeline 제한 시간 |
| `timestamps` | 콘솔 로그에 시간 표시 |
| `disableConcurrentBuilds` | 같은 job의 동시 실행 방지 |
| `buildDiscarder` | 오래된 build 기록 보관 정책 |
| `skipDefaultCheckout` | 기본 SCM checkout 생략 |
| `retry` | 전체 Pipeline 실패 시 재시도 |
| `preserveStashes` | restart를 위해 stash 보관 |
| `parallelsAlwaysFailFast` | 병렬 stage 중 하나 실패 시 나머지도 중단 |
| `disableRestartFromStage` | 특정 stage부터 재시작 기능 비활성화 |

```groovy
options {
    timestamps()
    timeout(time: 30, unit: 'MINUTES')
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '10'))
}
```

stage-level options는 더 제한적이다. 보통 다음 정도를 stage 안에서 사용한다.

| 옵션 | 설명 |
| --- | --- |
| `timeout` | 해당 stage 제한 시간 |
| `retry` | 해당 stage 실패 시 재시도 |
| `timestamps` | 해당 stage 로그에 시간 표시 |
| `skipDefaultCheckout` | 해당 stage 기본 checkout 생략 |

stage-level `options`는 `agent` 할당이나 `when` 조건 평가보다 먼저 적용될 수 있으므로 timeout을 걸 때 주의해야 한다.

### 5.6 `parameters`

`parameters`는 사용자가 Pipeline을 실행할 때 입력할 값을 정의한다. 실행 중에는 `params` 객체로 접근한다.

| 타입 | 설명 |
| --- | --- |
| `string` | 한 줄 문자열 |
| `text` | 여러 줄 문자열 |
| `booleanParam` | true/false |
| `choice` | 선택지 중 하나 |
| `password` | 비밀번호 입력 |

```groovy
pipeline {
    agent any

    parameters {
        choice(name: 'TARGET_ENV', choices: ['dev', 'staging', 'prod'], description: '배포 환경')
        booleanParam(name: 'RUN_TESTS', defaultValue: true, description: '테스트 실행 여부')
    }

    stages {
        stage('Print Parameters') {
            steps {
                echo "target = ${params.TARGET_ENV}"
                echo "run tests = ${params.RUN_TESTS}"
            }
        }
    }
}
```

### 5.7 `triggers`

`triggers`는 Pipeline을 자동으로 다시 실행하는 조건을 정의한다.

| trigger | 설명 |
| --- | --- |
| `cron` | 정해진 시간 규칙에 따라 실행 |
| `pollSCM` | 주기적으로 SCM 변경사항 확인 |
| `upstream` | 다른 Jenkins job 완료 후 실행 |
| `githubPush` | GitHub push webhook 기반 실행. GitHub Plugin 필요 |
| `gitlab` | GitLab push/MR event 기반 실행. GitLab Plugin 필요 |

```groovy
pipeline {
    agent any

    triggers {
        cron('H/15 * * * *')
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

Jenkins cron은 일반 cron처럼 5개 필드를 사용한다.

```text
MINUTE HOUR DOM MONTH DOW
```

Jenkins에서는 `H`를 자주 쓴다. `H`는 hash 기반 값으로, 많은 job이 같은 시각에 몰리지 않도록 실행 시간을 분산한다.

| 표현 | 의미 |
| --- | --- |
| `H/15 * * * *` | 매시간 15분 간격으로 분산 실행 |
| `H H * * *` | 하루 한 번 분산 실행 |
| `H 9 * * 1-5` | 평일 오전 9시대에 분산 실행 |
| `@hourly` | 매시간 한 번 |
| `@daily` | 매일 한 번 |

### 5.8 `when`

`when`은 특정 stage를 실행할지 말지 결정한다.

```groovy
stage('Deploy') {
    when {
        branch 'main'
    }
    steps {
        sh './deploy.sh'
    }
}
```

자주 쓰는 조건은 다음과 같다.

| 조건 | 설명 |
| --- | --- |
| `branch` | 특정 branch일 때 실행. Multibranch Pipeline에서 사용 |
| `buildingTag` | tag build일 때 실행 |
| `tag` | tag 이름이 패턴과 맞을 때 실행 |
| `changeRequest` | PR/MR 같은 change request일 때 실행 |
| `changeset` | 변경 파일 경로가 패턴과 맞을 때 실행 |
| `environment` | 환경 변수가 특정 값일 때 실행 |
| `equals` | 두 값이 같을 때 실행 |
| `expression` | Groovy 표현식이 true일 때 실행 |
| `not` | 내부 조건이 false일 때 실행 |
| `allOf` | 내부 조건이 모두 true일 때 실행 |
| `anyOf` | 내부 조건 중 하나라도 true일 때 실행 |
| `triggeredBy` | 특정 원인으로 build가 시작되었을 때 실행 |

복합 조건 예시는 다음과 같다.

```groovy
stage('Deploy Prod') {
    when {
        allOf {
            branch 'main'
            environment name: 'APP_ENV', value: 'prod'
            not {
                changeRequest()
            }
        }
    }
    steps {
        sh './deploy-prod.sh'
    }
}
```

`when`은 기본적으로 stage agent에 들어간 뒤 평가될 수 있다. 불필요한 agent 할당을 줄이고 싶으면 다음 옵션을 사용할 수 있다.

| 옵션 | 의미 |
| --- | --- |
| `beforeAgent true` | agent 할당 전에 when 평가 |
| `beforeInput true` | input 승인 요청 전에 when 평가 |
| `beforeOptions true` | stage options 적용 전에 when 평가 |

## 6. 실행 구조

### 6.1 Sequential Stages

stage 안에 다시 `stages`를 넣으면 큰 흐름 안에서 하위 stage를 순차 실행할 수 있다.

```groovy
stage('Release') {
    stages {
        stage('Package') {
            steps {
                sh './package.sh'
            }
        }

        stage('Upload') {
            steps {
                sh './upload.sh'
            }
        }
    }
}
```

이 구조는 `Release`라는 큰 묶음 안에 `Package`, `Upload` 같은 세부 단계를 보여주고 싶을 때 유용하다.

### 6.2 Parallel Execution

`parallel`은 여러 stage를 동시에 실행한다.

```groovy
stage('Test') {
    failFast true

    parallel {
        stage('Unit Test') {
            steps {
                sh './gradlew test'
            }
        }

        stage('Integration Test') {
            steps {
                sh './gradlew integrationTest'
            }
        }
    }
}
```

`failFast true`를 사용하면 병렬 stage 중 하나가 실패했을 때 나머지를 빠르게 중단한다. 전체 Pipeline에 `options { parallelsAlwaysFailFast() }`를 줄 수도 있다.

주의할 점은 `parallel` 또는 `matrix` 안의 stage에서 다시 `parallel`이나 `matrix`를 중첩할 수 없다는 것이다.

### 6.3 Matrix Builds

`matrix`는 여러 축의 값 조합을 만들어 병렬 실행한다. OS, JDK, Browser 조합 테스트에 적합하다.

```groovy
stage('Cross Test') {
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
                    sh './gradlew test'
                }
            }
        }
    }
}
```

위 예시는 총 4개 조합을 만든다.

| PLATFORM | JDK |
| --- | --- |
| linux | 17 |
| linux | 21 |
| windows | 17 |
| windows | 21 |

`excludes`를 사용하면 특정 조합을 제외할 수 있다.
예를 들어 `linux + safari`처럼 의미 없는 조합을 빼거나, 특정 OS에서는 특정 JDK만 테스트하도록 조합을 줄일 수 있다.

## 7. Error Handling과 Basic Steps

Declarative Pipeline 자체는 구조를 잡고, 실패 처리의 세부 동작은 `steps` 안의 step이 담당한다. 공식 `Pipeline: Basic Steps` 문서에서 특히 중요한 step은 다음이다.

| step | 용도 |
| --- | --- |
| `catchError` | 실패를 잡고 build/stage 결과를 표시한 뒤 계속 진행 |
| `unstable` | build와 stage를 `UNSTABLE`로 표시 |
| `warnError` | 실패를 잡아 `UNSTABLE`로 표시하고 계속 진행 |
| `error` | 명시적으로 실패 발생 |
| `retry` | 실패한 블록을 지정 횟수만큼 재시도 |
| `timeout` | 블록 실행 시간 제한 |
| `fileExists` | 파일/디렉터리 존재 여부 확인 |
| `stash` / `unstash` | 같은 Pipeline 실행 안에서 파일 임시 보관/복원 |
| `deleteDir` | 현재 workspace 내용 삭제 |
| `withEnv` | 블록 범위에서 환경 변수 설정 |

### 7.1 `catchError`

`catchError`는 내부 step이 실패해도 Pipeline을 바로 중단하지 않고 다음 step으로 넘어가게 한다. 대신 build 또는 stage 결과를 `FAILURE`, `UNSTABLE` 등으로 표시할 수 있다.

```groovy
stage('Test') {
    steps {
        catchError(
            buildResult: 'UNSTABLE',
            stageResult: 'UNSTABLE',
            message: '테스트 실패. 리포트 수집은 계속 진행합니다.'
        ) {
            sh './gradlew test'
        }

        junit 'build/test-results/**/*.xml'
    }
}
```

테스트가 실패해도 `junit` 리포트 수집은 하고 싶을 때 유용하다.

### 7.2 `unstable`과 `warnError`

`unstable`은 build/stage를 명시적으로 불안정 상태로 표시한다.

```groovy
script {
    if (coverage < 80) {
        unstable("테스트 커버리지가 기준보다 낮습니다: ${coverage}%")
    }
}
```

`warnError`는 실패를 `UNSTABLE`로 낮춰 처리하고 Pipeline을 계속 진행한다.

```groovy
stage('Lint') {
    steps {
        warnError('Lint 실패. 빌드는 계속 진행합니다.') {
            sh './gradlew lint'
        }
    }
}
```

정리하면 다음과 같다.

| 상황 | 추천 |
| --- | --- |
| 실패를 잡고 결과를 세밀하게 지정 | `catchError` |
| 품질 기준 미달을 직접 표시 | `unstable` |
| 실패하면 경고/불안정으로 처리 | `warnError` |

### 7.3 `error`, `retry`, `timeout`

`error`는 의도적으로 Pipeline을 실패시킨다.

```groovy
script {
    if (params.TARGET_ENV == 'prod' && env.BRANCH_NAME != 'main') {
        error('운영 배포는 main 브랜치에서만 가능합니다.')
    }
}
```

`retry`는 일시적인 실패 가능성이 있는 작업에 사용한다.

```groovy
retry(3) {
    sh './publish-artifact.sh'
}
```

`timeout`은 오래 걸리는 작업을 제한한다.

```groovy
timeout(time: 10, unit: 'MINUTES') {
    sh './run-integration-tests.sh'
}
```

코드 자체 문제로 실패하는 테스트나 컴파일 오류에는 `retry`가 큰 도움이 되지 않는다. 네트워크, registry, 임시 agent 장애처럼 재시도하면 성공할 가능성이 있는 작업에 쓰는 것이 좋다.

### 7.4 `stash`와 `unstash`

`stash`는 같은 Pipeline 실행 안에서 파일을 임시 보관하고, `unstash`는 다른 stage에서 복원한다.

```groovy
pipeline {
    agent none

    stages {
        stage('Build') {
            agent { label 'builder' }
            steps {
                sh './gradlew build'
                stash name: 'app-jar', includes: 'build/libs/*.jar'
            }
        }

        stage('Deploy') {
            agent { label 'deployer' }
            steps {
                unstash 'app-jar'
                sh './deploy.sh build/libs/*.jar'
            }
        }
    }
}
```

`stash`는 작은 파일 묶음을 넘길 때 적합하다. 큰 artifact는 artifact repository, object storage, `archiveArtifacts` 같은 다른 방법을 고려하는 것이 좋다.

## 8. Trigger와 Webhook

Declarative Pipeline의 `triggers`는 Jenkinsfile 안에서 자동 실행 조건을 선언하는 방식이다. 하지만 GitHub/GitLab webhook은 Jenkinsfile만으로 끝나는 것이 아니라 Jenkins job 설정, plugin 설정, SCM provider webhook 설정이 함께 맞아야 한다.

### 8.1 Jenkinsfile trigger

```groovy
triggers {
    cron('H 2 * * *')
    pollSCM('H/15 * * * *')
}
```

`cron`은 시간 기반 실행이고, `pollSCM`은 SCM 변경사항을 주기적으로 확인한다. webhook이 있다면 `pollSCM`은 fallback 성격으로만 쓰는 것이 좋다.

### 8.2 GitHub webhook

일반 Pipeline job에서 GitHub push event를 Jenkinsfile에 선언하면 다음처럼 쓸 수 있다.

```groovy
triggers {
    githubPush()
}
```

GitHub webhook URL은 보통 다음 형태다.

```text
https://JENKINS_URL/github-webhook/
```

Multibranch Pipeline에서는 GitHub Branch Source Plugin이 branch/PR scan과 build trigger를 관리하는 경우가 많다. 이 부분은 `02-multibranch-pipeline.md`에서 더 자세히 다룬다.

### 8.3 GitLab webhook

GitLab Plugin을 사용하는 일반 Pipeline job에서는 `triggers { gitlab(...) }` 형태를 사용할 수 있다.

```groovy
options {
    gitLabConnection('your-gitlab-connection-name')
}

triggers {
    gitlab(
        triggerOnPush: true,
        triggerOnMergeRequest: true,
        branchFilterType: 'All'
    )
}
```

GitLab webhook URL은 plugin에 따라 다르지만 일반 GitLab Plugin job에서는 보통 다음 형태를 사용한다.

```text
https://JENKINS_URL/project/PROJECT_NAME
```

GitLab Branch Source 기반 Multibranch 구성에서는 `/gitlab-webhook/post` endpoint를 사용하는 흐름도 있다. 이 역시 02번 문서에서 자세히 다룬다.

## 9. `script` 블록

Declarative Pipeline 안에서도 복잡한 Groovy 로직이 필요하면 `script` 블록을 사용할 수 있다.

```groovy
stage('Dynamic Logic') {
    steps {
        script {
            def targets = ['api', 'batch', 'worker']

            for (target in targets) {
                echo "build ${target}"
            }
        }
    }
}
```

다만 `script`가 길어지면 Declarative Pipeline의 장점이 줄어든다.

| 상황 | 추천 |
| --- | --- |
| 단순 CI/CD 흐름 | Declarative 문법 유지 |
| 짧은 동적 로직 | `script` 사용 가능 |
| 여러 Jenkinsfile에서 재사용 | Shared Library로 분리 |
| Pipeline 전체가 매우 동적 | Scripted Pipeline 검토 |

## 10. Declarative vs Scripted

두 방식은 같은 Jenkins Pipeline 시스템 위에서 동작하지만 작성 모델이 다르다.

| 비교 항목 | Declarative Pipeline | Scripted Pipeline |
| --- | --- | --- |
| 작성 방식 | 정해진 구조를 선언 | Groovy DSL을 자유롭게 작성 |
| 학습 난이도 | 낮은 편 | Groovy 이해 필요 |
| 자유도 | 제한적 | 높음 |
| 표준화 | 팀 단위 관리에 좋음 | 작성자 스타일 차이가 커질 수 있음 |
| 복잡한 로직 | `script` 또는 Shared Library 필요 | 직접 구현하기 쉬움 |
| 추천 상황 | 일반적인 CI/CD | 복잡하고 동적인 Pipeline |

Scripted Pipeline 기본 예시는 다음과 같다.

```groovy
node {
    stage('Build') {
        sh './gradlew build'
    }

    stage('Deploy') {
        if (env.BRANCH_NAME == 'main') {
            sh './deploy.sh'
        }
    }
}
```

공식 문서의 결론을 쉽게 정리하면 다음과 같다.

- 대부분의 일반 CI/CD는 Declarative로 충분하다.
- Declarative는 구조가 명확해서 리뷰와 유지보수가 쉽다.
- Scripted는 자유도가 높지만 Groovy와 Jenkins Pipeline CPS 특성을 알아야 한다.
- 복잡한 공통 로직은 Scripted로 다 밀어넣기보다 Shared Library로 분리하는 편이 좋다.

## 11. 실전 Jenkinsfile 예시

### 11.1 기본 CI Pipeline

```groovy
pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 20, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh './gradlew clean build'
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
            junit 'build/test-results/**/*.xml'
        }
        failure {
            echo 'CI Pipeline 실패'
        }
    }
}
```

### 11.2 파라미터 기반 배포

```groovy
pipeline {
    agent any

    parameters {
        choice(name: 'TARGET_ENV', choices: ['dev', 'staging', 'prod'], description: '배포 환경')
    }

    stages {
        stage('Build') {
            steps {
                sh './gradlew build'
            }
        }

        stage('Deploy Non-Prod') {
            when {
                expression { params.TARGET_ENV != 'prod' }
            }
            steps {
                sh "./deploy.sh ${params.TARGET_ENV}"
            }
        }

        stage('Deploy Prod') {
            when {
                expression { params.TARGET_ENV == 'prod' }
            }
            input {
                message '운영 배포를 진행할까요?'
                ok '배포'
            }
            steps {
                sh './deploy.sh prod'
            }
        }
    }
}
```

## 12. 실무에서 헷갈리는 포인트

### 12.1 `post`와 `catchError`

`post`는 stage나 Pipeline이 끝난 뒤 결과에 따라 실행된다. `catchError`는 step 실행 중 발생한 실패를 잡아 Pipeline을 계속 진행하게 한다.

| 목적 | 사용 |
| --- | --- |
| 실패 후 알림/정리 | `post { failure { ... } }` |
| 실패해도 다음 step 계속 실행 | `catchError { ... }` |
| 항상 리포트 수집 | `post { always { ... } }` 또는 `catchError` 뒤 `junit` |

### 12.2 `environment`와 `withEnv`

`environment`는 Declarative 문법으로 범위가 명확하다. `withEnv`는 step 블록 안에서 임시로 환경 변수를 바꿀 때 쓴다.

```groovy
steps {
    withEnv(['APP_ENV=local']) {
        sh './run.sh'
    }
}
```

### 12.3 `options { timeout(...) }`와 `timeout { ... }`

| 방식 | 범위 |
| --- | --- |
| `options { timeout(...) }` | Pipeline 또는 stage 전체 |
| `timeout { ... }` step | 특정 step 블록 |

전체 제한은 `options`, 특정 명령 제한은 `timeout` step으로 생각하면 쉽다.

### 12.4 `when`과 agent 낭비

stage에 무거운 Docker/Kubernetes agent가 있고 `when` 조건이 false라면, agent를 띄우기 전에 조건을 평가하는 편이 낫다.

```groovy
stage('Deploy') {
    when {
        beforeAgent true
        branch 'main'
    }
    agent { docker 'alpine:3.20' }
    steps {
        sh './deploy.sh'
    }
}
```

### 12.5 `script` 남용

`script` 블록이 길어지면 Declarative Pipeline이 아니라 Groovy 스크립트처럼 변한다. 다음 기준으로 판단하면 좋다.

| 코드 상태 | 추천 |
| --- | --- |
| 5-10줄 정도의 간단한 분기 | `script` 허용 |
| 여러 stage에서 반복 | Shared Library |
| 테스트가 필요한 복잡한 로직 | Shared Library 또는 별도 script file |

## 13. Troubleshooting 체크리스트

### 13.1 Jenkinsfile 문법 오류

- 최상위가 `pipeline {}`인지 확인한다.
- `stages`, `stage`, `steps` 중괄호가 제대로 닫혔는지 확인한다.
- `stage` 이름이 문자열로 들어갔는지 확인한다.
- Declarative 문법 안에 일반 Groovy 코드를 바로 넣지 않았는지 확인한다.
- 복잡한 Groovy 로직은 `script { ... }` 안으로 옮긴다.

### 13.2 stage가 실행되지 않을 때

- `when` 조건이 false인지 확인한다.
- Multibranch Pipeline이 아니라면 `branch` 조건이 기대대로 동작하지 않을 수 있다.
- `beforeAgent`, `beforeInput`, `beforeOptions` 평가 순서를 확인한다.
- parameter 값이 기대와 다른지 확인한다.

### 13.3 Docker agent가 실패할 때

- Jenkins agent node에 Docker 실행 환경이 있는지 확인한다.
- image 이름과 tag가 올바른지 확인한다.
- private registry라면 `registryCredentialsId`를 확인한다.
- volume mount나 workspace 권한 문제를 확인한다.

### 13.4 webhook trigger가 동작하지 않을 때

- 필요한 plugin이 설치되어 있는지 확인한다.
- Jenkins URL이 GitHub/GitLab에서 접근 가능한지 확인한다.
- webhook URL이 provider에 올바르게 등록되어 있는지 확인한다.
- GitLab Plugin은 Jenkinsfile trigger 반영을 위해 최초 1회 수동 실행이 필요할 수 있다.
- Multibranch Pipeline의 webhook/scan 문제는 02번 문서의 Branch Source 설정을 함께 확인한다.

### 13.5 build 결과가 기대와 다를 때

- `catchError`가 실패를 `UNSTABLE`로 바꾸고 계속 진행시키는지 확인한다.
- `warnError` 때문에 실패가 failure가 아니라 unstable로 표시되는지 확인한다.
- `post` 조건 중 `failure`, `unstable`, `unsuccessful`의 차이를 확인한다.
- Jenkins build result는 나빠지는 방향으로만 바뀌며, 이미 나빠진 결과를 `SUCCESS`로 되돌릴 수 없다.

## 14. 핵심 요약

- Declarative Pipeline은 정해진 구조로 CI/CD를 선언하는 방식이다.
- 기본 구조는 `pipeline -> stages -> stage -> steps`다.
- `agent`는 실행 위치를 정하고, top-level과 stage-level에서 timeout 기준이 달라질 수 있다.
- `post`는 성공/실패/항상 실행 같은 후처리를 담당한다.
- `environment`, `options`, `parameters`, `triggers`, `when`은 Pipeline 동작을 제어한다.
- `parallel`은 여러 stage 동시 실행, `matrix`는 여러 조합 테스트에 적합하다.
- `catchError`, `unstable`, `warnError`, `error`, `retry`, `timeout`은 실패 처리와 build 결과 제어에 중요하다.
- GitHub/GitLab webhook은 Jenkinsfile trigger뿐 아니라 Jenkins plugin/job 설정과 함께 맞아야 한다.
- `script`는 escape hatch이며, 길어지면 Shared Library로 분리하는 것이 좋다.
- 대부분의 일반 CI/CD는 Declarative Pipeline으로 시작하고, 복잡한 동적 로직만 Scripted 또는 Shared Library로 보완한다.

## 참고 자료

- Jenkins 공식 문서 - Pipeline Syntax: https://www.jenkins.io/doc/book/pipeline/syntax/
- Jenkins 공식 문서 - Pipeline: Basic Steps: https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/
- Jenkins 공식 문서 - Pipeline Steps Reference: https://www.jenkins.io/doc/pipeline/steps/
- Jenkins Plugin 문서 - GitHub Plugin: https://plugins.jenkins.io/github
- Jenkins Plugin 문서 - GitLab Plugin: https://plugins.jenkins.io/gitlab-plugin/
