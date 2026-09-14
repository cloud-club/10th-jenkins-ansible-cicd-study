# 3주차: Advanced Pipeline, Shared Library & Operations

> **목표:** 반복되는 CI/CD 로직을 재사용하고, 여러 브랜치와 PR을 안정적으로 검증할 수 있는 Jenkins Pipeline을 설계한다.

## 1. Declarative Pipeline 심화

Declarative Pipeline은 `Jenkinsfile`에 CI/CD 과정을 코드로 정의하는 방식이다. 정해진 구조를 사용하기 때문에 읽기 쉽고 검증하기 편하다.

### 주요 지시어

| 지시어 | 역할 |
|---|---|
| `agent` | 파이프라인이나 Stage를 실행할 노드 지정 |
| `stages` | 전체 작업 단계를 묶음 |
| `steps` | 각 Stage에서 실행할 명령 정의 |
| `post` | 성공·실패·항상 실행할 후처리 정의 |
| `environment` | 환경 변수와 자격 증명 정의 |
| `options` | 타임아웃, 동시 실행, 로그 보관 등 설정 |
| `parameters` | 사용자가 입력할 빌드 매개변수 정의 |
| `triggers` | 주기 실행이나 SCM 기반 실행 조건 정의 |
| `when` | 브랜치, 환경 등에 따라 Stage 실행 여부 결정 |

### 병렬 실행과 Matrix Build

- `parallel`: 서로 독립적인 테스트를 동시에 실행해 전체 시간을 줄인다.
- `matrix`: OS, JDK 버전 등 여러 조건의 조합을 자동으로 생성해 검증한다.
- 병렬 작업이 같은 파일이나 배포 환경을 동시에 수정하지 않도록 주의한다.

```groovy
stage('Test') {
    parallel {
        stage('Unit Test') {
            steps { sh './gradlew test' }
        }
        stage('Static Analysis') {
            steps { sh './gradlew check' }
        }
    }
}
```

### 오류 처리

일부 검증이 실패해도 결과를 기록하고 다음 Stage를 진행해야 할 때 `catchError`나 `unstable`을 사용한다.

```groovy
catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
    sh './run-quality-check.sh'
}
```

- `FAILURE`: 파이프라인 실행 자체가 실패한 상태
- `UNSTABLE`: 테스트 실패 등 문제가 있지만 후속 처리나 결과 수집은 가능한 상태
- `post { always { ... } }`: 성공 여부와 관계없이 테스트 결과와 로그를 수집할 때 유용

## 2. Webhook과 SCM 이벤트

Webhook을 사용하면 GitHub/GitLab의 Push나 PR 이벤트가 발생했을 때 Jenkins가 빌드를 시작할 수 있다.

```text
개발자 Push 또는 PR 생성
  → GitHub/GitLab Webhook
  → Jenkins가 이벤트 수신
  → 대상 브랜치의 Jenkinsfile 실행
  → 결과를 PR Status Check로 반환
```

주기적으로 저장소를 확인하는 Polling보다 이벤트 기반 Webhook이 불필요한 조회와 실행 지연을 줄이는 데 유리하다. Webhook Secret과 Jenkins Credential은 코드에 직접 작성하지 않고 Jenkins의 자격 증명 저장소에서 관리한다.

## 3. Multibranch Pipeline

Multibranch Pipeline은 저장소를 스캔하고 `Jenkinsfile`이 있는 브랜치를 자동으로 찾아 각각의 Pipeline Job을 만든다. Organization Folder를 사용하면 조직 내 여러 저장소까지 검색 범위를 확장할 수 있다.

주요 장점은 다음과 같다.

- 브랜치별 Job을 수동으로 생성하지 않아도 된다.
- 브랜치마다 다른 `Jenkinsfile`을 사용할 수 있다.
- PR이 생성되면 병합 전에 빌드와 테스트를 수행할 수 있다.
- Jenkins 결과를 GitHub/GitLab의 Status Check에 반영해 Merge 조건으로 사용할 수 있다.

### 중복 PR 빌드 처리

같은 PR에 새 커밋이 올라오면 이전 빌드 결과는 더 이상 의미가 없을 수 있다. 다음 설정은 실행 중인 이전 빌드를 중단하고 최신 빌드를 시작한다.

```groovy
options {
    disableConcurrentBuilds(abortPrevious: true)
}
```

`milestone()`은 최신 빌드가 특정 지점을 통과하면 그 지점에 도달하지 못한 이전 빌드를 중단한다. 배포 승인처럼 빌드 순서가 중요한 구간에서 사용할 수 있다.

## 4. Shared Libraries

여러 프로젝트의 `Jenkinsfile`에서 반복되는 빌드, 테스트, 배포 로직은 Shared Library로 분리한다. 이를 통해 중복을 줄이고 조직의 표준 절차를 한곳에서 관리할 수 있다.

### 기본 구조

```text
shared-library/
├── vars/
│   ├── buildApp.groovy
│   └── buildApp.txt
├── src/
│   └── com/example/pipeline/BuildUtils.groovy
├── resources/
│   └── templates/deployment.yaml
└── test/
```

| 경로 | 용도 |
|---|---|
| `vars/` | Jenkinsfile에서 바로 호출할 글로벌 함수와 변수 |
| `src/` | 패키지 구조를 가진 Groovy 클래스 |
| `resources/` | 설정, 템플릿 등 비-Groovy 파일 |
| `test/` | Shared Library 단위 테스트 |

### 간단한 글로벌 함수

```groovy
// vars/buildApp.groovy
def call(String task = 'build') {
    sh "./gradlew ${task}"
}
```

```groovy
// Jenkinsfile
@Library('company-pipeline-library@v1') _

pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                buildApp('build')
            }
        }
    }
}
```

운영 환경에서는 라이브러리 버전을 태그나 커밋으로 고정하면 라이브러리 변경으로 모든 파이프라인이 동시에 깨지는 위험을 줄일 수 있다. Trusted Library는 Jenkins 내부 API와 시스템에 강한 권한으로 접근할 수 있으므로 저장소 쓰기 권한을 엄격하게 관리해야 한다.

### Shared Library 테스트

JenkinsPipelineUnit은 Jenkins를 직접 실행하지 않고도 Pipeline 로직을 Mock 기반으로 테스트하는 프레임워크다.

- 조건문과 함수 호출 검증
- Jenkins Step Mock 처리
- 호출 순서와 전달 인자 확인
- 라이브러리 변경으로 발생하는 회귀 오류 방지

단위 테스트가 실제 Jenkins 플러그인, Agent, 네트워크 연동까지 완전히 검증하는 것은 아니므로 별도의 통합 테스트도 필요하다.

## 5. 운영과 성능 최적화

### Controller 부하와 Groovy CPS

Jenkins Pipeline의 Groovy 코드는 CPS 변환을 거쳐 실행 상태를 저장하고 재시작 후 복구할 수 있게 한다. 그러나 큰 JSON 파싱, 복잡한 반복문, 대용량 객체 처리 등을 Pipeline Groovy에서 수행하면 Controller의 CPU와 메모리를 많이 사용할 수 있다.

권장 방법은 다음과 같다.

- 무거운 계산은 Agent의 `sh`, `bat` 또는 별도 스크립트에서 실행한다.
- 대용량 파일 내용을 Pipeline 변수에 오래 저장하지 않는다.
- 불필요하게 많은 Pipeline Step과 로그 출력을 줄인다.
- `@NonCPS`는 Pipeline Step을 내부에서 호출할 수 없다는 제약을 이해하고 제한적으로 사용한다.

```groovy
steps {
    sh './scripts/analyze-large-report.sh'
}
```

### Artifact와 `stash` 구분

| 방식 | 사용 목적 |
|---|---|
| `stash` / `unstash` | 같은 Pipeline 실행 안에서 Agent나 Stage 사이에 작은 파일 전달 |
| `archiveArtifacts` | 빌드 완료 후 결과 파일 보관과 다운로드 |
| Nexus, Artifactory, Object Storage | 큰 파일, 장기 보관, 여러 Pipeline 간 공유 |

`stash`는 파일을 압축하면서 Controller 자원을 사용할 수 있으므로 대용량 파일 전달에는 적합하지 않다. 공식 문서는 대략 5~100MB 수준부터 외부 저장소나 Artifact Manager 같은 대안을 검토하도록 안내한다.

### 알림과 실패 로그 요약

알림은 단순히 “실패했다”는 메시지만 보내기보다 바로 대응할 수 있는 정보를 포함해야 한다.

- Job, 브랜치, 커밋, 실행 번호
- 실패한 Stage와 핵심 오류 메시지
- Jenkins 빌드 로그 링크
- 커밋 작성자 또는 담당 팀

```groovy
post {
    failure {
        slackSend(
            color: 'danger',
            message: "${env.JOB_NAME} #${env.BUILD_NUMBER} 실패: ${env.BUILD_URL}"
        )
    }
}
```

Slack·Teams 토큰은 Jenkins Credentials로 보관하고 로그에 출력되지 않도록 한다.

## 6. 전체 예시

```groovy
@Library('company-pipeline-library@v1') _

pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds(abortPrevious: true)
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }

    parameters {
        booleanParam(name: 'DEPLOY', defaultValue: false)
    }

    stages {
        stage('Build') {
            steps {
                buildApp('build')
            }
        }

        stage('Test') {
            parallel {
                stage('Unit') {
                    steps { sh './gradlew test' }
                }
                stage('Quality') {
                    steps {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh './gradlew check'
                        }
                    }
                }
            }
        }

        stage('Deploy') {
            when {
                allOf {
                    branch 'main'
                    expression { params.DEPLOY }
                }
            }
            steps {
                sh './scripts/deploy.sh'
            }
        }
    }

    post {
        always {
            junit testResults: '**/build/test-results/**/*.xml', allowEmptyResults: true
            archiveArtifacts artifacts: '**/build/libs/*.jar', fingerprint: true
        }
        failure {
            echo "실패한 빌드: ${env.BUILD_URL}"
        }
    }
}
```

## 7. 핵심 정리

1. Declarative Pipeline은 CI/CD 단계를 일관된 구조로 표현한다.
2. Multibranch Pipeline은 브랜치와 PR을 자동 탐색하고 검증한다.
3. 최신 커밋만 검증하면 되는 PR은 이전 중복 빌드를 취소해 자원을 절약한다.
4. 반복 로직은 Shared Library로 옮겨 DRY 원칙을 지킨다.
5. Shared Library도 단위 테스트와 버전 관리가 필요하다.
6. 무거운 연산은 Controller가 아니라 Agent에서 수행한다.
7. `stash`는 작은 임시 전달용이고, 장기·대용량 파일은 Artifact 저장소를 사용한다.
8. 알림에는 실패 지점, 오류 요약, 로그 링크를 포함한다.

## 8. 확인 질문

1. `post`와 `when`은 각각 어떤 상황에 사용하는가?
2. Shared Library의 `vars/`, `src/`, `resources/`는 각각 무엇을 저장하는가?
3. Pipeline Groovy에서 대용량 데이터를 처리하면 왜 Controller에 부담이 되는가?

## 참고 자료

- [Jenkins Pipeline Syntax](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Jenkins Multibranch Pipeline](https://www.jenkins.io/doc/book/pipeline/multibranch/)
- [Jenkins Shared Libraries](https://www.jenkins.io/doc/book/pipeline/shared-libraries/)
- [Jenkins Scaling Pipelines](https://www.jenkins.io/doc/book/pipeline/scaling-pipeline/)
- [Jenkins Pipeline Basic Steps](https://www.jenkins.io/doc/pipeline/steps/workflow-basic-steps/)
- [JenkinsPipelineUnit](https://github.com/jenkinsci/JenkinsPipelineUnit)
- [Jenkins GitHub Checks Plugin](https://plugins.jenkins.io/github-checks/)
- [Jenkins Slack Notification Plugin](https://plugins.jenkins.io/slack/)
